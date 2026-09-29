"""Sustained performance: keep the CPU and/or GPU fully loaded and chart performance over time.

Macs slow themselves down when they get hot (thermal throttling). A short benchmark
finishes before that happens; this one runs for minutes so you can see it.
"""

from __future__ import annotations

import os
import threading
import time

from asbench.benchmarks import gpu as gpu_bench
from asbench.core.context import RunContext
from asbench.core.model import OK, UNAVAILABLE, BenchmarkResult, Metric
from asbench.workers import WorkerPool

MODES = {"cpu": "CPU", "gpu": "GPU", "both": "CPU + GPU"}
THROTTLE_THRESHOLD = 0.9  # a 3-window average below 90% of peak counts as throttling


def availability() -> tuple[str, str]:
    return OK, ""


def analyse(values: list[float], times: list[float]) -> dict:
    """Peak, sustained (mean of the last 30%), % retained and when throttling began (or None)."""
    if not values:
        return {"peak": 0.0, "sustained": 0.0, "retained": 0.0, "throttle_at": None}
    peak = max(values)
    tail = values[-max(1, round(len(values) * 0.3)):]
    sustained = sum(tail) / len(tail)
    throttle_at = None
    for i in range(2, len(values)):
        if sum(values[i - 2 : i + 1]) / 3 < THROTTLE_THRESHOLD * peak:
            throttle_at = times[i - 2]
            break
    return {"peak": peak, "sustained": sustained, "retained": 100 * sustained / peak if peak else 0.0, "throttle_at": throttle_at}


class _GpuLoad(threading.Thread):
    """Runs back-to-back matrix multiplies on the Metal GPU and counts them."""

    def __init__(self, n: int = 4096):
        super().__init__(daemon=True)
        import mlx.core as mx

        self.mx = mx
        self.n = n
        self.count = 0
        self.error: Exception | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    def run(self):
        mx = self.mx
        try:
            with mx.stream(mx.gpu):
                a = mx.random.normal((self.n, self.n))
                b = mx.random.normal((self.n, self.n))
                mx.eval(a, b)
                while not self._stop.is_set():
                    mx.eval(a @ b)
                    with self._lock:
                        self.count += 1
        except Exception as exc:  # reported by the main loop
            self.error = exc

    def take(self) -> int:
        with self._lock:
            count, self.count = self.count, 0
        return count

    def stop(self):
        self._stop.set()
        self.join(timeout=10)


def run(ctx: RunContext) -> BenchmarkResult:
    mode = ctx.options.get("sustained_mode", "cpu")
    minutes = float(ctx.options.get("sustained_minutes", 3))
    total = ctx.pick(minutes * 60, 20.0)
    window = ctx.pick(2.0, 1.0)
    cores = os.cpu_count() or 1
    result = BenchmarkResult(key="sustained", title=f"Sustained · {MODES.get(mode, mode)}")

    gpu_status, gpu_note = gpu_bench.availability()
    use_gpu = mode in ("gpu", "both") and gpu_status == OK
    use_cpu = mode in ("cpu", "both")
    if mode in ("gpu", "both") and not use_gpu:
        if mode == "gpu":
            result.status = UNAVAILABLE
            result.notes.append(f"The GPU load needs a Metal GPU. {gpu_note}")
            return result
        result.notes.append("No Metal GPU was found, so only the CPU was loaded.")

    parts = []
    if use_cpu:
        parts.append(f"{cores} CPU worker processes")
    if use_gpu:
        parts.append("MLX matrix multiply on the Metal GPU")
    result.backend = " + ".join(parts)
    series: dict[str, list] = {"t": [], "cpu": [], "gpu": [], "power": [], "thermal": []}
    result.series = series

    pool = gpu_load = None
    try:
        if use_cpu:
            ctx.status(f"Starting {cores} worker processes")
            pool = WorkerPool(cores, warm=["mix"], is_cancelled=lambda: ctx.cancelled)
        if use_gpu:
            gpu_load = _GpuLoad()
            gpu_load.start()

        start = time.monotonic()
        gpu_flops = 2 * 4096**3
        while True:
            elapsed = time.monotonic() - start
            if elapsed >= total:
                break
            ctx.status(f"Running under load · {int(elapsed // 60)}:{int(elapsed % 60):02d} of {int(total // 60)}:{int(total % 60):02d}")
            w0 = time.monotonic()
            if gpu_load:
                gpu_load.take()
            if pool:
                cpu_rate, _ = pool.run("mix", window)
            else:
                ctx.sleep(window)
            w1 = time.monotonic()
            ctx.check()
            if gpu_load and gpu_load.error:
                raise gpu_load.error

            point = {"t": round(w1 - start, 2)}
            point["cpu"] = cpu_rate if pool else None
            point["gpu"] = gpu_load.take() * gpu_flops / (w1 - w0) / 1e9 if gpu_load else None
            watts, thermal = _power_in(ctx, w0, w1)
            point["power"], point["thermal"] = watts, thermal
            for key in series:
                series[key].append(point[key])
            ctx.event("sustained_point", point)
            ctx.progress((w1 - start) / total)
    finally:
        if pool:
            pool.close()
        if gpu_load:
            gpu_load.stop()

    for key, label, unit in (("cpu", "CPU", "ops/s"), ("gpu", "GPU", "GFLOPS")):
        values = [v for v in series[key] if v is not None]
        if not values:
            continue
        times = [t for t, v in zip(series["t"], series[key]) if v is not None]
        stats = analyse(values, times)
        result.metrics += [
            Metric(f"sustained.{key}_peak", f"{label} peak", stats["peak"], unit, group=label, scored=False),
            Metric(f"sustained.{key}_sustained", f"{label} sustained", stats["sustained"], unit, group=label, scored=False),
            Metric(f"sustained.{key}_retained", f"{label} performance retained", stats["retained"], "%", group=label, scored=False),
        ]
        if stats["throttle_at"] is not None:
            result.metrics.append(
                Metric(f"sustained.{key}_throttle", f"{label} slowed down after", stats["throttle_at"], "s", group=label, scored=False)
            )
            result.notes.append(f"{label} performance dropped below 90% of its peak after {stats['throttle_at']:.0f} s.")
        else:
            result.notes.append(f"{label} held at least 90% of its peak for the whole run.")
    return result


def _power_in(ctx: RunContext, start: float, end: float) -> tuple[float | None, str]:
    sampler = ctx.power_sampler
    if sampler is None:
        return None, ""
    samples = sampler.window(start, end + 0.6)  # samples arrive up to one interval late
    watts = [s.total_w for s in samples if s.total_w is not None]
    thermal = next((s.thermal for s in reversed(samples) if s.thermal), "")
    return (sum(watts) / len(watts) if watts else None), thermal
