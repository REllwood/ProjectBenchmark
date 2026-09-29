"""A shareable, self-contained HTML results page (no external files, works offline).

It follows the reader's light/dark setting and prints cleanly.
"""

from __future__ import annotations

from html import escape

from asbench import APP_NAME, __version__
from asbench.core import fmt
from asbench.core.model import ERROR, FALLBACK, OK, UNAVAILABLE, BenchmarkResult, RunRecord
from asbench.core.style import CATEGORY_COLOURS

STATUS_LABEL = {OK: "", FALLBACK: "CPU fallback · not in overall", UNAVAILABLE: "Unavailable", ERROR: "Error"}


def render(record: RunRecord) -> str:
    system = record.system
    title = " · ".join(p for p in (system.get("machine"), system.get("chip")) if p) or "Benchmark results"
    body = [
        _header(record, title),
        _hero(record),
        _system(system),
        _cards(record.results),
        *(_details(r) for r in record.results),
        _footer(record),
    ]
    return _PAGE.format(
        title=escape(f"{title} · {fmt.when(record.timestamp, with_time=False)}"),
        css=_css(),
        body="\n".join(b for b in body if b),
    )


def _header(record: RunRecord, title: str) -> str:
    kind = {
        "suite": "Full suite",
        "single": "Single benchmark",
        "sustained": "Sustained test",
        "latest": "Latest result of each benchmark",
    }.get(record.kind, record.kind)
    bits = [fmt.when(record.timestamp), kind, f"{record.mode.capitalize()} mode"]
    if not record.complete:
        bits.append("Cancelled part-way")
    return (
        f'<header><p class="eyebrow">{escape(APP_NAME)}</p><h1>{escape(title)}</h1>'
        f'<p class="muted">{escape(" · ".join(bits))}</p></header>'
    )


def _hero(record: RunRecord) -> str:
    if record.composite is None:
        return ""
    reference = (
        "your calibrated baseline" if record.reference == "custom" else "built-in reference values (roughly an M1 Mac)"
    )
    counted = sum(r.counts_towards_total for r in record.results)
    return (
        '<section class="hero card">'
        f'<div><p class="label">Overall score</p><p class="big">{fmt.score(record.composite)}</p></div>'
        f'<p class="muted">Geometric mean of {counted} categories. 1,000 = {escape(reference)}; '
        "2,000 means twice as fast.</p></section>"
    )


def _system(system: dict) -> str:
    cores = f"{system.get('cpu_cores', 0)}"
    if system.get("performance_cores") and system.get("efficiency_cores"):
        cores += f" ({system['performance_cores']} performance + {system['efficiency_cores']} efficiency)"
    rows = [
        ("Chip", system.get("chip")),
        ("CPU cores", cores),
        ("GPU cores", system.get("gpu_cores") or None),
        ("Memory", f"{system['memory_gb']:g} GB" if system.get("memory_gb") else None),
        ("System", system.get("os")),
        ("Model", system.get("model_id")),
    ]
    items = "".join(f"<div><dt>{escape(k)}</dt><dd>{escape(str(v))}</dd></div>" for k, v in rows if v)
    return f'<section><h2>This Mac</h2><dl class="system card">{items}</dl></section>'


def _cards(results: list[BenchmarkResult]) -> str:
    scored = [r.score for r in results if r.score]
    scale = max([2000.0, *(s * 1.1 for s in scored)])
    cards = []
    for r in results:
        if r.key == "sustained":
            continue
        colour = _var(r.key)
        width = min(100.0, 100.0 * (r.score or 0) / scale)
        ref = 100.0 * 1000 / scale
        status = STATUS_LABEL.get(r.status, "")
        extra = []
        if r.power and r.power.available and r.power.avg_w:
            extra.append(f"{fmt.value(r.power.avg_w, 'W')} average")
            if r.efficiency:
                extra.append(f"{r.efficiency:,.0f} points per watt")
        cards.append(
            f'<div class="card cat" style="--c:{colour}">'
            f'<p class="label"><span class="dot"></span>{escape(r.title)}</p>'
            f'<p class="score">{fmt.score(r.score)}</p>'
            f'<div class="bar"><span style="width:{width:.1f}%"></span><i style="left:{ref:.1f}%"></i></div>'
            + (f'<p class="pill">{escape(status)}</p>' if status else "")
            + (f'<p class="muted small">{escape(" · ".join(extra))}</p>' if extra else "")
            + "</div>"
        )
    if not cards:
        return ""
    return f'<section><h2>Scores</h2><div class="cards">{"".join(cards)}</div></section>'


