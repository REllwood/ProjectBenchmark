"""Dialogs: enabling power readings, and comparing two runs side by side."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFontDatabase, QGuiApplication
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from asbench.core import fmt
from asbench.core.history import change
from asbench.core.model import RunRecord
from asbench.core.power import setup_steps, sudoers_rule
from asbench.ui import theme
from asbench.ui.widgets import button, label


class PowerDialog(QDialog):
    def __init__(self, ctl, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        self.setWindowTitle("Enable power readings")
        self.setMinimumWidth(760)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(label("Enable power readings", "H2"))
        layout.addWidget(label(
            "Watts, energy and points-per-watt come from powermetrics, which is built into macOS but only runs as an "
            "administrator. The app never asks for or stores your password. Instead, you can allow this one exact "
            "command to run without a password:", "Muted", wrap=True))
        text = QPlainTextEdit(setup_steps().replace("\n  ", "\n").lstrip())
        text.setReadOnly(True)
        text.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        text.setMinimumHeight(200)
        layout.addWidget(text)
        layout.addWidget(label(
            "The rule only covers powermetrics with the exact options this app uses, so it can't be used to run "
            "anything else as an administrator.", "Small", wrap=True))
        self.status = label("", "Small", wrap=True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        copy = button("Copy the sudoers line")
        copy.clicked.connect(self._copy)
        check = button("Check again")
        check.clicked.connect(self._check)
        done = button("Done", "Primary")
        done.clicked.connect(self.accept)
        row.addWidget(copy)
        row.addWidget(check)
        row.addStretch()
        row.addWidget(done)
        layout.addLayout(row)
        ctl.machine_ready.connect(self._show_status)
        self._show_status()

    def _copy(self):
        QGuiApplication.clipboard().setText(sudoers_rule())
        self.status.setText("Copied. Paste it into the file that visudo opens.")

    def _check(self):
        self.status.setText("Checking…")
        self.ctl.refresh_power()

    def _show_status(self):
        s = self.ctl.power_status
        if s is None:
            self.status.setText("Checking…")
        elif s.available:
            self.status.setText("✓ Power readings are working.")
        else:
            self.status.setText(f"Not enabled yet: {s.reason}")


class CompareDialog(QDialog):
    """Two runs side by side, metric by metric, with the change coloured by better/worse."""

    def __init__(self, older: RunRecord, newer: RunRecord, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Compare runs")
        self.resize(820, 640)
        t = theme.current()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)
        layout.addWidget(label("Compare runs", "H2"))
        layout.addWidget(label(f"A: {fmt.when(older.timestamp)} · {older.system.get('chip', '')} · {older.mode} mode\n"
                               f"B: {fmt.when(newer.timestamp)} · {newer.system.get('chip', '')} · {newer.mode} mode",
                               "Muted", selectable=True))
        table = QTableWidget(0, 4)
        table.setHorizontalHeaderLabels(["Test", "A", "B", "Change"])
        table.verticalHeader().hide()
        table.setShowGrid(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        header = table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for col in (1, 2, 3):
            table.horizontalHeaderItem(col).setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        table.verticalHeader().setDefaultSectionSize(30)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2, 3):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

        def add(cells, bold=False, colour=None, muted=False):
            row = table.rowCount()
            table.insertRow(row)
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if bold:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                if col == 3 and colour:
                    item.setForeground(QColor(colour))
                if muted:
                    item.setForeground(QColor(t.muted))
                table.setItem(row, col, item)

        def coloured(pct):
            if pct is None or abs(pct) < 0.5:
                return None
            return t.positive if pct > 0 else t.negative

        if older.composite and newer.composite:
            pct = change(newer.composite, older.composite)
            add(["Overall score", fmt.score(older.composite), fmt.score(newer.composite), fmt.delta(pct)], True, coloured(pct))
        keys = [r.key for r in newer.results] + [r.key for r in older.results if newer.result(r.key) is None]
        for key in keys:
            a, b = older.result(key), newer.result(key)
            ref = b or a
            pct = change(b.score if b else None, a.score if a else None)
            add([ref.title, fmt.score(a.score) if a and a.score else "—", fmt.score(b.score) if b and b.score else "—",
                 fmt.delta(pct)], True, coloured(pct))
            ids = [m.id for m in ref.metrics] + ([m.id for m in a.metrics if b and not b.metric(m.id)] if a else [])
            group = None
            for metric_id in ids:
                ma = a.metric(metric_id) if a else None
                mb = b.metric(metric_id) if b else None
                m = mb or ma
                if m.group != group:
                    group = m.group
                    if group:
                        add(["    " + group, "", "", ""], muted=True)
                if ma and mb:
                    pct = change(mb.value, ma.value) if m.higher_is_better else change(ma.value, mb.value)
                else:
                    pct = None
                indent = "        " if m.group else "    "
                add([indent + m.name, fmt.value(ma.value, m.unit) if ma else "—", fmt.value(mb.value, m.unit) if mb else "—",
                     fmt.delta(pct)], colour=coloured(pct))
        layout.addWidget(table, 1)
        layout.addWidget(label("Change is shown so that positive always means better (for example, higher speed).", "Small"))
        row = QHBoxLayout()
        row.addStretch()
        close = button("Close", "Primary")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        layout.addLayout(row)
