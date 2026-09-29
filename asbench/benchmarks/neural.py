"""Neural Engine benchmark using Core ML.

Core ML is the only public way to run work on the Apple Neural Engine (ANE); TensorFlow,
PyTorch and MLX can't reach it. We build two small networks directly with Core ML's
model builder (no training framework needed), then time inference with Core ML limited
to the CPU and Neural Engine, and the same work on the GPU and on the CPU alone for
comparison. Core ML decides per layer where to run, so we also ask it for its compute
plan and report how many layers it actually placed on the Neural Engine.
"""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import sys
import tempfile

from asbench.benchmarks._timing import rate
from asbench.core.context import RunContext
from asbench.core.model import OK, UNAVAILABLE, BenchmarkResult, Metric
from asbench.core.paths import model_cache_dir

MODEL_VERSION = 1

# A stack of 3×3 convolutions (image-style work) and of 1×1 convolutions over a token
# sequence, the ANE-friendly layout for transformer linear layers.
CONV = {"channels": 128, "size": 64, "layers": 8}
LINEAR = {"dim": 768, "tokens": 512, "layers": 8}


def conv_ops() -> int:
    c, s = CONV["channels"], CONV["size"]
    return 2 * c * c * 9 * s * s * CONV["layers"]


def linear_ops() -> int:
    return 2 * LINEAR["dim"] ** 2 * LINEAR["tokens"] * LINEAR["layers"]


def availability() -> tuple[str, str]:
    if sys.platform != "darwin":
        return UNAVAILABLE, "The Neural Engine can only be reached through Core ML, which needs macOS."
    if platform.machine() != "arm64":
        return UNAVAILABLE, "Intel Macs don't have a Neural Engine."
    try:
        major = int(platform.mac_ver()[0].split(".")[0])
    except ValueError:
        major = 0
    if major and major < 13:
        return UNAVAILABLE, "This test needs macOS 13 Ventura or later."
    if importlib.util.find_spec("coremltools") is None:
        return UNAVAILABLE, "coremltools isn't installed. Run: pip install -r requirements.txt"
    return OK, ""


def build_model(kind: str, folder: str | None = None) -> str:
    """Build (or reuse a cached copy of) a Core ML model. Returns the .mlpackage path."""
    import coremltools as ct
    import numpy as np
    from coremltools.converters.mil import Builder as mb

    folder = folder or str(model_cache_dir())
    path = os.path.join(folder, f"{kind}_v{MODEL_VERSION}.mlpackage")
    if os.path.isdir(path):
        return path

    rng = np.random.default_rng(0)
    if kind == "conv":
        c, s, layers, k = CONV["channels"], CONV["size"], CONV["layers"], 3
        shape = (1, c, s, s)
    elif kind == "linear":
        c, layers, k = LINEAR["dim"], LINEAR["layers"], 1
        shape = (1, c, 1, LINEAR["tokens"])
    else:
        raise ValueError(kind)

    @mb.program(input_specs=[mb.TensorSpec(shape=shape)], opset_version=ct.target.macOS13)
    def program(x):
        for _ in range(layers):
            weight = (rng.standard_normal((c, c, k, k)) / np.sqrt(c * k * k)).astype(np.float32)
            x = mb.conv(x=x, weight=weight, pad_type="same")
            x = mb.relu(x=x)
        return x

    model = ct.convert(
        program,
        convert_to="mlprogram",
        compute_precision=ct.precision.FLOAT16,
        minimum_deployment_target=ct.target.macOS13,
        skip_model_load=True,
    )
    # Save to a temporary name first so an interrupted build never leaves a broken cache.
    tmp = tempfile.mkdtemp(dir=folder)
    try:
        model.save(os.path.join(tmp, "model.mlpackage"))
        os.replace(os.path.join(tmp, "model.mlpackage"), path)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return path


