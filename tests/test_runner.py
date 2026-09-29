import pytest

from asbench import benchmarks
from asbench.core import scoring
from asbench.core.context import RunContext
from asbench.core.model import ERROR, OK, UNAVAILABLE, BenchmarkResult, Metric
from asbench.core.runner import run_benchmark, run_many


def reference_result(key):
    """A result whose every metric equals its reference value (so it scores exactly 1,000)."""
    ids = [k for k in scoring.BUILTIN_REFERENCES if k.startswith(f"{key}.")]
    return BenchmarkResult(key=key, title=key, metrics=[Metric(i, i, scoring.BUILTIN_REFERENCES[i], "u") for i in ids])


@pytest.fixture
def fake_suite(monkeypatch):
    for spec in benchmarks.SPECS:
        module = spec.load()
        monkeypatch.setattr(module, "availability", lambda: (OK, ""))
        monkeypatch.setattr(module, "run", lambda ctx, k=spec.key: reference_result(k))


def test_a_crashing_benchmark_becomes_an_error_result(monkeypatch):
    module = benchmarks.get("memory").load()
    monkeypatch.setattr(module, "run", lambda ctx: 1 / 0)
    r = run_benchmark("memory", RunContext(), power=False)
    assert r.status == ERROR and "ZeroDivisionError" in r.error and r.score is None


def test_unavailable_benchmarks_are_skipped(monkeypatch):
    module = benchmarks.get("neural").load()
    monkeypatch.setattr(module, "availability", lambda: (UNAVAILABLE, "no chip"))
    r = run_benchmark("neural", RunContext(), power=False)
    assert r.status == UNAVAILABLE and r.notes == ["no chip"]


def test_full_suite_gets_an_overall_score(fake_suite):
    record = run_many(list(benchmarks.SUITE), RunContext(), power=False)
    assert record.kind == "suite" and record.complete
    assert [r.score for r in record.results] == pytest.approx([1000] * 5)
    assert record.composite == pytest.approx(1000)


def test_single_benchmark_has_no_overall_score(fake_suite):
    record = run_many(["cpu"], RunContext(), power=False)
    assert record.kind == "single" and record.composite is None


def test_cancelling_keeps_finished_results_only(fake_suite):
    ctx = RunContext()
    ctx._on_event = lambda name, payload: ctx.cancel() if name == "benchmark_finished" else None
    module = benchmarks.get("gpu").load()

    def checks_cancel(c):
        c.check()
        return reference_result("gpu")

    module.run = checks_cancel
    record = run_many(["cpu", "gpu", "memory"], ctx, power=False)
    assert not record.complete and [r.key for r in record.results] == ["cpu"] and record.composite is None


def test_progress_is_spread_across_benchmarks(fake_suite, monkeypatch):
    seen = []

    def run(ctx):
        ctx.progress(1.0)
        return reference_result("cpu")

    for key in ("cpu", "memory"):
        monkeypatch.setattr(benchmarks.get(key).load(), "run", run)
    run_many(["cpu", "memory"], RunContext(on_progress=seen.append), power=False)
    assert seen == [0.5, 1.0]
