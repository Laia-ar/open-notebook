from typing import Optional

from fastapi import HTTPException, Request

from open_notebook.domain.session import UserSession
from open_notebook.domain.user import User


OPEN_NOTEBOOK_SESSION_COOKIE = "open_notebook_session"


async def get_current_user(request: Request) -> User:
    """
    Returns the user authenticated via their Google session
    All routes that work with private information must use this dependency
    """
    session_token = request.cookies.get(OPEN_NOTEBOOK_SESSION_COOKIE)

    if not session_token:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
        )

    session = await UserSession.get_by_token(session_token)

    if session is None or not session.is_valid:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session",
        )

    try:
        user = await User.get(session.user_id)
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="User session is invalid",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="User account is inactive",
        )

    return user