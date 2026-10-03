"""The main window: sidebar navigation, the page stack and the run bar."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QByteArray, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from asbench import APP_NAME, __version__, benchmarks
from asbench.core import fmt, report
from asbench.core.model import OK
from asbench.ui import icons, theme
from asbench.ui.dialogs import PowerDialog
from asbench.ui.pages.benchmark import BenchmarkPage
from asbench.ui.pages.history import HistoryPage
from asbench.ui.pages.overview import OverviewPage
from asbench.ui.pages.sustained import SustainedPage
from asbench.ui.widgets import Segmented, button, label

NAV = [("overview", "Overview", "overview", None)] + [
    (s.key, s.title, s.key, "Benchmarks" if s.in_suite else "Tools") for s in benchmarks.SPECS
] + [("history", "History", "history", "Tools")]


class Sidebar(QFrame):
    def __init__(self, ctl, on_navigate, on_power_help):
        super().__init__()
        self.ctl = ctl
        self.setObjectName("Sidebar")
        self.setFixedWidth(236)
        col = QVBoxLayout(self)
        col.setContentsMargins(12, 18, 12, 14)
        col.setSpacing(2)

        brand = QHBoxLayout()
        brand.setContentsMargins(6, 0, 0, 10)
        brand.setSpacing(10)
        mark = label()
        mark.setPixmap(icons.app_mark(34))
        brand.addWidget(mark)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(label("System Benchmark", "AppName"))
        names.addWidget(label(f"Version {__version__}", "Small"))
        brand.addLayout(names, 1)
        col.addLayout(brand)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        section = None
        for key, title, icon_name, sec in NAV:
            if sec != section and sec:
                section = sec
                col.addWidget(label(sec.upper(), "Section"))
            b = QPushButton(title)
            b.setObjectName("Nav")
            b.setCheckable(True)
            b.setIconSize(QSize(18, 18))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: on_navigate(k))
            self.group.addButton(b)
            self.buttons[key] = (b, icon_name)
            col.addWidget(b)
        col.addStretch()

        panel = QFrame()
        panel.setObjectName("InfoPanel")
        info = QVBoxLayout(panel)
        info.setContentsMargins(12, 10, 12, 12)
        info.setSpacing(2)
        info.addWidget(label("THIS MAC", "Eyebrow"))
        self.chip = label("Checking…", "H3", wrap=True)
        self.cores = label("", "Small", wrap=True)
        self.gpu = label("", "Small", wrap=True)
        self.memory = label("", "Small", wrap=True)
        for w in (self.chip, self.cores, self.gpu, self.memory):
            info.addWidget(w)
        info.addSpacing(6)
        power_row = QHBoxLayout()
        power_row.setSpacing(6)
        self.power_icon = label()
        self.power = label("Power readings: checking…", "Small")
        power_row.addWidget(self.power_icon)
        power_row.addWidget(self.power, 1)
        info.addLayout(power_row)
        self.power_link = button("Enable power readings…", "Link")
        self.power_link.clicked.connect(on_power_help)
        self.power_link.hide()
        info.addWidget(self.power_link)
        col.addWidget(panel)
        col.addSpacing(10)

        mode = theme.manager().mode if theme.manager() else "auto"
        self.theme_switch = Segmented([("auto", ""), ("light", ""), ("dark", "")], mode,
                                      icon_names={"auto": "auto", "light": "light", "dark": "dark"})
        for key, tip in (("auto", "Match macOS"), ("light", "Light"), ("dark", "Dark")):
            self.theme_switch.buttons[key].setToolTip(tip)
        self.theme_switch.changed.connect(self._set_theme)
        col.addWidget(self.theme_switch)

        self._paint_icons()
        theme.on_change(lambda *_: self._paint_icons(), self)
        ctl.machine_ready.connect(self.refresh)

    def _set_theme(self, mode: str):
        theme.manager().set_mode(mode)
        self.ctl.settings.setValue("theme", mode)

    def _paint_icons(self):
        t = theme.current()
        for b, icon_name in self.buttons.values():
            b.setIcon(icons.icon(icon_name, t.muted, t.selected_text))
        self.refresh()

    def select(self, key: str):
        self.buttons[key][0].setChecked(True)

    def refresh(self):
        s = self.ctl.system
        t = theme.current()
        if s:
            self.chip.setText(s.chip or s.arch)
            self.cores.setText(f"CPU: {s.core_summary}")
            self.gpu.setText(f"GPU: {s.gpu_cores} cores" if s.gpu_cores else "")
            self.gpu.setVisible(bool(s.gpu_cores))
            self.memory.setText(f"{s.memory_gb:g} GB memory · {s.os}")
        p = self.ctl.power_status
        if p is None:
            return
        on = p.available
        self.power.setText("Power readings on" if on else "Power readings off")
        self.power.setToolTip("" if on else p.reason)
        self.power_icon.setPixmap(icons.pixmap("bolt", t.positive if on else t.faint, 14))
        self.power_link.setVisible(not on and "macOS" not in p.reason)


class RunBar(QFrame):
    """Shown at the bottom while a benchmark runs: what's happening, progress, power and Cancel."""

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.setObjectName("RunBar")
        row = QHBoxLayout(self)
        row.setContentsMargins(24, 10, 18, 10)
        row.setSpacing(14)
        text = QVBoxLayout()
        text.setSpacing(0)
        self.title = label("", "H3")
        self.status = label("", "Small")
        self.status.setMinimumWidth(260)
        text.addWidget(self.title)
        text.addWidget(self.status)
        row.addLayout(text, 2)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        row.addWidget(self.bar, 3)
        self.percent = label("", "Small")
        self.percent.setMinimumWidth(34)
        row.addWidget(self.percent)
        self.watts = label("", "Small")
        row.addWidget(self.watts)
        self.elapsed = label("", "Small")
        self.elapsed.setMinimumWidth(70)
        row.addWidget(self.elapsed)
        self.cancel = button("Cancel", "Ghost", "stop", tip="Stop the current run (Esc)")
        self.cancel.clicked.connect(ctl.cancel)
        row.addWidget(self.cancel)
        self.hide()

        self._keys: list[str] = []
        self._index = 0
        self._start = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

        ctl.job_started.connect(self._started)
        ctl.benchmark_started.connect(self._benchmark_started)
        ctl.progress.connect(self._progress)
        ctl.power_sample.connect(self._power)
        ctl.job_finished.connect(self._finished)
        ctl.job_failed.connect(self._failed)

    def _started(self, keys):
        self._keys, self._index = keys, 0
        self._start = time.monotonic()
        self._hide_timer.stop()
        self.title.setText("Starting…")
        self.status.setText("")
        self.watts.setText("")
        self.bar.setValue(0)
        self.bar.show()
        self.percent.setText("0%")
        self.cancel.show()
        self.cancel.setEnabled(True)
        self._tick()
        self._timer.start(1000)
        self.show()

    def _benchmark_started(self, key):
        self._index = self._keys.index(key) + 1 if key in self._keys else self._index
        title = benchmarks.get(key).title
        if len(self._keys) > 1:
            self.title.setText(f"Running {title}  ·  {self._index} of {len(self._keys)}")
        else:
            self.title.setText(f"Running {title}")

    def _progress(self, fraction: float, status: str):
        self.bar.setValue(int(fraction * 1000))
        self.percent.setText(f"{fraction * 100:.0f}%")
        self.status.setText(status)
        if status == "Stopping…":
            self.cancel.setEnabled(False)

    def _power(self, sample):
        if sample.total_w is not None:
            self.watts.setText(f"⚡ {sample.total_w:.1f} W")

    def _tick(self):
        self.elapsed.setText(fmt.duration(time.monotonic() - self._start))

    def _finished(self, record):
        self._timer.stop()
        self.bar.hide()
        self.percent.setText("")
        self.cancel.hide()
        if not record.complete:
            self.title.setText("Run cancelled")
            self.status.setText("Benchmarks that finished before you cancelled have been saved." if record.results else "Nothing was saved.")
        elif record.composite is not None:
            self.title.setText(f"Finished  ·  overall score {fmt.score(record.composite)}")
            self.status.setText(f"Took {fmt.duration(time.monotonic() - self._start)} · saved to History")
        else:
            self.title.setText("Finished  ·  " + ", ".join(_summary(r) for r in record.results))
            self.status.setText("Saved to History")
        self._hide_timer.start(8000)

    def _failed(self, message):
        self._timer.stop()
        self.bar.hide()
        self.cancel.hide()
        self.title.setText("Something went wrong")
        self.status.setText(message.strip().splitlines()[-1] if message.strip() else "Unknown error")
        self._hide_timer.start(15000)


