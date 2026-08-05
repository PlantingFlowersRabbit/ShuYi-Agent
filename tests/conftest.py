from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

@pytest.fixture(autouse=True)
def isolate_backend_runtime(monkeypatch, tmp_path):
    """v0.5 业务接口默认公开，不再依赖后端访问令牌。"""
    monkeypatch.delenv("SHUYI_API_TOKEN", raising=False)
    monkeypatch.setenv("SHUYI_DATA_DIR", str(tmp_path / "data"))
