"""
Tests for Dashboard API endpoints.

Uses an in-memory SQLite database for system DB.
LLM and MCP client calls are mocked out.
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
    SystemBase, User, Session as UserSession, UserRole, DashboardMetadata,
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
    from app.config import settings
    monkeypatch.setattr(settings, "secret_key", "test-secret-key-for-jwt")
    monkeypatch.setattr(settings, "jwt_expiry_hours", 24)
    monkeypatch.setattr(settings, "seed_admin_password", "TestAdminPass123!")
    monkeypatch.setattr(settings, "system_database_url", "sqlite://")


@pytest.fixture()
def db_session(test_engine):
    connection = test_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db_session):
    from app.database import get_system_db

    def _override_db():
        yield db_session

    app = FastAPI()

    from app.api.auth import router as auth_router
    from app.api.dashboard import router as dashboard_router
    app.include_router(auth_router)
    app.include_router(dashboard_router)

    app.dependency_overrides[get_system_db] = _override_db

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_user(db_session, email="user@test.com", password="secret123",
                 role=UserRole.user, full_name="Test User", is_active=True):
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
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    return resp


def _auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def _get_user_token(client, db_session, email="dash@test.com"):
    _create_user(db_session, email=email, password="userpass",
                 role=UserRole.user, full_name="Dashboard User")
    resp = _login(client, email, "userpass")
    return resp.json()["token"]


# ======================================================================
# AUTH TESTS
# ======================================================================

class TestDashboardAuth:
    def test_list_dashboards_no_token_returns_401(self, client):
        resp = client.get("/api/dashboards")
        assert resp.status_code == 401

    def test_save_dashboard_no_token_returns_401(self, client):
        resp = client.post("/api/dashboards", json={"name": "Test"})
        assert resp.status_code == 401

    def test_delete_dashboard_no_token_returns_401(self, client):
        resp = client.delete(f"/api/dashboards/{uuid.uuid4()}")
        assert resp.status_code == 401


# ======================================================================
# CRUD TESTS
# ======================================================================

class TestDashboardCRUD:
    def test_create_dashboard(self, client, db_session):
        token = _get_user_token(client, db_session)
        resp = client.post(
            "/api/dashboards",
            headers=_auth_header(token),
            json={
                "name": "Sales Dashboard",
                "layout": {"columns": 2},
                "charts": [{"title": "Revenue", "sql": "SELECT 1", "chart_type": "bar"}],
                "filters": {"region": ["East"]},
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Sales Dashboard"
        assert data["charts"] is not None
        assert len(data["charts"]) == 1
        assert data["id"] is not None

    def test_list_dashboards_empty(self, client, db_session):
        token = _get_user_token(client, db_session)
        resp = client.get("/api/dashboards", headers=_auth_header(token))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_dashboards_with_data(self, client, db_session):
        token = _get_user_token(client, db_session)
        client.post("/api/dashboards", headers=_auth_header(token),
                     json={"name": "Dash 1", "charts": [{"title": "A"}]})
        client.post("/api/dashboards", headers=_auth_header(token),
                     json={"name": "Dash 2"})
        resp = client.get("/api/dashboards", headers=_auth_header(token))
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 2

    def test_get_dashboard_by_id(self, client, db_session):
        token = _get_user_token(client, db_session)
        create_resp = client.post(
            "/api/dashboards", headers=_auth_header(token),
            json={"name": "Detail Test", "layout": {"x": 1}},
        )
        dash_id = create_resp.json()["id"]
        resp = client.get(f"/api/dashboards/{dash_id}", headers=_auth_header(token))
        assert resp.status_code == 200
        assert resp.json()["name"] == "Detail Test"

    def test_get_dashboard_not_found(self, client, db_session):
        token = _get_user_token(client, db_session)
        resp = client.get(f"/api/dashboards/{uuid.uuid4()}", headers=_auth_header(token))
        assert resp.status_code == 404

    def test_update_dashboard(self, client, db_session):
        token = _get_user_token(client, db_session)
        create_resp = client.post(
            "/api/dashboards", headers=_auth_header(token),
            json={"name": "Original"},
        )
        dash_id = create_resp.json()["id"]
        update_resp = client.put(
            f"/api/dashboards/{dash_id}", headers=_auth_header(token),
            json={"name": "Updated", "charts": [{"title": "New Chart"}]},
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["name"] == "Updated"
        assert len(update_resp.json()["charts"]) == 1

    def test_delete_dashboard(self, client, db_session):
        token = _get_user_token(client, db_session)
        create_resp = client.post(
            "/api/dashboards", headers=_auth_header(token),
            json={"name": "To Delete"},
        )
        dash_id = create_resp.json()["id"]
        del_resp = client.delete(f"/api/dashboards/{dash_id}", headers=_auth_header(token))
        assert del_resp.status_code == 200
        assert del_resp.json()["status"] == "deleted"

        # Verify gone
        get_resp = client.get(f"/api/dashboards/{dash_id}", headers=_auth_header(token))
        assert get_resp.status_code == 404

    def test_delete_nonexistent_returns_404(self, client, db_session):
        token = _get_user_token(client, db_session)
        resp = client.delete(f"/api/dashboards/{uuid.uuid4()}", headers=_auth_header(token))
        assert resp.status_code == 404


# ======================================================================
# FULL FLOW
# ======================================================================

class TestDashboardFullFlow:
    def test_create_list_update_delete(self, client, db_session):
        token = _get_user_token(client, db_session)

        # Create
        create_resp = client.post(
            "/api/dashboards", headers=_auth_header(token),
            json={"name": "Flow Test", "charts": [{"title": "C1"}]},
        )
        assert create_resp.status_code == 201
        dash_id = create_resp.json()["id"]

        # List
        list_resp = client.get("/api/dashboards", headers=_auth_header(token))
        assert any(d["id"] == dash_id for d in list_resp.json())

        # Update
        update_resp = client.put(
            f"/api/dashboards/{dash_id}", headers=_auth_header(token),
            json={"name": "Updated Flow"},
        )
        assert update_resp.json()["name"] == "Updated Flow"

        # Delete
        del_resp = client.delete(f"/api/dashboards/{dash_id}", headers=_auth_header(token))
        assert del_resp.status_code == 200

        # Verify deleted
        list_resp2 = client.get("/api/dashboards", headers=_auth_header(token))
        assert not any(d["id"] == dash_id for d in list_resp2.json())


# ======================================================================
# HELPER FUNCTION TESTS
# ======================================================================

class TestHelperFunctions:
    def test_inject_where_no_existing_where(self):
        from app.api.dashboard import _inject_where_clauses
        sql = "SELECT region, SUM(sales) FROM orders GROUP BY region"
        result = _inject_where_clauses(sql, {"region": "East"})
        assert "WHERE" in result
        assert "region = 'East'" in result
        assert "GROUP BY" in result

    def test_inject_where_with_existing_where(self):
        from app.api.dashboard import _inject_where_clauses
        sql = "SELECT * FROM orders WHERE status = 'active' ORDER BY id"
        result = _inject_where_clauses(sql, {"region": "West"})
        assert "region = 'West'" in result
        assert "ORDER BY" in result

    def test_inject_where_list_filter(self):
        from app.api.dashboard import _inject_where_clauses
        sql = "SELECT * FROM orders"
        result = _inject_where_clauses(sql, {"region": ["East", "West"]})
        assert "IN" in result
        assert "'East'" in result
        assert "'West'" in result

    def test_inject_where_range_filter(self):
        from app.api.dashboard import _inject_where_clauses
        sql = "SELECT * FROM orders"
        result = _inject_where_clauses(sql, {"sales": {"min": 100, "max": 500}})
        assert ">=" in result
        assert "<=" in result

    def test_inject_where_empty_filters(self):
        from app.api.dashboard import _inject_where_clauses
        sql = "SELECT * FROM orders"
        result = _inject_where_clauses(sql, {})
        assert result == sql

    def test_build_grid_layout(self):
        from app.api.dashboard import _build_grid_layout
        layout = _build_grid_layout(4)
        assert layout["columns"] == 2
        assert len(layout["positions"]) == 4

    def test_limit_query_no_existing_limit(self):
        from app.api.dashboard import _limit_query
        result = _limit_query("SELECT * FROM orders", 100)
        assert "LIMIT 100" in result

    def test_limit_query_with_existing_limit(self):
        from app.api.dashboard import _limit_query
        sql = "SELECT * FROM orders LIMIT 50"
        result = _limit_query(sql, 100)
        assert result == sql

    def test_quote_val_string(self):
        from app.api.dashboard import _quote_val
        assert _quote_val("hello") == "'hello'"

    def test_quote_val_number(self):
        from app.api.dashboard import _quote_val
        assert _quote_val(42) == "42"

    def test_quote_val_sql_injection(self):
        from app.api.dashboard import _quote_val
        result = _quote_val("test'; DROP TABLE --")
        assert "''" in result