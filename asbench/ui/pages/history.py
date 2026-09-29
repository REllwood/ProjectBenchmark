"""History: every saved run, with compare, export and delete."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QAbstractItemView, QFileDialog, QHeaderView, QMessageBox, QTableWidget, QTableWidgetItem

from asbench import benchmarks
from asbench.core import fmt
from asbench.core.history import export_csv, export_json
from asbench.ui import charts
from asbench.ui.dialogs import CompareDialog
from asbench.ui.widgets import Card, Page, PageHeader, button, label

KIND = {"suite": "Full run", "single": "Single", "sustained": "Sustained"}


class HistoryPage(Page):
    export_report = pyqtSignal(object)  # RunRecord

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        header = PageHeader("History", "Every run is saved on this Mac, so you can track changes over time.", "history", "accent")
        self.compare = button("Compare", icon_name="compare", tip="Select two runs to compare them side by side")
        self.compare.clicked.connect(self._compare)
        self.report = button("Report", icon_name="report", tip="Save a shareable HTML page for the selected run")
        self.report.clicked.connect(lambda: self.export_report.emit(self._selected()[0]))
        self.csv = button("CSV", icon_name="export", tip="Export the selected runs (or all runs) as CSV")
        self.csv.clicked.connect(lambda: self._export("csv"))
        self.json = button("JSON", icon_name="export", tip="Export the selected runs (or all runs) as JSON")
        self.json.clicked.connect(lambda: self._export("json"))
        self.delete = button("Delete", icon_name="trash", tip="Delete the selected runs")
        self.delete.clicked.connect(self._delete)
        for w in (self.compare, self.report, self.csv, self.json, self.delete):
            header.actions.addWidget(w, alignment=Qt.AlignmentFlag.AlignTop)
        self.content.addWidget(header)

        chart_card = Card()
        chart_card.body.addWidget(label("Scores over time", "H2"))
        self.chart = charts.Chart(height=240)
        chart_card.body.addWidget(self.chart)
        self.content.addWidget(chart_card)

        table_card = Card()
        table_card.body.addWidget(label("Runs", "H2"))
        self.hint = label("Select two runs and press Compare. Shift- or ⌘-click to select several.", "Small")
        table_card.body.addWidget(self.hint)
        self.columns = ["When", "Type", "Mode", "Overall"] + [s.short_title for s in benchmarks.SPECS] + ["Chip"]
        self.table = QTableWidget(0, len(self.columns))
        self.table.setHorizontalHeaderLabels(self.columns)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.setMinimumHeight(320)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        head.setSectionResizeMode(len(self.columns) - 1, QHeaderView.ResizeMode.Stretch)
        head.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        table_card.body.addWidget(self.table)
        self.content.addWidget(table_card)
        self.content.addStretch()

        ctl.history_changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        records = list(reversed(self.ctl.records))
        self.table.setRowCount(0)
        for record in records:
            row = self.table.rowCount()
            self.table.insertRow(row)
            kind = KIND.get(record.kind, record.kind) + ("" if record.complete else " (cancelled)")
            cells = [fmt.when(record.timestamp), kind, record.mode.capitalize(), fmt.score(record.composite) if record.composite else ""]
            for spec in benchmarks.SPECS:
                result = record.result(spec.key)
                if result is None:
                    cells.append("")
                elif spec.key == "sustained":
                    kept = [m for m in result.metrics if m.id.endswith("_retained")]
                    cells.append(" / ".join(fmt.value(m.value, "%") for m in kept))
                else:
                    cells.append(fmt.score(result.score) if result.score else result.status)
            cells.append(record.system.get("chip", ""))
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if 3 <= col < len(cells) - 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, record.id)
                self.table.setItem(row, col, item)
        self.hint.setText("No runs yet. Results are saved automatically each time you run a benchmark." if not records
                          else "Select two runs and press Compare. Shift- or ⌘-click to select several.")

        series = {s.key: [(r.timestamp, res.score) for r, res in self.ctl.results_for(s.key)] for s in benchmarks.SPECS if s.in_suite}
        overall = [(r.timestamp, r.composite) for r in self.ctl.suites()]
        titles = {s.key: s.title for s in benchmarks.SPECS}
        has_data = any(series.values()) or overall
        self.chart.plot(charts.multi_history(series, titles, overall) if has_data else None, "Run some benchmarks to build up a history")
        self._update_buttons()

    def _selected(self):
        ids = {self.table.item(i.row(), 0).data(Qt.ItemDataRole.UserRole) for i in self.table.selectionModel().selectedRows()}
        return [r for r in self.ctl.records if r.id in ids]

    def _update_buttons(self):
        selected = self._selected()
        self.compare.setEnabled(len(selected) == 2)
        self.report.setEnabled(len(selected) == 1)
        self.delete.setEnabled(bool(selected) and not self.ctl.running)
        has = bool(self.ctl.records)
        self.csv.setEnabled(has)
        self.json.setEnabled(has)

    def _compare(self):
        a, b = sorted(self._selected(), key=lambda r: r.timestamp)
        dialog = CompareDialog(a, b, self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.exec()

    def _export(self, kind: str):
        records = self._selected() or self.ctl.records
        name = f"benchmark-history.{kind}"
        path, _ = QFileDialog.getSaveFileName(self, f"Export {len(records)} run{'s' if len(records) != 1 else ''}",
                                              str(Path.home() / name), f"{kind.upper()} (*.{kind})")
        if not path:
            return
        (export_csv if kind == "csv" else export_json)(records, Path(path))

    def _delete(self):
        selected = self._selected()
        answer = QMessageBox.question(
            self, "Delete runs", f"Delete {len(selected)} saved run{'s' if len(selected) != 1 else ''}? This can't be undone.",
            QMessageBox.StandardButton.Delete | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Delete:
            self.ctl.delete({r.id for r in selected})
