"""Power readings from macOS `powermetrics`, sampled in the background while a benchmark runs.

powermetrics only runs as root. The app never asks for or handles a password: it uses
`sudo -n` (non-interactive), which only succeeds if a sudoers rule allows this exact
command without a password. `python main.py --setup-power` prints that rule.

The command line is fixed (see POWERMETRICS_ARGS) so the sudoers rule can allow exactly
this invocation and nothing else. powermetrics can write files as root with -o, so a
rule that allowed any arguments would be a security hole.
"""

from __future__ import annotations

import getpass
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass

from asbench.core.model import PowerSummary

POWERMETRICS = "/usr/bin/powermetrics"
# 500 ms samples, capped at one hour so a stray process can never run forever.
POWERMETRICS_ARGS = ["--samplers", "cpu_power,gpu_power,thermal", "-i", "500", "-n", "7200"]

THERMAL_LEVELS = ["Nominal", "Fair", "Moderate", "Serious", "Heavy", "Trapping", "Critical", "Sleeping"]

_BOUNDARY = "*** Sampled system activity"
_COMPONENT_RE = re.compile(r"^(CPU|GPU|ANE) Power:\s*([\d.]+)\s*(mW|W)\b", re.IGNORECASE)
_COMBINED_RE = re.compile(r"^Combined Power\b[^:]*:\s*([\d.]+)\s*(mW|W)\b", re.IGNORECASE)
_INTEL_PACKAGE_RE = re.compile(r"package power[^:]*:\s*([\d.]+)\s*(mW|W)\b", re.IGNORECASE)
_THERMAL_RE = re.compile(r"^Current pressure level:\s*(\w+)", re.IGNORECASE)


def sudoers_rule(user: str | None = None) -> str:
    """The one line to add with `sudo visudo -f /etc/sudoers.d/powermetrics`."""
    user = user or getpass.getuser()
    # Commas separate commands in sudoers, so literal commas in arguments must be escaped.
    args = " ".join(a.replace(",", "\\,") for a in POWERMETRICS_ARGS)
    return f"{user} ALL=(root) NOPASSWD: {POWERMETRICS} {args}"


def setup_instructions() -> str:
    return (
        "Power readings use macOS's built-in powermetrics tool, which needs administrator rights.\n"
        "To allow just that one command without a password prompt:\n\n" + setup_steps()
    )


def setup_steps() -> str:
    return (
        "  1. In Terminal, run:   sudo visudo -f /etc/sudoers.d/powermetrics\n"
        "  2. Add this line, then save and quit:\n\n"
        f"     {sudoers_rule()}\n\n"
        "  3. Restart Apple System Benchmark.\n\n"
        "visudo checks the syntax before saving. To undo it later, run:\n"
        "  sudo rm /etc/sudoers.d/powermetrics"
    )


@dataclass
class PowerSample:
    t: float                     # time.monotonic() when the sample finished
    combined_w: float | None = None
    cpu_w: float | None = None
    gpu_w: float | None = None
    ane_w: float | None = None
    thermal: str = ""

    @property
    def total_w(self) -> float | None:
        if self.combined_w is not None:
            return self.combined_w
        parts = [p for p in (self.cpu_w, self.gpu_w, self.ane_w) if p is not None]
        return sum(parts) if parts else None


def _watts(value: str, unit: str) -> float:
    return float(value) / (1000.0 if unit.lower() == "mw" else 1.0)


class PowermetricsParser:
    """Turns powermetrics' text output, line by line, into PowerSample objects."""

    def __init__(self):
        self._current: PowerSample | None = None

    def feed(self, line: str) -> PowerSample | None:
        """Parse one line. Returns a finished sample when a new one starts."""
        line = line.strip()
        if line.startswith(_BOUNDARY):
            finished = self._finish()
            self._current = PowerSample(t=0.0)
            return finished
        if self._current is None:
            self._current = PowerSample(t=0.0)
        s = self._current
        if m := _COMBINED_RE.match(line):
            s.combined_w = _watts(*m.groups())
        elif m := _COMPONENT_RE.match(line):
            name, value, unit = m.groups()
            setattr(s, f"{name.lower()}_w", _watts(value, unit))
        elif m := _INTEL_PACKAGE_RE.search(line):
            s.combined_w = _watts(*m.groups())
        elif m := _THERMAL_RE.match(line):
            s.thermal = m.group(1).capitalize()
        return None

    def flush(self) -> PowerSample | None:
        return self._finish()

    def _finish(self) -> PowerSample | None:
        s, self._current = self._current, None
        if s is None or (s.total_w is None and not s.thermal):
            return None
        s.t = time.monotonic()
        return s


