"""Memory benchmark: copy, read, write and random-access speed using NumPy.

Buffers are sized from the memory that is currently free, so the test never pushes the
Mac into swap (which would measure the SSD instead).
"""

from __future__ import annotations

import os
import threading
import time

from asbench.benchmarks._timing import rate as _rate
from asbench.core.context import RunContext
from asbench.core.model import OK, BenchmarkResult, Metric

MiB = 1024 * 1024


def availability() -> tuple[str, str]:
    return OK, ""


def _buffer_bytes(ctx: RunContext) -> int:
    wanted = ctx.pick(512, 128) * MiB
    try:
        import psutil

        available = psutil.virtual_memory().available
        wanted = min(wanted, available // 10)  # two buffers → at most 20% of free memory
    except Exception:
        pass
    return max(16 * MiB, wanted // MiB * MiB)


def run(ctx: RunContext) -> BenchmarkResult:
    import numpy as np

    size = _buffer_bytes(ctx)
    seconds = ctx.pick(1.5, 0.5)
    threads = min(os.cpu_count() or 1, 8)
    result = BenchmarkResult(key="memory", title="Memory", backend=f"NumPy {np.__version__} · {size // MiB} MB buffers")

    ctx.status(f"Allocating 2 × {size // MiB} MB")
    src = np.ones(size // 8, dtype=np.float64)   # np.ones touches every page, so no page faults are timed
    dst = np.zeros_like(src)
    ctx.progress(0.05)

    ctx.status("Copy · 1 thread")
    rate = _rate(ctx, seconds, lambda: np.copyto(dst, src))
    result.metrics.append(Metric("memory.copy", "Copy (1 thread)", 2 * size * rate / 1e9, "GB/s"))
    ctx.progress(0.25)

    ctx.status(f"Copy · {threads} threads")
    result.metrics.append(
        Metric("memory.copy_mt", f"Copy ({threads} threads)", _threaded_copy(ctx, src, dst, threads, seconds) / 1e9, "GB/s")
    )
    ctx.progress(0.45)

    ctx.status("Read · 1 thread")
    as_int = src.view(np.int64)  # integer sum is a straight streaming read
    rate = _rate(ctx, seconds, lambda: np.bitwise_xor.reduce(as_int))
    result.metrics.append(Metric("memory.read", "Read (1 thread)", size * rate / 1e9, "GB/s"))
    ctx.progress(0.6)

    ctx.status("Write · 1 thread")
    rate = _rate(ctx, seconds, lambda: dst.fill(1.5))
    result.metrics.append(Metric("memory.write", "Write (1 thread)", size * rate / 1e9, "GB/s"))
    ctx.progress(0.75)

    ctx.status("Random access · scattered reads")
    lookups = ctx.pick(4, 1) * MiB
    index = np.random.default_rng(1).integers(0, src.size, size=lookups)
    rate = _rate(ctx, seconds, lambda: src.take(index))
    result.metrics.append(Metric("memory.random", "Random access", lookups * rate / 1e6, "M/s"))
    ctx.progress(1.0)

    result.notes.append(
        "Copy counts bytes read plus bytes written. Random access reads 8-byte values from "
        "unpredictable locations, so it is limited by memory latency rather than bandwidth."
    )
    return result


def _threaded_copy(ctx: RunContext, src, dst, threads: int, seconds: float) -> float:
    """Copy with several threads at once (NumPy releases the GIL); returns bytes per second."""
    import numpy as np

    bounds = [(src.size * i // threads, src.size * (i + 1) // threads) for i in range(threads)]
    moved = [0] * threads
    start = threading.Barrier(threads + 1)
    stop = threading.Event()

    def worker(i):
        lo, hi = bounds[i]
        s, d = src[lo:hi], dst[lo:hi]
        np.copyto(d, s)
        start.wait()
        while not stop.is_set():
            np.copyto(d, s)
            moved[i] += 2 * s.nbytes

    pool = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(threads)]
    for t in pool:
        t.start()
    start.wait()
    t0 = time.perf_counter()
    try:
        ctx.sleep(seconds)
    finally:
        stop.set()
        for t in pool:
            t.join()
    return sum(moved) / (time.perf_counter() - t0)
