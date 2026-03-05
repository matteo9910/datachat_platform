"""
Comprehensive tests for Admin User Management CRUD API.

Covers:
- GET /api/admin/users (list all users, admin-only)
- POST /api/admin/users (create user with validation)
- PUT /api/admin/users/{id} (update user fields)
- Auth enforcement (401 without token, 403 without admin role)
- Email format validation
- Duplicate email (409)
- Role validation
- Admin cannot disable own account (400)

Uses an in-memory SQLite database to avoid needing a real Neon connection.
"""

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.models.system import (
    SystemBase, User, Session as UserSession, UserRole,
)


# ---------------------------------------------------------------------------
# SQLite compat: map JSONB -> TEXT
# ---------------------------------------------------------------------------

@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def test_engine():
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
    """Provide a DB session with SAVEPOINT for test isolation."""
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


def _get_admin_token(client, db_session, email="admin@mgmt.test", password="adminpass"):
    """Create an admin user and return an auth token."""
    _create_user(db_session, email=email, password=password,
                 role=UserRole.admin, full_name="Admin User")
    resp = _login(client, email, password)
    assert resp.status_code == 200
    return resp.json()["token"]


# ======================================================================
# AUTH ENFORCEMENT TESTS
# ======================================================================

class TestAdminUsersAuthEnforcement:
    """All admin endpoints require admin role -- 401 without token, 403 without admin role."""

    def test_list_users_no_token_returns_401(self, client):
        resp = client.get("/api/admin/users")
        assert resp.status_code == 401

    def test_list_users_invalid_token_returns_401(self, client):
        resp = client.get("/api/admin/users", headers=_auth_header("bad.jwt.token"))
        assert resp.status_code == 401

    def test_create_user_no_token_returns_401(self, client):
        resp = client.post("/api/admin/users", json={
            "email": "new@test.com", "password": "pass123456",
            "full_name": "New User", "role": "user",
        })
        assert resp.status_code == 401

    def test_update_user_no_token_returns_401(self, client):
        fake_id = str(uuid.uuid4())
        resp = client.put(f"/api/admin/users/{fake_id}", json={"full_name": "Updated"})
        assert resp.status_code == 401

    def test_list_users_user_role_returns_403(self, client, db_session):
        _create_user(db_session, email="regular@test.com", password="pass",
                     role=UserRole.user, full_name="Regular")
        resp = _login(client, "regular@test.com", "pass")
        token = resp.json()["token"]
        resp2 = client.get("/api/admin/users", headers=_auth_header(token))
        assert resp2.status_code == 403

    def test_list_users_analyst_role_returns_403(self, client, db_session):
        _create_user(db_session, email="analyst@test.com", password="pass",
                     role=UserRole.analyst, full_name="Analyst")
        resp = _login(client, "analyst@test.com", "pass")
        token = resp.json()["token"]
        resp2 = client.get("/api/admin/users", headers=_auth_header(token))
        assert resp2.status_code == 403

    def test_create_user_user_role_returns_403(self, client, db_session):
        _create_user(db_session, email="regular2@test.com", password="pass",
                     role=UserRole.user, full_name="Regular2")
        resp = _login(client, "regular2@test.com", "pass")
        token = resp.json()["token"]
        resp2 = client.post("/api/admin/users", headers=_auth_header(token), json={
            "email": "test@test.com", "password": "pass123456",
            "full_name": "Test", "role": "user",
        })
        assert resp2.status_code == 403

    def test_update_user_analyst_role_returns_403(self, client, db_session):
        _create_user(db_session, email="analyst2@test.com", password="pass",
                     role=UserRole.analyst, full_name="Analyst2")
        target = _create_user(db_session, email="target@test.com", password="pass",
                              role=UserRole.user, full_name="Target")
        resp = _login(client, "analyst2@test.com", "pass")
        token = resp.json()["token"]
        resp2 = client.put(f"/api/admin/users/{target.id}",
                           headers=_auth_header(token),
                           json={"full_name": "Updated"})
        assert resp2.status_code == 403


# ======================================================================
# LIST USERS TESTS
# ======================================================================

