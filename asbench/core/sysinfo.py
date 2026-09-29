"""Describe the machine: chip, core layout, GPU cores, memory and OS."""

from __future__ import annotations

import functools
import json
import os
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass


@dataclass
class SystemInfo:
    machine: str = ""              # e.g. "MacBook Pro"
    model_id: str = ""             # e.g. "Mac14,9"
    chip: str = ""                 # e.g. "Apple M2 Pro"
    cpu_cores: int = 0             # logical cores used by the multi-core tests
    performance_cores: int = 0
    efficiency_cores: int = 0
    gpu_cores: int = 0
    memory_gb: float = 0.0
    os: str = ""                   # e.g. "macOS 14.5"
    arch: str = ""                 # e.g. "arm64"
    python: str = ""

    @property
    def is_apple_silicon(self) -> bool:
        return sys.platform == "darwin" and self.arch == "arm64"

    @property
    def core_summary(self) -> str:
        if self.performance_cores and self.efficiency_cores:
            return f"{self.cpu_cores} cores ({self.performance_cores}P + {self.efficiency_cores}E)"
        return f"{self.cpu_cores} cores"

    def as_dict(self) -> dict:
        return asdict(self)


def _run(cmd: list[str], timeout: float = 10) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _sysctl(name: str) -> str:
    return _run(["sysctl", "-n", name], timeout=3)


def _int(text: str) -> int:
    try:
        return int(str(text).strip())
    except ValueError:
        return 0


@functools.lru_cache(maxsize=1)
def collect() -> SystemInfo:
    info = SystemInfo(
        cpu_cores=os.cpu_count() or 1,
        arch=platform.machine(),
        python=platform.python_version(),
    )
    try:
        import psutil

        info.memory_gb = round(psutil.virtual_memory().total / 2**30, 1)
    except Exception:
        pass

    if sys.platform == "darwin":
        _collect_macos(info)
    else:
        info.os = f"{platform.system()} {platform.release()}"
        info.chip = _linux_cpu_name() or platform.processor() or platform.machine()
        info.machine = platform.node()
    return info


def _collect_macos(info: SystemInfo) -> None:
    info.os = f"macOS {platform.mac_ver()[0]}"
    info.chip = _sysctl("machdep.cpu.brand_string")
    info.model_id = _sysctl("hw.model")
    info.performance_cores = _int(_sysctl("hw.perflevel0.physicalcpu"))
    info.efficiency_cores = _int(_sysctl("hw.perflevel1.physicalcpu"))
    if not info.memory_gb:
        info.memory_gb = round(_int(_sysctl("hw.memsize")) / 2**30, 1)

    raw = _run(["system_profiler", "SPHardwareDataType", "SPDisplaysDataType", "-json"], timeout=15)
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        data = {}
    hardware = (data.get("SPHardwareDataType") or [{}])[0]
    info.machine = hardware.get("machine_name", "") or info.model_id
    info.chip = hardware.get("chip_type", "") or info.chip
    for display in data.get("SPDisplaysDataType") or []:
        cores = _int(display.get("sppci_cores", ""))
        if cores:
            info.gpu_cores = cores
            break


def _linux_cpu_name() -> str:
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            for line in f:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return ""
