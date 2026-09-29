"""Each benchmark in quick mode: it runs, measures something real, and cleans up after itself."""

import os
import sys
import threading

import pytest

from asbench.benchmarks import cpu, gpu, memory, neural, storage, sustained
from asbench.core.context import Cancelled, RunContext
from asbench.core.model import FALLBACK, OK, UNAVAILABLE
from asbench.workers import WorkerPool


def quick(**options):
    return RunContext(quick=True, options=options)


def test_worker_pool_uses_every_worker():
    with WorkerPool(2) as pool:
        total, per_worker = pool.run("integer", 0.4)
    assert total > 0 and len(per_worker) == 2 and all(count > 0 for count, _ in per_worker)


def test_worker_pool_cancels_promptly():
    flag = threading.Event()
    with WorkerPool(2, is_cancelled=flag.is_set) as pool:
        threading.Timer(0.3, flag.set).start()
        import time

        t0 = time.monotonic()
        pool.run("float", 30)
        assert time.monotonic() - t0 < 5


@pytest.mark.parametrize("cores", [3, 12])
def test_cpu_benchmark_works_with_any_core_count(monkeypatch, cores):
    # The old version hung forever below 10 cores and scored 0 above 10.
    monkeypatch.setattr(os, "cpu_count", lambda: cores)
    r = cpu.run(quick())
    single = [m for m in r.metrics if m.group == "Single-core"]
    multi = [m for m in r.metrics if m.group == "Multi-core" and m.scored]
    assert len(single) == len(multi) == 5
    assert all(m.value > 0 and m.unit == "ops/s" for m in single + multi)
    assert r.metric("cpu.scaling").value > 1.2  # several processes beat one


def test_memory():
    r = memory.run(quick())
    assert {m.id for m in r.metrics} == {"memory.copy", "memory.copy_mt", "memory.read", "memory.write", "memory.random"}
    assert all(m.value > 0 for m in r.metrics)


def test_storage_measures_and_cleans_up(tmp_path):
    r = storage.run(quick(storage_path=str(tmp_path)))
    assert {m.id for m in r.metrics} == {"storage.seq_write", "storage.seq_read", "storage.rand_read", "storage.rand_write"}
    assert all(m.value > 0 for m in r.metrics)
    assert list(tmp_path.iterdir()) == []


def test_storage_cleans_up_when_cancelled(tmp_path):
    ctx = quick(storage_path=str(tmp_path))
    ctx._on_progress = lambda f: ctx.cancel() if f > 0.1 else None
    with pytest.raises(Cancelled):
        storage.run(ctx)
    assert list(tmp_path.iterdir()) == []


def test_gpu_falls_back_to_numpy_without_mlx(monkeypatch):
    monkeypatch.setattr(gpu, "_mlx", lambda: None)
    r = gpu.run(quick())
    assert r.status == FALLBACK and "NumPy" in r.backend
    assert r.metric("gpu.matmul_fp32").value > 0 and r.metric("gpu.bandwidth").value > 0


def test_gpu_mlx_code_path():
    mx = pytest.importorskip("mlx.core")
    r = gpu.run(quick(gpu_device="mlx-cpu"))
    assert "MLX" in r.backend
    assert {m.id for m in r.metrics} == {"gpu.matmul_fp32", "gpu.matmul_fp16", "gpu.conv", "gpu.bandwidth"}
    assert all(m.value > 0 for m in r.metrics)
    assert r.status == (OK if gpu._metal_available(mx) else FALLBACK)


@pytest.mark.skipif(sys.platform == "darwin", reason="checks the explanation shown off macOS")
def test_neural_engine_explains_why_it_is_unavailable():
    status, reason = neural.availability()
    assert status == UNAVAILABLE and "Core ML" in reason


def test_neural_models_build_and_are_cached(tmp_path):
    pytest.importorskip("coremltools")
    folder = tmp_path / "models"
    folder.mkdir()
    path = neural.build_model("linear", folder=str(folder))
    assert path.endswith(".mlpackage") and os.path.isdir(path)
    assert neural.build_model("linear", folder=str(folder)) == path
    assert [p.name for p in folder.iterdir()] == [os.path.basename(path)]  # no temporary folders left


def test_sustained_analysis_finds_throttling():
    times = [2.0 * i for i in range(1, 21)]
    steady = sustained.analyse([100.0] * 20, times)
    assert steady["retained"] == 100 and steady["throttle_at"] is None
    values = [100.0] * 10 + [70.0] * 10
    throttled = sustained.analyse(values, times)
    assert throttled["retained"] == 70 and throttled["throttle_at"] == times[9]


class ShortContext(RunContext):
    def pick(self, standard, quick):
        return quick / 5  # 4 s run, 0.2 s windows


def test_sustained_short_cpu_run():
    points = []
    ctx = ShortContext(quick=True, options={"sustained_mode": "cpu"}, on_event=lambda name, p: points.append(p))
    r = sustained.run(ctx)
    assert r.status == OK and len(r.series["t"]) == len(points) >= 5
    assert all(v > 0 for v in r.series["cpu"])
    assert r.metric("sustained.cpu_retained").value > 0
