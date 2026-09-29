"""Where the app keeps its history, custom reference values and cached models."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from asbench import APP_NAME


def data_dir() -> Path:
    """Per-user data folder. Set ASB_DATA_DIR to override it (the tests do)."""
    override = os.environ.get("ASB_DATA_DIR")
    if override:
        path = Path(override)
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_NAME
    elif sys.platform == "win32":
        path = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
    else:
        path = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "apple-system-benchmark"
    path.mkdir(parents=True, exist_ok=True)
    return path


def history_file() -> Path:
    return data_dir() / "history.jsonl"


def references_file() -> Path:
    return data_dir() / "references.json"


def model_cache_dir() -> Path:
    path = data_dir() / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path
