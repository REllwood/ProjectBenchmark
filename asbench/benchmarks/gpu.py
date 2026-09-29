"""GPU benchmark: matrix maths, convolution and memory bandwidth using Apple's MLX on Metal.

Without a Metal GPU (or without MLX) the same tests run on the CPU and the result is
marked as a fallback, so it's shown but doesn't count towards the overall score.
"""

from __future__ import annotations

from asbench.benchmarks._timing import rate as _rate
from asbench.core.context import RunContext
from asbench.core.model import FALLBACK, OK, BenchmarkResult, Metric


def _mlx():
    try:
        import mlx.core as mx

        return mx
    except Exception:
        return None


def _metal_available(mx) -> bool:
    try:
        return bool(mx.is_available(mx.gpu))
    except AttributeError:  # older MLX
        return bool(mx.metal.is_available())


def availability() -> tuple[str, str]:
    mx = _mlx()
    if mx is None:
        return FALLBACK, "MLX isn't installed (it needs an Apple Silicon Mac), so the GPU tests run on the CPU with NumPy."
    if not _metal_available(mx):
        return FALLBACK, "No Metal GPU was found, so the GPU tests run on the CPU with NumPy."
    return OK, ""


def run(ctx: RunContext) -> BenchmarkResult:
    status, note = availability()
    mx = _mlx()
    result = BenchmarkResult(key="gpu", title="GPU", status=status)
    if note:
        result.notes.append(note)
    if mx is not None and status == OK:
        _run_mlx(ctx, mx, on_gpu=True, result=result)
    elif mx is not None and ctx.options.get("gpu_device") == "mlx-cpu":
        # Lets the tests exercise the MLX code path on machines without a Metal GPU.
        _run_mlx(ctx, mx, on_gpu=False, result=result)
    else:
        _run_numpy(ctx, result)
    if mx is not None:
        _release_memory(mx)  # the test arrays went out of scope when _run_mlx returned
    return result


def _release_memory(mx) -> None:
    try:
        mx.clear_cache()
    except AttributeError:  # older MLX
        mx.metal.clear_cache()


def _run_mlx(ctx: RunContext, mx, on_gpu: bool, result: BenchmarkResult) -> None:
    device = mx.gpu if on_gpu else mx.cpu
    try:
        name = mx.device_info().get("device_name", "") if on_gpu else ""
    except Exception:
        name = ""
    result.backend = f"MLX {mx.__version__} · " + (f"Metal GPU ({name})" if name else "Metal GPU" if on_gpu else "CPU (no Metal GPU)")
    seconds = ctx.pick(2.0, 0.6)
    n = ctx.pick(4096, 2048) if on_gpu else ctx.pick(1024, 512)

    def matmul_gflops(dtype, label):
        ctx.status(f"Matrix multiply · {label} · {n}×{n}")
        with mx.stream(device):
            a = mx.random.normal((n, n)).astype(dtype)
            b = mx.random.normal((n, n)).astype(dtype)
            mx.eval(a, b)
            rate = _rate(ctx, seconds, lambda: mx.eval(a @ b))
        return 2 * n**3 * rate / 1e9

    fp32 = matmul_gflops(mx.float32, "32-bit")
    result.metrics.append(Metric("gpu.matmul_fp32", "Matrix multiply (32-bit)", fp32, "GFLOPS"))
    ctx.progress(0.25)

    fp16 = matmul_gflops(mx.float16, "16-bit")
    result.metrics.append(Metric("gpu.matmul_fp16", "Matrix multiply (16-bit)", fp16, "GFLOPS"))
    ctx.progress(0.5)

    ctx.status("Image convolution · 3×3, 64 channels")
    batch, size, channels = (4, 256, 64) if on_gpu else (1, 128, 64)
    with mx.stream(device):
        x = mx.random.normal((batch, size, size, channels))
        w = mx.random.normal((channels, 3, 3, channels)) * 0.05
        mx.eval(x, w)
        rate = _rate(ctx, seconds, lambda: mx.eval(mx.conv2d(x, w, padding=1)))
    conv_flops = 2 * batch * size * size * channels * channels * 9
    result.metrics.append(Metric("gpu.conv", "Image convolution", conv_flops * rate / 1e9, "GFLOPS"))
    ctx.progress(0.75)

    ctx.status("Memory bandwidth · streaming add")
    elements = ctx.pick(64, 16) * 1024 * 1024 if on_gpu else 8 * 1024 * 1024
    with mx.stream(device):
        a = mx.random.normal((elements,))
        b = mx.random.normal((elements,))
        mx.eval(a, b)
        rate = _rate(ctx, seconds, lambda: mx.eval(a + b))
    moved = 3 * 4 * elements  # read a and b, write the result; 4 bytes each
    result.metrics.append(Metric("gpu.bandwidth", "Memory bandwidth", moved * rate / 1e9, "GB/s"))
    ctx.progress(1.0)


def _run_numpy(ctx: RunContext, result: BenchmarkResult) -> None:
    import numpy as np

    result.backend = f"NumPy {np.__version__} · CPU (no GPU backend)"
    seconds = ctx.pick(2.0, 0.6)
    n = ctx.pick(1024, 512)
    rng = np.random.default_rng(0)

    ctx.status(f"Matrix multiply · 32-bit · {n}×{n} (CPU)")
    a = rng.standard_normal((n, n), dtype=np.float32)
    b = rng.standard_normal((n, n), dtype=np.float32)
    rate = _rate(ctx, seconds, lambda: a @ b)
    result.metrics.append(Metric("gpu.matmul_fp32", "Matrix multiply (32-bit)", 2 * n**3 * rate / 1e9, "GFLOPS"))
    ctx.progress(0.5)

    ctx.status("Memory bandwidth · streaming add (CPU)")
    elements = 8 * 1024 * 1024
    x = rng.standard_normal(elements, dtype=np.float32)
    y = rng.standard_normal(elements, dtype=np.float32)
    out = np.empty_like(x)
    rate = _rate(ctx, seconds, lambda: np.add(x, y, out=out))
    result.metrics.append(Metric("gpu.bandwidth", "Memory bandwidth", 12 * elements * rate / 1e9, "GB/s"))
    result.notes.append("16-bit matrix and convolution tests need MLX, so they were skipped.")
    ctx.progress(1.0)
