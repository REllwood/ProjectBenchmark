"""Runs benchmarks on a background thread and tells the pages what happened.

Only one job runs at a time; running two benchmarks at once would make both results
meaningless. Cancel is cooperative (a flag the benchmarks check), so threads are
never killed mid-way.
"""

from __future__ import annotations

import logging
import threading
import traceback
from datetime import datetime

from PyQt6.QtCore import QObject, QSettings, QThread, pyqtSignal

from asbench import APP_NAME, __version__, benchmarks
from asbench.core.context import RunContext
from asbench.core.history import History
from asbench.core.model import OK, BenchmarkResult, RunRecord

log = logging.getLogger(__name__)


class JobWorker(QThread):
    progress = pyqtSignal(float)
    status = pyqtSignal(str)
    event = pyqtSignal(str, object)
    done = pyqtSignal(object)   # RunRecord
    failed = pyqtSignal(str)

    def __init__(self, keys: list[str], quick: bool, options: dict, power: bool):
        super().__init__()
        self.keys, self.quick, self.options, self.power = keys, quick, options, power
        self.cancel_event = threading.Event()

    def run(self):
        from asbench.core.runner import run_many

        try:
            ctx = RunContext(
                quick=self.quick,
                cancel_event=self.cancel_event,
                on_progress=self.progress.emit,
                on_status=self.status.emit,
                on_event=self.event.emit,
                options=self.options,
            )
            record = run_many(self.keys, ctx, power=self.power, on_power_sample=lambda s: self.event.emit("power_sample", s))
            self.done.emit(record)
        except Exception:  # anything the runner didn't turn into an ERROR result
            log.exception("Benchmark job failed")
            self.failed.emit(traceback.format_exc(limit=3))


