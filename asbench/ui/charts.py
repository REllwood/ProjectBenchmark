"""Matplotlib charts styled to sit inside the app's cards, in either theme."""

from __future__ import annotations

from datetime import datetime

import matplotlib
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, MaxNLocator

from asbench.core import fmt
from asbench.ui import theme

matplotlib.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 9,
        "axes.titlesize": 10,
    }
)


class Chart(FigureCanvasQTAgg):
    """A canvas that redraws itself (via a draw function) whenever the theme changes."""

    def __init__(self, height: int = 220):
        self.fig = Figure(figsize=(6, height / 100), dpi=100, layout="constrained")
        super().__init__(self.fig)
        self.setFixedHeight(height)
        self._draw_fn = None
        self._empty_text = ""
        theme.on_change(lambda *_: self.redraw(), self)
        self.redraw()

    def plot(self, draw_fn, empty_text: str = "") -> None:
        """draw_fn(ax, theme) draws the chart, or pass None with empty_text for a placeholder."""
        self._draw_fn, self._empty_text = draw_fn, empty_text
        self.redraw()

    def redraw(self) -> None:
        t = theme.current()
        self.fig.clear()
        self.fig.set_facecolor(t.card)
        ax = self.fig.add_subplot(111)
        _style(ax, t)
        if self._draw_fn:
            self._draw_fn(ax, t)
        else:
            ax.set_axis_off()
            ax.text(0.5, 0.5, self._empty_text, ha="center", va="center", color=t.muted, fontsize=10, transform=ax.transAxes)
        self.draw_idle()


def _style(ax, t) -> None:
    ax.set_facecolor(t.card)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(t.border)
    ax.tick_params(colors=t.muted, length=0, pad=6)
    ax.grid(True, axis="y", color=t.border, linewidth=0.8)
    ax.set_axisbelow(True)


def category_bars(items: list[tuple[str, str, float | None, float | None]]):
    """items: (key, title, score, previous score). Horizontal bars with the 1,000 reference line."""

    def draw(ax, t):
        ax.grid(False)
        ax.grid(True, axis="x", color=t.border, linewidth=0.8)
        ax.spines["bottom"].set_visible(False)
        scores = [s for _, _, s, _ in items if s] + [p for *_, p in items if p]
        top = max([2000.0, *(s * 1.18 for s in scores)])
        ys = list(range(len(items)))[::-1]
        for y, (key, _title, score, previous) in zip(ys, items):
            colour = t.category(key)
            ax.barh(y, top, height=0.52, color=t.track, zorder=1)
            if score:
                ax.barh(y, score, height=0.52, color=colour, zorder=2)
                ax.text(score + top * 0.012, y, fmt.score(score), va="center", color=t.text, fontsize=9, fontweight="bold", zorder=4)
            else:
                ax.text(top * 0.012, y, "—", va="center", color=t.muted, fontsize=9, zorder=4)
            if previous:
                ax.plot([previous, previous], [y - 0.33, y + 0.33], color=t.text, linewidth=1.4, alpha=0.55, zorder=3)
        ax.axvline(1000, color=t.muted, linewidth=1, linestyle=(0, (3, 3)), zorder=3)
        ax.text(1000, len(items) - 0.45, " 1,000 reference", color=t.muted, fontsize=8, va="bottom")
        ax.set_yticks(ys, [title for _, title, _, _ in items])
        ax.tick_params(axis="y", colors=t.text, labelsize=10)
        ax.set_xlim(0, top)
        ax.set_ylim(-0.6, len(items) - 0.1)
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
        ax.xaxis.set_major_locator(MaxNLocator(5))

    return draw


def _short_date(timestamp: str) -> str:
    try:
        dt = datetime.fromisoformat(timestamp)
        return f"{dt.day} {dt:%b}"
    except ValueError:
        return timestamp[:10]


