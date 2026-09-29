"""Shared timing loop for benchmarks that repeat one operation for a fixed time."""

from __future__ import annotations

import time

from asbench.core.context import RunContext


def rate(ctx: RunContext, seconds: float, step, warmup: float = 0.3) -> float:
    """Call step() repeatedly for about `seconds` and return calls per second.

    The first call and a short warm-up aren't timed: they compile kernels, allocate
    buffers and let clocks ramp up. A step that takes longer than `seconds` still runs
    once, so slow machines get a result instead of a zero.
    """
    step()
    warm_until = time.perf_counter() + min(warmup, seconds / 3)
    while time.perf_counter() < warm_until:
        step()
    ctx.check()
    count, t0 = 0, time.perf_counter()
    while True:
        step()
        count += 1
        elapsed = time.perf_counter() - t0
        if elapsed >= seconds:
            return count / elapsed
        ctx.check()