class TestListUsers:
    """GET /api/admin/users -- list all users (admin-only, no passwords)."""

    def test_list_users_returns_all(self, client, db_session):
        token = _get_admin_token(client, db_session)
        _create_user(db_session, email="user1@test.com", full_name="User One")
        _create_user(db_session, email="user2@test.com", full_name="User Two")
        resp = client.get("/api/admin/users", headers=_auth_header(token))
        assert resp.status_code == 200
        users = resp.json()
        assert len(users) >= 3  # admin + user1 + user2
        emails = [u["email"] for u in users]
        assert "user1@test.com" in emails
        assert "user2@test.com" in emails

    def test_list_users_excludes_passwords(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.get("/api/admin/users", headers=_auth_header(token))
        assert resp.status_code == 200
        for user in resp.json():
            assert "password" not in user
            assert "hashed_password" not in user

    def test_list_users_returns_expected_fields(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.get("/api/admin/users", headers=_auth_header(token))
        assert resp.status_code == 200
        user = resp.json()[0]
        assert "id" in user
        assert "email" in user
        assert "full_name" in user
        assert "role" in user
        assert "is_active" in user
        assert "created_at" in user

    def test_list_users_empty_except_admin(self, client, db_session):
        """Only the admin user we create for auth should appear."""
        token = _get_admin_token(client, db_session)
        resp = client.get("/api/admin/users", headers=_auth_header(token))
        assert resp.status_code == 200
        assert len(resp.json()) == 1


# ======================================================================
# CREATE USER TESTS
# ======================================================================

class TestCreateUser:
    """POST /api/admin/users -- create user (admin-only)."""

    def test_create_user_success(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/admin/users", headers=_auth_header(token), json={
            "email": "newuser@example.com",
            "password": "securepass123",
            "full_name": "New User",
            "role": "analyst",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "newuser@example.com"
        assert data["full_name"] == "New User"
        assert data["role"] == "analyst"
        assert data["is_active"] is True
        assert "id" in data

    def test_create_user_default_role_is_user(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/admin/users", headers=_auth_header(token), json={
            "email": "default@example.com",
            "password": "securepass123",
            "full_name": "Default Role",
        })
        assert resp.status_code == 201
        assert resp.json()["role"] == "user"

    def test_create_user_all_roles(self, client, db_session):
        token = _get_admin_token(client, db_session)
        for role in ["admin", "analyst", "user"]:
            resp = client.post("/api/admin/users", headers=_auth_header(token), json={
                "email": f"{role}test@example.com",
                "password": "securepass123",
                "full_name": f"{role.title()} Test",
                "role": role,
            })
            assert resp.status_code == 201
            assert resp.json()["role"] == role

    def test_create_user_duplicate_email_returns_409(self, client, db_session):
        token = _get_admin_token(client, db_session)
        # Create first user
        resp1 = client.post("/api/admin/users", headers=_auth_header(token), json={
            "email": "duplicate@example.com",
            "password": "pass123456",
            "full_name": "First User",
            "role": "user",
        })
        assert resp1.status_code == 201
        # Try duplicate
        resp2 = client.post("/api/admin/users", headers=_auth_header(token), json={
            "email": "duplicate@example.com",
            "password": "otherpass123",
            "full_name": "Second User",
            "role": "user",
        })
        assert resp2.status_code == 409
        assert "already exists" in resp2.json()["detail"].lower()

    def test_create_user_invalid_role_returns_400(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/admin/users", headers=_auth_header(token), json={
            "email": "badrole@example.com",
            "password": "pass123456",
            "full_name": "Bad Role",
            "role": "superadmin",
        })
        assert resp.status_code == 400
        assert "Invalid role" in resp.json()["detail"]

    def test_created_user_can_login(self, client, db_session):
        """Integration: newly created user can authenticate."""
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/admin/users", headers=_auth_header(token), json={
            "email": "logintest@example.com",
            "password": "loginpass123",
            "full_name": "Login Test",
            "role": "user",
        })
        assert resp.status_code == 201
        # Now login as the new user
        login_resp = _login(client, "logintest@example.com", "loginpass123")
        assert login_resp.status_code == 200
        assert login_resp.json()["user"]["email"] == "logintest@example.com"

    def test_created_user_appears_in_list(self, client, db_session):
        """Integration: newly created user appears in GET /api/admin/users."""
        token = _get_admin_token(client, db_session)
        client.post("/api/admin/users", headers=_auth_header(token), json={
            "email": "listcheck@example.com",
            "password": "pass123456",
            "full_name": "List Check",
            "role": "analyst",
        })
        resp = client.get("/api/admin/users", headers=_auth_header(token))
        assert resp.status_code == 200
        emails = [u["email"] for u in resp.json()]
        assert "listcheck@example.com" in emails


# ======================================================================
# EMAIL VALIDATION TESTS
# ======================================================================

