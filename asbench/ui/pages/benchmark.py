"""One page per benchmark: what it measures, the latest result in detail, and its history."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFileDialog, QHBoxLayout

from asbench.core import fmt
from asbench.core.history import change
from asbench.core.model import ERROR, OK, UNAVAILABLE
from asbench.ui import charts
from asbench.ui.widgets import Banner, Card, MetricsTable, Page, PageHeader, StatTile, button, label


class BenchmarkPage(Page):
    open_power_help = pyqtSignal()

    def __init__(self, spec, ctl):
        super().__init__()
        self.spec, self.ctl = spec, ctl
        header = PageHeader(spec.title, spec.subtitle, icon_name=spec.key, colour_key=spec.key)
        if spec.key == "storage":
            self.folder = button("Choose drive…", icon_name="folder", tip="Test a different drive or folder")
            self.folder.clicked.connect(self._choose_folder)
            header.actions.addWidget(self.folder, alignment=Qt.AlignmentFlag.AlignTop)
        self.run = button(f"Run {spec.title}", "Primary", "play")
        self.run.clicked.connect(lambda: ctl.start([spec.key]))
        header.actions.addWidget(self.run, alignment=Qt.AlignmentFlag.AlignTop)
        self.content.addWidget(header)

        about = label(spec.description, "Muted", wrap=True)
        self.content.addWidget(about)
        if spec.key == "storage":
            self.location = label("", "Small", wrap=True)
            self.content.addWidget(self.location)

        self.banner = Banner()
        self.content.addWidget(self.banner)
        self.error = Banner("error")
        self.content.addWidget(self.error)

        tiles = QHBoxLayout()
        tiles.setSpacing(14)
        self.score_tile = StatTile("Score")
        self.power_tile = StatTile("Power")
        self.info_tile = StatTile("Last run")
        for tile in (self.score_tile, self.power_tile, self.info_tile):
            tiles.addWidget(tile, 1)
        self.power_link = button("Enable power readings…", "Link")
        self.power_link.clicked.connect(self.open_power_help.emit)
        self.power_tile.body.insertWidget(3, self.power_link)
        self.content.addLayout(tiles)

        results = Card()
        results.body.addWidget(label("Results", "H2"))
        self.table = MetricsTable()
        results.body.addWidget(self.table)
        self.notes = label("", "Small", wrap=True)
        results.body.addWidget(self.notes)
        self.content.addWidget(results)

        history = Card()
        history.body.addWidget(label("Score history", "H2"))
        self.chart = charts.Chart(height=200)
        history.body.addWidget(self.chart)
        self.content.addWidget(history)
        self.content.addStretch()

        for signal in (ctl.history_changed, ctl.machine_ready, ctl.job_started, ctl.job_finished, ctl.job_failed):
            signal.connect(lambda *_: self.refresh())
        self.refresh()

    def _choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder on the drive to test", self.ctl.storage_path or "")
        if folder:
            self.ctl.set_storage_path(folder)
            self.refresh()

    def refresh(self):
        ctl, key = self.ctl, self.spec.key
        self.run.setEnabled(not ctl.running and ctl.ok(key))
        status, reason = ctl.availability.get(key, (OK, ""))
        if key == "storage":
            import tempfile

            where = ctl.storage_path or tempfile.gettempdir()
            self.location.setText(f"Testing: {where}" + ("" if ctl.storage_path else "  (the system's temporary folder)"))

        latest = ctl.latest(key)
        if status == UNAVAILABLE:
            self.banner.show_message(f"Not available on this Mac: {reason}")
        elif status != OK and reason:
            self.banner.show_message(reason)
        else:
            self.banner.show_message("")

        if not latest:
            self.error.show_message("")
            self.score_tile.set("—", "Not run yet")
            self.info_tile.set("—", "")
            self._power(None)
            self.table.set_result(None)
            self.notes.setText("Results appear here after you run this benchmark.")
            self.chart.plot(None, "Your score history will appear here")
            return

        record, result = latest
        previous = ctl.previous_ok(key, record)
        self.error.show_message(f"The last run failed: {result.error}" if result.status == ERROR else "")
        if result.status == OK and result.score:
            best = ctl.best(key)
            detail = []
            pct = change(result.score, previous.score if previous else None)
            if pct is not None:
                detail.append(f"{fmt.delta(pct)} vs the run before")
            if best and best[1].score and best[0].id != record.id:
                detail.append(f"Best: {fmt.score(best[1].score)}")
            if result.group_scores:
                detail.insert(0, " · ".join(f"{g} {fmt.score(s)}" for g, s in result.group_scores.items()))
            self.score_tile.set(fmt.score(result.score), "\n".join(detail))
        else:
            label_text = {UNAVAILABLE: "Unavailable", ERROR: "Failed"}.get(result.status, "Not scored")
            self.score_tile.set("—", f"{label_text}. " + (result.notes[0] if result.notes else ""))
        self.info_tile.set(
            fmt.when(record.timestamp, with_time=False),
            f"{fmt.when(record.timestamp).split(', ')[-1]} · took {fmt.duration(result.duration_s)} · {record.mode} mode\n{result.backend}",
        )
        self._power(result)
        self.table.set_result(result, previous if result.status == OK else None)
        self.notes.setText("\n".join(f"• {n}" for n in result.notes))

        points = [(r.timestamp, res.score) for r, res in ctl.results_for(key)]
        self.chart.plot(charts.score_history(points, key) if points else None, "Your score history will appear here")

    def _power(self, result):
        p = result.power if result else None
        power = self.ctl.power_status
        if p and p.available and p.avg_w is not None:
            bits = [f"Peak {fmt.value(p.peak_w, 'W')}"]
            if p.energy_j:
                bits.append(f"{fmt.value(p.energy_j, 'J')} used")
            if result.efficiency:
                bits.append(f"{result.efficiency:,.0f} points per watt")
            if p.thermal:
                bits.append(f"Thermal pressure: {p.thermal}")
            self.power_tile.set(f"{fmt.value(p.avg_w, 'W')} avg", "\n".join(bits))
            self.power_link.hide()
        elif power is not None and not power.available:
            self.power_tile.set("Off", power.reason)
            self.power_link.setVisible("macOS" not in power.reason)
        else:
            self.power_tile.set("—", "Measured while the benchmark runs" if result is None else "No readings for this run")
            self.power_link.hide()
