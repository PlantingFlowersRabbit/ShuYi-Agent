from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

API_TOKEN = "contract-test-bearer-token"
ALLOWED_ORIGIN = "https://shuyi.example.test"


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("SHUYI_API_TOKEN", API_TOKEN)
    monkeypatch.setenv("SHUYI_CORS_ORIGINS", ALLOWED_ORIGIN)
    from backend.app.api.app import create_app

    return TestClient(create_app())


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {API_TOKEN}"}


def test_v0_4_health_probes_are_public_and_report_release(monkeypatch):
    """Covers v0.4 unauthenticated liveness, startup, and readiness probes."""
    with _client(monkeypatch) as client:
        for path in ("/health/live", "/health/startup", "/health/ready"):
            response = client.get(path)
            assert response.status_code == 200, path
            payload = response.json()
            assert payload["status"] == "ok"
            assert payload["service"] == "shuyi-agent"
            assert payload["version"] == "0.4.0"


def test_v0_4_readiness_returns_503_when_sqlite_ping_fails(monkeypatch):
    """Readiness must degrade to 503 instead of leaking repository exceptions."""
    monkeypatch.setenv("SHUYI_API_TOKEN", API_TOKEN)
    from backend.app.api.app import create_app

    app = create_app()

    def broken_ping() -> bool:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(app.state.repository, "ping", broken_ping)
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["database"] == "not_ready"


def test_v0_4_shuyi_environment_is_required(monkeypatch):
    """服务只读取统一的 SHUYI_* 环境变量。"""
    legacy_prefix = "NOVEL" + "VOICE"
    monkeypatch.delenv("SHUYI_API_TOKEN", raising=False)
    monkeypatch.delenv("SHUYI_CORS_ORIGINS", raising=False)
    monkeypatch.setenv(f"{legacy_prefix}_API_TOKEN", API_TOKEN)
    monkeypatch.setenv(f"{legacy_prefix}_CORS_ORIGINS", ALLOWED_ORIGIN)
    from backend.app.api.app import create_app

    with TestClient(create_app()) as client:
        response = client.get("/api/v1/characters", headers=_auth())
        assert response.status_code == 401
        cors = client.get("/api/v1/characters", headers={"Origin": ALLOWED_ORIGIN})
        assert cors.status_code == 401
        assert "access-control-allow-origin" not in cors.headers


def test_v0_4_chapter_rule_cache_is_scoped_to_runtime_data_dir(monkeypatch, tmp_path):
    """Generated chapter rules must never target the application source tree."""
    monkeypatch.setenv("SHUYI_DATA_DIR", str(tmp_path))
    from backend.app.api.app import create_app

    app = create_app()

    assert app.state.chapter_rule_dir == tmp_path / "cache/chapter-rules"


def test_v0_4_business_api_is_versioned_and_requires_bearer_auth(monkeypatch):
    """Covers v0.4 /api/v1 routing and Bearer authentication."""
    with _client(monkeypatch) as client:
        assert client.get("/api/v1/characters").status_code == 401
        assert (
            client.get("/api/v1/characters", headers={"Authorization": "Basic nope"}).status_code
            == 401
        )
        assert client.get(
            "/api/v1/characters", headers={"Authorization": "Bearer wrong-token"}
        ).status_code in {401, 403}
        assert client.get("/api/v1/characters", headers=_auth()).status_code == 200
        assert client.get("/api/characters", headers=_auth()).status_code == 404


def test_v0_4_legacy_api_is_closed_even_when_token_is_not_configured(monkeypatch):
    """未配置访问令牌时也不能重新开放旧接口。"""
    monkeypatch.delenv("SHUYI_API_TOKEN", raising=False)
    from backend.app.api.app import create_app

    with TestClient(create_app()) as client:
        assert client.get("/api/model-config").status_code == 404
        assert (
            client.patch("/api/model-config", json={"llm": {"api_key": "secret"}}).status_code
            == 404
        )
        assert client.get("/api/v1/model-config").status_code == 401


def test_v0_4_all_business_routes_use_v1_and_bearer_auth(monkeypatch):
    """核心业务必须通过统一 v1 鉴权入口访问，旧入口不得旁路。"""
    with _client(monkeypatch) as client:
        payload = {"text": "第一章 开始\n正文"}
        assert client.post("/api/v1/books/parse", json=payload).status_code == 401
        parsed = client.post("/api/v1/books/parse", headers=_auth(), json=payload)
        assert parsed.status_code == 200
        assert parsed.json()["chapters"][0]["title"] == "第一章 开始"

        assert client.post("/api/v1/novels/parse", headers=_auth(), json=payload).status_code == 404
        assert client.post("/api/books/parse", headers=_auth(), json=payload).status_code == 404
        assert client.get("/api/model-config", headers=_auth()).status_code == 404
        assert client.get("/outputs/audio/missing.wav", headers=_auth()).status_code == 404


