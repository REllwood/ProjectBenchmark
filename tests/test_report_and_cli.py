import json
import os
import subprocess
import sys
from pathlib import Path

from asbench.core import fmt, report
from asbench.core.model import OK, BenchmarkResult, Metric, RunRecord

ROOT = Path(__file__).resolve().parents[1]


def test_report_is_self_contained_and_escapes_text():
    result = BenchmarkResult(key="cpu", title="CPU", status=OK, score=1234, notes=["<script>alert(1)</script>"],
                             metrics=[Metric("cpu.single.integer", "Integer", 950, "ops/s", score=1000)])
    record = RunRecord(id="r1", timestamp="2026-09-29T15:04:00+10:00", kind="suite", mode="standard", app_version="2.0.0",
                       system={"chip": "Apple M2 Pro", "machine": "MacBook Pro"}, results=[result], composite=1234)
    html = report.render(record)
    assert "<script>alert" not in html and "&lt;script&gt;" in html
    assert "1,234" in html and "Apple M2 Pro" in html
    assert "http://" not in html and "https://" not in html  # nothing loaded from the internet


def test_formatting():
    assert fmt.score(1234.4) == "1,234" and fmt.score(None) == "—"
    assert fmt.value(3.14159, "TOPS") == "3.14 TOPS" and fmt.value(2.5, "×") == "2.50×"
    assert fmt.delta(2.345) == "+2.3%" and fmt.delta(-1.0) == "−1.0%"
    assert fmt.duration(42) == "42 s" and fmt.duration(125) == "2 min 05 s"
    assert fmt.when("2026-09-29T15:04:00+10:00") == "29 Sep 2026, 3:04 pm"


def run_cli(*args, data_dir):
    env = dict(os.environ, ASB_DATA_DIR=str(data_dir))
    return subprocess.run([sys.executable, "main.py", *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)


def test_cli_runs_saves_and_exports(tmp_path, data_dir):
    out = run_cli("--cli", "--quick", "--only", "memory", "--no-power", "--json", str(tmp_path / "r.json"),
                  "--csv", str(tmp_path / "r.csv"), "--report", str(tmp_path / "r.html"), data_dir=data_dir)
    assert out.returncode == 0, out.stderr
    record = json.loads((tmp_path / "r.json").read_text())
    assert record["results"][0]["key"] == "memory" and record["results"][0]["score"] > 0
    assert (tmp_path / "r.csv").read_text().startswith("run_id,")
    assert (tmp_path / "r.html").read_text().startswith("<!doctype html>")
    history = run_cli("--history", data_dir=data_dir)
    assert history.returncode == 0 and "single" in history.stdout


def test_cli_rejects_unknown_benchmarks(data_dir):
    out = run_cli("--cli", "--only", "warp-drive", data_dir=data_dir)
    assert out.returncode == 2 and "Unknown benchmark" in out.stderr
