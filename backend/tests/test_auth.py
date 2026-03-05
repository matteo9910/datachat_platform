"""
Comprehensive tests for JWT authentication API endpoints and middleware.

Uses an in-memory SQLite database to avoid needing a real Neon connection.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.models.system import (
    SystemBase, User, Session as UserSession, UserRole,
)


# ---------------------------------------------------------------------------
# SQLite compat: map JSONB → TEXT
# ---------------------------------------------------------------------------

@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def test_engine():
    # check_same_thread=False is required because FastAPI TestClient runs
    # the ASGI app in a different thread than the test itself.
    eng = create_engine(
        "sqlite://",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    SystemBase.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch):
    """Ensure consistent settings for all tests."""
    from app.config import settings
    monkeypatch.setattr(settings, "secret_key", "test-secret-key-for-jwt")
    monkeypatch.setattr(settings, "jwt_expiry_hours", 24)
    monkeypatch.setattr(settings, "seed_admin_password", "TestAdminPass123!")
    monkeypatch.setattr(settings, "system_database_url", "sqlite://")


@pytest.fixture()
def db_session(test_engine):
    """Provide a DB session. We create all tables fresh per-test via SAVEPOINT."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db_session):
    """FastAPI TestClient wired to the test DB session."""
    from app.database import get_system_db

    def _override_db():
        yield db_session

    app = FastAPI()

    from app.api.auth import router as auth_router
    from app.api.admin import router as admin_router
    app.include_router(auth_router)
    app.include_router(admin_router)

    # Health endpoint for sanity
    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    app.dependency_overrides[get_system_db] = _override_db

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_user(db_session, email="user@test.com", password="secret123",
                 role=UserRole.user, full_name="Test User", is_active=True):
    """Create a user directly in the DB and return it."""
    from app.services.auth_service import hash_password
    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        role=role,
        is_active=is_active,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _login(client, email, password):
    """Helper to login and get token."""
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    return resp


def _auth_header(token):
    return {"Authorization": f"Bearer {token}"}


# ======================================================================
# AUTH SERVICE UNIT TESTS
# ======================================================================

class TestPasswordHashing:
    def test_hash_and_verify(self):
        from app.services.auth_service import hash_password, verify_password
        hashed = hash_password("mypassword")
        assert hashed != "mypassword"
        assert verify_password("mypassword", hashed) is True
        assert verify_password("wrongpassword", hashed) is False


class TestJWT:
    def test_create_and_decode(self):
        from app.services.auth_service import create_access_token, decode_access_token
        token = create_access_token(
            user_id="abc-123",
            email="test@example.com",
            role="admin",
        )
        claims = decode_access_token(token)
        assert claims is not None
        assert claims["user_id"] == "abc-123"
        assert claims["email"] == "test@example.com"
        assert claims["role"] == "admin"
        assert "exp" in claims

    def test_expired_token(self):
        from app.services.auth_service import create_access_token, decode_access_token
        token = create_access_token(
            user_id="abc-123",
            email="test@example.com",
            role="admin",
            expires_delta=timedelta(seconds=-1),
        )
        claims = decode_access_token(token)
        assert claims is None

    def test_invalid_token(self):
        from app.services.auth_service import decode_access_token
        claims = decode_access_token("not.a.valid.jwt.token")
        assert claims is None

    def test_jwt_contains_required_claims(self):
        from app.services.auth_service import create_access_token, decode_access_token
        token = create_access_token(
            user_id="user-id-1",
            email="user@test.com",
            role="analyst",
        )
        claims = decode_access_token(token)
        assert "user_id" in claims
        assert "email" in claims
        assert "role" in claims
        assert "exp" in claims


class TestAuthenticateUser:
    def test_valid_credentials(self, db_session):
        from app.services.auth_service import authenticate_user
        _create_user(db_session, email="login@test.com", password="pass123")
        user = authenticate_user(db_session, "login@test.com", "pass123")
        assert user is not None
        assert user.email == "login@test.com"

    def test_invalid_password(self, db_session):
        from app.services.auth_service import authenticate_user
        _create_user(db_session, email="login2@test.com", password="pass123")
        user = authenticate_user(db_session, "login2@test.com", "wrongpass")
        assert user is None

    def test_nonexistent_email(self, db_session):
        from app.services.auth_service import authenticate_user
        user = authenticate_user(db_session, "nobody@test.com", "pass123")
        assert user is None


class TestSeedAdmin:
    def test_seed_admin_creates_when_empty(self, db_session):
        from app.services.auth_service import seed_admin_user
        admin = seed_admin_user(db_session)
        assert admin is not None
        assert admin.email == "admin@datachat.local"
        assert admin.role == UserRole.admin
        assert admin.is_active is True

    def test_seed_admin_skips_when_users_exist(self, db_session):
        from app.services.auth_service import seed_admin_user
        _create_user(db_session, email="existing@test.com")
        admin = seed_admin_user(db_session)
        assert admin is None

    def test_seed_admin_skips_without_password(self, db_session, monkeypatch):
        from app.services.auth_service import seed_admin_user
        from app.config import settings
        monkeypatch.setattr(settings, "seed_admin_password", None)
        admin = seed_admin_user(db_session)
        assert admin is None


