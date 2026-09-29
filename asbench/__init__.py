"""Apple System Benchmark: CPU, GPU, memory, storage and Neural Engine benchmarks for Macs.

Keep this module free of heavy imports. CPU worker processes are started with the
"spawn" method, which re-imports the package in every child process.
"""

APP_NAME = "Apple System Benchmark"
__version__ = "2.0.0"
