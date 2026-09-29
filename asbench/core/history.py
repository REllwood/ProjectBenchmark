"""Saved runs: a JSON Lines file with one run per line, plus comparison and export helpers."""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from asbench.core.model import OK, BenchmarkResult, RunRecord, record_from_dict, record_to_dict
from asbench.core.paths import history_file

log = logging.getLogger(__name__)


class History:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else history_file()

    def load(self) -> list[RunRecord]:
        """All saved runs, oldest first. Unreadable lines are skipped, not fatal."""
        if not self.path.exists():
            return []
        records = []
        with self.path.open(encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    records.append(record_from_dict(json.loads(line)))
                except (ValueError, TypeError, KeyError) as exc:
                    log.warning("Skipping unreadable line %d in %s: %s", n, self.path, exc)
        records.sort(key=lambda r: r.timestamp)
        return records

    def add(self, record: RunRecord) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record_to_dict(record)) + "\n")

    def delete(self, ids: set[str]) -> None:
        keep = [r for r in self.load() if r.id not in ids]
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for r in keep:
                f.write(json.dumps(record_to_dict(r)) + "\n")
        tmp.replace(self.path)

    def results_for(self, key: str, records: list[RunRecord] | None = None) -> list[tuple[RunRecord, BenchmarkResult]]:
        """Every successful result for one benchmark, oldest first."""
        out = []
        for record in records if records is not None else self.load():
            result = record.result(key)
            if result and result.status == OK and result.score is not None:
                out.append((record, result))
        return out

    def previous(self, key: str, before: RunRecord | None = None, records=None) -> tuple[RunRecord, BenchmarkResult] | None:
        """The most recent successful result for `key` from before `before` (or overall)."""
        found = None
        for record, result in self.results_for(key, records):
            if before is not None and (record.id == before.id or record.timestamp > before.timestamp):
                continue
            found = (record, result)
        return found

    def best(self, key: str, records=None) -> tuple[RunRecord, BenchmarkResult] | None:
        return max(self.results_for(key, records), key=lambda rr: rr[1].score, default=None)


def change(current: float | None, previous: float | None) -> float | None:
    """Percentage change from previous to current, or None if either is missing."""
    if not current or not previous:
        return None
    return 100.0 * (current - previous) / previous


def export_json(records: list[RunRecord], path: Path) -> None:
    Path(path).write_text(json.dumps([record_to_dict(r) for r in records], indent=2), encoding="utf-8")


CSV_COLUMNS = [
    "run_id", "timestamp", "kind", "mode", "overall", "benchmark", "status", "benchmark_score",
    "group", "metric", "metric_id", "value", "unit", "metric_score", "avg_watts", "points_per_watt",
    "chip", "app_version",
]


def export_csv(records: list[RunRecord], path: Path) -> None:
    """One row per metric: easy to filter and chart in Numbers or Excel."""
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for record in records:
            for result in record.results:
                base = {
                    "run_id": record.id,
                    "timestamp": record.timestamp,
                    "kind": record.kind,
                    "mode": record.mode,
                    "overall": _num(record.composite),
                    "benchmark": result.title,
                    "status": result.status,
                    "benchmark_score": _num(result.score),
                    "avg_watts": _num(result.power.avg_w if result.power else None),
                    "points_per_watt": _num(result.efficiency),
                    "chip": record.system.get("chip", ""),
                    "app_version": record.app_version,
                }
                if not result.metrics:
                    writer.writerow(base)
                for m in result.metrics:
                    writer.writerow(
                        base
                        | {
                            "group": m.group,
                            "metric": m.name,
                            "metric_id": m.id,
                            "value": _num(m.value, 4),
                            "unit": m.unit,
                            "metric_score": _num(m.score),
                        }
                    )


def _num(value, digits: int = 1):
    return "" if value is None else round(value, digits)
