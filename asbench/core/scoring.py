"""Turn raw measurements into points.

Each metric is compared with a reference value: matching the reference scores 1,000
points, twice as fast scores 2,000. A benchmark's score is the geometric mean of its
metric scores, and the overall score is the geometric mean of the benchmark scores. The
geometric mean means a 10% gain anywhere moves the total by the same amount, and no
single huge number can dominate.

The built-in reference values below are nominal round numbers, chosen so an M1-class Mac
lands roughly near 1,000 in each category. They are estimates, not measurements of a
specific machine. For exact comparisons, run `python main.py --cli --calibrate` on
the Mac you want as your baseline; that machine then scores exactly 1,000 everywhere.
"""

from __future__ import annotations

import json
import math

from asbench.core.model import OK, BenchmarkResult
from asbench.core.paths import references_file

REFERENCE_POINTS = 1000.0

BUILTIN_REFERENCES: dict[str, float] = {
    # CPU: work units per second (see asbench/workers.py). An M1 has 4 performance and
    # 4 efficiency cores, so multi-core is estimated at about 5.4 × single-core.
    "cpu.single.integer": 950,
    "cpu.single.float": 560,
    "cpu.single.json": 1230,
    "cpu.single.compression": 250,
    "cpu.single.hashing": 550,
    "cpu.multi.integer": 5100,
    "cpu.multi.float": 3000,
    "cpu.multi.json": 6600,
    "cpu.multi.compression": 1350,
    "cpu.multi.hashing": 3000,
    # GPU (MLX on Metal): GFLOPS and GB/s. M1 8-core GPU: 2.6 TFLOPS peak, 68 GB/s peak.
    "gpu.matmul_fp32": 1800,
    "gpu.matmul_fp16": 2000,
    "gpu.conv": 1000,
    "gpu.bandwidth": 58,
    # Memory: GB/s, and millions of random 8-byte reads per second
    "memory.copy": 55,
    "memory.copy_mt": 60,
    "memory.read": 55,
    "memory.write": 40,
    "memory.random": 150,
    # Storage (uncached): MB/s and 4 KB IOPS at queue depth 1
    "storage.seq_write": 1800,
    "storage.seq_read": 2600,
    "storage.rand_read": 15000,
    "storage.rand_write": 15000,
    # Neural Engine (Core ML, 16-bit): effective TOPS. M1 Neural Engine: 11 TOPS peak.
    "neural.conv": 4.0,
    "neural.linear": 3.0,
}


def load_references() -> tuple[dict[str, float], str]:
    """Built-in references, overridden by any saved with --calibrate. Returns (values, source)."""
    refs = dict(BUILTIN_REFERENCES)
    path = references_file()
    if path.exists():
        try:
            custom = json.loads(path.read_text(encoding="utf-8"))
            refs.update({k: float(v) for k, v in custom.items() if float(v) > 0})
            return refs, "custom"
        except (ValueError, OSError, AttributeError):
            pass
    return refs, "built-in"


def save_references(results: list[BenchmarkResult]) -> dict[str, float]:
    """Make these results the new 1,000-point baseline."""
    values = {m.id: m.value for r in results if r.status == OK for m in r.metrics if m.scored and m.value > 0}
    references_file().write_text(json.dumps(values, indent=2), encoding="utf-8")
    return values


def reset_references() -> None:
    references_file().unlink(missing_ok=True)


def geomean(values) -> float | None:
    values = [v for v in values if v is not None and v > 0]
    if not values:
        return None
    return math.exp(sum(math.log(v) for v in values) / len(values))


def score_result(result: BenchmarkResult, refs: dict[str, float]) -> BenchmarkResult:
    """Fill in points for each metric, the benchmark score, group scores and efficiency.

    Only results that ran on the intended hardware are scored: a GPU test that fell back
    to the CPU keeps its measurements but gets no points, so it can't pass for a GPU score.
    """
    for m in result.metrics:
        m.score = None
        ref = refs.get(m.id)
        if result.status == OK and m.scored and ref and m.value > 0:
            ratio = m.value / ref if m.higher_is_better else ref / m.value
            m.score = REFERENCE_POINTS * ratio
    result.score = geomean(m.score for m in result.metrics)
    groups: dict[str, list[float]] = {}
    for m in result.metrics:
        if m.score is not None and m.group:
            groups.setdefault(m.group, []).append(m.score)
    result.group_scores = {g: geomean(v) for g, v in groups.items()} if len(groups) > 1 else {}
    if result.score and result.power and result.power.avg_w:
        result.efficiency = result.score / result.power.avg_w
    return result


def composite(results: list[BenchmarkResult]) -> float | None:
    return geomean(r.score for r in results if r.counts_towards_total)
