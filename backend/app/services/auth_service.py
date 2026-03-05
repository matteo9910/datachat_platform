"""
Authentication service — JWT token management, password hashing, seed admin.

Uses python-jose for JWT, passlib+bcrypt for password hashing.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import settings
from app.models.system import User, Session as UserSession, UserRole

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Hash a plain-text password using bcrypt."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    return pwd_context.verify(plain, hashed)


# ---------------------------------------------------------------------------
# JWT token creation & validation
# ---------------------------------------------------------------------------

JWT_ALGORITHM = "HS256"


def create_access_token(
    user_id: str,
    email: str,
    role: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a JWT access token.

    Claims: user_id, email, role, exp.
    """
    if expires_delta is None:
        expires_delta = timedelta(hours=settings.jwt_expiry_hours)

    expire = datetime.now(timezone.utc) + expires_delta

    payload = {
        "user_id": user_id,
        "email": email,
        "role": role,
        "exp": expire,
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM)
    return token


def decode_access_token(token: str) -> Optional[dict]:
    """
    Decode and validate a JWT token. Returns claims dict or None on failure.
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

def create_session(db: Session, user: User, token: str) -> UserSession:
    """Create a session record in the system DB."""
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expiry_hours)
    session = UserSession(
        id=uuid.uuid4(),
        user_id=user.id,
        token=token,
        expires_at=expires_at,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def invalidate_session(db: Session, token: str) -> bool:
    """Remove a session record (logout). Returns True if found and deleted."""
    sess = db.query(UserSession).filter(UserSession.token == token).first()
    if sess:
        db.delete(sess)
        db.commit()
        return True
    return False


def is_session_valid(db: Session, token: str) -> bool:
    """Check if a session exists and has not expired."""
    sess = db.query(UserSession).filter(UserSession.token == token).first()
    if not sess:
        return False
    if sess.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        # Expired — clean up
        db.delete(sess)
        db.commit()
        return False
    return True


# ---------------------------------------------------------------------------
# Login flow
# ---------------------------------------------------------------------------

def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """
    Validate email + password. Returns the User object or None.
    Does NOT check is_active — caller must handle that.
    """
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


# ---------------------------------------------------------------------------
# Seed admin
# ---------------------------------------------------------------------------

def seed_admin_user(db: Session) -> Optional[User]:
    """
    Create the seed admin account if the users table is empty.

    Uses SEED_ADMIN_PASSWORD from env. Returns the created User or None.
    """
    user_count = db.query(User).count()
    if user_count > 0:
        logger.info("Users table not empty — skipping seed admin creation")
        return None

    password = settings.seed_admin_password
    if not password:
        logger.warning(
            "SEED_ADMIN_PASSWORD not set — cannot create seed admin. "
            "Set it in .env and restart."
        )
        return None

    admin = User(
        id=uuid.uuid4(),
        email="admin@datachat.local",
        hashed_password=hash_password(password),
        full_name="Admin",
        role=UserRole.admin,
        is_active=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    logger.info("Seed admin account created: admin@datachat.local")
    return admin
