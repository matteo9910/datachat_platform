"""
Tests for Knowledge Base API endpoints.

Uses an in-memory SQLite database to avoid needing a real Neon connection.
ChromaDB training calls are mocked out.
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
    SystemBase, User, Session as UserSession, UserRole, KBPair,
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
    """FastAPI TestClient wired to the test DB session with mocked ChromaDB."""
    from app.database import get_system_db

    def _override_db():
        yield db_session

    app = FastAPI()

    from app.api.auth import router as auth_router
    from app.api.knowledge import router as knowledge_router
    app.include_router(auth_router)
    app.include_router(knowledge_router)

    app.dependency_overrides[get_system_db] = _override_db

    # Mock ChromaDB training to avoid needing actual ChromaDB/Azure
    with patch("app.api.knowledge._train_chromadb") as mock_train:
        mock_train.return_value = None
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
    _create_user(db_session, email="admin@kb.test", password="adminpass",
                 role=UserRole.admin, full_name="KB Admin")
    resp = _login(client, "admin@kb.test", "adminpass")
    return resp.json()["token"]


def _get_analyst_token(client, db_session):
    """Create analyst user and return auth token."""
    _create_user(db_session, email="analyst@kb.test", password="analystpass",
                 role=UserRole.analyst, full_name="KB Analyst")
    resp = _login(client, "analyst@kb.test", "analystpass")
    return resp.json()["token"]


def _get_user_token(client, db_session):
    """Create regular user and return auth token."""
    _create_user(db_session, email="regular@kb.test", password="userpass",
                 role=UserRole.user, full_name="Regular User")
    resp = _login(client, "regular@kb.test", "userpass")
    return resp.json()["token"]


# ======================================================================
# AUTH TESTS
# ======================================================================

class TestKBAuth:
    def test_list_pairs_no_token_returns_401(self, client):
        resp = client.get("/api/knowledge/pairs")
        assert resp.status_code == 401

    def test_list_pairs_invalid_token_returns_401(self, client):
        resp = client.get("/api/knowledge/pairs", headers=_auth_header("garbage"))
        assert resp.status_code == 401

    def test_list_pairs_user_role_returns_403(self, client, db_session):
        token = _get_user_token(client, db_session)
        resp = client.get("/api/knowledge/pairs", headers=_auth_header(token))
        assert resp.status_code == 403

    def test_create_pair_user_role_returns_403(self, client, db_session):
        token = _get_user_token(client, db_session)
        resp = client.post("/api/knowledge/pairs", headers=_auth_header(token),
                           json={"question": "test", "sql_query": "SELECT 1"})
        assert resp.status_code == 403


# ======================================================================
# CRUD TESTS
# ======================================================================

class TestKBCreatePair:
    def test_create_pair_as_admin(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/knowledge/pairs", headers=_auth_header(token),
                           json={"question": "What are total sales?",
                                 "sql_query": "SELECT SUM(amount) FROM sales"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["question"] == "What are total sales?"
        assert data["sql_query"] == "SELECT SUM(amount) FROM sales"
        assert "id" in data
        assert data["created_by"] is not None

    def test_create_pair_as_analyst(self, client, db_session):
        token = _get_analyst_token(client, db_session)
        resp = client.post("/api/knowledge/pairs", headers=_auth_header(token),
                           json={"question": "Count customers",
                                 "sql_query": "SELECT COUNT(*) FROM customers"})
        assert resp.status_code == 201
        assert resp.json()["question"] == "Count customers"

    def test_create_pair_empty_question(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/knowledge/pairs", headers=_auth_header(token),
                           json={"question": "   ", "sql_query": "SELECT 1"})
        assert resp.status_code == 400
        assert "Question" in resp.json()["detail"]

    def test_create_pair_empty_sql(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/knowledge/pairs", headers=_auth_header(token),
                           json={"question": "Valid question", "sql_query": "  "})
        assert resp.status_code == 400
        assert "SQL" in resp.json()["detail"]


class TestKBListPairs:
    def test_list_pairs_empty(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.get("/api/knowledge/pairs", headers=_auth_header(token))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_pairs_with_data(self, client, db_session):
        token = _get_admin_token(client, db_session)
        # Create two pairs
        client.post("/api/knowledge/pairs", headers=_auth_header(token),
                    json={"question": "Q1", "sql_query": "SQL1"})
        client.post("/api/knowledge/pairs", headers=_auth_header(token),
                    json={"question": "Q2", "sql_query": "SQL2"})
        resp = client.get("/api/knowledge/pairs", headers=_auth_header(token))
        assert resp.status_code == 200
        pairs = resp.json()
        assert len(pairs) == 2


class TestKBUpdatePair:
    def test_update_pair_question(self, client, db_session):
        token = _get_admin_token(client, db_session)
        create_resp = client.post("/api/knowledge/pairs", headers=_auth_header(token),
                                  json={"question": "Original Q", "sql_query": "SELECT 1"})
        pair_id = create_resp.json()["id"]
        resp = client.put(f"/api/knowledge/pairs/{pair_id}", headers=_auth_header(token),
                          json={"question": "Updated Q"})
        assert resp.status_code == 200
        assert resp.json()["question"] == "Updated Q"
        assert resp.json()["sql_query"] == "SELECT 1"

    def test_update_pair_sql(self, client, db_session):
        token = _get_admin_token(client, db_session)
        create_resp = client.post("/api/knowledge/pairs", headers=_auth_header(token),
                                  json={"question": "Q", "sql_query": "SELECT 1"})
        pair_id = create_resp.json()["id"]
        resp = client.put(f"/api/knowledge/pairs/{pair_id}", headers=_auth_header(token),
                          json={"sql_query": "SELECT 2"})
        assert resp.status_code == 200
        assert resp.json()["sql_query"] == "SELECT 2"

    def test_update_nonexistent_pair(self, client, db_session):
        token = _get_admin_token(client, db_session)
        fake_id = str(uuid.uuid4())
        resp = client.put(f"/api/knowledge/pairs/{fake_id}", headers=_auth_header(token),
                          json={"question": "Updated"})
        assert resp.status_code == 404

    def test_update_pair_empty_question(self, client, db_session):
        token = _get_admin_token(client, db_session)
        create_resp = client.post("/api/knowledge/pairs", headers=_auth_header(token),
                                  json={"question": "Q", "sql_query": "S"})
        pair_id = create_resp.json()["id"]
        resp = client.put(f"/api/knowledge/pairs/{pair_id}", headers=_auth_header(token),
                          json={"question": "  "})
        assert resp.status_code == 400


class TestKBDeletePair:
    def test_delete_pair(self, client, db_session):
        token = _get_admin_token(client, db_session)
        create_resp = client.post("/api/knowledge/pairs", headers=_auth_header(token),
                                  json={"question": "To delete", "sql_query": "SELECT 1"})
        pair_id = create_resp.json()["id"]

        # Mock the ChromaDB delete
        with patch("app.services.vanna_service.get_vanna_service", return_value=MagicMock()):
            resp = client.delete(f"/api/knowledge/pairs/{pair_id}",
                                 headers=_auth_header(token))
        assert resp.status_code == 200
        assert "deleted" in resp.json()["message"].lower()

        # Verify it's gone
        list_resp = client.get("/api/knowledge/pairs", headers=_auth_header(token))
        ids = [p["id"] for p in list_resp.json()]
        assert pair_id not in ids

    def test_delete_nonexistent_pair(self, client, db_session):
        token = _get_admin_token(client, db_session)
        fake_id = str(uuid.uuid4())
        resp = client.delete(f"/api/knowledge/pairs/{fake_id}",
                             headers=_auth_header(token))
        assert resp.status_code == 404


# ======================================================================
# INTEGRATION FLOW
# ======================================================================

class TestKBFullFlow:
    def test_create_list_update_delete(self, client, db_session):
        """Full CRUD flow for a KB pair."""
        token = _get_admin_token(client, db_session)

        # Create
        create_resp = client.post("/api/knowledge/pairs", headers=_auth_header(token),
                                  json={"question": "Flow Q", "sql_query": "Flow SQL"})
        assert create_resp.status_code == 201
        pair_id = create_resp.json()["id"]

        # List
        list_resp = client.get("/api/knowledge/pairs", headers=_auth_header(token))
        assert len(list_resp.json()) >= 1
        assert any(p["id"] == pair_id for p in list_resp.json())

        # Update
        update_resp = client.put(f"/api/knowledge/pairs/{pair_id}",
                                 headers=_auth_header(token),
                                 json={"question": "Updated Flow Q",
                                       "sql_query": "Updated Flow SQL"})
        assert update_resp.status_code == 200
        assert update_resp.json()["question"] == "Updated Flow Q"

        # Delete
        with patch("app.services.vanna_service.get_vanna_service", return_value=MagicMock()):
            delete_resp = client.delete(f"/api/knowledge/pairs/{pair_id}",
                                        headers=_auth_header(token))
        assert delete_resp.status_code == 200

        # Verify gone
        list_resp2 = client.get("/api/knowledge/pairs", headers=_auth_header(token))
        assert not any(p["id"] == pair_id for p in list_resp2.json())
