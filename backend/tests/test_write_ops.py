"""
Tests for Write Operations API — whitelist, generate, execute, audit, auth.

Uses an in-memory SQLite database to avoid needing a real Neon connection.
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
    SystemBase, User, Session as UserSession, UserRole,
    WriteWhitelist, AuditLog,
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
    from app.api.write import router as write_router
    app.include_router(auth_router)
    app.include_router(write_router)

    app.dependency_overrides[get_system_db] = _override_db

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_user(db_session, email="user@test.com", password="secret123",
                 role=UserRole.user, full_name="Test User"):
    from app.services.auth_service import hash_password
    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        role=role,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _login(client, email, password):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def _auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def _get_admin_token(client, db_session):
    _create_user(db_session, email="admin@write.test", password="adminpass",
                 role=UserRole.admin, full_name="Write Admin")
    resp = _login(client, "admin@write.test", "adminpass")
    return resp.json()["token"]


def _get_analyst_token(client, db_session):
    _create_user(db_session, email="analyst@write.test", password="analystpass",
                 role=UserRole.analyst, full_name="Write Analyst")
    resp = _login(client, "analyst@write.test", "analystpass")
    return resp.json()["token"]


def _get_user_token(client, db_session):
    _create_user(db_session, email="regular@write.test", password="userpass",
                 role=UserRole.user, full_name="Regular User")
    resp = _login(client, "regular@write.test", "userpass")
    return resp.json()["token"]


def _add_whitelist(db_session, table_name, column_name):
    entry = WriteWhitelist(
        id=uuid.uuid4(),
        table_name=table_name,
        column_name=column_name,
    )
    db_session.add(entry)
    db_session.flush()
    return entry


# ======================================================================
# UNIT TESTS — Internal helpers
# ======================================================================

class TestDestructiveDetection:
    def test_delete_detected(self):
        from app.api.write import _is_destructive
        assert _is_destructive("DELETE FROM orders WHERE id = 1") is True

    def test_truncate_detected(self):
        from app.api.write import _is_destructive
        assert _is_destructive("TRUNCATE TABLE orders") is True

    def test_drop_table_detected(self):
        from app.api.write import _is_destructive
        assert _is_destructive("DROP TABLE orders") is True

    def test_alter_drop_detected(self):
        from app.api.write import _is_destructive
        assert _is_destructive("ALTER TABLE orders DROP COLUMN name") is True

    def test_update_not_destructive(self):
        from app.api.write import _is_destructive
        assert _is_destructive("UPDATE orders SET name = 'x' WHERE id = 1") is False

    def test_insert_not_destructive(self):
        from app.api.write import _is_destructive
        assert _is_destructive("INSERT INTO orders (name) VALUES ('x')") is False


class TestExtractTargets:
    def test_update_table(self):
        from app.api.write import _extract_target_tables
        tables = _extract_target_tables("UPDATE orders SET name = 'x' WHERE id = 1")
        assert "orders" in tables

    def test_insert_table(self):
        from app.api.write import _extract_target_tables
        tables = _extract_target_tables("INSERT INTO products (name) VALUES ('x')")
        assert "products" in tables

    def test_update_columns(self):
        from app.api.write import _extract_target_columns
        cols = _extract_target_columns("UPDATE orders SET name = 'x', price = 10 WHERE id = 1")
        assert "name" in cols
        assert "price" in cols

    def test_insert_columns(self):
        from app.api.write import _extract_target_columns
        cols = _extract_target_columns("INSERT INTO products (name, price) VALUES ('x', 10)")
        assert "name" in cols
        assert "price" in cols


class TestBulkDetection:
    def test_update_without_where_is_bulk(self):
        from app.api.write import _is_bulk_operation
        assert _is_bulk_operation("UPDATE orders SET name = 'x'") is True

    def test_update_with_where_not_bulk(self):
        from app.api.write import _is_bulk_operation
        assert _is_bulk_operation("UPDATE orders SET name = 'x' WHERE id = 1") is False

    def test_update_where_true_is_bulk(self):
        from app.api.write import _is_bulk_operation
        assert _is_bulk_operation("UPDATE orders SET name = 'x' WHERE TRUE") is True

    def test_insert_never_bulk(self):
        from app.api.write import _is_bulk_operation
        assert _is_bulk_operation("INSERT INTO orders (name) VALUES ('x')") is False


# ======================================================================
# AUTH TESTS
# ======================================================================

class TestWriteAuth:
    def test_whitelist_no_token_returns_401(self, client):
        resp = client.get("/api/write/whitelist")
        assert resp.status_code == 401

    def test_whitelist_user_role_returns_403(self, client, db_session):
        token = _get_user_token(client, db_session)
        resp = client.get("/api/write/whitelist", headers=_auth_header(token))
        assert resp.status_code == 403

    def test_whitelist_analyst_can_read(self, client, db_session):
        token = _get_analyst_token(client, db_session)
        resp = client.get("/api/write/whitelist", headers=_auth_header(token))
        assert resp.status_code == 200

    def test_whitelist_admin_can_read(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.get("/api/write/whitelist", headers=_auth_header(token))
        assert resp.status_code == 200

    def test_save_whitelist_analyst_returns_403(self, client, db_session):
        token = _get_analyst_token(client, db_session)
        resp = client.post("/api/write/whitelist",
                           headers=_auth_header(token),
                           json={"entries": [{"table_name": "t", "column_name": "c"}]})
        assert resp.status_code == 403

    def test_save_whitelist_admin_allowed(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/write/whitelist",
                           headers=_auth_header(token),
                           json={"entries": [{"table_name": "orders", "column_name": "status"}]})
        assert resp.status_code == 200

    def test_generate_user_role_returns_403(self, client, db_session):
        token = _get_user_token(client, db_session)
        resp = client.post("/api/write/generate",
                           headers=_auth_header(token),
                           json={"nl_text": "update something"})
        assert resp.status_code == 403

    def test_execute_user_role_returns_403(self, client, db_session):
        token = _get_user_token(client, db_session)
        resp = client.post("/api/write/execute",
                           headers=_auth_header(token),
                           json={"sql": "UPDATE t SET c = 1"})
        assert resp.status_code == 403

    def test_audit_logs_user_returns_403(self, client, db_session):
        token = _get_user_token(client, db_session)
        resp = client.get("/api/audit/logs", headers=_auth_header(token))
        assert resp.status_code == 403

    def test_audit_logs_analyst_returns_403(self, client, db_session):
        token = _get_analyst_token(client, db_session)
        resp = client.get("/api/audit/logs", headers=_auth_header(token))
        assert resp.status_code == 403

    def test_audit_logs_admin_allowed(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.get("/api/audit/logs", headers=_auth_header(token))
        assert resp.status_code == 200


# ======================================================================
# WHITELIST CRUD TESTS
# ======================================================================

class TestWhitelistCRUD:
    def test_empty_whitelist(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.get("/api/write/whitelist", headers=_auth_header(token))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_save_and_list_whitelist(self, client, db_session):
        token = _get_admin_token(client, db_session)
        save_resp = client.post("/api/write/whitelist",
                                headers=_auth_header(token),
                                json={"entries": [
                                    {"table_name": "orders", "column_name": "status"},
                                    {"table_name": "orders", "column_name": "quantity"},
                                ]})
        assert save_resp.status_code == 200
        assert len(save_resp.json()) == 2

        list_resp = client.get("/api/write/whitelist", headers=_auth_header(token))
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 2

    def test_delete_whitelist_entry(self, client, db_session):
        token = _get_admin_token(client, db_session)
        save_resp = client.post("/api/write/whitelist",
                                headers=_auth_header(token),
                                json={"entries": [
                                    {"table_name": "products", "column_name": "price"},
                                ]})
        entry_id = save_resp.json()[0]["id"]

        del_resp = client.delete(f"/api/write/whitelist/{entry_id}",
                                 headers=_auth_header(token))
        assert del_resp.status_code == 200

        list_resp = client.get("/api/write/whitelist", headers=_auth_header(token))
        ids = [e["id"] for e in list_resp.json()]
        assert entry_id not in ids

    def test_delete_nonexistent_returns_404(self, client, db_session):
        token = _get_admin_token(client, db_session)
        fake_id = str(uuid.uuid4())
        resp = client.delete(f"/api/write/whitelist/{fake_id}",
                             headers=_auth_header(token))
        assert resp.status_code == 404

    def test_duplicate_whitelist_entry_not_duplicated(self, client, db_session):
        token = _get_admin_token(client, db_session)
        entry = {"table_name": "orders", "column_name": "status"}
        client.post("/api/write/whitelist",
                     headers=_auth_header(token), json={"entries": [entry]})
        resp2 = client.post("/api/write/whitelist",
                            headers=_auth_header(token), json={"entries": [entry]})
        assert resp2.status_code == 200
        # Should return 1 entry (the existing one) not create a duplicate
        assert len(resp2.json()) == 1


# ======================================================================
# GENERATE SQL TESTS (mocked LLM)
# ======================================================================

class TestGenerateSQL:
    @patch("app.api.write.get_llm_provider_manager")
    @patch("app.api.write._get_client_schema_ddl")
    def test_generate_update_success(self, mock_ddl, mock_llm, client, db_session):
        mock_ddl.return_value = "TABLE orders (id integer, status text, quantity integer)"

        mock_manager = MagicMock()
        mock_manager.complete.return_value = {
            "content": "UPDATE orders SET status = 'shipped' WHERE id = 1;"
        }
        mock_llm.return_value = mock_manager

        _add_whitelist(db_session, "orders", "status")

        token = _get_analyst_token(client, db_session)
        resp = client.post("/api/write/generate",
                           headers=_auth_header(token),
                           json={"nl_text": "Set order 1 status to shipped"})
        assert resp.status_code == 200
        data = resp.json()
        assert "UPDATE" in data["sql"]
        assert "orders" in data["target_tables"]
        assert "status" in data["target_columns"]

    @patch("app.api.write.get_llm_provider_manager")
    @patch("app.api.write._get_client_schema_ddl")
    def test_generate_blocks_delete(self, mock_ddl, mock_llm, client, db_session):
        mock_ddl.return_value = "TABLE orders (id integer, status text)"

        mock_manager = MagicMock()
        mock_manager.complete.return_value = {
            "content": "DELETE FROM orders WHERE id = 1;"
        }
        mock_llm.return_value = mock_manager

        _add_whitelist(db_session, "orders", "status")

        token = _get_admin_token(client, db_session)
        resp = client.post("/api/write/generate",
                           headers=_auth_header(token),
                           json={"nl_text": "Delete order 1"})
        assert resp.status_code == 400
        assert "Destructive" in resp.json()["detail"]

    @patch("app.api.write.get_llm_provider_manager")
    @patch("app.api.write._get_client_schema_ddl")
    def test_generate_blocks_non_whitelisted_table(self, mock_ddl, mock_llm, client, db_session):
        mock_ddl.return_value = "TABLE orders (id integer, status text)"

        mock_manager = MagicMock()
        mock_manager.complete.return_value = {
            "content": "UPDATE secret_table SET data = 'x' WHERE id = 1;"
        }
        mock_llm.return_value = mock_manager

        _add_whitelist(db_session, "orders", "status")

        token = _get_admin_token(client, db_session)
        resp = client.post("/api/write/generate",
                           headers=_auth_header(token),
                           json={"nl_text": "Update secret_table"})
        assert resp.status_code == 403
        assert "not in the write whitelist" in resp.json()["detail"]

    @patch("app.api.write.get_llm_provider_manager")
    @patch("app.api.write._get_client_schema_ddl")
    def test_generate_blocks_non_whitelisted_column(self, mock_ddl, mock_llm, client, db_session):
        mock_ddl.return_value = "TABLE orders (id integer, status text, secret_col text)"

        mock_manager = MagicMock()
        mock_manager.complete.return_value = {
            "content": "UPDATE orders SET secret_col = 'x' WHERE id = 1;"
        }
        mock_llm.return_value = mock_manager

        _add_whitelist(db_session, "orders", "status")

        token = _get_admin_token(client, db_session)
        resp = client.post("/api/write/generate",
                           headers=_auth_header(token),
                           json={"nl_text": "Update orders secret_col"})
        assert resp.status_code == 403
        assert "not in the write whitelist" in resp.json()["detail"]

    @patch("app.api.write.get_llm_provider_manager")
    @patch("app.api.write._get_client_schema_ddl")
    def test_generate_empty_whitelist_returns_403(self, mock_ddl, mock_llm, client, db_session):
        mock_ddl.return_value = "TABLE orders (id integer, status text)"

        mock_manager = MagicMock()
        mock_manager.complete.return_value = {
            "content": "UPDATE orders SET status = 'x' WHERE id = 1;"
        }
        mock_llm.return_value = mock_manager

        token = _get_admin_token(client, db_session)
        resp = client.post("/api/write/generate",
                           headers=_auth_header(token),
                           json={"nl_text": "Update order status"})
        assert resp.status_code == 403
        assert "whitelist" in resp.json()["detail"].lower()

    @patch("app.api.write.get_llm_provider_manager")
    @patch("app.api.write._get_client_schema_ddl")
    def test_generate_detects_bulk(self, mock_ddl, mock_llm, client, db_session):
        mock_ddl.return_value = "TABLE orders (id integer, status text)"

        mock_manager = MagicMock()
        mock_manager.complete.return_value = {
            "content": "UPDATE orders SET status = 'pending'"
        }
        mock_llm.return_value = mock_manager

        _add_whitelist(db_session, "orders", "status")

        token = _get_admin_token(client, db_session)
        resp = client.post("/api/write/generate",
                           headers=_auth_header(token),
                           json={"nl_text": "Set all orders to pending"})
        assert resp.status_code == 200
        assert resp.json()["is_bulk"] is True


# ======================================================================
# EXECUTE SQL TESTS (mocked MCP client)
# ======================================================================

class TestExecuteSQL:
    @patch("app.api.write.mcp_postgres_client")
    def test_execute_success(self, mock_mcp, client, db_session):
        mock_mcp._connected = True
        mock_mcp.execute_query.return_value = []

        _add_whitelist(db_session, "orders", "status")

        token = _get_admin_token(client, db_session)
        resp = client.post("/api/write/execute",
                           headers=_auth_header(token),
                           json={"sql": "UPDATE orders SET status = 'shipped' WHERE id = 1"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    @patch("app.api.write.mcp_postgres_client")
    def test_execute_blocks_delete(self, mock_mcp, client, db_session):
        mock_mcp._connected = True

        _add_whitelist(db_session, "orders", "status")

        token = _get_admin_token(client, db_session)
        resp = client.post("/api/write/execute",
                           headers=_auth_header(token),
                           json={"sql": "DELETE FROM orders WHERE id = 1"})
        assert resp.status_code == 400
        assert "Destructive" in resp.json()["detail"]

    @patch("app.api.write.mcp_postgres_client")
    def test_execute_bulk_requires_confirmation(self, mock_mcp, client, db_session):
        mock_mcp._connected = True

        _add_whitelist(db_session, "orders", "status")

        token = _get_admin_token(client, db_session)
        resp = client.post("/api/write/execute",
                           headers=_auth_header(token),
                           json={"sql": "UPDATE orders SET status = 'pending'"})
        assert resp.status_code == 400
        assert "bulk operation" in resp.json()["detail"].lower()

    @patch("app.api.write.mcp_postgres_client")
    def test_execute_bulk_with_confirmation(self, mock_mcp, client, db_session):
        mock_mcp._connected = True
        mock_mcp.execute_query.return_value = []

        _add_whitelist(db_session, "orders", "status")

        token = _get_admin_token(client, db_session)
        resp = client.post("/api/write/execute",
                           headers=_auth_header(token),
                           json={
                               "sql": "UPDATE orders SET status = 'pending'",
                               "extra_confirmation": True,
                           })
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @patch("app.api.write.mcp_postgres_client")
    def test_execute_logs_to_audit(self, mock_mcp, client, db_session):
        mock_mcp._connected = True
        mock_mcp.execute_query.return_value = []

        _add_whitelist(db_session, "orders", "status")

        token = _get_admin_token(client, db_session)
        client.post("/api/write/execute",
                     headers=_auth_header(token),
                     json={"sql": "UPDATE orders SET status = 'shipped' WHERE id = 1"})

        # Verify audit log was created
        audit_entries = db_session.query(AuditLog).filter(
            AuditLog.action == "write_execute"
        ).all()
        assert len(audit_entries) >= 1

    @patch("app.api.write.mcp_postgres_client")
    def test_execute_db_not_connected(self, mock_mcp, client, db_session):
        mock_mcp._connected = False

        _add_whitelist(db_session, "orders", "status")

        token = _get_admin_token(client, db_session)
        resp = client.post("/api/write/execute",
                           headers=_auth_header(token),
                           json={"sql": "UPDATE orders SET status = 'x' WHERE id = 1"})
        assert resp.status_code == 400
        assert "not connected" in resp.json()["detail"].lower()


# ======================================================================
# AUDIT LOG TESTS
# ======================================================================

class TestAuditLog:
    def test_audit_log_empty(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.get("/api/audit/logs", headers=_auth_header(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 0
        assert isinstance(data["logs"], list)

    def test_audit_log_pagination(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.get("/api/audit/logs?page=1&page_size=5",
                          headers=_auth_header(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        assert data["page_size"] == 5