def _details(r: BenchmarkResult) -> str:
    has_points = any(m.score for m in r.metrics)
    rows, group = [], None
    for m in r.metrics:
        if m.group != group:
            group = m.group
            if group:
                rows.append(f'<tr class="group"><td colspan="{3 if has_points else 2}">{escape(group)}</td></tr>')
        points = f"<td class='num'>{fmt.score(m.score) if m.score else ''}</td>" if has_points else ""
        rows.append(f"<tr><td>{escape(m.name)}</td><td class='num'>{escape(fmt.value(m.value, m.unit))}</td>{points}</tr>")
    head = '<th class="num">Points</th>' if has_points else ""
    table = (
        f'<table><thead><tr><th>Test</th><th class="num">Result</th>{head}</tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table>"
        if rows
        else ""
    )
    meta = [x for x in (r.backend, fmt.duration(r.duration_s) if r.duration_s else "") if x]
    power = ""
    if r.power and r.power.available:
        parts = [f"Average {fmt.value(r.power.avg_w, 'W')}", f"peak {fmt.value(r.power.peak_w, 'W')}"]
        if r.power.energy_j:
            parts.append(f"{fmt.value(r.power.energy_j, 'J')} used")
        if r.power.thermal:
            parts.append(f"thermal pressure: {r.power.thermal}")
        power = f'<p class="muted small">Power: {escape(", ".join(parts))}</p>'
    notes = "".join(f"<li>{escape(n)}</li>" for n in r.notes)
    error = f'<p class="error">{escape(r.error)}</p>' if r.error else ""
    chart = _sustained_chart(r) if r.series.get("t") else ""
    colour = _var(r.key)
    return (
        f'<section class="card detail" style="--c:{colour}">'
        f'<h3><span class="dot"></span>{escape(r.title)}'
        f'<span class="right">{fmt.score(r.score) if r.score else escape(STATUS_LABEL.get(r.status, ""))}</span></h3>'
        f'<p class="muted small">{escape(" · ".join(meta))}</p>{power}{error}{chart}{table}'
        + (f'<ul class="notes">{notes}</ul>' if notes else "")
        + "</section>"
    )


def _sustained_chart(r: BenchmarkResult) -> str:
    """Performance as % of peak over time, as an inline SVG line chart."""
    w, h, pad_l, pad_b, pad_t, pad_r = 640, 220, 44, 28, 12, 12
    times = r.series["t"]
    t_max = max(times) or 1
    lines, legend = [], []
    for key, label, colour in (("cpu", "CPU", _var("cpu")), ("gpu", "GPU", _var("gpu"))):
        values = r.series.get(key) or []
        pts = [(t, v) for t, v in zip(times, values) if v is not None]
        if not pts:
            continue
        peak = max(v for _, v in pts) or 1
        coords = " ".join(
            f"{pad_l + (w - pad_l - pad_r) * t / t_max:.1f},{pad_t + (h - pad_t - pad_b) * (1 - min(v / peak, 1.1) / 1.1):.1f}"
            for t, v in pts
        )
        lines.append(f'<polyline fill="none" style="stroke:{colour}" stroke-width="2" points="{coords}"/>')
        legend.append(f'<span><i style="background:{colour}"></i>{label}</span>')
    grid = []
    for pct in (0, 25, 50, 75, 100):
        y = pad_t + (h - pad_t - pad_b) * (1 - pct / 110)
        grid.append(
            f'<line x1="{pad_l}" x2="{w - pad_r}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>'
            f'<text x="{pad_l - 6}" y="{y + 4:.1f}" text-anchor="end">{pct}%</text>'
        )
    for i in range(5):
        t = t_max * i / 4
        x = pad_l + (w - pad_l - pad_r) * i / 4
        anchor = "start" if i == 0 else "end" if i == 4 else "middle"
        grid.append(f'<text x="{x:.1f}" y="{h - 8}" text-anchor="{anchor}">{fmt.duration(t)}</text>')
    return (
        f'<figure class="chart"><svg viewBox="0 0 {w} {h}" role="img" aria-label="Performance over time">'
        f"{''.join(grid)}{''.join(lines)}</svg>"
        f'<figcaption>Performance as a percentage of peak over time {"".join(legend)}</figcaption></figure>'
    )


def _footer(record: RunRecord) -> str:
    return (
        f'<footer class="muted small">{escape(APP_NAME)} {escape(record.app_version or __version__)} · '
        f"run {escape(record.id)} · Python {escape(str(record.system.get('python', '')))}</footer>"
    )