@dataclass
class PowerStatus:
    available: bool
    reason: str = ""


_status_lock = threading.Lock()
_status: PowerStatus | None = None


def _command() -> list[str]:
    cmd = [POWERMETRICS, *POWERMETRICS_ARGS]
    return cmd if os.geteuid() == 0 else ["sudo", "-n", *cmd]


def power_status(refresh: bool = False) -> PowerStatus:
    """Whether power readings work on this machine. The result is cached; it takes about a second."""
    global _status
    with _status_lock:
        if _status is None or refresh:
            _status = _probe()
        return _status


def _probe() -> PowerStatus:
    if sys.platform != "darwin":
        return PowerStatus(False, "Power readings need macOS (they use powermetrics).")
    if not os.path.exists(POWERMETRICS):
        return PowerStatus(False, "powermetrics was not found on this Mac.")
    sampler = PowerSampler()
    try:
        sampler.start()
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline and sampler.running and not sampler.samples:
            time.sleep(0.1)
        got_sample = bool(sampler.samples)
    finally:
        sampler.stop()
    if got_sample:
        return PowerStatus(True)
    err = sampler.stderr_text.lower()
    if "password" in err or "sudo" in err or "superuser" in err:
        return PowerStatus(False, "Needs permission to run powermetrics.")
    return PowerStatus(False, "powermetrics did not return any readings" + (f": {sampler.stderr_text.strip()[:200]}" if err else "."))


class PowerSampler:
    """Runs powermetrics in the background and collects samples until stop() is called."""

    def __init__(self, on_sample=None):
        self.samples: list[PowerSample] = []
        self.stderr_text = ""
        self._on_sample = on_sample
        self._proc: subprocess.Popen | None = None
        self._threads: list[threading.Thread] = []
        self._t0 = 0.0

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        self._t0 = time.monotonic()
        self._proc = subprocess.Popen(
            _command(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._threads = [
            threading.Thread(target=self._read_stdout, daemon=True),
            threading.Thread(target=self._read_stderr, daemon=True),
        ]
        for t in self._threads:
            t.start()

    def _read_stdout(self) -> None:
        parser = PowermetricsParser()
        try:
            for line in self._proc.stdout:
                if sample := parser.feed(line):
                    self._add(sample)
            if sample := parser.flush():
                self._add(sample)
        except (ValueError, OSError):
            pass  # pipe closed by stop()

    def _read_stderr(self) -> None:
        try:
            self.stderr_text = self._proc.stderr.read()
        except (ValueError, OSError):
            pass

    def _add(self, sample: PowerSample) -> None:
        self.samples.append(sample)
        if self._on_sample:
            self._on_sample(sample)

    def stop(self) -> PowerSummary:
        proc = self._proc
        if proc is not None and proc.poll() is None:
            # sudo passes SIGTERM on to powermetrics. If that is not allowed, closing our
            # end of the pipe makes powermetrics exit on its next write (SIGPIPE).
            try:
                proc.terminate()
            except (PermissionError, ProcessLookupError):
                pass
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        if proc is not None:
            for stream in (proc.stdout, proc.stderr):
                try:
                    stream.close()
                except Exception:
                    pass
        for t in self._threads:
            t.join(timeout=1)
        return self.summary()

    def window(self, start: float, end: float) -> list[PowerSample]:
        return [s for s in self.samples if start <= s.t <= end]

    def summary(self) -> PowerSummary:
        return summarise(self.samples, duration=time.monotonic() - self._t0)


def summarise(samples: list[PowerSample], duration: float) -> PowerSummary:
    totals = [s.total_w for s in samples if s.total_w is not None]
    if not totals:
        return PowerSummary(available=False, reason="No power samples were recorded.")

    def avg(values):
        values = [v for v in values if v is not None]
        return sum(values) / len(values) if values else None

    thermal = [s.thermal for s in samples if s.thermal]
    worst = max(thermal, key=lambda t: THERMAL_LEVELS.index(t) if t in THERMAL_LEVELS else 0, default="")
    avg_w = avg(totals)
    return PowerSummary(
        available=True,
        samples=len(totals),
        avg_w=avg_w,
        peak_w=max(totals),
        cpu_w=avg(s.cpu_w for s in samples),
        gpu_w=avg(s.gpu_w for s in samples),
        ane_w=avg(s.ane_w for s in samples),
        energy_j=avg_w * duration,
        thermal=worst,
    )