def _layers_on_neural_engine(model, units) -> tuple[int, int] | None:
    """(layers on the ANE, total compute layers) from Core ML's compute plan, if available."""
    try:
        from coremltools.models.compute_device import MLNeuralEngineComputeDevice
        from coremltools.models.compute_plan import MLComputePlan

        plan = MLComputePlan.load_from_path(model.get_compiled_model_path(), compute_units=units)
        on_ne = total = 0
        for op in plan.model_structure.program.functions["main"].block.operations:
            if op.operator_name.split(".")[-1] == "const":
                continue
            usage = plan.get_compute_device_usage_for_mlprogram_operation(op)
            if usage is None:
                continue
            total += 1
            on_ne += isinstance(usage.preferred_compute_device, MLNeuralEngineComputeDevice)
        return (on_ne, total) if total else None
    except Exception:
        return None  # compute plans need macOS 14.4+ and coremltools 8+


def run(ctx: RunContext) -> BenchmarkResult:
    import coremltools as ct
    import numpy as np

    result = BenchmarkResult(key="neural", title="Neural Engine", backend=f"Core ML (coremltools {ct.__version__})")
    seconds = ctx.pick(2.0, 0.7)

    ctx.status("Building Core ML models (first run only)")
    conv_path = build_model("conv")
    linear_path = build_model("linear")
    ctx.check()
    ctx.progress(0.15)

    rng = np.random.default_rng(1)
    conv_input = {"x": rng.standard_normal((1, CONV["channels"], CONV["size"], CONV["size"])).astype(np.float32)}
    linear_input = {"x": rng.standard_normal((1, LINEAR["dim"], 1, LINEAR["tokens"])).astype(np.float32)}

    def measure(path, inputs, units, label):
        ctx.status(f"{label} · compiling for this chip")
        model = ct.models.MLModel(path, compute_units=units)
        ctx.status(f"{label} · timing inference")
        # The first prediction compiles the model for the chosen chip; rate() doesn't time it.
        return rate(ctx, seconds, lambda: model.predict(inputs), warmup=0.5), model

    conv_ne, model = measure(conv_path, conv_input, ct.ComputeUnit.CPU_AND_NE, "Convolution network on the Neural Engine")
    placement = _layers_on_neural_engine(model, ct.ComputeUnit.CPU_AND_NE)
    del model
    ctx.progress(0.4)
    linear_ne, model = measure(linear_path, linear_input, ct.ComputeUnit.CPU_AND_NE, "Transformer-style layers on the Neural Engine")
    del model
    ctx.progress(0.6)
    conv_gpu, model = measure(conv_path, conv_input, ct.ComputeUnit.CPU_AND_GPU, "Same network on the GPU")
    del model
    ctx.progress(0.8)
    conv_cpu, model = measure(conv_path, conv_input, ct.ComputeUnit.CPU_ONLY, "Same network on the CPU")
    del model
    ctx.progress(1.0)

    tops = lambda per_second, ops: per_second * ops / 1e12  # noqa: E731
    group, compare = "Neural Engine", "Same convolution network on other chips"
    result.metrics += [
        Metric("neural.conv", "Convolution network", tops(conv_ne, conv_ops()), "TOPS", group=group),
        Metric("neural.linear", "Transformer-style layers", tops(linear_ne, linear_ops()), "TOPS", group=group),
        Metric("neural.conv_gpu", "GPU (Core ML)", tops(conv_gpu, conv_ops()), "TOPS", group=compare, scored=False),
        Metric("neural.conv_cpu", "CPU only (Core ML)", tops(conv_cpu, conv_ops()), "TOPS", group=compare, scored=False),
    ]
    if conv_cpu > 0:
        result.metrics.append(Metric("neural.speedup", "Neural Engine vs CPU", conv_ne / conv_cpu, "×", group=compare, scored=False))

    result.notes.append(
        f"Convolution network: {conv_ne:,.0f} inferences/s on the Neural Engine, {conv_gpu:,.0f} on the GPU, "
        f"{conv_cpu:,.0f} on the CPU. TOPS = trillions of operations per second."
    )
    if placement:
        on_ne, total = placement
        result.notes.append(f"Core ML placed {on_ne} of {total} layers on the Neural Engine.")
        if on_ne == 0:
            result.notes.append("Nothing ran on the Neural Engine, so these figures reflect the CPU.")
    return result
