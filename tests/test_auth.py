import pytest
from fastapi import HTTPException
from google.oauth2 import id_token
from starlette.requests import Request

from advisory.auth import IdentityVerifier


def request(headers: dict[str, str] | None = None) -> Request:
    raw_headers = [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": raw_headers})


def test_development_identity_is_explicit_and_header_scoped() -> None:
    verifier = IdentityVerifier("development", "")
    assert verifier.verify(request()).subject == "preview-user"
    assert verifier.verify(request({"x-advisory-user": "alice"})).subject == "alice"


def test_google_identity_requires_bearer_and_configuration() -> None:
    with pytest.raises(HTTPException) as missing:
        IdentityVerifier("google", "client-id").verify(request())
    assert missing.value.status_code == 401
    with pytest.raises(HTTPException) as unconfigured:
        IdentityVerifier("google", "").verify(request({"authorization": "Bearer token"}))
    assert unconfigured.value.status_code == 503


def test_google_identity_uses_stable_subject_not_email(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        id_token,
        "verify_oauth2_token",
        lambda token, google_request, audience: {
            "sub": "google-subject-123",
            "email": "person@example.com",
            "iss": "https://accounts.google.com",
        },
    )
    identity = IdentityVerifier("google", "client-id").verify(
        request({"authorization": "Bearer signed-token"})
    )
    assert identity.subject == "google-subject-123"
    assert identity.email == "person@example.com"


def test_google_identity_rejects_invalid_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(id_token, "verify_oauth2_token", lambda *args: {"sub": "", "iss": "other"})
    with pytest.raises(HTTPException) as invalid:
        IdentityVerifier("google", "client-id").verify(request({"authorization": "Bearer signed-token"}))
    assert invalid.value.status_code == 401
