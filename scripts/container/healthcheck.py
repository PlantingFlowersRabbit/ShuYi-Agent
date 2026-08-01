#!/usr/bin/env python3
"""确认公开 API 与回环 TTS 模型服务均已就绪。"""

from __future__ import annotations

import json
import urllib.request


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.load(response)


def main() -> int:
    api = get_json("http://127.0.0.1:8000/health/ready")
    tts = get_json("http://127.0.0.1:7811/health")
    if api.get("status") != "ok" or tts.get("ok") is not True:
        raise RuntimeError("API 或 TTS 服务尚未就绪")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
