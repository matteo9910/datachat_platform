"""
Tests for SQL Views API endpoints.

Uses an in-memory SQLite database for system DB.
Client DB operations (CREATE VIEW, DROP VIEW) are mocked out.
"""

import uuid
from unittest.mock import patch, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.models.system import (
    SystemBase, User, Session as UserSession, UserRole, ViewMetadata,
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
    """Provide a DB session with savepoint-based isolation."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db_session):
    """FastAPI TestClient wired to the test DB session with mocked client DB."""
    from app.database import get_system_db

    def _override_db():
        yield db_session

    app = FastAPI()

    from app.api.auth import router as auth_router
    from app.api.views import router as views_router
    app.include_router(auth_router)
    app.include_router(views_router)

    app.dependency_overrides[get_system_db] = _override_db

    # Mock client DB connection to avoid needing a real PostgreSQL
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with patch("app.api.views._get_client_db_connection", return_value=mock_conn):
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


def _get_admin_token(client, db_session):
    """Create admin user and return auth token."""
    _create_user(db_session, email="admin@views.test", password="adminpass",
                 role=UserRole.admin, full_name="Views Admin")
    resp = _login(client, "admin@views.test", "adminpass")
    return resp.json()["token"]


def _get_analyst_token(client, db_session):
    """Create analyst user and return auth token."""
    _create_user(db_session, email="analyst@views.test", password="analystpass",
                 role=UserRole.analyst, full_name="Views Analyst")
    resp = _login(client, "analyst@views.test", "analystpass")
    return resp.json()["token"]


def _get_user_token(client, db_session):
    """Create regular user and return auth token."""
    _create_user(db_session, email="regular@views.test", password="userpass",
                 role=UserRole.user, full_name="Regular User")
    resp = _login(client, "regular@views.test", "userpass")
    return resp.json()["token"]


# ======================================================================
# AUTH TESTS
# ======================================================================

class TestViewsAuth:
    def test_list_views_no_token_returns_401(self, client):
        resp = client.get("/api/views")
        assert resp.status_code == 401

    def test_list_views_invalid_token_returns_401(self, client):
        resp = client.get("/api/views", headers=_auth_header("garbage"))
        assert resp.status_code == 401

    def test_list_views_user_role_can_access(self, client, db_session):
        """All roles (including user) can list views."""
        token = _get_user_token(client, db_session)
        resp = client.get("/api/views", headers=_auth_header(token))
        assert resp.status_code == 200

    def test_create_view_user_role_returns_403(self, client, db_session):
        token = _get_user_token(client, db_session)
        resp = client.post("/api/views", headers=_auth_header(token),
                           json={"view_name": "test_view", "sql_query": "SELECT 1"})
        assert resp.status_code == 403

    def test_delete_view_user_role_returns_403(self, client, db_session):
        token = _get_user_token(client, db_session)
        fake_id = str(uuid.uuid4())
        resp = client.delete(f"/api/views/{fake_id}", headers=_auth_header(token))
        assert resp.status_code == 403


# ======================================================================
# NAME VALIDATION TESTS
# ======================================================================

class TestViewNameValidation:
    def test_create_view_empty_name(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/views", headers=_auth_header(token),
                           json={"view_name": "   ", "sql_query": "SELECT 1"})
        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()

    def test_create_view_invalid_characters(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/views", headers=_auth_header(token),
                           json={"view_name": "my view!", "sql_query": "SELECT 1"})
        assert resp.status_code == 400
        assert "letters" in resp.json()["detail"].lower() or "alphanumeric" in resp.json()["detail"].lower()

    def test_create_view_starts_with_number(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/views", headers=_auth_header(token),
                           json={"view_name": "123view", "sql_query": "SELECT 1"})
        assert resp.status_code == 400

    def test_create_view_sql_reserved_word(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/views", headers=_auth_header(token),
                           json={"view_name": "select", "sql_query": "SELECT 1"})
        assert resp.status_code == 400
        assert "reserved" in resp.json()["detail"].lower()

    def test_create_view_reserved_word_case_insensitive(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/views", headers=_auth_header(token),
                           json={"view_name": "SELECT", "sql_query": "SELECT 1"})
        assert resp.status_code == 400
        assert "reserved" in resp.json()["detail"].lower()

    def test_create_view_empty_sql(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/views", headers=_auth_header(token),
                           json={"view_name": "valid_name", "sql_query": "  "})
        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()

    def test_create_view_valid_name_with_underscore(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/views", headers=_auth_header(token),
                           json={"view_name": "_my_view_123", "sql_query": "SELECT 1"})
        assert resp.status_code == 201


# ======================================================================
# CRUD TESTS
# ======================================================================

class TestViewCreate:
    def test_create_view_as_admin(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/views", headers=_auth_header(token),
                           json={"view_name": "sales_summary",
                                 "sql_query": "SELECT region, SUM(amount) FROM sales GROUP BY region"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["view_name"] == "sales_summary"
        assert data["sql_query"] == "SELECT region, SUM(amount) FROM sales GROUP BY region"
        assert "id" in data
        assert data["created_by"] is not None

    def test_create_view_as_analyst(self, client, db_session):
        token = _get_analyst_token(client, db_session)
        resp = client.post("/api/views", headers=_auth_header(token),
                           json={"view_name": "analyst_view",
                                 "sql_query": "SELECT COUNT(*) FROM customers"})
        assert resp.status_code == 201
        assert resp.json()["view_name"] == "analyst_view"


class TestViewDuplicate:
    def test_create_duplicate_view_returns_409(self, client, db_session):
        token = _get_admin_token(client, db_session)
        # Create first view
        resp1 = client.post("/api/views", headers=_auth_header(token),
                            json={"view_name": "dup_test_view",
                                  "sql_query": "SELECT 1"})
        assert resp1.status_code == 201

        # Try to create duplicate
        resp2 = client.post("/api/views", headers=_auth_header(token),
                            json={"view_name": "dup_test_view",
                                  "sql_query": "SELECT 2"})
        assert resp2.status_code == 409
        assert "already exists" in resp2.json()["detail"].lower()


class TestViewList:
    def test_list_views_empty(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.get("/api/views", headers=_auth_header(token))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_views_with_data(self, client, db_session):
        token = _get_admin_token(client, db_session)
        # Create two views
        client.post("/api/views", headers=_auth_header(token),
                    json={"view_name": "view_one", "sql_query": "SELECT 1"})
        client.post("/api/views", headers=_auth_header(token),
                    json={"view_name": "view_two", "sql_query": "SELECT 2"})
        resp = client.get("/api/views", headers=_auth_header(token))
        assert resp.status_code == 200
        views = resp.json()
        assert len(views) == 2


class TestViewDelete:
    def test_delete_view(self, client, db_session):
        token = _get_admin_token(client, db_session)
        create_resp = client.post("/api/views", headers=_auth_header(token),
                                  json={"view_name": "to_delete_view",
                                        "sql_query": "SELECT 1"})
        view_id = create_resp.json()["id"]

        resp = client.delete(f"/api/views/{view_id}", headers=_auth_header(token))
        assert resp.status_code == 200
        assert "deleted" in resp.json()["message"].lower()

        # Verify it's gone
        list_resp = client.get("/api/views", headers=_auth_header(token))
        ids = [v["id"] for v in list_resp.json()]
        assert view_id not in ids

    def test_delete_nonexistent_view(self, client, db_session):
        token = _get_admin_token(client, db_session)
        fake_id = str(uuid.uuid4())
        resp = client.delete(f"/api/views/{fake_id}", headers=_auth_header(token))
        assert resp.status_code == 404

    def test_delete_invalid_uuid(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.delete("/api/views/not-a-uuid", headers=_auth_header(token))
        assert resp.status_code == 404


# ======================================================================
# INTEGRATION FLOW
# ======================================================================

class TestViewFullFlow:
    def test_create_list_delete(self, client, db_session):
        """Full CRUD flow for a SQL view."""
        token = _get_admin_token(client, db_session)

        # Create
        create_resp = client.post("/api/views", headers=_auth_header(token),
                                  json={"view_name": "flow_test_view",
                                        "sql_query": "SELECT id, name FROM products"})
        assert create_resp.status_code == 201
        view_id = create_resp.json()["id"]

        # List
        list_resp = client.get("/api/views", headers=_auth_header(token))
        assert len(list_resp.json()) >= 1
        assert any(v["id"] == view_id for v in list_resp.json())

        # Delete
        delete_resp = client.delete(f"/api/views/{view_id}",
                                    headers=_auth_header(token))
        assert delete_resp.status_code == 200

        # Verify gone
        list_resp2 = client.get("/api/views", headers=_auth_header(token))
        assert not any(v["id"] == view_id for v in list_resp2.json())