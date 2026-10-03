"""Overview: the overall score, a chart of every category, and a card per benchmark."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from asbench import benchmarks
from asbench.core import fmt
from asbench.core.history import change
from asbench.core.model import OK, UNAVAILABLE
from asbench.ui import charts
from asbench.ui.summaries import STATUS_PILL, headline, power_line, why_not
from asbench.ui.widgets import Badge, Card, DeltaLabel, Page, PageHeader, Segmented, button, label, repolish


class CategoryCard(Card):
    run_clicked = pyqtSignal(str)

    def __init__(self, spec):
        super().__init__(clickable=True, margins=16, spacing=4)
        self.key = spec.key
        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(Badge(spec.key, spec.key, 30))
        top.addWidget(label(spec.title, "H2"), 1)
        self.pill = label("", "Pill")
        self.pill.hide()
        top.addWidget(self.pill)
        self.body.addLayout(top)
        self.body.addSpacing(4)
        self.score = label("—", "CardScore")
        self.body.addWidget(self.score)
        self.delta = DeltaLabel()
        self.body.addWidget(self.delta)
        self.detail = label(spec.summary, "Small", wrap=True)
        self.body.addWidget(self.detail)
        self.power = label("", "Small")
        self.body.addWidget(self.power)
        self.body.addStretch()
        row = QHBoxLayout()
        row.addStretch()
        self.run = button("Run", "Ghost", "play")
        self.run.clicked.connect(lambda: self.run_clicked.emit(self.key))
        row.addWidget(self.run)
        self.body.addLayout(row)
        self.setMinimumHeight(196)


class OverviewPage(Page):
    navigate = pyqtSignal(str)

    def __init__(self, ctl, export_report):
        super().__init__()
        self.ctl = ctl
        header = PageHeader("Overview", "How this Mac performs across every benchmark.")
        self.mode = Segmented([("standard", "Standard"), ("quick", "Quick")], "quick" if ctl.quick else "standard")
        self.mode.setToolTip("Quick runs take about a quarter of the time, but results vary more between runs.")
        self.mode.changed.connect(lambda v: ctl.set_quick(v == "quick"))
        self.export = button("Export report", icon_name="report", tip="Save a shareable HTML page of your latest results")
        self.export.clicked.connect(export_report)
        self.run_all = button("Run all", "Primary", "play", tip="Run every benchmark (⌘R)")
        self.run_all.clicked.connect(lambda: ctl.start(list(benchmarks.SUITE)))
        for w in (self.mode, self.export, self.run_all):
            header.actions.addWidget(w, alignment=Qt.AlignmentFlag.AlignTop)
        self.content.addWidget(header)

        hero = Card(margins=22)
        row = QHBoxLayout()
        row.setSpacing(24)
        left = QVBoxLayout()
        left.setSpacing(2)
        left.addWidget(label("Overall score", "Eyebrow"))
        self.overall = label("—", "BigScore")
        left.addWidget(self.overall)
        self.overall_delta = DeltaLabel()
        left.addWidget(self.overall_delta)
        self.overall_note = label("", "Small", wrap=True)
        left.addWidget(self.overall_note)
        left.addStretch()
        left_box = QWidget()
        left_box.setLayout(left)
        left_box.setFixedWidth(270)
        left.setContentsMargins(0, 0, 0, 0)
        row.addWidget(left_box)
        self.chart = charts.Chart(height=230)
        row.addWidget(self.chart, 1)
        hero.body.addLayout(row)
        self.content.addWidget(hero)

        grid = QGridLayout()
        grid.setSpacing(14)
        self.cards: dict[str, CategoryCard] = {}
        for i, spec in enumerate(benchmarks.SPECS):
            card = CategoryCard(spec)
            card.clicked.connect(lambda k=spec.key: self.navigate.emit(k))
            if spec.in_suite:
                card.run_clicked.connect(lambda k: ctl.start([k]))
            else:
                card.run.setText("Open")
                card.run_clicked.connect(self.navigate.emit)
            self.cards[spec.key] = card
            grid.addWidget(card, i // 3, i % 3)
        for col in range(3):
            grid.setColumnStretch(col, 1)
        self.content.addLayout(grid)
        self.content.addStretch()

        for signal in (ctl.history_changed, ctl.machine_ready, ctl.job_started, ctl.job_finished, ctl.job_failed,
                       ctl.benchmark_started, ctl.result_ready):
            signal.connect(lambda *_: self.refresh())
        self.refresh()

    def refresh(self):
        ctl = self.ctl
        busy = ctl.running
        self.run_all.setEnabled(not busy)
        self.export.setEnabled(bool(ctl.records))

        suites = ctl.suites()
        if suites:
            last = suites[-1]
            self.overall.setText(fmt.score(last.composite))
            prev = suites[-2].composite if len(suites) > 1 else None
            self.overall_delta.set_change(change(last.composite, prev), "vs previous full run")
            counted = sum(r.counts_towards_total for r in last.results)
            ref = "your calibrated baseline" if last.reference == "custom" else "roughly an M1 Mac"
            self.overall_note.setText(
                f"{fmt.when(last.timestamp)} · {last.mode.capitalize()} mode\n"
                f"Combines {counted} categories. 1,000 = {ref}; 2,000 = twice as fast."
            )
        else:
            self.overall.setText("—")
            self.overall_delta.set_change(None)
            self.overall_note.setText("Press Run all to benchmark every part of this Mac. It takes a few minutes.")

        items = []
        for spec in benchmarks.SPECS:
            card = self.cards[spec.key]
            card.run.setEnabled((not busy and ctl.ok(spec.key)) or not spec.in_suite)
            latest = ctl.latest(spec.key)
            status = ctl.availability.get(spec.key, (OK, ""))
            if spec.key == "sustained":
                self._fill_sustained(card, latest)
                continue
            score = prev = None
            if latest:
                record, result = latest
                score = result.score if result.status == OK else None
                previous = ctl.previous_ok(spec.key, record)
                prev = previous.score if previous else None
                card.score.setText(fmt.score(score) if score else "—")
                card.delta.set_change(change(score, prev))
                card.detail.setText(headline(result) if result.status == OK else why_not(result))
                card.power.setText(power_line(result))
                pill = STATUS_PILL.get(result.status, "")
            else:
                card.score.setText("—")
                card.delta.set_change(None)
                card.detail.setText(status[1] if status[0] == UNAVAILABLE else spec.summary)
                card.power.setText("")
                pill = "Unavailable" if status[0] == UNAVAILABLE else ""
            running = busy and ctl.current == spec.key
            card.pill.setObjectName("PillAccent" if running else "Pill")
            repolish(card.pill)
            card.pill.setText("Running…" if running else pill)
            card.pill.setVisible(running or bool(pill))
            items.append((spec.key, spec.title, score, prev))
        self.chart.plot(charts.category_bars(items) if any(s for _, _, s, _ in items) else None,
                        empty_text="Scores appear here after your first run")

    def _fill_sustained(self, card, latest):
        card.pill.hide()
        if not latest:
            card.score.setText("—")
            card.delta.set_change(None)
            card.detail.setText("Load the Mac for minutes and watch for thermal throttling.")
            card.power.setText("")
            return
        _, result = latest
        retained = [m for m in result.metrics if m.id.endswith("_retained")]
        card.score.setText(" / ".join(fmt.value(m.value, "%") for m in retained) or "—")
        card.delta.set_change(None)
        card.detail.setText(" · ".join(m.name.replace(" performance retained", "") for m in retained) + " performance retained"
                            if retained else why_not(result))
        card.power.setText(power_line(result))
