import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    """Keep every test's history, references and settings out of the real user folders."""
    path = tmp_path / "data"
    monkeypatch.setenv("ASB_DATA_DIR", str(path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return path
