"""The benchmark catalogue.

Each benchmark module provides:
    availability() -> (status, message)   status is model.OK, model.FALLBACK or model.UNAVAILABLE
    run(ctx: RunContext) -> BenchmarkResult

Modules are imported only when needed, so the app starts quickly and a missing optional
dependency (e.g. MLX on an Intel Mac) only affects the benchmark that uses it.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass


@dataclass(frozen=True)
class BenchmarkSpec:
    key: str
    title: str
    subtitle: str
    module: str
    summary: str       # one line for cards
    description: str   # a paragraph for the benchmark's page
    in_suite: bool = True
    short: str = ""    # compact label for tables; defaults to the title

    @property
    def short_title(self) -> str:
        return self.short or self.title

    def load(self):
        return importlib.import_module(self.module)

    def availability(self) -> tuple[str, str]:
        try:
            return self.load().availability()
        except Exception as exc:  # e.g. a broken optional dependency
            from asbench.core.model import UNAVAILABLE

            return UNAVAILABLE, f"Could not load this benchmark: {exc}"


SPECS: list[BenchmarkSpec] = [
    BenchmarkSpec(
        "cpu",
        "CPU",
        "Processor",
        "asbench.benchmarks.cpu",
        "Single-core and multi-core throughput",
        "Runs five everyday workloads (whole-number maths, decimal maths, JSON, compression and "
        "hashing), first on one core and then on every core at once. Each runs for a fixed time "
        "in its own process, and the score comes from how many units of work it completes per "
        "second.",
    ),
    BenchmarkSpec(
        "gpu",
        "GPU",
        "Graphics processor",
        "asbench.benchmarks.gpu",
        "Matrix maths and memory bandwidth on Metal",
        "Uses Apple's MLX framework to run large matrix multiplications (32-bit and 16-bit), an "
        "image convolution and a memory-bandwidth test on the Metal GPU. Results are reported in "
        "GFLOPS (billions of operations per second) and GB/s. Without a Metal GPU it runs on the "
        "CPU instead, clearly labelled, and doesn't count towards the overall score.",
    ),
    BenchmarkSpec(
        "memory",
        "Memory",
        "Unified memory",
        "asbench.benchmarks.memory",
        "Copy, read, write and random-access speed",
        "Measures how fast data moves between memory and the processor: copying, reading and "
        "writing large blocks on one core and on many, plus random access to scattered "
        "locations. Buffers are sized to your Mac's free memory, so it never pushes it into "
        "swap.",
    ),
    BenchmarkSpec(
        "storage",
        "Storage",
        "SSD",
        "asbench.benchmarks.storage",
        "Sequential and random read/write",
        "Writes and reads a test file with the macOS file cache switched off, so it measures the "
        "drive rather than memory. Reports sequential throughput (large files) and random 4 KB "
        "operations per second (IOPS; small scattered files). The file goes in a temporary folder "
        "that is always cleaned up. You can point it at another drive.",
    ),
    BenchmarkSpec(
        "neural",
        "Neural Engine",
        "Apple Neural Engine",
        "asbench.benchmarks.neural",
        "Core ML inference on the Neural Engine",
        "Builds two small neural networks with Core ML and times inference on the Neural Engine, "
        "then the same work on the GPU and the CPU for comparison. Core ML is the only way to "
        "reach the Neural Engine, so this needs macOS on Apple Silicon. The page also shows how "
        "many layers Core ML actually scheduled on the Neural Engine.",
        short="Neural",
    ),
    BenchmarkSpec(
        "sustained",
        "Sustained",
        "Thermal & sustained performance",
        "asbench.benchmarks.sustained",
        "Performance over several minutes",
        "Keeps the CPU and/or GPU fully loaded for several minutes and charts performance over "
        "time. A falling line means the Mac is slowing itself down to stay cool (thermal "
        "throttling), which is common in fanless machines such as the MacBook Air.",
        in_suite=False,
    ),
]

SUITE = [s.key for s in SPECS if s.in_suite]


def get(key: str) -> BenchmarkSpec:
    for spec in SPECS:
        if spec.key == key:
            return spec
    raise KeyError(f"Unknown benchmark: {key!r}. Choose from: {', '.join(s.key for s in SPECS)}")