# ======================================================================
# AUTH API ENDPOINT TESTS
# ======================================================================

class TestLoginEndpoint:
    def test_login_success(self, client, db_session):
        _create_user(db_session, email="admin@datachat.local", password="secret",
                      role=UserRole.admin, full_name="Admin")
        resp = _login(client, "admin@datachat.local", "secret")
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["email"] == "admin@datachat.local"
        assert data["user"]["role"] == "admin"
        assert "id" in data["user"]

    def test_login_invalid_credentials(self, client, db_session):
        _create_user(db_session, email="user@test.com", password="correct")
        resp = _login(client, "user@test.com", "wrong")
        assert resp.status_code == 401
        assert "Invalid" in resp.json()["detail"]

    def test_login_nonexistent_user(self, client):
        resp = _login(client, "noone@test.com", "pass")
        assert resp.status_code == 401

    def test_login_disabled_account(self, client, db_session):
        _create_user(db_session, email="disabled@test.com", password="pass",
                      is_active=False)
        resp = _login(client, "disabled@test.com", "pass")
        assert resp.status_code == 403
        assert "disabled" in resp.json()["detail"].lower()


class TestLogoutEndpoint:
    def test_logout_success(self, client, db_session):
        _create_user(db_session, email="logout@test.com", password="pass",
                      role=UserRole.admin)
        resp = _login(client, "logout@test.com", "pass")
        token = resp.json()["token"]
        logout_resp = client.post("/api/auth/logout", headers=_auth_header(token))
        assert logout_resp.status_code == 200
        assert "Logged out" in logout_resp.json()["message"]

    def test_logout_without_token(self, client):
        resp = client.post("/api/auth/logout")
        assert resp.status_code == 401

    def test_logout_invalidates_session(self, client, db_session):
        _create_user(db_session, email="invalidate@test.com", password="pass",
                      role=UserRole.admin)
        resp = _login(client, "invalidate@test.com", "pass")
        token = resp.json()["token"]
        # Logout
        client.post("/api/auth/logout", headers=_auth_header(token))
        # Try to use the same token again
        resp2 = client.post("/api/auth/logout", headers=_auth_header(token))
        assert resp2.status_code == 401


# ======================================================================
# AUTH MIDDLEWARE / PROTECTED ENDPOINT TESTS
# ======================================================================

class TestProtectedEndpoints:
    def test_no_token_returns_401(self, client):
        resp = client.get("/api/admin/users")
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self, client):
        resp = client.get("/api/admin/users", headers=_auth_header("garbage"))
        assert resp.status_code == 401

    def test_valid_admin_token_returns_200(self, client, db_session):
        _create_user(db_session, email="admin@test.com", password="adminpass",
                      role=UserRole.admin, full_name="Admin")
        resp = _login(client, "admin@test.com", "adminpass")
        token = resp.json()["token"]
        resp2 = client.get("/api/admin/users", headers=_auth_header(token))
        assert resp2.status_code == 200

    def test_user_role_on_admin_endpoint_returns_403(self, client, db_session):
        _create_user(db_session, email="regular@test.com", password="pass",
                      role=UserRole.user, full_name="Regular")
        resp = _login(client, "regular@test.com", "pass")
        token = resp.json()["token"]
        resp2 = client.get("/api/admin/users", headers=_auth_header(token))
        assert resp2.status_code == 403

    def test_analyst_role_on_admin_endpoint_returns_403(self, client, db_session):
        _create_user(db_session, email="analyst@test.com", password="pass",
                      role=UserRole.analyst, full_name="Analyst")
        resp = _login(client, "analyst@test.com", "pass")
        token = resp.json()["token"]
        resp2 = client.get("/api/admin/users", headers=_auth_header(token))
        assert resp2.status_code == 403


# ======================================================================
# ADMIN USER MANAGEMENT TESTS
# ======================================================================

