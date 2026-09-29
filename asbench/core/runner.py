"""Runs benchmarks: availability checks, power sampling, error capture and scoring."""

from __future__ import annotations

import logging
import secrets
import time
from datetime import datetime

from asbench import __version__, benchmarks
from asbench.core import scoring
from asbench.core.context import Cancelled, RunContext
from asbench.core.model import ERROR, UNAVAILABLE, BenchmarkResult, PowerSummary, RunRecord
from asbench.core.power import PowerSampler, power_status
from asbench.core.sysinfo import collect

log = logging.getLogger(__name__)


def run_benchmark(key: str, ctx: RunContext, *, refs=None, power: bool = True, on_power_sample=None) -> BenchmarkResult:
    """Run one benchmark. Errors become an ERROR result; only Cancelled propagates."""
    spec = benchmarks.get(key)
    status, message = spec.availability()
    if status == UNAVAILABLE:
        return BenchmarkResult(key=key, title=spec.title, status=UNAVAILABLE, notes=[message])

    sampler, summary = None, None
    if power:
        state = power_status()
        if state.available:
            sampler = PowerSampler(on_sample=on_power_sample)
            try:
                sampler.start()
                ctx.power_sampler = sampler
            except OSError as exc:
                sampler, summary = None, PowerSummary(False, f"Couldn't start powermetrics: {exc}")
        else:
            summary = PowerSummary(False, state.reason)

    t0 = time.perf_counter()
    try:
        result = spec.load().run(ctx)
    except Cancelled:
        raise
    except Exception as exc:
        log.exception("%s benchmark failed", spec.title)
        result = BenchmarkResult(key=key, title=spec.title, status=ERROR, error=f"{type(exc).__name__}: {exc}")
    finally:
        if sampler:
            summary = sampler.stop()
            ctx.power_sampler = None
    result.duration_s = time.perf_counter() - t0
    result.power = summary
    return scoring.score_result(result, refs if refs is not None else scoring.load_references()[0])


def run_many(keys: list[str], ctx: RunContext, *, power: bool = True, on_power_sample=None) -> RunRecord:
    """Run several benchmarks in order and return a RunRecord.

    If Cancel is pressed part-way, the record holds the benchmarks that finished and
    has complete=False. The overall score is only given for a complete full suite.
    """
    refs, source = scoring.load_references()
    results: list[BenchmarkResult] = []
    complete = True
    n = len(keys)
    try:
        for i, key in enumerate(keys):
            ctx.event("benchmark_started", key)
            result = run_benchmark(key, ctx.sub(i / n, (i + 1) / n), refs=refs, power=power, on_power_sample=on_power_sample)
            results.append(result)
            ctx.event("benchmark_finished", result)
    except Cancelled:
        complete = False

    if keys == ["sustained"]:
        kind = "sustained"
    elif sorted(keys) == sorted(benchmarks.SUITE):
        kind = "suite"
    else:
        kind = "single"
    now = datetime.now().astimezone()
    return RunRecord(
        id=f"{now:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}",
        timestamp=now.isoformat(timespec="seconds"),
        kind=kind,
        mode="quick" if ctx.quick else "standard",
        app_version=__version__,
        system=collect().as_dict(),
        results=results,
        composite=scoring.composite(results) if kind == "suite" and complete else None,
        complete=complete,
        reference=source,
    )