def _summary(r) -> str:
    """'CPU 1,361', 'Sustained · CPU kept 85.9%, GPU kept 92.9%' or 'GPU: error'."""
    if r.key == "sustained" and r.status == OK:
        kept = [f"{m.group} kept {fmt.value(m.value, '%')}" for m in r.metrics if m.id.endswith("_retained")]
        return "Sustained · " + ", ".join(kept) if kept else r.title
    if r.status == OK and r.score:
        return f"{r.title} {fmt.score(r.score)}"
    return f"{r.title}: {r.status}"


class MainWindow(QMainWindow):
    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self._closing = False
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(icons.app_mark(128)))
        self.setMinimumSize(1060, 700)

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.sidebar = Sidebar(ctl, self.navigate, self.show_power_help)
        layout.addWidget(self.sidebar)

        content = QWidget()
        content.setObjectName("Content")
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self.stack = QStackedWidget()
        column.addWidget(self.stack, 1)
        self.run_bar = RunBar(ctl)
        column.addWidget(self.run_bar)
        layout.addWidget(content, 1)
        self.setCentralWidget(root)

        self.pages: dict[str, QWidget] = {}
        overview = OverviewPage(ctl, lambda: self.export_report())
        overview.navigate.connect(self.navigate)
        self._add("overview", overview)
        for spec in benchmarks.SPECS:
            if spec.key == "sustained":
                self._add("sustained", SustainedPage(ctl))
            else:
                page = BenchmarkPage(spec, ctl)
                page.open_power_help.connect(self.show_power_help)
                self._add(spec.key, page)
        history = HistoryPage(ctl)
        history.export_report.connect(self.export_report)
        self._add("history", history)

        QShortcut(QKeySequence("Ctrl+R"), self, activated=lambda: ctl.start(list(benchmarks.SUITE)))
        QShortcut(QKeySequence("Esc"), self, activated=ctl.cancel)
        for i, (key, *_rest) in enumerate(NAV[:9], 1):
            QShortcut(QKeySequence(f"Ctrl+{i}"), self, activated=lambda k=key: self.navigate(k))

        ctl.job_finished.connect(self._job_finished)
        ctl.job_failed.connect(self._job_finished)

        geometry = ctl.settings.value("geometry", QByteArray())
        if not geometry or not self.restoreGeometry(geometry):
            self.resize(1280, 860)
        self.navigate(ctl.settings.value("page", "overview", type=str) if ctl.settings.value("page") in self.pages else "overview")

    def _add(self, key, page):
        self.pages[key] = page
        self.stack.addWidget(page)

    def navigate(self, key: str):
        if key in self.pages:
            self.stack.setCurrentWidget(self.pages[key])
            self.sidebar.select(key)
            self.ctl.settings.setValue("page", key)

    def show_power_help(self):
        dialog = PowerDialog(self.ctl, self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.exec()

    def export_report(self, record=None):
        record = record or self.ctl.report_record()
        if record is None:
            QMessageBox.information(self, "Nothing to export yet", "Run a benchmark first, then export a report.")
            return
        stamp = datetime.fromisoformat(record.timestamp).strftime("%Y-%m-%d %H.%M")
        suggested = str(Path.home() / "Desktop" / f"Benchmark {stamp}.html")
        path, _ = QFileDialog.getSaveFileName(self, "Save report", suggested, "Web page (*.html)")
        if not path:
            return
        Path(path).write_text(report.render(record), encoding="utf-8")
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _job_finished(self, *_):
        QApplication.alert(self)  # bounce the Dock icon if the app is in the background
        if self._closing:
            QApplication.quit()

    def closeEvent(self, event):
        self.ctl.settings.setValue("geometry", self.saveGeometry())
        if not self.ctl.running:
            event.accept()
            return
        answer = QMessageBox.question(self, "A benchmark is running", "Stop the benchmark and quit?",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            event.ignore()
            return
        # Let the job stop cleanly (it checks the cancel flag often) and quit once it has.
        self._closing = True
        self.ctl.cancel()
        self.hide()
        event.ignore()