class TestEmailValidation:
    """Email validation rejects malformed emails."""

    def test_valid_email_accepted(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/admin/users", headers=_auth_header(token), json={
            "email": "valid.email@example.com",
            "password": "pass123456",
            "full_name": "Valid Email",
            "role": "user",
        })
        assert resp.status_code == 201

    def test_email_with_plus_accepted(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/admin/users", headers=_auth_header(token), json={
            "email": "user+tag@example.com",
            "password": "pass123456",
            "full_name": "Plus Email",
            "role": "user",
        })
        assert resp.status_code == 201

    def test_email_no_at_sign_rejected(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/admin/users", headers=_auth_header(token), json={
            "email": "not-an-email",
            "password": "pass123456",
            "full_name": "Bad Email",
            "role": "user",
        })
        assert resp.status_code == 422
        assert "email" in str(resp.json()).lower()

    def test_email_no_domain_rejected(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/admin/users", headers=_auth_header(token), json={
            "email": "user@",
            "password": "pass123456",
            "full_name": "Bad Domain",
            "role": "user",
        })
        assert resp.status_code == 422

    def test_email_no_tld_rejected(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/admin/users", headers=_auth_header(token), json={
            "email": "user@localhost",
            "password": "pass123456",
            "full_name": "No TLD",
            "role": "user",
        })
        assert resp.status_code == 422

    def test_email_empty_string_rejected(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/admin/users", headers=_auth_header(token), json={
            "email": "",
            "password": "pass123456",
            "full_name": "Empty Email",
            "role": "user",
        })
        assert resp.status_code == 422

    def test_email_with_spaces_rejected(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/admin/users", headers=_auth_header(token), json={
            "email": "user @example.com",
            "password": "pass123456",
            "full_name": "Space Email",
            "role": "user",
        })
        assert resp.status_code == 422

    def test_email_double_at_rejected(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/admin/users", headers=_auth_header(token), json={
            "email": "user@@example.com",
            "password": "pass123456",
            "full_name": "Double At",
            "role": "user",
        })
        assert resp.status_code == 422

    def test_update_email_invalid_rejected(self, client, db_session):
        """PUT also validates email format."""
        token = _get_admin_token(client, db_session)
        target = _create_user(db_session, email="updateme@test.com",
                              password="pass", full_name="Update Me")
        resp = client.put(f"/api/admin/users/{target.id}",
                          headers=_auth_header(token),
                          json={"email": "not-valid"})
        assert resp.status_code == 422

    def test_email_normalized_to_lowercase(self, client, db_session):
        """Email should be stored in lowercase."""
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/admin/users", headers=_auth_header(token), json={
            "email": "User@Example.COM",
            "password": "pass123456",
            "full_name": "Case Test",
            "role": "user",
        })
        assert resp.status_code == 201
        assert resp.json()["email"] == "user@example.com"


# ======================================================================
# UPDATE USER TESTS
# ======================================================================

