from __future__ import annotations

from fastapi.testclient import TestClient

API_TOKEN = "contract-test-bearer-token"
ALLOWED_ORIGIN = "https://shuyi.example.test"


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("NOVELVOICE_API_TOKEN", API_TOKEN)
    monkeypatch.setenv("NOVELVOICE_CORS_ORIGINS", ALLOWED_ORIGIN)
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
