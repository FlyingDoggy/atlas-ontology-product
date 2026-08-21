from __future__ import annotations

import json

from fastapi.testclient import TestClient

from ontology_agent.demo_auth import (
    AuthSettings,
    DemoAuthService,
    SESSION_COOKIE,
    create_auth_app,
    derive_password_hash,
)


def settings(**changes: object) -> AuthSettings:
    values: dict[str, object] = {
        "username": "atlas-demo",
        "password_hash": derive_password_hash(
            "correct horse battery staple", salt=b"0123456789abcdef"
        ),
        "session_secret": b"test-session-secret-with-at-least-32-bytes",
        "session_ttl_seconds": 3600,
        "secure_cookie": True,
        "max_failed_attempts": 2,
        "attempt_window_seconds": 60,
    }
    values.update(changes)
    return AuthSettings(**values)  # type: ignore[arg-type]


def test_health_is_public_but_readiness_requires_configuration(monkeypatch) -> None:
    for name in (
        "ONTOLOGY_AUTH_USERNAME",
        "ONTOLOGY_AUTH_PASSWORD_HASH",
        "ONTOLOGY_AUTH_SESSION_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)
    client = TestClient(create_auth_app())

    assert client.get("/auth/healthz").status_code == 200
    ready = client.get("/auth/readyz")
    assert ready.status_code == 503
    assert ready.json() == {"detail": "Authentication service is not configured"}


def test_login_issues_secure_http_only_session_and_logout_expires_it() -> None:
    client = TestClient(create_auth_app(settings()), base_url="https://testserver")

    assert client.get("/auth/session").json() == {"authenticated": False}
    rejected = client.post(
        "/auth/login",
        json={"username": "atlas-demo", "password": "wrong"},
    )
    assert rejected.status_code == 401
    assert SESSION_COOKIE not in client.cookies

    accepted = client.post(
        "/auth/login",
        json={
            "username": "atlas-demo",
            "password": "correct horse battery staple",
        },
    )
    assert accepted.status_code == 200
    assert accepted.json()["authenticated"] is True
    assert accepted.json()["role"] == "operator"
    cookie = accepted.headers["set-cookie"]
    assert f"{SESSION_COOKIE}=" in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/" in cookie

    assert client.get("/auth/session").json()["username"] == "atlas-demo"
    assert client.get("/auth/session").json()["role"] == "operator"
    verified = client.get("/auth/verify")
    assert verified.status_code == 204
    assert verified.headers["x-atlas-user"] == "atlas-demo"
    assert verified.headers["x-atlas-role"] == "operator"

    logged_out = client.post("/auth/logout")
    assert logged_out.status_code == 200
    assert logged_out.json() == {"authenticated": False}
    assert client.get("/auth/session").json() == {"authenticated": False}


def test_login_is_closed_to_extra_fields_cross_site_posts_and_rate_bypass() -> None:
    client = TestClient(create_auth_app(settings()), base_url="https://testserver")

    extra = client.post(
        "/auth/login",
        json={"username": "atlas-demo", "password": "wrong", "next": "https://evil.test"},
    )
    assert extra.status_code == 422

    cross_site = client.post(
        "/auth/login",
        headers={"Sec-Fetch-Site": "cross-site"},
        json={"username": "atlas-demo", "password": "correct horse battery staple"},
    )
    assert cross_site.status_code == 403

    for password in ("wrong-1", "wrong-2"):
        assert client.post(
            "/auth/login",
            headers={"X-Forwarded-For": "203.0.113.8"},
            json={"username": "atlas-demo", "password": password},
        ).status_code == 401
    blocked = client.post(
        "/auth/login",
        headers={"X-Forwarded-For": "203.0.113.8"},
        json={"username": "atlas-demo", "password": "correct horse battery staple"},
    )
    assert blocked.status_code == 429


def test_tampered_expired_and_future_sessions_fail_closed() -> None:
    now = 2_000_000_000
    configured = settings()
    auth = DemoAuthService(configured, clock=lambda: float(now))
    client = TestClient(create_auth_app(configured, clock=lambda: float(now)), base_url="https://testserver")

    token = auth.issue_session(now=now)
    encoded, signature = token.split(".")
    tampered = f"{encoded[:-1]}A.{signature}"
    client.cookies.set(SESSION_COOKIE, tampered)
    assert client.get("/auth/verify").status_code == 401

    expired = auth.issue_session(now=now - configured.session_ttl_seconds)
    client.cookies.set(SESSION_COOKIE, expired)
    assert client.get("/auth/verify").status_code == 401

    future = auth.issue_session(now=now + 61)
    client.cookies.set(SESSION_COOKIE, future)
    assert client.get("/auth/verify").status_code == 401

    payload_text, _ = token.split(".")
    payload = json.loads(
        __import__("base64").urlsafe_b64decode(payload_text + "=" * (-len(payload_text) % 4))
    )
    assert payload["sub"] == "atlas-demo"
    assert payload["role"] == "operator"
    assert payload["v"] == 2
    assert "correct horse battery staple" not in token


def test_viewer_can_read_but_product_mutations_require_operator() -> None:
    configured = settings(
        viewer_username="atlas-viewer",
        viewer_password_hash=derive_password_hash(
            "viewer password", salt=b"fedcba9876543210"
        ),
    )
    viewer = TestClient(create_auth_app(configured), base_url="https://testserver")
    accepted = viewer.post(
        "/auth/login",
        json={"username": "atlas-viewer", "password": "viewer password"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["role"] == "viewer"
    assert viewer.get("/auth/verify-product", headers={"X-Original-Method": "GET"}).status_code == 204
    forbidden = viewer.get(
        "/auth/verify-product", headers={"X-Original-Method": "POST"}
    )
    assert forbidden.status_code == 403
    assert viewer.get("/auth/verify-operator").status_code == 403

    operator = TestClient(create_auth_app(configured), base_url="https://testserver")
    assert operator.post(
        "/auth/login",
        json={
            "username": "atlas-demo",
            "password": "correct horse battery staple",
        },
    ).status_code == 200
    assert operator.get(
        "/auth/verify-product", headers={"X-Original-Method": "DELETE"}
    ).status_code == 204
