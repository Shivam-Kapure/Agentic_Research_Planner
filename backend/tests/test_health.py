from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_client(**overrides) -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, **overrides)))


def test_health_returns_ok_and_version():
    response = make_client(app_env="test").get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["env"] == "test"
    assert body["version"]


def test_cors_allows_only_configured_origin():
    client = make_client(cors_allowed_origins="https://app.example.com")

    allowed = client.get("/health", headers={"Origin": "https://app.example.com"})
    blocked = client.get("/health", headers={"Origin": "https://evil.example.com"})

    assert allowed.headers.get("access-control-allow-origin") == "https://app.example.com"
    assert "access-control-allow-origin" not in blocked.headers


def test_settings_parses_comma_separated_origins():
    settings = Settings(_env_file=None, cors_allowed_origins="http://a.com, http://b.com ,")

    assert settings.cors_origins == ["http://a.com", "http://b.com"]
