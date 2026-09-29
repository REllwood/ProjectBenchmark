"""Short text summaries of results, shared by the cards, tiles and run bar."""

from __future__ import annotations

from asbench.core import fmt
from asbench.core.model import ERROR, FALLBACK, UNAVAILABLE, BenchmarkResult

STATUS_PILL = {FALLBACK: "CPU fallback", UNAVAILABLE: "Unavailable", ERROR: "Error"}


def headline(result: BenchmarkResult) -> str:
    """e.g. 'Single-core 1,043 · Multi-core 5,210' or 'Sequential read 3,092 MB/s'."""
    if result.group_scores:
        return " · ".join(f"{group} {fmt.score(score)}" for group, score in result.group_scores.items())
    first = next((m for m in result.metrics if m.scored), None) or (result.metrics[0] if result.metrics else None)
    return f"{first.name} {fmt.value(first.value, first.unit)}" if first else ""


def power_line(result: BenchmarkResult) -> str:
    p = result.power
    if not p or not p.available or p.avg_w is None:
        return ""
    text = f"{fmt.value(p.avg_w, 'W')} average"
    if result.efficiency:
        text += f" · {result.efficiency:,.0f} points per watt"
    return text


def why_not(result: BenchmarkResult) -> str:
    if result.error:
        return result.error
    return result.notes[0] if result.notes else ""
