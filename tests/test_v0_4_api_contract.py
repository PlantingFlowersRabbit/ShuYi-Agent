from __future__ import annotations

import base64
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

ALLOWED_ORIGIN = "https://shuyi.example.test"


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("SHUYI_CORS_ORIGINS", ALLOWED_ORIGIN)
    from backend.app.api.app import create_app

    return TestClient(create_app())


def _encrypted_exchange(secret: str, challenge: dict[str, str]) -> dict[str, object]:
    secret_bytes = secret.encode("utf-8")
    pad = base64.b64decode(challenge["pad_b64"])
    cipher = bytes(value ^ pad[index] for index, value in enumerate(secret_bytes))
    return {
        "secret_id": challenge["secret_id"],
        "ciphertext_b64": base64.b64encode(cipher).decode("ascii"),
        "length": len(secret_bytes),
    }


def _wait_for_deployment(client: TestClient, expected: str, timeout: float = 2.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = client.get("/api/v1/model-config/tts/deployment")
        assert response.status_code == 200
        last = response.json()["deployment"]
        if last["status"] == expected:
            return last
        time.sleep(0.02)
    raise AssertionError(f"deployment did not reach {expected}: {last}")


def test_v0_5_health_probes_are_public_and_report_release(monkeypatch):
    """Covers v0.5 unauthenticated liveness, startup, and readiness probes."""
    with _client(monkeypatch) as client:
        for path in ("/health/live", "/health/startup", "/health/ready"):
            response = client.get(path)
            assert response.status_code == 200, path
            payload = response.json()
            assert payload["status"] == "ok"
            assert payload["service"] == "shuyi-agent"
            assert payload["version"] == "0.5.2"


def test_v0_5_connection_test_is_a_backend_api_smoke_test(monkeypatch):
    """模型配置页的“测试连接”只验证后端普通 API 是否可达。"""
    with _client(monkeypatch) as client:
        response = client.get("/api/v1/connection-test")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["service"] == "shuyi-agent"
    assert payload["version"] == "0.5.2"
    assert payload["message"] == "后端 API 连接成功"


def test_v0_5_models_test_checks_text_and_tts_model_apis(monkeypatch):
    """模型配置页的“测试模型”同时验证文本模型 API 与 TTS 模型 API。"""
    import backend.app.api.app as app_module

    tested: dict[str, str] = {}

    async def fake_test_model_link(config: dict[str, str]) -> None:
        tested["text_model"] = config["base_url"]

    def fake_fetch_tts_health(base_url: str) -> dict[str, object]:
        tested["tts"] = base_url
        return {
            "ok": True,
            "voice_clone": True,
            "voice_design": True,
            "voice_design_capable": True,
        }

    monkeypatch.setattr(app_module, "_test_model_link", fake_test_model_link)
    monkeypatch.setattr(app_module, "_fetch_tts_health", fake_fetch_tts_health)
    with TestClient(app_module.create_app()) as client:
        response = client.post(
            "/api/v1/model-config/models/test",
            json={
                "text_model": {
                    "base_url": "https://models.example.test/v1",
                    "model": "demo-model",
                },
                "tts": {"base_url": "http://127.0.0.1:7811"},
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["models"]["text_model"]["ok"] is True
    assert payload["models"]["tts"]["ok"] is True
    assert tested == {
        "text_model": "https://models.example.test/v1",
        "tts": "http://127.0.0.1:7811",
    }


def test_v0_5_models_test_reports_tts_model_api_failure_separately(monkeypatch):
    """TTS 模型 API 未就绪时，应区别于普通后端 API 连接失败。"""
    import backend.app.api.app as app_module

    async def fake_test_model_link(_config: dict[str, str]) -> None:
        return None

    monkeypatch.setattr(app_module, "_test_model_link", fake_test_model_link)
    monkeypatch.setattr(
        app_module,
        "_fetch_tts_health",
        lambda _base_url: {"reachable": False, "ready": False, "error": "connection refused"},
    )
    with TestClient(app_module.create_app()) as client:
        response = client.post(
            "/api/v1/model-config/models/test",
            json={
                "text_model": {
                    "base_url": "https://models.example.test/v1",
                    "model": "demo-model",
                },
                "tts": {"base_url": "http://127.0.0.1:7811"},
            },
        )

    assert response.status_code == 503
    assert "TTS模型 API 测试失败" in response.json()["detail"]


def test_v0_5_defaults_have_no_bundled_roles_or_voice_resources(monkeypatch):
    """v0.5.2 ships with empty role and voice libraries to avoid bundled copyrighted assets."""
    with _client(monkeypatch) as client:
        characters = client.get("/api/v1/characters")
        voices = client.get("/api/v1/voice-profiles")

    assert characters.status_code == 200
    assert characters.json()["roles"] == []
    assert characters.json()["role_options"] == []
    assert voices.status_code == 200
    assert voices.json()["voices"] == []


def test_v0_5_text_model_config_is_openai_compatible_and_uses_ephemeral_secret(
    monkeypatch,
    tmp_path,
):
    """Text model secrets are sent obfuscated once, kept only in memory, and never echoed."""
    monkeypatch.setenv("SHUYI_DATA_DIR", str(tmp_path))
    provider_secret = "sk-runtime-only"
    with _client(monkeypatch) as client:
        fetched = client.get("/api/v1/model-config")
        assert fetched.status_code == 200
        config = fetched.json()["config"]
        assert "text_model" in config
        assert "llm" not in config
        assert "chapter_agent" not in config
        assert config["text_model"]["has_api_key"] is False

        challenge = client.post(
            "/api/v1/model-config/secret-exchange",
            json={"byte_length": 128},
        )
        assert challenge.status_code == 200
        exchange = _encrypted_exchange(provider_secret, challenge.json())
        assert provider_secret not in str(exchange)

        configured = client.patch(
            "/api/v1/model-config",
            json={
                "text_model": {
                    "base_url": "https://models.example.test/v1",
                    "model": "openai-compatible-model",
                },
                "text_model_secret": exchange,
            },
        )
        assert configured.status_code == 200
        assert provider_secret not in configured.text
        assert configured.json()["config"]["text_model"]["has_api_key"] is True

    with _client(monkeypatch) as restarted:
        fetched_after_restart = restarted.get("/api/v1/model-config")

    assert fetched_after_restart.status_code == 200
    assert provider_secret not in fetched_after_restart.text
    assert fetched_after_restart.json()["config"]["text_model"]["has_api_key"] is False


def test_v0_5_readiness_returns_503_when_sqlite_ping_fails():
    """Readiness must degrade to 503 instead of leaking repository exceptions."""
    from backend.app.api.app import create_app

    app = create_app()

    def broken_ping() -> bool:
        raise sqlite3.OperationalError("database is locked")

    app.state.repository.ping = broken_ping
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["database"] == "not_ready"


def test_v0_5_legacy_environment_does_not_re_enable_old_api(monkeypatch):
    """服务只读取统一 SHUYI_* 配置；旧 /api 路径仍关闭，v1 不再需要访问令牌。"""
    legacy_prefix = "NOVEL" + "VOICE"
    monkeypatch.delenv("SHUYI_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("SHUYI_CORS_ORIGIN_REGEX", raising=False)
    monkeypatch.setenv(f"{legacy_prefix}_API_TOKEN", "legacy-token")
    monkeypatch.setenv(f"{legacy_prefix}_CORS_ORIGINS", ALLOWED_ORIGIN)
    from backend.app.api.app import create_app

    with TestClient(create_app()) as client:
        response = client.get("/api/v1/characters")
        assert response.status_code == 200
        cors = client.get("/api/v1/characters", headers={"Origin": ALLOWED_ORIGIN})
        assert cors.status_code == 200
        assert cors.headers["access-control-allow-origin"] == "*"
        assert client.get("/api/model-config").status_code == 404
        assert client.patch("/api/model-config", json={"llm": {"api_key": "secret"}}).status_code == 404


def test_v0_5_chapter_rule_cache_is_scoped_to_runtime_data_dir(monkeypatch, tmp_path):
    """Generated chapter rules must never target the application source tree."""
    monkeypatch.setenv("SHUYI_DATA_DIR", str(tmp_path))
    from backend.app.api.app import create_app

    app = create_app()

    assert app.state.chapter_rule_dir == tmp_path / "cache/chapter-rules"


def test_v0_5_business_api_is_versioned_and_public(monkeypatch):
    """Core business routes stay under /api/v1 but no longer require Bearer authentication."""
    with _client(monkeypatch) as client:
        assert client.get("/api/v1/characters").status_code == 200
        assert client.get("/api/v1/characters", headers={"Authorization": "Basic nope"}).status_code == 200
        assert client.get(
            "/api/v1/characters", headers={"Authorization": "Bearer wrong-token"}
        ).status_code == 200
        assert client.get("/api/characters").status_code == 404


def test_v0_5_all_business_routes_use_v1_without_auth(monkeypatch):
    """核心业务必须通过统一 v1 入口访问，旧入口不得旁路。"""
    with _client(monkeypatch) as client:
        payload = {"text": "第一章 开始\n正文"}
        parsed = client.post("/api/v1/books/parse", json=payload)
        assert parsed.status_code == 200
        assert parsed.json()["chapters"][0]["title"] == "第一章 开始"

        assert client.post("/api/v1/novels/parse", json=payload).status_code == 404
        assert client.post("/api/books/parse", json=payload).status_code == 404
        assert client.get("/api/model-config").status_code == 404
        assert client.get("/outputs/audio/missing.wav").status_code == 404


def test_v0_5_cors_allows_public_browser_preflight_without_workspace_whitelist(monkeypatch):
    """CNB forwarded domains are ephemeral, so public API CORS must not rely on a per-run whitelist."""
    with _client(monkeypatch) as client:
        for origin in (
            "https://plantingflowersrabbit.github.io",
            "https://ip3somvmrr-8000.cnb.run",
            "https://attacker.example.test",
        ):
            response = client.options(
                "/api/v1/characters",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "content-type,x-custom-header",
                },
            )
            assert response.status_code in {200, 204}
            assert response.headers["access-control-allow-origin"] == "*"
            assert response.headers["access-control-allow-methods"] == "*"
            assert response.headers["access-control-allow-headers"] == "*"
            assert response.headers["access-control-allow-credentials"] == "false"


def test_v0_5_cors_environment_cannot_break_pages_to_cnb_preflight(monkeypatch):
    monkeypatch.setenv("SHUYI_CORS_ORIGINS", "https://old.example.test")
    monkeypatch.setenv("SHUYI_CORS_ORIGIN_REGEX", r"https://old-[0-9]+\.example\.test")
    from backend.app.api.app import create_app

    with TestClient(create_app()) as client:
        allowed = client.options(
            "/api/v1/connection-test",
            headers={
                "Origin": "https://faho62u6pf-8000.cnb.run",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert allowed.status_code in {200, 204}
        assert allowed.headers["access-control-allow-origin"] == "*"


def test_v0_5_role_crud_and_model_config_use_public_v1_routes(monkeypatch):
    """角色写操作和配置保存不能被 v1 路由代理破坏。"""
    with _client(monkeypatch) as client:
        created = client.post(
            "/api/v1/characters",
            json={
                "role_id": "heroine",
                "name": "女主角",
                "description": "冷静果断",
                "voice_mode": "voice_design",
                "design_prompt": "冷静、清晰、果断",
            },
        )
        assert created.status_code == 200
        updated = client.patch("/api/v1/characters/heroine", json={"name": "女主角改"})
        assert updated.status_code == 200
        assert updated.json()["role"]["name"] == "女主角改"

        configured = client.patch(
            "/api/v1/model-config",
            json={"text_model": {"model": "new-model", "api_key": "must-not-be-stored"}},
        )
        assert configured.status_code == 200
        assert configured.json()["config"]["text_model"]["model"] == "new-model"
        assert '"api_key":' not in configured.text
        assert "must-not-be-stored" not in configured.text


def test_v0_5_role_delete_reports_references_and_unbinds_on_explicit_action(monkeypatch):
    """Deleting a referenced role first reports the conflict, then unbinds and deletes on confirmation."""
    utterances = {
        "p-001": [
            {
                "utterance_id": "u-001",
                "paragraph_id": "p-001",
                "text": "她说了一句话。",
                "speaker_name": "女主角",
                "speaker_role_id": "heroine",
                "role_id": "heroine",
                "audio_status": "尚未生成",
                "needs_human_review": False,
            }
        ]
    }
    payload = {"utterances_by_paragraph": utterances}
    with _client(monkeypatch) as client:
        created = client.post(
            "/api/v1/characters",
            json={
                "role_id": "heroine",
                "name": "女主角",
                "description": "冷静果断",
                "voice_mode": "voice_design",
            },
        )
        assert created.status_code == 200

        blocked = client.request("DELETE", "/api/v1/characters/heroine", json=payload)
        assert blocked.status_code == 409
        detail = blocked.json()["detail"]
        assert detail["delete_result"]["referenced_count"] == 1
        assert detail["delete_result"]["deleted"] is False
        assert detail["roles"][0]["role_id"] == "heroine"

        deleted = client.request(
            "DELETE",
            "/api/v1/characters/heroine",
            json={**payload, "action": "unbind"},
        )
        assert deleted.status_code == 200
        body = deleted.json()
        assert body["roles"] == []
        unbound = body["utterances_by_paragraph"]["p-001"][0]
        assert unbound["speaker_role_id"] is None
        assert unbound["role_id"] is None


def test_v0_5_sqlite_restores_business_state_after_restart(monkeypatch, tmp_path):
    """SQLite WAL 快照必须在应用重建后恢复小说章节。"""
    monkeypatch.setenv("SHUYI_DATA_DIR", str(tmp_path))
    payload = {"text": "第一章 重启前\n这是一段正文。"}

    with _client(monkeypatch) as client:
        created = client.post("/api/v1/books/parse", json=payload)
        assert created.status_code == 200

    with _client(monkeypatch) as restarted:
        chapters = restarted.get("/api/v1/chapters")
        assert chapters.status_code == 200
        assert chapters.json()["chapters"][0]["title"] == "第一章 重启前"


def test_v0_5_generated_audio_uses_public_download_route(monkeypatch):
    """生成音频不得返回 outputs 路径或宿主机绝对路径，下载路由随公开 API 一起开放。"""
    from backend.app.domain.audio import TTSServiceError

    def unavailable_tts(*_args, **_kwargs):
        raise TTSServiceError("测试中不启动 TTS")

    monkeypatch.setattr("backend.app.api.app.synthesize_local_qwen3", unavailable_tts)
    with _client(monkeypatch) as client:
        role = client.post(
            "/api/v1/characters",
            json={
                "role_id": "narrator",
                "name": "旁白",
                "description": "测试旁白",
                "voice_mode": "voice_cloning",
                "reference_audio_path": "assets/samples/voices/cmn_qixinxieli_canonni_cc0.wav",
                "reference_text": "测试参考文本。",
                "design_prompt": None,
            },
        )
        assert role.status_code == 200
        response = client.post(
            "/api/v1/dubbing-segments/u-001/dubbing-jobs",
            json={"role_id": "narrator", "text": "测试配音。"},
        )
        assert response.status_code == 200
        audio_url = response.json()["audio_url"]
        assert audio_url.startswith("/api/v1/downloads/audio/")
        downloaded = client.get(audio_url)
        assert downloaded.status_code == 200
        assert downloaded.headers["content-type"].startswith("audio/")


def test_v0_5_tts_download_and_deploy_runs_as_background_job(monkeypatch, tmp_path):
    """下载并部署按钮应启动后台任务，并在运行中重复点击时复用同一个任务。"""
    import backend.app.api.app as app_module

    monkeypatch.setenv("SHUYI_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SHUYI_MODEL_DIR", str(tmp_path / "models"))
    release_download = threading.Event()
    download_started = threading.Event()
    downloaded_targets: list[Path] = []

    def fake_ensure_model(spec):
        download_started.set()
        assert release_download.wait(1), "test did not release fake download"
        downloaded_targets.append(spec.target)
        spec.target.mkdir(parents=True, exist_ok=True)
        (spec.target / "config.json").write_text("{}", encoding="utf-8")
        return "downloaded"

    class FakeProcess:
        pid = 4242

        def poll(self):
            return None

    monkeypatch.setattr(app_module, "ensure_model", fake_ensure_model, raising=False)
    monkeypatch.setattr(app_module, "_fetch_tts_health", lambda _base_url: {"reachable": False, "ready": False})
    monkeypatch.setattr(app_module, "_start_tts_process", lambda _command: FakeProcess())
    monkeypatch.setattr(
        app_module,
        "_wait_for_tts_ready",
        lambda _process, _base_url, _timeout_seconds=None: {
            "ok": True,
            "voice_clone": True,
            "voice_design": True,
            "voice_design_capable": True,
        },
    )

    with TestClient(app_module.create_app()) as client:
        first = client.post("/api/v1/model-config/tts/deploy", json={"tts": {}})
        assert first.status_code == 202
        assert download_started.wait(1)

        duplicate = client.post("/api/v1/model-config/tts/deploy", json={"tts": {}})
        assert duplicate.status_code == 202
        assert duplicate.json()["deployment"]["status"] == "running"
        assert duplicate.json()["deployment"]["progress"] < 100

        release_download.set()
        completed = _wait_for_deployment(client, "succeeded")

    assert completed["progress"] == 100
    assert completed["pid"] == 4242
    assert [target.name for target in downloaded_targets] == [
        "Qwen3-TTS-12Hz-1.7B-Base",
        "Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    ]


def test_v0_5_tts_deploy_can_retry_after_downloaded_models_fail_to_start(monkeypatch, tmp_path):
    """模型下载完成但部署失败时，状态应反馈失败，下一次点击可重新尝试部署。"""
    import backend.app.api.app as app_module

    monkeypatch.setenv("SHUYI_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SHUYI_MODEL_DIR", str(tmp_path / "models"))
    start_calls = 0

    def fake_ensure_model(spec):
        spec.target.mkdir(parents=True, exist_ok=True)
        (spec.target / "config.json").write_text("{}", encoding="utf-8")
        return "cached"

    class FakeProcess:
        pid = 5252

        def poll(self):
            return None

    def flaky_start(_command):
        nonlocal start_calls
        start_calls += 1
        if start_calls == 1:
            raise RuntimeError("boom")
        return FakeProcess()

    monkeypatch.setattr(app_module, "ensure_model", fake_ensure_model, raising=False)
    monkeypatch.setattr(app_module, "_fetch_tts_health", lambda _base_url: {"reachable": False, "ready": False})
    monkeypatch.setattr(app_module, "_start_tts_process", flaky_start)
    monkeypatch.setattr(
        app_module,
        "_wait_for_tts_ready",
        lambda _process, _base_url, _timeout_seconds=None: {
            "ok": True,
            "voice_clone": True,
            "voice_design": True,
            "voice_design_capable": True,
        },
    )

    with TestClient(app_module.create_app()) as client:
        first = client.post("/api/v1/model-config/tts/deploy", json={"tts": {}})
        assert first.status_code == 202
        failed = _wait_for_deployment(client, "failed")
        assert failed["stage"] == "deploying"
        assert "模型下载已完成，但部署失败" in failed["message"]
        assert failed["can_retry"] is True

        retry = client.post("/api/v1/model-config/tts/deploy", json={"tts": {}})
        assert retry.status_code == 202
        completed = _wait_for_deployment(client, "succeeded")

    assert completed["pid"] == 5252
    assert start_calls == 2


def test_v0_5_provider_keys_are_environment_only_and_never_echoed(monkeypatch):
    """Provider secrets stay server-side and are redacted from configuration reads."""
    provider_secret = "provider-secret-must-not-be-returned"
    monkeypatch.setenv("SHUYI_TEXT_MODEL_API_KEY", provider_secret)
    with _client(monkeypatch) as client:
        fetched = client.get("/api/v1/model-config")
        assert fetched.status_code == 200
        assert provider_secret not in fetched.text
        text_model = fetched.json()["config"]["text_model"]
        assert "api_key" not in text_model
        assert text_model.get("has_api_key") is True
