"""Sustained performance: choose a load and duration, watch the live chart, see how much speed was kept."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QHBoxLayout

from asbench import benchmarks
from asbench.core import fmt
from asbench.core.model import OK
from asbench.ui import charts
from asbench.ui.widgets import Card, MetricsTable, Page, PageHeader, Segmented, StatTile, button, label

DURATIONS = [1, 3, 5, 10, 20]


class SustainedPage(Page):
    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        spec = benchmarks.get("sustained")
        self.live: dict[str, list] | None = None
        header = PageHeader("Sustained performance", spec.subtitle, icon_name="sustained", colour_key="sustained")
        self.start = button("Start", "Primary", "play")
        self.start.clicked.connect(self._start)
        header.actions.addWidget(self.start, alignment=Qt.AlignmentFlag.AlignTop)
        self.content.addWidget(header)
        self.content.addWidget(label(spec.description, "Muted", wrap=True))

        controls = Card(margins=16)
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(label("Load", "H3"))
        self.mode = Segmented([("cpu", "CPU"), ("gpu", "GPU"), ("both", "CPU + GPU")], ctl.settings.value("sustained_mode", "cpu"))
        self.mode.changed.connect(lambda v: ctl.settings.setValue("sustained_mode", v))
        row.addWidget(self.mode)
        row.addSpacing(18)
        row.addWidget(label("Duration", "H3"))
        self.duration = QComboBox()
        for minutes in DURATIONS:
            self.duration.addItem(f"{minutes} minute{'s' if minutes > 1 else ''}", minutes)
        saved = ctl.settings.value("sustained_minutes", 3, type=int)
        self.duration.setCurrentIndex(DURATIONS.index(saved) if saved in DURATIONS else 1)
        self.duration.currentIndexChanged.connect(lambda _: ctl.settings.setValue("sustained_minutes", self.duration.currentData()))
        row.addWidget(self.duration)
        row.addStretch()
        controls.body.addLayout(row)
        self.gpu_note = label("", "Small", wrap=True)
        controls.body.addWidget(self.gpu_note)
        self.content.addWidget(controls)

        chart_card = Card()
        title_row = QHBoxLayout()
        title_row.addWidget(label("Performance over time", "H2"))
        title_row.addStretch()
        self.live_label = label("", "Small")
        title_row.addWidget(self.live_label)
        chart_card.body.addLayout(title_row)
        self.chart = charts.Chart(height=280)
        chart_card.body.addWidget(self.chart)
        self.content.addWidget(chart_card)

        tiles = QHBoxLayout()
        tiles.setSpacing(14)
        self.cpu_tile = StatTile("CPU performance kept")
        self.gpu_tile = StatTile("GPU performance kept")
        self.power_tile = StatTile("Average power")
        for tile in (self.cpu_tile, self.gpu_tile, self.power_tile):
            tiles.addWidget(tile, 1)
        self.content.addLayout(tiles)

        details = Card()
        details.body.addWidget(label("Details", "H2"))
        self.table = MetricsTable()
        details.body.addWidget(self.table)
        self.notes = label("", "Small", wrap=True)
        details.body.addWidget(self.notes)
        self.content.addWidget(details)
        self.content.addStretch()

        ctl.sustained_point.connect(self._point)
        ctl.job_started.connect(self._job_started)
        for signal in (ctl.history_changed, ctl.machine_ready, ctl.job_finished, ctl.job_failed):
            signal.connect(lambda *_: self.refresh())
        self.refresh()

    def _start(self):
        self.ctl.start(["sustained"], {"sustained_mode": self.mode.value(), "sustained_minutes": self.duration.currentData()})

    def _job_started(self, keys):
        if keys == ["sustained"]:
            self.live = {"t": [], "cpu": [], "gpu": [], "power": [], "thermal": []}
            self.chart.plot(None, "Warming up…")
        self.refresh()

    def _point(self, point: dict):
        if self.live is None:
            return
        for key in self.live:
            self.live[key].append(point.get(key))
        self.chart.plot(charts.sustained(self.live))
        bits = []
        if point.get("cpu") is not None:
            bits.append(f"CPU {point['cpu']:,.1f} ops/s")
        if point.get("gpu") is not None:
            bits.append(f"GPU {point['gpu']:,.0f} GFLOPS")
        if point.get("power") is not None:
            bits.append(f"{point['power']:.1f} W")
        if point.get("thermal"):
            bits.append(point["thermal"])
        self.live_label.setText("Live · " + " · ".join(bits))

    def refresh(self):
        ctl = self.ctl
        running_this = ctl.running and self.live is not None
        self.start.setEnabled(not ctl.running)
        self.mode.setEnabled(not ctl.running)
        self.duration.setEnabled(not ctl.running)

        gpu_status, gpu_reason = ctl.availability.get("gpu", (OK, ""))
        gpu_ok = gpu_status == OK
        for key in ("gpu", "both"):
            self.mode.buttons[key].setEnabled(gpu_ok)
        if not gpu_ok and self.mode.value() != "cpu":
            self.mode.set_value("cpu")
        self.gpu_note.setText("" if gpu_ok else f"GPU load unavailable: {gpu_reason}")
        self.gpu_note.setVisible(not gpu_ok and bool(gpu_reason))

        if running_this:
            return
        self.live = None
        self.live_label.setText("")
        latest = ctl.latest("sustained")
        if not latest:
            self.chart.plot(None, "Press Start to load this Mac and chart its performance")
            for tile in (self.cpu_tile, self.gpu_tile, self.power_tile):
                tile.set("—", "")
            self.table.set_result(None)
            self.notes.setText("")
            return
        record, result = latest
        self.chart.plot(charts.sustained(result.series) if result.series.get("t") else None, "No data")
        for tile, key in ((self.cpu_tile, "cpu"), (self.gpu_tile, "gpu")):
            kept = result.metric(f"sustained.{key}_retained")
            slowed = result.metric(f"sustained.{key}_throttle")
            if kept:
                tile.set(fmt.value(kept.value, "%"), f"Slowed after {fmt.duration(slowed.value)}" if slowed else "No throttling detected")
            else:
                tile.set("—", "Not loaded in this run")
        p = result.power
        if p and p.available and p.avg_w:
            self.power_tile.set(fmt.value(p.avg_w, "W"), f"Peak {fmt.value(p.peak_w, 'W')} · thermal pressure: {p.thermal or '—'}")
        else:
            self.power_tile.set("—", ctl.power_status.reason if ctl.power_status and not ctl.power_status.available else "")
        self.table.set_result(result)
        when = fmt.when(record.timestamp)
        self.notes.setText("\n".join([f"• Run on {when}, {fmt.duration(result.duration_s)} · {result.backend}"] + [f"• {n}" for n in result.notes]))
