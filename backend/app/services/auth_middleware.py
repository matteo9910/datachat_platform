"""
Authentication middleware — JWT extraction from Authorization header,
user injection into request state, role-based access decorator.
"""

import logging
import uuid as uuid_module
from typing import List, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_system_db
from app.models.system import User
from app.services.auth_service import decode_access_token, is_session_valid

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bearer token extractor
# ---------------------------------------------------------------------------

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_system_db),
) -> User:
    """
    FastAPI dependency: extract JWT from Authorization Bearer header,
    validate signature + expiry, check session in DB, and return the User.

    Raises 401 if token missing/invalid/expired/session-not-found.
    Raises 403 if user account is disabled.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    claims = decode_access_token(token)
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate session still exists in DB
    if not is_session_valid(db, token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalidated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fetch the user (convert string to UUID for DB query)
    user_id_str = claims.get("user_id")
    try:
        user_id = uuid_module.UUID(user_id_str)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims",
        )
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    # Store user in request state for downstream access
    request.state.current_user = user
    return user


# ---------------------------------------------------------------------------
# Role-based access decorator
# ---------------------------------------------------------------------------

def require_role(allowed_roles: List[str]):
    """
    Dependency factory: returns a FastAPI dependency that checks the
    current user has one of the allowed roles.

    Usage::

        @router.get("/admin-only")
        async def admin_only(user: User = Depends(require_role(["admin"]))):
            ...
    """
    async def role_checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        user_role = current_user.role.value if hasattr(current_user.role, "value") else current_user.role
        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {allowed_roles}",
            )
        return current_user

    return role_checker
