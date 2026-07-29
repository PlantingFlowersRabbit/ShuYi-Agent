from copy import deepcopy
from typing import Any

DEFAULT_PROVIDER_REGISTRY: dict[str, dict[str, Any]] = {
    "siliconflow-qwen3-8b": {
        "name": "siliconflow-qwen3-8b",
        "kind": "chat_completions",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "Qwen/Qwen3-8B",
        "api_key_env": "SILICONFLOW_API_KEY",
        "timeout_seconds": 60,
        "max_tokens": 768,
        "max_retries": 2,
        "extra_body": {"enable_thinking": False},
    },
    "deepseek-harness": {
        "name": "deepseek-harness",
        "kind": "chat_completions",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
        "api_key_env": "DEEPSEEK_API_KEY",
        "timeout_seconds": 120,
        "max_retries": 2,
        "extra_body": {},
    },
}


def default_provider_registry() -> dict[str, dict[str, Any]]:
    return deepcopy(DEFAULT_PROVIDER_REGISTRY)
