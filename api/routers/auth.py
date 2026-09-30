import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from loguru import logger
from starlette.responses import JSONResponse, RedirectResponse

from open_notebook.config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_REDIRECT_URI,
    OPEN_NOTEBOOK_COOKIE_SECURE,
    OPEN_NOTEBOOK_FRONTEND_URL,
    OPEN_NOTEBOOK_SESSION_DAYS,
)
from open_notebook.database.repository import repo_query
from open_notebook.domain.session import UserSession
from open_notebook.domain.user import User
from open_notebook.utils.encryption import get_secret_from_env

router = APIRouter(prefix="/auth", tags=["auth"])

GOOGLE_AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_TOKEN_INFO_URL = "https://oauth2.googleapis.com/tokeninfo"

GOOGLE_STATE_COOKIE = "open_notebook_google_state"
OPEN_NOTEBOOK_SESSION_COOKIE = "open_notebook_session"


def _google_client_secret() -> str:
    return get_secret_from_env("GOOGLE_CLIENT_SECRET") or ""


def _google_is_configured() -> bool:
    return bool(
        GOOGLE_CLIENT_ID
        and GOOGLE_REDIRECT_URI
        and _google_client_secret()
    )


def _frontend_error_redirect(error: str) -> RedirectResponse:
    query = urlencode({"error": error})
    return RedirectResponse(
        url=f"{OPEN_NOTEBOOK_FRONTEND_URL}/login?{query}",
        status_code=302,
    )


def _get_google_authorization_url(state: str) -> str:
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }

    return f"{GOOGLE_AUTHORIZATION_URL}?{urlencode(params)}"


async def _exchange_code_for_tokens(code: str) -> dict[str, Any]:
    payload = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": _google_client_secret(),
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(GOOGLE_TOKEN_URL, data=payload)
        response.raise_for_status()
        token_data = response.json()

    if not token_data.get("id_token"):
        raise ValueError("Google did not return an ID token")

    return token_data


async def _validate_google_id_token(id_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            GOOGLE_TOKEN_INFO_URL,
            params={"id_token": id_token},
        )

    if response.status_code != 200:
        raise ValueError("Invalid Google ID token")

    claims = response.json()

    valid_issuers = {
        "accounts.google.com",
        "https://accounts.google.com",
    }

    if claims.get("iss") not in valid_issuers:
        raise ValueError("Invalid Google token issuer")

    if claims.get("aud") != GOOGLE_CLIENT_ID:
        raise ValueError("Google token audience does not match this application")

    subject = claims.get("sub")
    email = claims.get("email")
    email_verified = claims.get("email_verified")

    if not subject:
        raise ValueError("Google token does not contain a user identifier")

    if not email:
        raise ValueError("Google token does not contain an email")

    if email_verified not in (True, "true", "True"):
        raise ValueError("Google email is not verified")

    expiration = claims.get("exp")

    if expiration:
        try:
            if datetime.now(timezone.utc).timestamp() >= int(expiration):
                raise ValueError("Google ID token has expired")
        except (TypeError, ValueError) as exc:
            if str(exc) == "Google ID token has expired":
                raise
            raise ValueError("Invalid Google token expiration") from exc

    return claims


async def _find_user_by_email(email: str) -> Optional[User]:
    result = await repo_query(
        """
        SELECT * FROM app_user
        WHERE email = $email
        LIMIT 1
        """,
        {"email": email.lower()},
    )

    if not result:
        return None

    return User(**result[0])


async def _find_or_create_user(claims: dict[str, Any]) -> User:
    email = str(claims["email"]).strip().lower()
    name = str(claims.get("name") or email.split("@", 1)[0]).strip()
    picture = claims.get("picture")

    user = await _find_user_by_email(email)

    if user is not None:
        if not user.is_active:
            raise PermissionError("User account is inactive")

        changed = False

        if user.name != name:
            user.name = name
            changed = True

        if user.avatar_url != picture:
            user.avatar_url = picture
            changed = True

        if changed:
            await user.save()

        return user

    user = User(
        name=name,
        email=email,
        avatar_url=picture,
        is_active=True,
    )

    await user.save()

    return user

