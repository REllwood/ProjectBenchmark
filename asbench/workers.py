"""CPU workloads and the worker-process pool that runs them.

This module must only import the standard library. Worker processes use the "spawn" start
method (the macOS default, and the only one that is safe alongside Qt's threads), so each
worker re-imports this module; heavy imports here would slow every worker's start-up.

Each workload does one fixed "unit" of work per call. Benchmarks run a workload
repeatedly for a fixed time and report units per second, so faster machines score higher
and every machine finishes in the same time.
"""

from __future__ import annotations

import hashlib
import json
import multiprocessing
import random
import signal
import time
import zlib
from concurrent.futures import ProcessPoolExecutor, wait

# name -> (label shown to people, short description)
WORKLOADS = {
    "integer": ("Integer", "Prime sieve (whole-number maths, branching)"),
    "float": ("Floating point", "Mandelbrot set (decimal maths)"),
    "json": ("Text & JSON", "Encode and parse structured data"),
    "compression": ("Compression", "zlib compress 256 KB of text"),
    "hashing": ("Hashing", "SHA-256 of 4 MB"),
}


def _integer():
    limit = 40_000
    sieve = [True] * (limit + 1)
    sieve[0] = sieve[1] = False
    for i in range(2, int(limit**0.5) + 1):
        if sieve[i]:
            sieve[i * i :: i] = [False] * len(range(i * i, limit + 1, i))
    count = 0
    for n in range(limit):  # the sieve slice is C-speed; this loop keeps it interpreter-bound
        if sieve[n] and n % 4 == 1:
            count += 1
    return count


def _float():
    size, max_iter, total = 40, 48, 0
    for py in range(size):
        ci = py / size * 2.4 - 1.2
        for px in range(size):
            cr = px / size * 3.0 - 2.1
            zr = zi = 0.0
            n = 0
            while n < max_iter and zr * zr + zi * zi < 4.0:
                zr, zi = zr * zr - zi * zi + cr, 2 * zr * zi + ci
                n += 1
            total += n
    return total


def _make_records():
    rng = random.Random(7)
    words = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel"]
    return [
        {
            "id": i,
            "name": " ".join(rng.choice(words) for _ in range(3)),
            "price": round(rng.uniform(1, 500), 2),
            "tags": rng.sample(words, 3),
            "stock": {"sydney": rng.randint(0, 99), "melbourne": rng.randint(0, 99)},
        }
        for i in range(400)
    ]


def _make_text(size: int) -> bytes:
    rng = random.Random(11)
    words = [bytes(rng.choice(b"abcdefghijklmnopqrstuvwxyz") for _ in range(rng.randint(2, 9))) for _ in range(2000)]
    out = bytearray()
    while len(out) < size:
        out += rng.choice(words) + b" "
    return bytes(out[:size])


_prepared: dict = {}


def _workload(name: str):
    """Return a zero-argument function doing one unit of the named workload."""
    if name in _prepared:
        return _prepared[name]
    if name == "integer":
        fn = _integer
    elif name == "float":
        fn = _float
    elif name == "json":
        records = _make_records()
        fn = lambda: len(json.loads(json.dumps(records)))  # noqa: E731
    elif name == "compression":
        text = _make_text(256 * 1024)
        fn = lambda: len(zlib.compress(text, 6))  # noqa: E731
    elif name == "hashing":
        blob = random.Random(3).randbytes(4 * 1024 * 1024)
        fn = lambda: hashlib.sha256(blob).digest()  # noqa: E731
    elif name == "mix":
        parts = [_workload(n) for n in WORKLOADS]

        def fn():
            for part in parts:
                part()
    else:
        raise KeyError(name)
    _prepared[name] = fn
    return fn


# --- Running inside worker processes -------------------------------------------------

_stop_event = None


def _init_worker(stop_event) -> None:
    global _stop_event
    _stop_event = stop_event
    # Ctrl+C in a terminal reaches every process in the group. Let the parent handle it
    # (it sets the stop event) instead of each worker dying mid-task.
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def _warm_up(names: list[str]) -> int:
    for name in names:
        _workload(name)()
    time.sleep(0.2)  # hold this worker so the pool starts a separate process for each task
    return multiprocessing.current_process().pid


def run_until(name: str, start_at: float, end_at: float) -> tuple[int, float]:
    """Wait until start_at (wall clock), then run the workload until end_at.

    Returns (units completed, seconds spent). Stops early if the pool's stop event is set.
    """
    fn = _workload(name)
    delay = start_at - time.time()
    if delay > 0:
        time.sleep(delay)
    duration = end_at - time.time()
    count = 0
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < duration:
        if _stop_event is not None and _stop_event.is_set():
            break
        fn()
        count += 1
    return count, time.perf_counter() - t0


class WorkerPool:
    """A pool of worker processes that run a workload in lock-step on every worker.

    Used by the CPU benchmark (1 worker for single-core, one per core for multi-core) and
    by the sustained test. Workers run in separate processes, so the GUI thread can't
    steal time from them and the GIL doesn't limit them.
    """

    def __init__(self, workers: int, warm: list[str] | None = None, is_cancelled=lambda: False):
        ctx = multiprocessing.get_context("spawn")
        self.workers = workers
        self._is_cancelled = is_cancelled
        self._stop = ctx.Event()
        self._pool = ProcessPoolExecutor(
            max_workers=workers, mp_context=ctx, initializer=_init_worker, initargs=(self._stop,)
        )
        names = warm or list(WORKLOADS)
        self._wait([self._pool.submit(_warm_up, names) for _ in range(workers)])

    def run(self, name: str, seconds: float) -> tuple[float, list[tuple[int, float]]]:
        """Run `name` on every worker for `seconds`. Returns (units per second, per-worker results)."""
        start_at = time.time() + 0.15
        futures = [self._pool.submit(run_until, name, start_at, start_at + seconds) for _ in range(self.workers)]
        results = self._wait(futures)
        throughput = sum(count / elapsed for count, elapsed in results if elapsed > 0)
        return throughput, results

    def _wait(self, futures):
        pending = set(futures)
        while pending:
            if self._is_cancelled():
                self._stop.set()
            _, pending = wait(pending, timeout=0.1)
        return [f.result() for f in futures]

    def close(self) -> None:
        self._stop.set()
        self._pool.shutdown(wait=True, cancel_futures=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