class Controller(QObject):
    job_started = pyqtSignal(list)
    benchmark_started = pyqtSignal(str)
    progress = pyqtSignal(float, str)       # overall fraction, status text
    result_ready = pyqtSignal(object)       # BenchmarkResult, as each benchmark finishes
    job_finished = pyqtSignal(object)       # RunRecord
    job_failed = pyqtSignal(str)
    power_sample = pyqtSignal(object)       # PowerSample, live
    sustained_point = pyqtSignal(dict)
    history_changed = pyqtSignal()
    machine_ready = pyqtSignal()            # system info, power status and availability are known

    def __init__(self, quick: bool = False, storage_path: str = "", power: bool = True):
        super().__init__()
        self.settings = QSettings(APP_NAME, APP_NAME)
        self.history = History()
        self.records: list[RunRecord] = self.history.load()
        self.worker: JobWorker | None = None
        self.quick = quick or self.settings.value("quick", False, type=bool)
        self.storage_path = storage_path or self.settings.value("storage_path", "", type=str)
        self.power_enabled = power
        self.system = None
        self.power_status = None
        self.availability: dict[str, tuple[str, str]] = {}
        self._status = ""
        self._fraction = 0.0
        self.current: str | None = None          # the benchmark running right now
        self._live: RunRecord | None = None      # results of the job in progress, before it's saved
        threading.Thread(target=self._probe_machine, daemon=True).start()

    # --- machine info, gathered off the UI thread because it takes a second or two ---------

    def _probe_machine(self):
        from asbench.core.power import power_status
        from asbench.core.sysinfo import collect

        self.system = collect()
        self.availability = {s.key: s.availability() for s in benchmarks.SPECS}
        self.power_status = power_status()
        self.machine_ready.emit()

    def refresh_power(self):
        def work():
            from asbench.core.power import power_status

            self.power_status = power_status(refresh=True)
            self.machine_ready.emit()

        threading.Thread(target=work, daemon=True).start()

    # --- running ---------------------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def set_quick(self, quick: bool):
        self.quick = quick
        self.settings.setValue("quick", quick)

    def set_storage_path(self, path: str):
        self.storage_path = path
        self.settings.setValue("storage_path", path)

    def start(self, keys: list[str], options: dict | None = None) -> bool:
        if self.running:
            return False
        options = dict(options or {})
        if self.storage_path:
            options.setdefault("storage_path", self.storage_path)
        self._status, self._fraction = "Starting…", 0.0
        worker = JobWorker(keys, self.quick, options, self.power_enabled)
        worker.progress.connect(self._on_progress)
        worker.status.connect(self._on_status)
        worker.event.connect(self._on_event)
        worker.done.connect(self._on_done)
        worker.failed.connect(self._on_failed)
        self.worker = worker
        self.current = None
        self._live = RunRecord(
            id="live",
            timestamp=datetime.now().astimezone().isoformat(timespec="seconds"),
            kind="live",
            mode="quick" if self.quick else "standard",
            app_version=__version__,
            system={},
            results=[],
        )
        worker.start()
        self.job_started.emit(keys)
        return True

    def cancel(self):
        if self.worker:
            self.worker.cancel_event.set()
            self._on_status("Stopping…")

    def _on_progress(self, fraction: float):
        self._fraction = fraction
        self.progress.emit(fraction, self._status)

    def _on_status(self, text: str):
        self._status = text
        self.progress.emit(self._fraction, text)

    def _on_event(self, name: str, payload):
        if name == "benchmark_started":
            self.current = payload
            self.benchmark_started.emit(payload)
        elif name == "benchmark_finished":
            self.current = None
            if self._live is not None:
                self._live.results.append(payload)
            self.result_ready.emit(payload)
        elif name == "power_sample":
            self.power_sample.emit(payload)
        elif name == "sustained_point":
            self.sustained_point.emit(payload)

    def _on_done(self, record: RunRecord):
        self.worker = None
        self.current, self._live = None, None
        if record.results:
            self.history.add(record)
            self.records.append(record)
            self.history_changed.emit()
        self.job_finished.emit(record)

    def _on_failed(self, message: str):
        self.worker = None
        self.current, self._live = None, None
        self.job_failed.emit(message)

    # --- history ---------------------------------------------------------------------------

    def latest(self, key: str) -> tuple[RunRecord, BenchmarkResult] | None:
        """The most recent result for a benchmark, whatever its status.

        Includes results from the run in progress, so pages update as each benchmark
        finishes rather than only when the whole run ends.
        """
        if self._live is not None and (result := self._live.result(key)) is not None:
            return self._live, result
        for record in reversed(self.records):
            result = record.result(key)
            if result is not None:
                return record, result
        return None

    def previous_ok(self, key: str, before: RunRecord) -> BenchmarkResult | None:
        found = self.history.previous(key, before=before, records=self.records)
        return found[1] if found else None

    def best(self, key: str) -> tuple[RunRecord, BenchmarkResult] | None:
        return self.history.best(key, records=self.records)

    def results_for(self, key: str):
        return self.history.results_for(key, records=self.records)

    def suites(self) -> list[RunRecord]:
        return [r for r in self.records if r.kind == "suite" and r.composite is not None]

    def report_record(self) -> RunRecord | None:
        """What 'Export report' should show: the last full run if it's the newest thing,
        otherwise the latest result of each benchmark combined into one page."""
        if not self.records:
            return None
        last = self.records[-1]
        if last.kind == "suite" and last.complete:
            return last
        results, stamps = [], []
        for key in benchmarks.SUITE:
            found = self.latest(key)
            if found:
                stamps.append(found[0].timestamp)
                results.append(found[1])
        if not results:
            return last
        from asbench.core.scoring import composite

        return RunRecord(
            id="latest",
            timestamp=max(stamps),
            kind="latest",
            mode=last.mode,
            app_version=last.app_version,
            system=last.system,
            results=results,
            composite=composite(results) if len(results) == len(benchmarks.SUITE) else None,
            reference=last.reference,
        )

    def delete(self, ids: set[str]):
        self.history.delete(ids)
        self.records = self.history.load()
        self.history_changed.emit()

    def ok(self, key: str) -> bool:
        return self.availability.get(key, (OK, ""))[0] != "unavailable"