async def _get_authenticated_user(
    request: Request,
) -> tuple[User, UserSession] | None:
    session_token = request.cookies.get(OPEN_NOTEBOOK_SESSION_COOKIE)

    if not session_token:
        return None

    session = await UserSession.get_by_token(session_token)

    if session is None or not session.is_valid:
        return None

    try:
        user = await User.get(session.user_id)
    except Exception:
        return None

    if not user.is_active:
        return None

    return user, session

@router.get("/status")
async def get_auth_status():
    password_auth_enabled = bool(
        get_secret_from_env("OPEN_NOTEBOOK_PASSWORD")
    )

    return {
        "auth_enabled": password_auth_enabled or _google_is_configured(),
        "google_auth_enabled": _google_is_configured(),
        "message": (
            "Authentication is configured"
            if password_auth_enabled or _google_is_configured()
            else "Authentication is disabled"
        ),
    }


@router.get("/google/login")
async def google_login():
    if not _google_is_configured():
        return _frontend_error_redirect("google_not_configured")

    state = secrets.token_urlsafe(32)
    redirect = RedirectResponse(
        url=_get_google_authorization_url(state),
        status_code=302,
    )

    redirect.set_cookie(
        key=GOOGLE_STATE_COOKIE,
        value=state,
        max_age=600,
        httponly=True,
        secure=OPEN_NOTEBOOK_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )

    return redirect


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
):
    if error:
        logger.warning("Google OAuth was cancelled or rejected: {}", error)
        return _frontend_error_redirect("google_login_cancelled")

    if not code or not state:
        return _frontend_error_redirect("google_callback_incomplete")

    stored_state = request.cookies.get(GOOGLE_STATE_COOKIE)

    if (
        not stored_state
        or not secrets.compare_digest(stored_state, state)
    ):
        logger.warning("Invalid Google OAuth state")
        return _frontend_error_redirect("invalid_google_state")

    try:
        token_data = await _exchange_code_for_tokens(code)
        claims = await _validate_google_id_token(token_data["id_token"])
        user = await _find_or_create_user(claims)

        if not user.id:
            raise ValueError("Created user does not have an ID")

        expires_at = datetime.now(timezone.utc) + timedelta(
            days=OPEN_NOTEBOOK_SESSION_DAYS
        )

        _, raw_session_token = await UserSession.create_for_user(
            user_id=user.id,
            expires_at=expires_at,
        )

    except PermissionError:
        logger.warning("Inactive user attempted Google login")
        return _frontend_error_redirect("user_inactive")
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Google OAuth failed: {}", exc)
        return _frontend_error_redirect("google_login_failed")
    except Exception:
        logger.exception("Unexpected error during Google OAuth callback")
        return _frontend_error_redirect("google_login_failed")

    redirect = RedirectResponse(
        url=f"{OPEN_NOTEBOOK_FRONTEND_URL}/",
        status_code=302,
    )

    redirect.delete_cookie(
        key=GOOGLE_STATE_COOKIE,
        path="/",
    )

    redirect.set_cookie(
        key=OPEN_NOTEBOOK_SESSION_COOKIE,
        value=raw_session_token,
        max_age=OPEN_NOTEBOOK_SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=OPEN_NOTEBOOK_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )

    return redirect

@router.get("/me")
async def get_current_user(request: Request):
    """
    Devuelve los datos del usuario autenticado actualmente.
    """
    authenticated_user = await _get_authenticated_user(request)

    if authenticated_user is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
        )

    user, _ = authenticated_user

    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "avatar_url": user.avatar_url,
        "is_active": user.is_active,
        "created": user.created,
        "updated": user.updated,
    }

@router.post("/logout")
async def logout(request: Request):
    session_token = request.cookies.get(OPEN_NOTEBOOK_SESSION_COOKIE)

    if session_token:
        session = await UserSession.get_by_token(session_token)

        if session is not None and session.is_valid:
            await session.revoke()

    response = {
        "success": True,
        "message": "Logged out successfully",
    }

    result = JSONResponse(content=response)

    result.delete_cookie(
        key=OPEN_NOTEBOOK_SESSION_COOKIE,
        path="/",
    )

    return result