class TestAdminCreateUser:
    def _admin_token(self, client, db_session):
        _create_user(db_session, email="admin_c@test.com", password="admin",
                      role=UserRole.admin, full_name="Admin")
        resp = _login(client, "admin_c@test.com", "admin")
        return resp.json()["token"]

    def test_create_user_success(self, client, db_session):
        token = self._admin_token(client, db_session)
        resp = client.post("/api/admin/users", headers=_auth_header(token), json={
            "email": "newuser@test.com",
            "password": "newpass",
            "full_name": "New User",
            "role": "analyst",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "newuser@test.com"
        assert data["role"] == "analyst"
        assert data["is_active"] is True

    def test_create_user_duplicate_email(self, client, db_session):
        token = self._admin_token(client, db_session)
        # Create first user
        client.post("/api/admin/users", headers=_auth_header(token), json={
            "email": "dup@test.com", "password": "pass123456",
            "full_name": "First", "role": "user",
        })
        # Try duplicate
        resp = client.post("/api/admin/users", headers=_auth_header(token), json={
            "email": "dup@test.com", "password": "pass123456",
            "full_name": "Second", "role": "user",
        })
        assert resp.status_code == 409

    def test_create_user_invalid_role(self, client, db_session):
        token = self._admin_token(client, db_session)
        resp = client.post("/api/admin/users", headers=_auth_header(token), json={
            "email": "badrole@test.com", "password": "pass123456",
            "full_name": "Bad", "role": "superadmin",
        })
        assert resp.status_code == 400


class TestAdminUpdateUser:
    def _setup(self, client, db_session):
        admin = _create_user(db_session, email="admin_u@test.com", password="admin",
                              role=UserRole.admin, full_name="Admin")
        target = _create_user(db_session, email="target@test.com", password="pass",
                               role=UserRole.user, full_name="Target")
        resp = _login(client, "admin_u@test.com", "admin")
        token = resp.json()["token"]
        return token, str(admin.id), str(target.id)

    def test_update_role(self, client, db_session):
        token, _, target_id = self._setup(client, db_session)
        resp = client.put(f"/api/admin/users/{target_id}",
                          headers=_auth_header(token),
                          json={"role": "analyst"})
        assert resp.status_code == 200
        assert resp.json()["role"] == "analyst"

    def test_disable_user(self, client, db_session):
        token, _, target_id = self._setup(client, db_session)
        resp = client.put(f"/api/admin/users/{target_id}",
                          headers=_auth_header(token),
                          json={"is_active": False})
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    def test_admin_cannot_disable_self(self, client, db_session):
        token, admin_id, _ = self._setup(client, db_session)
        resp = client.put(f"/api/admin/users/{admin_id}",
                          headers=_auth_header(token),
                          json={"is_active": False})
        assert resp.status_code == 400
        assert "own account" in resp.json()["detail"].lower()

    def test_update_nonexistent_user(self, client, db_session):
        token, _, _ = self._setup(client, db_session)
        fake_id = str(uuid.uuid4())
        resp = client.put(f"/api/admin/users/{fake_id}",
                          headers=_auth_header(token),
                          json={"full_name": "Ghost"})
        assert resp.status_code == 404


class TestAdminGetUser:
    def test_get_user_by_id(self, client, db_session):
        admin = _create_user(db_session, email="admin_g@test.com", password="admin",
                              role=UserRole.admin)
        target = _create_user(db_session, email="gettarget@test.com", password="pass")
        resp = _login(client, "admin_g@test.com", "admin")
        token = resp.json()["token"]
        resp2 = client.get(f"/api/admin/users/{target.id}", headers=_auth_header(token))
        assert resp2.status_code == 200
        assert resp2.json()["email"] == "gettarget@test.com"


class TestAdminListUsers:
    def test_list_users(self, client, db_session):
        _create_user(db_session, email="admin_l@test.com", password="admin",
                      role=UserRole.admin)
        _create_user(db_session, email="user1@test.com", password="pass")
        _create_user(db_session, email="user2@test.com", password="pass")
        resp = _login(client, "admin_l@test.com", "admin")
        token = resp.json()["token"]
        resp2 = client.get("/api/admin/users", headers=_auth_header(token))
        assert resp2.status_code == 200
        users = resp2.json()
        assert len(users) >= 3


# ======================================================================
# INTEGRATION FLOW TESTS
# ======================================================================

class TestFullLoginFlow:
    def test_login_use_protected_endpoint_logout(self, client, db_session):
        """Full flow: login -> access protected endpoint -> logout -> can't access."""
        _create_user(db_session, email="flow@test.com", password="flowpass",
                      role=UserRole.admin, full_name="Flow")

        # Login
        resp = _login(client, "flow@test.com", "flowpass")
        assert resp.status_code == 200
        token = resp.json()["token"]

        # Access protected endpoint
        resp2 = client.get("/api/admin/users", headers=_auth_header(token))
        assert resp2.status_code == 200

        # Logout
        resp3 = client.post("/api/auth/logout", headers=_auth_header(token))
        assert resp3.status_code == 200

        # Token should no longer work
        resp4 = client.get("/api/admin/users", headers=_auth_header(token))
        assert resp4.status_code == 401

    def test_disabled_account_cannot_login(self, client, db_session):
        """Create user, disable, try login -> 403."""
        admin = _create_user(db_session, email="disabler@test.com", password="admin",
                              role=UserRole.admin)
        target = _create_user(db_session, email="victim@test.com", password="pass",
                               role=UserRole.user)

        # Login as admin
        resp = _login(client, "disabler@test.com", "admin")
        token = resp.json()["token"]

        # Disable target
        client.put(f"/api/admin/users/{target.id}",
                   headers=_auth_header(token),
                   json={"is_active": False})

        # Target cannot login
        resp2 = _login(client, "victim@test.com", "pass")
        assert resp2.status_code == 403
