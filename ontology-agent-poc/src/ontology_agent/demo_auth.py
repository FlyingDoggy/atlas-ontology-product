from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Callable

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field


PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 600_000
SESSION_COOKIE = "atlas_demo_session"
_USERNAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_NONCE = re.compile(r"[A-Za-z0-9_-]{12,64}")


class AuthConfigurationError(RuntimeError):
    pass


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    if not value or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("Invalid base64url value")
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def derive_password_hash(
    password: str,
    *,
    salt: bytes | None = None,
    iterations: int = PASSWORD_ITERATIONS,
) -> str:
    """Create the deploy-time password verifier; never call this in a browser."""
    if not password or len(password) > 512:
        raise ValueError("Password length is invalid")
    if iterations < 210_000:
        raise ValueError("PBKDF2 work factor is too low")
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), actual_salt, iterations
    )
    return "$".join(
        (PASSWORD_SCHEME, str(iterations), _b64encode(actual_salt), _b64encode(digest))
    )


@dataclass(frozen=True)
class PasswordVerifier:
    iterations: int
    salt: bytes
    digest: bytes

    @classmethod
    def parse(cls, value: str) -> PasswordVerifier:
        try:
            scheme, iterations_text, salt_text, digest_text = value.split("$")
            iterations = int(iterations_text)
            salt = _b64decode(salt_text)
            digest = _b64decode(digest_text)
        except (TypeError, ValueError) as exc:
            raise AuthConfigurationError("Password verifier is malformed") from exc
        if scheme != PASSWORD_SCHEME or iterations < 210_000:
            raise AuthConfigurationError("Password verifier scheme is unsupported")
        if not 16 <= len(salt) <= 64 or len(digest) != 32:
            raise AuthConfigurationError("Password verifier material is invalid")
        return cls(iterations=iterations, salt=salt, digest=digest)

    def verify(self, password: str) -> bool:
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), self.salt, self.iterations
        )
        return hmac.compare_digest(candidate, self.digest)


@dataclass(frozen=True)
class AuthSettings:
    username: str
    password_hash: str
    session_secret: bytes
    viewer_username: str | None = None
    viewer_password_hash: str | None = None
    session_ttl_seconds: int = 28_800
    secure_cookie: bool = True
    max_failed_attempts: int = 8
    attempt_window_seconds: int = 300

    def __post_init__(self) -> None:
        if not _USERNAME.fullmatch(self.username):
            raise AuthConfigurationError("Demo username is invalid")
        PasswordVerifier.parse(self.password_hash)
        if (self.viewer_username is None) != (self.viewer_password_hash is None):
            raise AuthConfigurationError("Viewer username and verifier must be configured together")
        if self.viewer_username is not None:
            if not _USERNAME.fullmatch(self.viewer_username):
                raise AuthConfigurationError("Viewer username is invalid")
            if hmac.compare_digest(self.viewer_username, self.username):
                raise AuthConfigurationError("Operator and viewer usernames must differ")
            PasswordVerifier.parse(self.viewer_password_hash or "")
        if len(self.session_secret) < 32:
            raise AuthConfigurationError("Session signing secret is too short")
        if not 300 <= self.session_ttl_seconds <= 86_400:
            raise AuthConfigurationError("Session lifetime is outside the supported range")
        if not 1 <= self.max_failed_attempts <= 100:
            raise AuthConfigurationError("Login attempt limit is invalid")
        if not 30 <= self.attempt_window_seconds <= 3600:
            raise AuthConfigurationError("Login attempt window is invalid")

    @classmethod
    def from_env(cls) -> AuthSettings:
        username = os.environ.get("ONTOLOGY_AUTH_USERNAME", "")
        password_hash = os.environ.get("ONTOLOGY_AUTH_PASSWORD_HASH", "")
        session_secret = os.environ.get("ONTOLOGY_AUTH_SESSION_SECRET", "").encode(
            "utf-8"
        )
        secure_text = os.environ.get("ONTOLOGY_AUTH_SECURE_COOKIE", "true").lower()
        if secure_text not in {"true", "false"}:
            raise AuthConfigurationError("Secure-cookie flag must be true or false")
        try:
            return cls(
                username=username,
                password_hash=password_hash,
                session_secret=session_secret,
                viewer_username=os.environ.get("ONTOLOGY_AUTH_VIEWER_USERNAME") or None,
                viewer_password_hash=os.environ.get("ONTOLOGY_AUTH_VIEWER_PASSWORD_HASH") or None,
                session_ttl_seconds=int(
                    os.environ.get("ONTOLOGY_AUTH_SESSION_TTL_SECONDS", "28800")
                ),
                secure_cookie=secure_text == "true",
                max_failed_attempts=int(
                    os.environ.get("ONTOLOGY_AUTH_MAX_FAILED_ATTEMPTS", "8")
                ),
                attempt_window_seconds=int(
                    os.environ.get("ONTOLOGY_AUTH_ATTEMPT_WINDOW_SECONDS", "300")
                ),
            )
        except ValueError as exc:
            raise AuthConfigurationError("Numeric authentication setting is invalid") from exc


class AttemptLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, values: deque[float], now: float) -> None:
        threshold = now - self.window_seconds
        while values and values[0] <= threshold:
            values.popleft()

    def blocked(self, key: str, now: float) -> bool:
        with self._lock:
            values = self._attempts[key]
            self._prune(values, now)
            return len(values) >= self.limit

    def fail(self, key: str, now: float) -> None:
        with self._lock:
            values = self._attempts[key]
            self._prune(values, now)
            values.append(now)

    def clear(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)


class DemoAuthService:
    def __init__(
        self,
        settings: AuthSettings,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.settings = settings
        self.password = PasswordVerifier.parse(settings.password_hash)
        self.principals: dict[str, tuple[PasswordVerifier, str]] = {
            settings.username: (self.password, "operator")
        }
        if settings.viewer_username and settings.viewer_password_hash:
            self.principals[settings.viewer_username] = (
                PasswordVerifier.parse(settings.viewer_password_hash),
                "viewer",
            )
        self.clock = clock
        self.attempts = AttemptLimiter(
            settings.max_failed_attempts, settings.attempt_window_seconds
        )

    def authenticate(self, username: str, password: str, client_key: str) -> str:
        now = self.clock()
        attempt_key = f"{client_key}:{username[:64]}"
        if self.attempts.blocked(attempt_key, now):
            raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
        matched_username: str | None = None
        matched_role: str | None = None
        valid_password = False
        for configured_username, (verifier, role) in self.principals.items():
            password_matches = verifier.verify(password)
            if hmac.compare_digest(username, configured_username) and password_matches:
                matched_username = configured_username
                matched_role = role
                valid_password = True
        if not valid_password or matched_username is None or matched_role is None:
            self.attempts.fail(attempt_key, now)
            raise HTTPException(status_code=401, detail="Invalid username or password")
        self.attempts.clear(attempt_key)
        return self.issue_session(
            now=int(now), username=matched_username, role=matched_role
        )

    def issue_session(
        self,
        *,
        now: int | None = None,
        username: str | None = None,
        role: str = "operator",
    ) -> str:
        issued_at = int(self.clock()) if now is None else now
        subject = username or self.settings.username
        configured = self.principals.get(subject)
        if configured is None or configured[1] != role:
            raise ValueError("Unknown authentication principal or role")
        payload = {
            "v": 2,
            "sub": subject,
            "role": role,
            "iat": issued_at,
            "exp": issued_at + self.settings.session_ttl_seconds,
            "nonce": secrets.token_urlsafe(12),
        }
        encoded = _b64encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        signature = hmac.new(
            self.settings.session_secret, encoded.encode("ascii"), hashlib.sha256
        ).digest()
        return f"{encoded}.{_b64encode(signature)}"

    def verify_session(self, token: str | None) -> dict[str, int | str]:
        try:
            encoded, signature_text = (token or "").split(".")
            signature = _b64decode(signature_text)
            expected = hmac.new(
                self.settings.session_secret, encoded.encode("ascii"), hashlib.sha256
            ).digest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError("Signature mismatch")
            payload = json.loads(_b64decode(encoded))
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=401, detail="Authentication required") from exc
        if not isinstance(payload, dict) or set(payload) != {
            "v",
            "sub",
            "iat",
            "exp",
            "nonce",
            "role",
        }:
            raise HTTPException(status_code=401, detail="Authentication required")
        issued_at = payload.get("iat")
        expires_at = payload.get("exp")
        if (
            payload.get("v") != 2
            or payload.get("sub") not in self.principals
            or payload.get("role") not in {"operator", "viewer"}
            or self.principals[str(payload.get("sub"))][1] != payload.get("role")
            or isinstance(issued_at, bool)
            or not isinstance(issued_at, int)
            or isinstance(expires_at, bool)
            or not isinstance(expires_at, int)
            or not isinstance(payload.get("nonce"), str)
            or not _NONCE.fullmatch(payload["nonce"])
        ):
            raise HTTPException(status_code=401, detail="Authentication required")
        now = int(self.clock())
        if (
            issued_at > now + 60
            or expires_at <= now
            or expires_at - issued_at != self.settings.session_ttl_seconds
        ):
            raise HTTPException(status_code=401, detail="Authentication required")
        return payload


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=512)


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    if forwarded:
        return forwarded[:128]
    return request.client.host[:128] if request.client else "unknown"


