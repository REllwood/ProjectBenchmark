"""The object every benchmark receives: progress reporting, status text and cancellation."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any


class Cancelled(Exception):
    """Raised inside a benchmark when the person presses Cancel."""


class RunContext:
    """Passed to each benchmark's run() function.

    Benchmarks call progress() with a fraction from 0 to 1, status() with a short line of
    text, and check() often enough that Cancel takes effect within about a second.
    """

    def __init__(
        self,
        *,
        quick: bool = False,
        cancel_event: threading.Event | None = None,
        on_progress: Callable[[float], None] | None = None,
        on_status: Callable[[str], None] | None = None,
        on_event: Callable[[str, Any], None] | None = None,
        options: dict[str, Any] | None = None,
    ):
        self.quick = quick
        self.cancel_event = cancel_event or threading.Event()
        self.options = options or {}
        self.power_sampler = None  # set by the runner while powermetrics is sampling
        self._on_progress = on_progress
        self._on_status = on_status
        self._on_event = on_event

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def cancel(self) -> None:
        self.cancel_event.set()

    def check(self) -> None:
        if self.cancel_event.is_set():
            raise Cancelled()

    def sleep(self, seconds: float) -> None:
        """Sleep, but wake up and raise Cancelled as soon as Cancel is pressed."""
        if self.cancel_event.wait(seconds):
            raise Cancelled()

    def progress(self, fraction: float) -> None:
        if self._on_progress:
            self._on_progress(min(1.0, max(0.0, fraction)))

    def status(self, text: str) -> None:
        if self._on_status:
            self._on_status(text)

    def event(self, name: str, payload: Any = None) -> None:
        """Send live data (e.g. a sustained-test data point) to whoever is listening."""
        if self._on_event:
            self._on_event(name, payload)

    def pick(self, standard, quick):
        """Return the quick-mode value when running in quick mode."""
        return quick if self.quick else standard

    def sub(self, start: float, end: float) -> "RunContext":
        """A child context whose 0-1 progress maps onto start-end of this one."""
        child = RunContext(
            quick=self.quick,
            cancel_event=self.cancel_event,
            on_progress=lambda f: self.progress(start + (end - start) * f),
            on_status=self._on_status,
            on_event=self._on_event,
            options=self.options,
        )
        child.power_sampler = self.power_sampler
        return child
