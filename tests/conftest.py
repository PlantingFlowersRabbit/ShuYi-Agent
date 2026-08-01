from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEST_API_TOKEN = "test-v0-4-token"


@pytest.fixture(autouse=True)
def configure_v0_4_api_token(monkeypatch):
    """业务测试默认运行在 v0.4 的 Bearer 鉴权边界内。"""
    monkeypatch.setenv("SHUYI_API_TOKEN", TEST_API_TOKEN)