def _reject_cross_site_post(request: Request) -> None:
    if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        raise HTTPException(status_code=403, detail="Cross-site request is not allowed")


def create_auth_app(
    settings: AuthSettings | None = None,
    *,
    clock: Callable[[], float] = time.time,
) -> FastAPI:
    application = FastAPI(
        title="Atlas Access Gateway",
        version="1.0",
        description="Shared authenticated access gateway with viewer and operator roles.",
    )
    service = DemoAuthService(settings, clock=clock) if settings else None
    service_lock = threading.Lock()

    def configured_service() -> DemoAuthService:
        nonlocal service
        if service is None:
            with service_lock:
                if service is None:
                    try:
                        service = DemoAuthService(AuthSettings.from_env(), clock=clock)
                    except AuthConfigurationError as exc:
                        raise HTTPException(
                            status_code=503, detail="Authentication service is not configured"
                        ) from exc
        return service

    @application.middleware("http")
    async def no_store_auth_responses(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        return response

    @application.get("/auth/healthz")
    def health() -> dict[str, str]:
        return {"status": "alive", "service": "atlas-demo-auth"}

    @application.get("/auth/readyz")
    def ready() -> dict[str, str]:
        configured_service()
        return {"status": "ready", "service": "atlas-demo-auth"}

    @application.post("/auth/login")
    def login(payload: LoginRequest, request: Request, response: Response) -> dict[str, object]:
        _reject_cross_site_post(request)
        auth = configured_service()
        token = auth.authenticate(payload.username, payload.password, _client_key(request))
        subject = auth.verify_session(token)
        response.set_cookie(
            key=SESSION_COOKIE,
            value=token,
            max_age=auth.settings.session_ttl_seconds,
            secure=auth.settings.secure_cookie,
            httponly=True,
            samesite="lax",
            path="/",
        )
        return {
            "authenticated": True,
            "username": subject["sub"],
            "role": subject["role"],
            "expires_in": auth.settings.session_ttl_seconds,
        }

    def require_session(request: Request) -> tuple[DemoAuthService, dict[str, int | str]]:
        auth = configured_service()
        token = request.cookies.get(SESSION_COOKIE)
        return auth, auth.verify_session(token)

    @application.get("/auth/session")
    def session(request: Request, response: Response) -> dict[str, object]:
        auth = configured_service()
        try:
            subject = auth.verify_session(request.cookies.get(SESSION_COOKIE))
        except HTTPException:
            response.delete_cookie(
                key=SESSION_COOKIE,
                secure=auth.settings.secure_cookie,
                httponly=True,
                samesite="lax",
                path="/",
            )
            return {"authenticated": False}
        return {
            "authenticated": True,
            "username": subject["sub"],
            "role": subject["role"],
            "expires_at": subject["exp"],
        }

    @application.get("/auth/verify", status_code=204)
    def verify(request: Request) -> Response:
        _, subject = require_session(request)
        return Response(
            status_code=204,
            headers={
                "X-Atlas-User": str(subject["sub"]),
                "X-Atlas-Role": str(subject["role"]),
            },
        )

    @application.get("/auth/verify-operator", status_code=204)
    def verify_operator(request: Request) -> Response:
        _, subject = require_session(request)
        if subject["role"] != "operator":
            raise HTTPException(status_code=403, detail="Operator role required")
        return Response(
            status_code=204,
            headers={
                "X-Atlas-User": str(subject["sub"]),
                "X-Atlas-Role": "operator",
            },
        )

    @application.get("/auth/verify-product", status_code=204)
    def verify_product(request: Request) -> Response:
        """Authorize product traffic without turning read-only users into operators.

        Nginx sends the original HTTP method because auth subrequests are GETs.
        Viewer sessions may inspect product state, while every state-changing
        request still requires the operator role.
        """
        _, subject = require_session(request)
        original_method = request.headers.get("x-original-method", "").upper()
        if original_method not in {"GET", "HEAD", "OPTIONS"} and subject["role"] != "operator":
            raise HTTPException(status_code=403, detail="Operator role required")
        return Response(
            status_code=204,
            headers={
                "X-Atlas-User": str(subject["sub"]),
                "X-Atlas-Role": str(subject["role"]),
            },
        )

    @application.post("/auth/logout")
    def logout(request: Request, response: Response) -> dict[str, bool]:
        _reject_cross_site_post(request)
        response.delete_cookie(
            key=SESSION_COOKIE,
            secure=configured_service().settings.secure_cookie,
            httponly=True,
            samesite="lax",
            path="/",
        )
        return {"authenticated": False}

    return application


app = create_auth_app()