def score_history(points: list[tuple[str, float]], colour_key: str):
    """points: (ISO timestamp, score), oldest first."""

    def draw(ax, t):
        colour = t.category(colour_key)
        xs = list(range(len(points)))
        ys = [s for _, s in points]
        ax.plot(xs, ys, color=colour, linewidth=2, marker="o", markersize=5, zorder=3)
        ax.fill_between(xs, ys, [min(ys) * 0.9] * len(ys), color=colour, alpha=0.08, zorder=2)
        ax.annotate(fmt.score(ys[-1]), (xs[-1], ys[-1]), textcoords="offset points", xytext=(0, 9), ha="center",
                    color=t.text, fontsize=9, fontweight="bold")
        step = max(1, len(points) // 8)
        ax.set_xticks(xs[::step], [_short_date(ts) for ts, _ in points][::step])
        ax.set_xlim(-0.4, max(len(points) - 0.6, 0.4))
        ax.set_ylim(min(ys) * 0.88, max(ys) * 1.12)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
        ax.yaxis.set_major_locator(MaxNLocator(4))

    return draw


def multi_history(series: dict[str, list[tuple[str, float]]], titles: dict[str, str], overall: list[tuple[str, float]]):
    """Score over time for every category (thin lines) and the overall score (thick)."""

    def draw(ax, t):
        stamps = sorted({ts for pts in series.values() for ts, _ in pts} | {ts for ts, _ in overall})
        index = {ts: i for i, ts in enumerate(stamps)}
        for key, pts in series.items():
            if pts:
                ax.plot([index[ts] for ts, _ in pts], [s for _, s in pts], color=t.category(key), linewidth=1.4,
                        marker="o", markersize=3, label=titles.get(key, key), alpha=0.9)
        if overall:
            ax.plot([index[ts] for ts, _ in overall], [s for _, s in overall], color=t.text, linewidth=2.6, marker="o",
                    markersize=5, label="Overall", zorder=5)
        step = max(1, len(stamps) // 8)
        ax.set_xticks(list(range(len(stamps)))[::step], [_short_date(s) for s in stamps][::step])
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
        ax.yaxis.set_major_locator(MaxNLocator(5))
        legend = ax.legend(loc="upper left", ncols=6, frameon=False, fontsize=8, labelcolor=t.muted,
                           bbox_to_anchor=(0, 1.16), handlelength=1.2)
        legend.set_in_layout(True)

    return draw


def sustained(series: dict[str, list], height_note: str = ""):
    """Performance as % of peak (CPU/GPU), average power on a second axis, thermal pressure shaded."""

    def draw(ax, t):
        times = series.get("t", [])
        ax.set_ylim(0, 110)
        ax.set_xlim(0, max(times[-1] if times else 60, 10))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
        ax.yaxis.set_major_locator(MaxNLocator(5))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{int(v // 60)}:{int(v % 60):02d}"))
        handles = []
        for key, label in (("cpu", "CPU"), ("gpu", "GPU")):
            pts = [(x, v) for x, v in zip(times, series.get(key, [])) if v is not None]
            if pts:
                peak = max(v for _, v in pts) or 1
                (line,) = ax.plot([x for x, _ in pts], [100 * v / peak for _, v in pts], color=t.category(key),
                                  linewidth=2, label=f"{label} (% of peak)")
                handles.append(line)
        # thermal pressure: shade the stretches that weren't Nominal
        thermal = series.get("thermal", [])
        for i, level in enumerate(thermal):
            if level and level != "Nominal" and i < len(times):
                start = times[i - 1] if i else 0
                ax.axvspan(start, times[i], color=t.negative, alpha=0.08, linewidth=0)
        watts = [(x, w) for x, w in zip(times, series.get("power", [])) if w is not None]
        if watts:
            ax2 = ax.twinx()
            _style(ax2, t)
            ax2.grid(False)
            ax2.spines["bottom"].set_visible(False)
            (pline,) = ax2.plot([x for x, _ in watts], [w for _, w in watts], color=t.muted, linewidth=1.3,
                                linestyle=(0, (4, 2)), label="Power (W)")
            ax2.set_ylim(0, max(w for _, w in watts) * 1.35)
            ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f} W"))
            ax2.yaxis.set_major_locator(MaxNLocator(4))
            handles.append(pline)
        if any(level and level != "Nominal" for level in thermal):
            from matplotlib.patches import Patch

            handles.append(Patch(color=t.negative, alpha=0.2, label="Thermal pressure above nominal"))
        if handles:
            ax.legend(handles=handles, loc="lower left", frameon=False, fontsize=8, labelcolor=t.muted, ncols=4)

    return draw
