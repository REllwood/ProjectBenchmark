"""CPU benchmark: five workloads, timed on one core and then on every core."""

from __future__ import annotations

import os

from asbench.core.context import RunContext
from asbench.core.model import OK, BenchmarkResult, Metric
from asbench.workers import WORKLOADS, WorkerPool


def availability() -> tuple[str, str]:
    return OK, ""


def run(ctx: RunContext) -> BenchmarkResult:
    cores = os.cpu_count() or 1
    seconds_single = ctx.pick(1.5, 0.4)
    seconds_multi = ctx.pick(2.0, 0.6)
    names = list(WORKLOADS)
    result = BenchmarkResult(key="cpu", title="CPU", backend=f"{cores} worker processes")
    single: dict[str, float] = {}

    ctx.status("Starting single-core worker")
    with WorkerPool(1, is_cancelled=lambda: ctx.cancelled) as pool:
        for i, name in enumerate(names):
            label = WORKLOADS[name][0]
            ctx.status(f"Single-core · {label}")
            single[name], _ = pool.run(name, seconds_single)
            ctx.check()
            ctx.progress(0.05 + 0.4 * (i + 1) / len(names))
            result.metrics.append(Metric(f"cpu.single.{name}", label, single[name], "ops/s", group="Single-core"))

    ctx.status(f"Starting {cores} worker processes")
    with WorkerPool(cores, is_cancelled=lambda: ctx.cancelled) as pool:
        ctx.progress(0.5)
        scaling = []
        for i, name in enumerate(names):
            label = WORKLOADS[name][0]
            ctx.status(f"Multi-core ({cores} cores) · {label}")
            total, _ = pool.run(name, seconds_multi)
            ctx.check()
            ctx.progress(0.5 + 0.5 * (i + 1) / len(names))
            result.metrics.append(Metric(f"cpu.multi.{name}", label, total, "ops/s", group="Multi-core"))
            if single[name] > 0:
                scaling.append(total / single[name])

    if scaling:
        result.metrics.append(
            Metric("cpu.scaling", "Multi-core scaling", sum(scaling) / len(scaling), "×", group="Multi-core", scored=False)
        )
    result.notes.append(
        f"Multi-core uses all {cores} cores. On Apple Silicon, efficiency cores are slower than "
        "performance cores, so scaling is usually lower than the core count."
    )
    return result