def test_v0_4_cors_allows_only_configured_browser_origin(monkeypatch):
    """Covers v0.4 browser CORS preflight without broad wildcard access."""
    with _client(monkeypatch) as client:
        allowed = client.options(
            "/api/v1/characters",
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        assert allowed.status_code in {200, 204}
        assert allowed.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
        assert "authorization" in allowed.headers["access-control-allow-headers"].lower()

        rejected = client.options(
            "/api/v1/characters",
            headers={
                "Origin": "https://attacker.example.test",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert rejected.headers.get("access-control-allow-origin") is None


def test_v0_4_authentication_errors_keep_cors_headers(monkeypatch):
    """浏览器必须能读取允许来源上的中文鉴权错误。"""
    with _client(monkeypatch) as client:
        response = client.get("/api/v1/characters", headers={"Origin": ALLOWED_ORIGIN})

    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert response.json()["detail"] == "需要访问令牌"


def test_v0_4_role_crud_and_model_config_use_authenticated_v1_routes(monkeypatch):
    """角色写操作和配置保存不能被 v1 路由代理破坏。"""
    with _client(monkeypatch) as client:
        created = client.post(
            "/api/v1/characters",
            headers=_auth(),
            json={
                "role_id": "heroine",
                "name": "女主角",
                "description": "冷静果断",
                "voice_resource_id": "voice-yujie",
            },
        )
        assert created.status_code == 200
        updated = client.patch(
            "/api/v1/characters/heroine",
            headers=_auth(),
            json={"name": "女主角改"},
        )
        assert updated.status_code == 200
        assert updated.json()["role"]["name"] == "女主角改"

        configured = client.patch(
            "/api/v1/model-config",
            headers=_auth(),
            json={"llm": {"model": "new-model", "api_key": "must-not-be-stored"}},
        )
        assert configured.status_code == 200
        assert configured.json()["config"]["llm"]["model"] == "new-model"
        assert '"api_key":' not in configured.text
        assert "must-not-be-stored" not in configured.text


def test_v0_4_sqlite_restores_business_state_after_restart(monkeypatch, tmp_path):
    """SQLite WAL 快照必须在应用重建后恢复小说章节。"""
    monkeypatch.setenv("SHUYI_DATA_DIR", str(tmp_path))
    payload = {"text": "第一章 重启前\n这是一段正文。"}

    with _client(monkeypatch) as client:
        created = client.post("/api/v1/books/parse", headers=_auth(), json=payload)
        assert created.status_code == 200

    with _client(monkeypatch) as restarted:
        chapters = restarted.get("/api/v1/chapters", headers=_auth())
        assert chapters.status_code == 200
        assert chapters.json()["chapters"][0]["title"] == "第一章 重启前"


def test_v0_4_generated_audio_uses_authenticated_download_route(monkeypatch):
    """生成音频不得返回公开 outputs 路径或宿主机绝对路径。"""
    from backend.app.domain.audio import TTSServiceError

    def unavailable_tts(*_args, **_kwargs):
        raise TTSServiceError("测试中不启动 TTS")

    monkeypatch.setattr("backend.app.api.app.synthesize_local_qwen3", unavailable_tts)
    with _client(monkeypatch) as client:
        response = client.post(
            "/api/v1/dubbing-segments/u-001/dubbing-jobs",
            headers=_auth(),
            json={"role_id": "narrator", "text": "测试配音。"},
        )
        assert response.status_code == 200
        audio_url = response.json()["audio_url"]
        assert audio_url.startswith("/api/v1/downloads/audio/")
        assert client.get(audio_url).status_code == 401
        downloaded = client.get(audio_url, headers=_auth())
        assert downloaded.status_code == 200
        assert downloaded.headers["content-type"].startswith("audio/")


def test_v0_4_provider_keys_are_environment_only_and_never_echoed(monkeypatch):
    """Covers v0.4 environment-only provider secrets and redacted configuration reads."""
    provider_secret = "provider-secret-must-not-be-returned"
    monkeypatch.setenv("SILICONFLOW_API_KEY", provider_secret)
    with _client(monkeypatch) as client:
        fetched = client.get("/api/v1/model-config", headers=_auth())
        assert fetched.status_code == 200
        assert provider_secret not in fetched.text
        assert API_TOKEN not in fetched.text
        llm = fetched.json()["config"]["llm"]
        assert "api_key" not in llm
        assert llm.get("has_api_key") is True