def _var(key: str) -> str:
    return f"var(--{key})" if key in CATEGORY_COLOURS else "var(--muted)"


def _css() -> str:
    light = "".join(f"--{k}:{v[0]};" for k, v in CATEGORY_COLOURS.items())
    dark = "".join(f"--{k}:{v[1]};" for k, v in CATEGORY_COLOURS.items())
    return _CSS.replace("/*LIGHT_CATEGORIES*/", light).replace("/*DARK_CATEGORIES*/", dark)


_CSS = """
:root{--bg:#f5f5f7;--card:#fff;--text:#1d1d1f;--muted:#6e6e73;--line:#e5e5ea;--track:#ececf0;--pill:#fff4e5;--pill-text:#8a4b00;--err:#c9302c;/*LIGHT_CATEGORIES*/}
@media (prefers-color-scheme: dark){:root{--bg:#0f1115;--card:#1a1d23;--text:#f2f2f7;--muted:#9a9aa1;--line:#2c2f36;--track:#2a2d34;--pill:#3a2a12;--pill-text:#ffcf8a;--err:#ff6961;/*DARK_CATEGORIES*/}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 -apple-system,BlinkMacSystemFont,"SF Pro Text","Helvetica Neue",Arial,sans-serif;-webkit-font-smoothing:antialiased}
main{max-width:920px;margin:0 auto;padding:40px 16px 56px}
h1{font-size:30px;line-height:1.2;margin:4px 0 6px;letter-spacing:-.02em}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:32px 0 10px;font-weight:600}
h3{display:flex;align-items:center;gap:8px;font-size:18px;margin:0 0 2px}
.right{margin-left:auto;font-variant-numeric:tabular-nums}
.eyebrow{margin:0;color:var(--muted);font-weight:600;font-size:13px}
.muted{color:var(--muted)}.small{font-size:13px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 20px}
.hero{display:flex;flex-wrap:wrap;align-items:flex-end;gap:8px 28px;margin-top:24px}
.hero .muted{flex:1;min-width:220px;margin:0 0 10px}
.label{margin:0;color:var(--muted);font-size:13px;font-weight:600;display:flex;align-items:center;gap:6px}
.big{font-size:64px;font-weight:700;line-height:1;margin:6px 0 4px;letter-spacing:-.03em;font-variant-numeric:tabular-nums}
.system{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px 24px;margin:0}
.system dt{color:var(--muted);font-size:12px}.system dd{margin:0;font-weight:600}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}
.cat .score{font-size:32px;font-weight:700;margin:6px 0 10px;font-variant-numeric:tabular-nums}
.dot{width:10px;height:10px;border-radius:50%;background:var(--c);display:inline-block;flex:none}
.bar{position:relative;height:6px;border-radius:3px;background:var(--track)}
.bar span{position:absolute;inset:0 auto 0 0;border-radius:3px;background:var(--c)}
.bar i{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--muted);opacity:.6}
.pill{display:inline-block;margin:10px 0 0;padding:2px 8px;border-radius:999px;background:var(--pill);color:var(--pill-text);font-size:12px;font-weight:600}
.detail{margin-top:12px}
table{width:100%;border-collapse:collapse;margin-top:10px;font-size:14px}
th{text-align:left;color:var(--muted);font-weight:600;font-size:12px;border-bottom:1px solid var(--line);padding:6px 0}
td{padding:6px 0;border-bottom:1px solid var(--line)}
tr.group td{color:var(--muted);font-size:12px;font-weight:600;padding-top:14px}
.num{text-align:right;font-variant-numeric:tabular-nums}
.notes{margin:12px 0 0;padding-left:18px;color:var(--muted);font-size:13px}
.error{color:var(--err);font-weight:600}
.chart{margin:14px 0 4px}.chart svg{width:100%;height:auto;display:block}
.chart text{font-size:11px;fill:var(--muted)}.chart .grid{stroke:var(--line)}
figcaption{display:flex;flex-wrap:wrap;gap:14px;color:var(--muted);font-size:12px;margin-top:6px}
figcaption span{display:inline-flex;align-items:center;gap:5px}figcaption i{width:14px;height:3px;border-radius:2px;display:inline-block}
footer{margin-top:32px}
@media print{body{background:#fff}.card{break-inside:avoid}}
"""

_PAGE = """<!doctype html>
<html lang="en-AU">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{css}</style>
</head>
<body><main>
{body}
</main></body>
</html>
"""
