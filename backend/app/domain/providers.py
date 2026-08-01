from copy import deepcopy
from typing import Any

DEFAULT_PROVIDER_REGISTRY: dict[str, dict[str, Any]] = {
    "openai-compatible-text": {
        "name": "openai-compatible-text",
        "kind": "chat_completions",
        "base_url": "",
        "model": "",
        "api_key_env": "SHUYI_TEXT_MODEL_API_KEY",
        "timeout_seconds": 120,
        "max_tokens": 1024,
        "max_retries": 2,
        "extra_body": {},
    },
}


def default_provider_registry() -> dict[str, dict[str, Any]]:
    return deepcopy(DEFAULT_PROVIDER_REGISTRY)