class TestUpdateUser:
    """PUT /api/admin/users/{id} -- update role, full_name, is_active (admin-only)."""

    def _setup(self, client, db_session):
        """Create admin + target user, return (token, admin_id, target_id)."""
        admin = _create_user(db_session, email="admin_up@test.com", password="admin",
                             role=UserRole.admin, full_name="Admin")
        target = _create_user(db_session, email="target_up@test.com", password="pass",
                              role=UserRole.user, full_name="Target User")
        resp = _login(client, "admin_up@test.com", "admin")
        token = resp.json()["token"]
        return token, str(admin.id), str(target.id)

    def test_update_role(self, client, db_session):
        token, _, target_id = self._setup(client, db_session)
        resp = client.put(f"/api/admin/users/{target_id}",
                          headers=_auth_header(token),
                          json={"role": "analyst"})
        assert resp.status_code == 200
        assert resp.json()["role"] == "analyst"

    def test_update_full_name(self, client, db_session):
        token, _, target_id = self._setup(client, db_session)
        resp = client.put(f"/api/admin/users/{target_id}",
                          headers=_auth_header(token),
                          json={"full_name": "Updated Name"})
        assert resp.status_code == 200
        assert resp.json()["full_name"] == "Updated Name"

    def test_disable_user(self, client, db_session):
        token, _, target_id = self._setup(client, db_session)
        resp = client.put(f"/api/admin/users/{target_id}",
                          headers=_auth_header(token),
                          json={"is_active": False})
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    def test_enable_user(self, client, db_session):
        token, _, target_id = self._setup(client, db_session)
        # Disable first
        client.put(f"/api/admin/users/{target_id}",
                   headers=_auth_header(token),
                   json={"is_active": False})
        # Re-enable
        resp = client.put(f"/api/admin/users/{target_id}",
                          headers=_auth_header(token),
                          json={"is_active": True})
        assert resp.status_code == 200
        assert resp.json()["is_active"] is True

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

    def test_update_invalid_uuid(self, client, db_session):
        token, _, _ = self._setup(client, db_session)
        resp = client.put("/api/admin/users/not-a-uuid",
                          headers=_auth_header(token),
                          json={"full_name": "Ghost"})
        assert resp.status_code == 404

    def test_update_invalid_role(self, client, db_session):
        token, _, target_id = self._setup(client, db_session)
        resp = client.put(f"/api/admin/users/{target_id}",
                          headers=_auth_header(token),
                          json={"role": "superadmin"})
        assert resp.status_code == 400
        assert "Invalid role" in resp.json()["detail"]

    def test_update_email_to_duplicate(self, client, db_session):
        token, _, target_id = self._setup(client, db_session)
        _create_user(db_session, email="existing@test.com", password="pass",
                     full_name="Existing")
        resp = client.put(f"/api/admin/users/{target_id}",
                          headers=_auth_header(token),
                          json={"email": "existing@test.com"})
        assert resp.status_code == 409

    def test_update_multiple_fields(self, client, db_session):
        token, _, target_id = self._setup(client, db_session)
        resp = client.put(f"/api/admin/users/{target_id}",
                          headers=_auth_header(token),
                          json={"full_name": "New Name", "role": "analyst"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["full_name"] == "New Name"
        assert data["role"] == "analyst"

    def test_disabled_user_cannot_login(self, client, db_session):
        """Integration: disabling a user prevents login."""
        token, _, target_id = self._setup(client, db_session)
        # Disable
        client.put(f"/api/admin/users/{target_id}",
                   headers=_auth_header(token),
                   json={"is_active": False})
        # Target cannot login
        resp = _login(client, "target_up@test.com", "pass")
        assert resp.status_code == 403


# ======================================================================
# INTEGRATION / FULL FLOW TESTS
# ======================================================================

class TestAdminUserManagementFlow:
    """End-to-end admin user management flows."""

    def test_create_then_list_then_update_flow(self, client, db_session):
        """Full CRUD flow: create -> list -> update -> verify changes."""
        token = _get_admin_token(client, db_session)

        # Create a user
        create_resp = client.post("/api/admin/users", headers=_auth_header(token), json={
            "email": "flowuser@example.com",
            "password": "flowpass123",
            "full_name": "Flow User",
            "role": "user",
        })
        assert create_resp.status_code == 201
        user_id = create_resp.json()["id"]

        # List -- user should appear
        list_resp = client.get("/api/admin/users", headers=_auth_header(token))
        assert list_resp.status_code == 200
        emails = [u["email"] for u in list_resp.json()]
        assert "flowuser@example.com" in emails

        # Update role to analyst
        update_resp = client.put(f"/api/admin/users/{user_id}",
                                 headers=_auth_header(token),
                                 json={"role": "analyst"})
        assert update_resp.status_code == 200
        assert update_resp.json()["role"] == "analyst"

        # Verify the update persisted via GET
        get_resp = client.get(f"/api/admin/users/{user_id}",
                              headers=_auth_header(token))
        assert get_resp.status_code == 200
        assert get_resp.json()["role"] == "analyst"

    def test_create_disable_reenable_login_flow(self, client, db_session):
        """Create user -> disable -> can't login -> re-enable -> can login."""
        token = _get_admin_token(client, db_session)

        # Create
        create_resp = client.post("/api/admin/users", headers=_auth_header(token), json={
            "email": "toggle@example.com",
            "password": "togglepass123",
            "full_name": "Toggle User",
            "role": "user",
        })
        assert create_resp.status_code == 201
        user_id = create_resp.json()["id"]

        # Can login
        login_resp = _login(client, "toggle@example.com", "togglepass123")
        assert login_resp.status_code == 200
        # Logout to avoid session token collision on re-login
        user_token = login_resp.json()["token"]
        client.post("/api/auth/logout", headers=_auth_header(user_token))

        # Disable
        client.put(f"/api/admin/users/{user_id}",
                   headers=_auth_header(token),
                   json={"is_active": False})

        # Cannot login
        login_resp2 = _login(client, "toggle@example.com", "togglepass123")
        assert login_resp2.status_code == 403

        # Re-enable
        client.put(f"/api/admin/users/{user_id}",
                   headers=_auth_header(token),
                   json={"is_active": True})

        # Can login again
        login_resp3 = _login(client, "toggle@example.com", "togglepass123")
        assert login_resp3.status_code == 200

    def test_duplicate_email_409_preserves_original(self, client, db_session):
        """Creating a duplicate doesn't modify the existing user."""
        token = _get_admin_token(client, db_session)

        # Create original
        resp1 = client.post("/api/admin/users", headers=_auth_header(token), json={
            "email": "original@example.com",
            "password": "origpass123",
            "full_name": "Original User",
            "role": "analyst",
        })
        assert resp1.status_code == 201
        original_id = resp1.json()["id"]

        # Try duplicate -- should 409
        resp2 = client.post("/api/admin/users", headers=_auth_header(token), json={
            "email": "original@example.com",
            "password": "otherpass123",
            "full_name": "Imposter",
            "role": "admin",
        })
        assert resp2.status_code == 409

        # Verify original is unchanged
        get_resp = client.get(f"/api/admin/users/{original_id}",
                              headers=_auth_header(token))
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["full_name"] == "Original User"
        assert data["role"] == "analyst"