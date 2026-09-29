"""Storage benchmark: sequential and random reads and writes, with the file cache bypassed.

Without bypassing the cache, a file you've just written is read straight back from
memory and the "SSD" result is really a memory result. On macOS we set F_NOCACHE on
every file handle; on Linux we try O_DIRECT and fall back to dropping the cache with
posix_fadvise.
"""

from __future__ import annotations

import mmap
import os
import random
import shutil
import sys
import tempfile
import time

from asbench.core.context import RunContext
from asbench.core.model import OK, BenchmarkResult, Metric

MiB = 1024 * 1024
BLOCK = 4096
SEQ_CHUNK = 8 * MiB

# fcntl commands from macOS <sys/fcntl.h>; older Pythons don't expose them all
F_RDAHEAD = 45
F_NOCACHE = 48
F_FULLFSYNC = 51


def availability() -> tuple[str, str]:
    return OK, ""


def target_dir(ctx: RunContext) -> str:
    return ctx.options.get("storage_path") or tempfile.gettempdir()


def _no_cache(fd: int) -> None:
    if sys.platform == "darwin":
        import fcntl

        fcntl.fcntl(fd, getattr(fcntl, "F_NOCACHE", F_NOCACHE), 1)
        fcntl.fcntl(fd, F_RDAHEAD, 0)


def _drop_cache(fd: int) -> None:
    if hasattr(os, "posix_fadvise"):
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)


def _full_sync(fd: int) -> None:
    os.fsync(fd)
    if sys.platform == "darwin":
        import fcntl

        try:
            fcntl.fcntl(fd, getattr(fcntl, "F_FULLFSYNC", F_FULLFSYNC))  # also flushes the drive's own cache
        except OSError:
            pass  # not supported on some network and external file systems


def _open(path: str, flags: int) -> tuple[int, bool]:
    """Open with the cache bypassed where possible. Returns (fd, direct)."""
    if hasattr(os, "O_DIRECT"):
        try:
            return os.open(path, flags | os.O_DIRECT), True
        except OSError:
            pass  # e.g. tmpfs doesn't support O_DIRECT
    fd = os.open(path, flags)
    _no_cache(fd)
    return fd, sys.platform == "darwin"


def run(ctx: RunContext) -> BenchmarkResult:
    folder = target_dir(ctx)
    free = shutil.disk_usage(folder).free
    size = min(ctx.pick(1024, 256) * MiB, free // 4) // SEQ_CHUNK * SEQ_CHUNK
    if size < 32 * MiB:
        raise RuntimeError(f"Not enough free space in {folder} (need at least 128 MB).")
    seconds = ctx.pick(2.0, 0.6)
    result = BenchmarkResult(key="storage", title="Storage", backend=f"{size // MiB} MB test file in {folder}")

    # Page-aligned buffers (mmap) so O_DIRECT accepts them; random data so nothing can be compressed.
    chunk = mmap.mmap(-1, SEQ_CHUNK)
    chunk.write(os.urandom(SEQ_CHUNK))
    block = mmap.mmap(-1, BLOCK)
    block.write(os.urandom(BLOCK))

    with tempfile.TemporaryDirectory(prefix="asbench-", dir=folder) as tmp:
        path = os.path.join(tmp, "testfile.bin")

        ctx.status(f"Sequential write · {size // MiB} MB")
        fd, direct = _open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
        try:
            t0 = time.perf_counter()
            written = 0
            while written < size:
                written += os.write(fd, chunk)
                ctx.progress(0.3 * written / size)
                ctx.check()
            _full_sync(fd)
            elapsed = time.perf_counter() - t0
        finally:
            os.close(fd)
        result.metrics.append(Metric("storage.seq_write", "Sequential write", size / MiB / elapsed, "MB/s"))

        ctx.status(f"Sequential read · {size // MiB} MB")
        fd, direct = _open(path, os.O_RDONLY)
        try:
            if not direct:
                _drop_cache(fd)
            t0 = time.perf_counter()
            read = 0
            while read < size:
                n = os.readv(fd, [chunk])
                if n <= 0:
                    break
                read += n
                ctx.progress(0.3 + 0.3 * read / size)
                ctx.check()
            elapsed = time.perf_counter() - t0
        finally:
            os.close(fd)
        result.metrics.append(Metric("storage.seq_read", "Sequential read", read / MiB / elapsed, "MB/s"))

        blocks = size // BLOCK
        rng = random.Random(5)

        ctx.status("Random read · 4 KB blocks")
        fd, direct = _open(path, os.O_RDONLY)
        try:
            if not direct:
                _drop_cache(fd)
                if hasattr(os, "posix_fadvise"):
                    os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_RANDOM)
            if direct and hasattr(os, "preadv"):
                # O_DIRECT needs a page-aligned destination, which the mmap block provides
                read_block = lambda: os.preadv(fd, [block], rng.randrange(blocks) * BLOCK)  # noqa: E731
            else:
                read_block = lambda: os.pread(fd, BLOCK, rng.randrange(blocks) * BLOCK)  # noqa: E731
            iops = _random_io(ctx, seconds, read_block)
        finally:
            os.close(fd)
        result.metrics.append(Metric("storage.rand_read", "Random read 4 KB", iops, "IOPS"))
        ctx.progress(0.8)

        ctx.status("Random write · 4 KB blocks")
        fd, direct = _open(path, os.O_WRONLY)
        try:
            count, t0 = 0, time.perf_counter()
            while time.perf_counter() - t0 < seconds:
                os.pwrite(fd, block, rng.randrange(blocks) * BLOCK)
                count += 1
                if count % 256 == 0:
                    ctx.check()
            _full_sync(fd)  # include the flush, so cached writes can't flatter the result
            iops = count / (time.perf_counter() - t0)
        finally:
            os.close(fd)
        result.metrics.append(Metric("storage.rand_write", "Random write 4 KB", iops, "IOPS"))
        ctx.progress(1.0)

    if not direct and sys.platform != "darwin":
        result.notes.append("This file system doesn't support uncached I/O, so random-read figures may be flattered by the cache.")
    result.notes.append("Random tests use one request at a time (queue depth 1), like most everyday app activity.")
    return result


def _random_io(ctx: RunContext, seconds: float, op) -> float:
    count, t0 = 0, time.perf_counter()
    while True:
        op()
        count += 1
        if count % 256 == 0:
            ctx.check()
        elapsed = time.perf_counter() - t0
        if elapsed >= seconds:
            return count / elapsed
