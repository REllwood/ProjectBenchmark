"""Number formatting shared by the GUI, the terminal output and the HTML report."""

from __future__ import annotations

from datetime import datetime

MINUS = "−"

# decimal places per unit
_DECIMALS = {"GB/s": 1, "MB/s": 0, "IOPS": 0, "GFLOPS": 0, "TOPS": 2, "M/s": 0, "×": 2, "%": 1, "s": 0, "W": 1, "J": 0}


def score(value: float | None) -> str:
    return "—" if value is None else f"{value:,.0f}"


def value(v: float | None, unit: str = "") -> str:
    if v is None:
        return "—"
    places = _DECIMALS.get(unit, 0 if abs(v) >= 100 else 1)
    text = f"{v:,.{places}f}"
    if unit in ("×", "%"):
        return f"{text}{unit}"
    return f"{text} {unit}".strip()


def delta(pct: float | None) -> str:
    if pct is None:
        return ""
    if abs(pct) < 0.05:
        return "±0.0%"
    return f"+{pct:.1f}%" if pct > 0 else f"{MINUS}{abs(pct):.1f}%"


def duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds} s"
    minutes, secs = divmod(seconds, 60)
    return f"{minutes} min {secs:02d} s"


def when(timestamp: str, with_time: bool = True) -> str:
    """'29 Sep 2026, 3:04 pm' from an ISO 8601 timestamp."""
    try:
        dt = datetime.fromisoformat(timestamp)
    except ValueError:
        return timestamp
    day = f"{dt.day} {dt:%b %Y}"
    if not with_time:
        return day
    hour = dt.hour % 12 or 12
    return f"{day}, {hour}:{dt:%M} {'am' if dt.hour < 12 else 'pm'}"
