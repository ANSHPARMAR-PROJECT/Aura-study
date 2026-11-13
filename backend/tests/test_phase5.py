"""Phase 5 security, operational health, and rate-limit checks."""
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test_phase5.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file.as_posix()}")
    monkeypatch.setenv("FLASK_SECRET_KEY", "phase5-test-secret-key-at-least-32-bytes-long")
    monkeypatch.setenv("AUTO_CREATE_DB", "true")
    import app as aura_app
    from database import Base, engine, init_db
    Base.metadata.drop_all(bind=engine)
    init_db()
    aura_app.app.config.update(TESTING=True)
    with aura_app.app.test_client() as test_client:
        yield test_client
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_health_endpoint_is_public_and_returns_operational_status(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "service": "aura-study"}
    assert response.headers.get("X-Request-ID")


def test_security_headers_are_set_on_api_responses(client):
    response = client.get("/api/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert "object-src 'none'" in response.headers["Content-Security-Policy"]
    assert "fonts.googleapis.com" in response.headers["Content-Security-Policy"]
    assert "frame-ancestors 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_login_is_rate_limited_and_returns_retry_after(client):
    for _ in range(8):
        response = client.post("/api/login", json={"identifier": "nobody", "password": "wrong-password"})
        assert response.status_code == 401
    limited = client.post("/api/login", json={"identifier": "nobody", "password": "wrong-password"})
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) > 0
    assert "Too many requests" in limited.get_json()["error"]


def test_unknown_api_routes_return_json_not_html(client):
    response = client.get("/api/not-a-real-route")
    assert response.status_code == 404
    assert response.is_json
    assert "error" in response.get_json()
