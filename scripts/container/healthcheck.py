#!/usr/bin/env python3
"""通过公开 API 的 readiness 结果确认容器是否可接收请求。"""

from __future__ import annotations

import json
import urllib.request


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.load(response)


def main() -> int:
    api = get_json("http://127.0.0.1:8000/health/ready")
    if api.get("status") != "ok":
        raise RuntimeError("书弈 Agent 服务尚未就绪")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
