import math

import pytest

from asbench.core import scoring
from asbench.core.model import FALLBACK, OK, UNAVAILABLE, BenchmarkResult, Metric, PowerSummary


def result(*metrics, status=OK, key="x"):
    return BenchmarkResult(key=key, title=key, status=status, metrics=list(metrics))


REFS = {"a": 100.0, "b": 50.0, "lat": 10.0}


def test_matching_the_reference_scores_1000_and_double_scores_2000():
    r = scoring.score_result(result(Metric("a", "A", 100, "u"), Metric("b", "B", 100, "u")), REFS)
    assert r.metrics[0].score == 1000 and r.metrics[1].score == 2000
    assert r.score == pytest.approx(math.sqrt(1000 * 2000))


def test_lower_is_better_metrics_are_inverted():
    r = scoring.score_result(result(Metric("lat", "Latency", 5, "ms", higher_is_better=False)), REFS)
    assert r.score == pytest.approx(2000)


def test_informational_and_unknown_metrics_are_not_scored():
    r = scoring.score_result(result(Metric("a", "A", 100, "u"), Metric("a", "Info", 5, "×", scored=False), Metric("zzz", "?", 1, "u")), REFS)
    assert [m.score for m in r.metrics] == [1000, None, None]
    assert r.score == pytest.approx(1000)


def test_group_scores():
    r = scoring.score_result(result(Metric("a", "A", 100, "u", group="One"), Metric("b", "B", 100, "u", group="Two")), REFS)
    assert r.group_scores == pytest.approx({"One": 1000, "Two": 2000})


def test_fallback_results_keep_measurements_but_get_no_points():
    r = scoring.score_result(result(Metric("a", "A", 100, "u"), status=FALLBACK), REFS)
    assert r.metrics[0].value == 100 and r.metrics[0].score is None and r.score is None


def test_composite_only_counts_results_that_ran_on_the_intended_hardware():
    ok1 = scoring.score_result(result(Metric("a", "A", 100, "u")), REFS)
    ok2 = scoring.score_result(result(Metric("a", "A", 400, "u")), REFS)
    fb = scoring.score_result(result(Metric("a", "A", 1, "u"), status=FALLBACK), REFS)
    na = result(status=UNAVAILABLE)
    assert scoring.composite([ok1, ok2, fb, na]) == pytest.approx(2000)


def test_efficiency_is_points_per_watt():
    r = result(Metric("a", "A", 100, "u"))
    r.power = PowerSummary(available=True, avg_w=4.0)
    assert scoring.score_result(r, REFS).efficiency == pytest.approx(250)


def test_calibration_round_trip():
    refs, source = scoring.load_references()
    assert source == "built-in"
    r = scoring.score_result(result(Metric("cpu.single.integer", "Integer", 123.0, "ops/s")), refs)
    scoring.save_references([r])
    refs, source = scoring.load_references()
    assert source == "custom" and refs["cpu.single.integer"] == 123.0
    assert scoring.score_result(r, refs).score == pytest.approx(1000)
    scoring.reset_references()
    assert scoring.load_references()[1] == "built-in"


def test_every_scored_metric_id_has_a_reference():
    ids = {
        *(f"cpu.{g}.{w}" for g in ("single", "multi") for w in ("integer", "float", "json", "compression", "hashing")),
        "gpu.matmul_fp32", "gpu.matmul_fp16", "gpu.conv", "gpu.bandwidth",
        "memory.copy", "memory.copy_mt", "memory.read", "memory.write", "memory.random",
        "storage.seq_write", "storage.seq_read", "storage.rand_read", "storage.rand_write",
        "neural.conv", "neural.linear",
    }
    assert ids == set(scoring.BUILTIN_REFERENCES)
