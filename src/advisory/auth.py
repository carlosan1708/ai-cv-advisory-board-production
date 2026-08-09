from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request


@dataclass(frozen=True)
class UserIdentity:
    subject: str
    email: str = ""


class IdentityVerifier:
    def __init__(self, mode: str, google_client_id: str) -> None:
        self.mode = mode
        self.google_client_id = google_client_id

    def verify(self, request: Request) -> UserIdentity:
        if self.mode == "development":
            return UserIdentity(
                request.headers.get("x-advisory-user", "preview-user"),
                request.headers.get("x-advisory-email", "carlosan.1708@gmail.com"),
            )
        authorization = request.headers.get("authorization", "")
        token = authorization.removeprefix("Bearer ").strip() if authorization.startswith("Bearer ") else ""
        token = token or request.cookies.get("advisory_session", "")
        if not token:
            raise HTTPException(status_code=401, detail="Sign in with Google to continue")
        return self.verify_token(token)

    def verify_token(self, token: str) -> UserIdentity:
        if self.mode == "development":
            return UserIdentity("preview-user", "carlosan.1708@gmail.com")
        if not self.google_client_id:
            raise HTTPException(status_code=503, detail="Google sign-in is not configured")
        try:
            from google.auth.transport.requests import Request as GoogleRequest
            from google.oauth2 import id_token

            claims = id_token.verify_oauth2_token(  # type: ignore[no-untyped-call]
                token, GoogleRequest(), self.google_client_id
            )
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=401, detail="Google sign-in expired or is invalid") from exc
        subject = str(claims.get("sub", ""))
        issuer = claims.get("iss")
        if not subject or issuer not in {"accounts.google.com", "https://accounts.google.com"}:
            raise HTTPException(status_code=401, detail="Google identity is invalid")
        return UserIdentity(subject=subject, email=str(claims.get("email", "")))
