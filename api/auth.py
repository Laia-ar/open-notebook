import secrets
from typing import Optional

from fastapi import Request
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from api.dependencies import OPEN_NOTEBOOK_SESSION_COOKIE
from open_notebook.domain.session import UserSession
from open_notebook.utils.encryption import get_secret_from_env


class PasswordAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware to check authentication for all API requests.
    Accepts either the instance password as `Authorization: Bearer <password>`
    or a valid Google session cookie (OPEN_NOTEBOOK_SESSION_COOKIE).
    Auth is fully disabled (no hardcoded default password) if
    OPEN_NOTEBOOK_PASSWORD is not set.
    Supports Docker secrets via OPEN_NOTEBOOK_PASSWORD_FILE.
    """

    def __init__(
        self, app: ASGIApp, excluded_paths: Optional[list[str]] = None
    ) -> None:
        super().__init__(app)
        self.password = get_secret_from_env("OPEN_NOTEBOOK_PASSWORD")
        self.excluded_paths: list[str] = excluded_paths or [
            "/",
            "/health",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/api/auth/status",
            "/api/auth/google/login",
            "/api/auth/google/callback",
            "/api/auth/me",
            "/api/auth/logout",
        ]

    @staticmethod
    async def _has_valid_session(session_token: str) -> bool:
        try:
            session = await UserSession.get_by_token(session_token)
            return session is not None and session.is_valid
        except Exception:
            logger.exception("Session lookup failed in auth middleware")
            return False

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip authentication if no password is set
        if not self.password:
            return await call_next(request)

        # Skip authentication for excluded paths
        if request.url.path in self.excluded_paths:
            return await call_next(request)

        # Skip authentication for the public (no-login) notebook endpoints —
        # these already check notebook.is_public themselves before returning
        # anything, so they are safe to leave open here.
        if request.url.path.startswith("/api/public/"):
            return await call_next(request)

        # Skip authentication for CORS preflight requests (OPTIONS)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Check authorization header
        auth_header = request.headers.get("Authorization")

        if auth_header:
            # Expected format: "Bearer {password}"
            try:
                scheme, credentials = auth_header.split(" ", 1)
                if scheme.lower() != "bearer":
                    raise ValueError("Invalid authentication scheme")
            except ValueError:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid authorization header format"},
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # Check password (constant-time to avoid a timing side-channel)
            if secrets.compare_digest(
                credentials.encode("utf-8"), self.password.encode("utf-8")
            ):
                return await call_next(request)

        # No (valid) Bearer credential — fall back to the Google session
        # cookie so cookie-authenticated users pass this layer too.
        session_token = request.cookies.get(OPEN_NOTEBOOK_SESSION_COOKIE)
        if session_token and await self._has_valid_session(session_token):
            return await call_next(request)

        if not auth_header:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing authorization header"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid password"},
            headers={"WWW-Authenticate": "Bearer"},
        )
