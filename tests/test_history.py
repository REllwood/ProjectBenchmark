import csv
import json

from asbench.core.history import History, change, export_csv, export_json
from asbench.core.model import OK, BenchmarkResult, Metric, RunRecord, record_from_dict, record_to_dict


def make(rid, day, score, key="cpu", status=OK):
    result = BenchmarkResult(key=key, title=key.upper(), status=status, score=score,
                             metrics=[Metric(f"{key}.m", "Metric", score / 10, "u", score=score)])
    return RunRecord(id=rid, timestamp=f"2026-09-{day:02d}T10:00:00+10:00", kind="single", mode="quick",
                     app_version="2.0.0", system={"chip": "Test chip"}, results=[result])


def test_add_and_load_sorted_and_skip_corrupt_lines():
    h = History()
    h.add(make("b", 5, 1100))
    h.add(make("a", 2, 1000))
    with h.path.open("a") as f:
        f.write("{not json\n\n")
    assert [r.id for r in h.load()] == ["a", "b"]


def test_previous_and_best():
    h = History()
    for rid, day, score in (("a", 1, 900), ("b", 2, 1200), ("c", 3, 1000)):
        h.add(make(rid, day, score))
    records = h.load()
    assert h.previous("cpu", before=records[2])[0].id == "b"
    assert h.previous("cpu", before=records[0]) is None
    assert h.best("cpu")[0].id == "b"


def test_failed_results_are_ignored_for_comparisons():
    h = History()
    h.add(make("a", 1, 900))
    h.add(make("b", 2, 1, status="error"))
    assert [r.id for r, _ in h.results_for("cpu")] == ["a"]


def test_delete():
    h = History()
    for rid, day in (("a", 1), ("b", 2), ("c", 3)):
        h.add(make(rid, day, 1000))
    h.delete({"b"})
    assert [r.id for r in h.load()] == ["a", "c"]


def test_change():
    assert change(110, 100) == 10
    assert change(None, 100) is None and change(100, 0) is None


def test_exports(tmp_path):
    records = [make("a", 1, 1000), make("b", 2, 1100)]
    export_json(records, tmp_path / "out.json")
    assert [r["id"] for r in json.loads((tmp_path / "out.json").read_text())] == ["a", "b"]
    export_csv(records, tmp_path / "out.csv")
    rows = list(csv.DictReader((tmp_path / "out.csv").open()))
    assert len(rows) == 2 and rows[1]["metric_id"] == "cpu.m" and rows[1]["benchmark_score"] == "1100"


def test_records_from_newer_versions_still_load():
    data = record_to_dict(make("a", 1, 1000))
    data["future_field"] = 1
    data["results"][0]["another_new_field"] = "x"
    data["results"][0]["metrics"][0]["extra"] = True
    assert record_from_dict(data).results[0].metrics[0].score == 1000
