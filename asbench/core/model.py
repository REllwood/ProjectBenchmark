"""Data types shared by the benchmarks, the runner, the UI and the history store.

Everything here round-trips through plain dictionaries so runs can be saved as JSON.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Result statuses
OK = "ok"                    # ran on the intended hardware; counts towards the overall score
FALLBACK = "fallback"        # ran, but on substitute hardware (e.g. CPU instead of GPU)
UNAVAILABLE = "unavailable"  # could not run on this machine
ERROR = "error"              # crashed; see BenchmarkResult.error


@dataclass
class Metric:
    """One measured quantity, e.g. sequential read speed."""

    id: str                        # stable key used for scoring and comparisons, e.g. "storage.seq_read"
    name: str                      # label shown to people
    value: float
    unit: str
    group: str = ""                # optional sub-heading, e.g. "Single-core"
    higher_is_better: bool = True
    scored: bool = True            # False for informational metrics such as a scaling factor
    score: float | None = None     # filled in by scoring.score_result()


@dataclass
class PowerSummary:
    """Power drawn while a benchmark ran, from powermetrics."""

    available: bool
    reason: str = ""               # why readings are unavailable, when they are
    samples: int = 0
    avg_w: float | None = None     # combined CPU + GPU + ANE
    peak_w: float | None = None
    cpu_w: float | None = None
    gpu_w: float | None = None
    ane_w: float | None = None
    energy_j: float | None = None
    thermal: str = ""              # worst thermal pressure level seen, e.g. "Nominal"


@dataclass
class BenchmarkResult:
    key: str                       # benchmark key, e.g. "cpu"
    title: str
    status: str = OK
    metrics: list[Metric] = field(default_factory=list)
    score: float | None = None
    group_scores: dict[str, float] = field(default_factory=dict)
    efficiency: float | None = None  # points per watt, when power readings exist
    duration_s: float = 0.0
    backend: str = ""              # what actually ran the work, e.g. "MLX · Metal GPU"
    notes: list[str] = field(default_factory=list)
    error: str = ""
    power: PowerSummary | None = None
    series: dict[str, list[Any]] = field(default_factory=dict)  # time series (sustained test)

    @property
    def counts_towards_total(self) -> bool:
        return self.status == OK and self.score is not None

    def metric(self, metric_id: str) -> Metric | None:
        return next((m for m in self.metrics if m.id == metric_id), None)


@dataclass
class RunRecord:
    """One saved run: a full suite, a single benchmark, or a sustained test."""

    id: str
    timestamp: str                 # ISO 8601 with UTC offset
    kind: str                      # "suite" | "single" | "sustained"
    mode: str                      # "standard" | "quick"
    app_version: str
    system: dict[str, Any]
    results: list[BenchmarkResult]
    composite: float | None = None
    complete: bool = True          # False if the run was cancelled part-way
    reference: str = "built-in"    # "built-in" or "custom" (after --calibrate)

    def result(self, key: str) -> BenchmarkResult | None:
        return next((r for r in self.results if r.key == key), None)


def record_to_dict(record: RunRecord) -> dict[str, Any]:
    return asdict(record)


def record_from_dict(data: dict[str, Any]) -> RunRecord:
    results = [result_from_dict(r) for r in data.get("results", [])]
    fields = {k: v for k, v in data.items() if k in RunRecord.__dataclass_fields__ and k != "results"}
    return RunRecord(results=results, **fields)


def result_from_dict(data: dict[str, Any]) -> BenchmarkResult:
    metrics = [Metric(**_known(Metric, m)) for m in data.get("metrics", [])]
    power = data.get("power")
    fields = _known(BenchmarkResult, data)
    fields.pop("metrics", None)
    fields.pop("power", None)
    return BenchmarkResult(
        metrics=metrics,
        power=PowerSummary(**_known(PowerSummary, power)) if power else None,
        **fields,
    )


def _known(cls, data: dict[str, Any]) -> dict[str, Any]:
    """Drop keys a newer version may have written, so old code can still read new files."""
    return {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
