"""The app, run offscreen: it builds, runs a real benchmark, and survives a crashing one."""

import time

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from asbench import benchmarks  # noqa: E402
from asbench.ui import theme  # noqa: E402


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    theme.install(application, "light")
    return application


def pump(app, until, timeout=120.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if until():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def window(app):
    from asbench.ui.controller import Controller
    from asbench.ui.window import MainWindow

    ctl = Controller(quick=True, power=False)
    win = MainWindow(ctl)
    win.show()
    assert pump(app, lambda: ctl.power_status is not None, timeout=30)
    yield win
    win.hide()
    win.deleteLater()


def test_every_page_opens(app, window):
    for key in window.pages:
        window.navigate(key)
        app.processEvents()
        assert window.stack.currentWidget() is window.pages[key]


def test_a_run_updates_the_pages_and_is_saved(app, window):
    ctl = window.ctl
    done = []
    ctl.job_finished.connect(done.append)
    assert ctl.start(["memory"])
    assert not ctl.start(["memory"])  # only one job at a time
    assert pump(app, lambda: done)
    app.processEvents()
    assert done[0].results[0].score > 0
    assert window.pages["memory"].score_tile.value.text() not in ("", "—")
    assert window.pages["overview"].cards["memory"].score.text() not in ("", "—")
    assert window.pages["history"].table.rowCount() == 1


def test_a_crashing_benchmark_shows_an_error_and_the_app_keeps_going(app, window, monkeypatch):
    monkeypatch.setattr(benchmarks.get("storage").load(), "run", lambda ctx: 1 / 0)
    done = []
    window.ctl.job_finished.connect(done.append)
    window.ctl.start(["storage"])
    assert pump(app, lambda: done)
    app.processEvents()
    page = window.pages["storage"]
    assert page.error.isVisibleTo(page) and "ZeroDivisionError" in page.error.text.text()


def test_theme_switch_restyles_the_app(app, window):
    theme.manager().set_mode("dark")
    assert theme.DARK.window in app.styleSheet()
    theme.manager().set_mode("light")
    assert theme.LIGHT.window in app.styleSheet()


def test_switching_theme_after_widgets_are_deleted_does_not_crash(app, monkeypatch):
    """Theme-aware widgets must stop listening for theme changes once they are deleted."""
    import sys

    from PyQt6 import sip
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtWidgets import QDialog, QVBoxLayout

    from asbench.ui import charts
    from asbench.ui.widgets import Badge, MetricsTable, Segmented, button

    dialog = QDialog()
    layout = QVBoxLayout(dialog)
    for widget in (button("Run", icon_name="play"), Badge("cpu", "cpu"), MetricsTable(), charts.Chart(),
                   Segmented([("a", "")], icon_names={"a": "light"})):
        layout.addWidget(widget)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialog.show()
    dialog.close()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(dialog)

    errors = []  # PyQt reports exceptions raised in slots here (outside pytest it aborts the app)
    monkeypatch.setattr(sys, "excepthook", lambda *exc: errors.append(exc[1]))
    theme.manager().set_mode("dark")
    theme.manager().set_mode("light")
    assert errors == []


def test_overview_updates_as_each_benchmark_finishes(app, window, monkeypatch):
    import threading

    from asbench.core.model import BenchmarkResult, Metric

    release = threading.Event()
    monkeypatch.setattr(benchmarks.get("memory").load(), "run",
                        lambda ctx: BenchmarkResult(key="memory", title="Memory", metrics=[Metric("memory.copy", "Copy", 55.0, "GB/s")]))

    def slow_storage(ctx):
        release.wait(30)
        return BenchmarkResult(key="storage", title="Storage", metrics=[Metric("storage.seq_read", "Read", 2600.0, "MB/s")])

    monkeypatch.setattr(benchmarks.get("storage").load(), "run", slow_storage)
    done = []
    window.ctl.job_finished.connect(done.append)
    window.ctl.start(["memory", "storage"])
    cards = window.pages["overview"].cards
    try:
        assert pump(app, lambda: cards["memory"].score.text() == "1,000", timeout=30)  # shown before the run ends
        assert pump(app, lambda: cards["storage"].pill.text() == "Running…", timeout=30)
        assert not done
    finally:
        release.set()
    assert pump(app, lambda: done)
    app.processEvents()
    assert cards["storage"].score.text() == "1,000" and cards["storage"].pill.isHidden()


def test_finish_message_summarises_each_kind_of_result():
    from asbench.core.model import BenchmarkResult, Metric
    from asbench.ui.window import _summary

    scored = BenchmarkResult(key="cpu", title="CPU", score=1361.2)
    sustained = BenchmarkResult(key="sustained", title="Sustained · CPU + GPU", metrics=[
        Metric("sustained.cpu_retained", "CPU performance retained", 85.8, "%", group="CPU", scored=False),
        Metric("sustained.gpu_retained", "GPU performance retained", 93.1, "%", group="GPU", scored=False),
    ])
    failed = BenchmarkResult(key="gpu", title="GPU", status="error")
    assert _summary(scored) == "CPU 1,361"
    assert _summary(sustained) == "Sustained · CPU kept 85.8%, GPU kept 93.1%"
    assert _summary(failed) == "GPU: error"
