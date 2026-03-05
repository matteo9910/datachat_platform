"""
Tests for Instructions API endpoints.

Uses an in-memory SQLite database to avoid needing a real Neon connection.
Follows the same pattern as test_knowledge.py.
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
    SystemBase, User, Session as UserSession, UserRole, Instruction, InstructionType,
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
    """FastAPI TestClient wired to the test DB session."""
    from app.database import get_system_db

    def _override_db():
        yield db_session

    app = FastAPI()

    from app.api.auth import router as auth_router
    from app.api.knowledge import router as knowledge_router
    app.include_router(auth_router)
    app.include_router(knowledge_router)

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


def _get_admin_token(client, db_session):
    """Create admin user and return auth token."""
    _create_user(db_session, email="admin@inst.test", password="adminpass",
                 role=UserRole.admin, full_name="Inst Admin")
    resp = _login(client, "admin@inst.test", "adminpass")
    return resp.json()["token"]


def _get_analyst_token(client, db_session):
    """Create analyst user and return auth token."""
    _create_user(db_session, email="analyst@inst.test", password="analystpass",
                 role=UserRole.analyst, full_name="Inst Analyst")
    resp = _login(client, "analyst@inst.test", "analystpass")
    return resp.json()["token"]


def _get_user_token(client, db_session):
    """Create regular user and return auth token."""
    _create_user(db_session, email="regular@inst.test", password="userpass",
                 role=UserRole.user, full_name="Regular User")
    resp = _login(client, "regular@inst.test", "userpass")
    return resp.json()["token"]


# ======================================================================
# AUTH TESTS
# ======================================================================

class TestInstructionAuth:
    def test_list_instructions_no_token_returns_401(self, client):
        resp = client.get("/api/knowledge/instructions")
        assert resp.status_code == 401

    def test_list_instructions_invalid_token_returns_401(self, client):
        resp = client.get("/api/knowledge/instructions", headers=_auth_header("garbage"))
        assert resp.status_code == 401

    def test_list_instructions_user_role_returns_403(self, client, db_session):
        token = _get_user_token(client, db_session)
        resp = client.get("/api/knowledge/instructions", headers=_auth_header(token))
        assert resp.status_code == 403

    def test_create_instruction_user_role_returns_403(self, client, db_session):
        token = _get_user_token(client, db_session)
        resp = client.post("/api/knowledge/instructions", headers=_auth_header(token),
                           json={"type": "global", "text": "Always use LIMIT"})
        assert resp.status_code == 403

    def test_update_instruction_user_role_returns_403(self, client, db_session):
        token = _get_user_token(client, db_session)
        fake_id = str(uuid.uuid4())
        resp = client.put(f"/api/knowledge/instructions/{fake_id}",
                          headers=_auth_header(token),
                          json={"text": "New text"})
        assert resp.status_code == 403

    def test_delete_instruction_user_role_returns_403(self, client, db_session):
        token = _get_user_token(client, db_session)
        fake_id = str(uuid.uuid4())
        resp = client.delete(f"/api/knowledge/instructions/{fake_id}",
                             headers=_auth_header(token))
        assert resp.status_code == 403


# ======================================================================
# CREATE TESTS
# ======================================================================

class TestInstructionCreate:
    def test_create_global_instruction_as_admin(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/knowledge/instructions", headers=_auth_header(token),
                           json={"type": "global", "text": "Always use LIMIT 1000"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["type"] == "global"
        assert data["text"] == "Always use LIMIT 1000"
        assert data["topic"] is None
        assert "id" in data
        assert data["created_by"] is not None

    def test_create_topic_instruction_as_analyst(self, client, db_session):
        token = _get_analyst_token(client, db_session)
        resp = client.post("/api/knowledge/instructions", headers=_auth_header(token),
                           json={"type": "topic", "topic": "vendite",
                                 "text": "Use fact_orders for sales data"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["type"] == "topic"
        assert data["topic"] == "vendite"
        assert data["text"] == "Use fact_orders for sales data"

    def test_create_instruction_empty_text(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/knowledge/instructions", headers=_auth_header(token),
                           json={"type": "global", "text": "   "})
        assert resp.status_code == 400
        assert "text" in resp.json()["detail"].lower()

    def test_create_topic_instruction_missing_topic(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/knowledge/instructions", headers=_auth_header(token),
                           json={"type": "topic", "text": "Some rule"})
        assert resp.status_code == 400
        assert "topic" in resp.json()["detail"].lower()

    def test_create_instruction_invalid_type(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/knowledge/instructions", headers=_auth_header(token),
                           json={"type": "invalid", "text": "Some rule"})
        assert resp.status_code == 400
        assert "type" in resp.json()["detail"].lower()


# ======================================================================
# LIST TESTS
# ======================================================================

class TestInstructionList:
    def test_list_instructions_empty(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.get("/api/knowledge/instructions", headers=_auth_header(token))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_instructions_with_data(self, client, db_session):
        token = _get_admin_token(client, db_session)
        client.post("/api/knowledge/instructions", headers=_auth_header(token),
                    json={"type": "global", "text": "Rule 1"})
        client.post("/api/knowledge/instructions", headers=_auth_header(token),
                    json={"type": "topic", "topic": "sales", "text": "Rule 2"})
        resp = client.get("/api/knowledge/instructions", headers=_auth_header(token))
        assert resp.status_code == 200
        assert len(resp.json()) == 2


# ======================================================================
# UPDATE TESTS
# ======================================================================

class TestInstructionUpdate:
    def test_update_instruction_text(self, client, db_session):
        token = _get_admin_token(client, db_session)
        create_resp = client.post("/api/knowledge/instructions", headers=_auth_header(token),
                                  json={"type": "global", "text": "Original rule"})
        inst_id = create_resp.json()["id"]
        resp = client.put(f"/api/knowledge/instructions/{inst_id}", headers=_auth_header(token),
                          json={"text": "Updated rule"})
        assert resp.status_code == 200
        assert resp.json()["text"] == "Updated rule"
        assert resp.json()["type"] == "global"

    def test_update_instruction_type_and_topic(self, client, db_session):
        token = _get_admin_token(client, db_session)
        create_resp = client.post("/api/knowledge/instructions", headers=_auth_header(token),
                                  json={"type": "global", "text": "A rule"})
        inst_id = create_resp.json()["id"]
        resp = client.put(f"/api/knowledge/instructions/{inst_id}", headers=_auth_header(token),
                          json={"type": "topic", "topic": "revenue"})
        assert resp.status_code == 200
        assert resp.json()["type"] == "topic"
        assert resp.json()["topic"] == "revenue"

    def test_update_nonexistent_instruction(self, client, db_session):
        token = _get_admin_token(client, db_session)
        fake_id = str(uuid.uuid4())
        resp = client.put(f"/api/knowledge/instructions/{fake_id}", headers=_auth_header(token),
                          json={"text": "Updated"})
        assert resp.status_code == 404

    def test_update_instruction_empty_text(self, client, db_session):
        token = _get_admin_token(client, db_session)
        create_resp = client.post("/api/knowledge/instructions", headers=_auth_header(token),
                                  json={"type": "global", "text": "Original"})
        inst_id = create_resp.json()["id"]
        resp = client.put(f"/api/knowledge/instructions/{inst_id}", headers=_auth_header(token),
                          json={"text": "  "})
        assert resp.status_code == 400

    def test_update_topic_type_without_topic(self, client, db_session):
        token = _get_admin_token(client, db_session)
        create_resp = client.post("/api/knowledge/instructions", headers=_auth_header(token),
                                  json={"type": "global", "text": "Rule"})
        inst_id = create_resp.json()["id"]
        # Change to topic without providing topic
        resp = client.put(f"/api/knowledge/instructions/{inst_id}", headers=_auth_header(token),
                          json={"type": "topic"})
        assert resp.status_code == 400


# ======================================================================
# DELETE TESTS
# ======================================================================

class TestInstructionDelete:
    def test_delete_instruction(self, client, db_session):
        token = _get_admin_token(client, db_session)
        create_resp = client.post("/api/knowledge/instructions", headers=_auth_header(token),
                                  json={"type": "global", "text": "To delete"})
        inst_id = create_resp.json()["id"]
        resp = client.delete(f"/api/knowledge/instructions/{inst_id}",
                             headers=_auth_header(token))
        assert resp.status_code == 200
        assert "deleted" in resp.json()["message"].lower()

        # Verify it's gone
        list_resp = client.get("/api/knowledge/instructions", headers=_auth_header(token))
        ids = [i["id"] for i in list_resp.json()]
        assert inst_id not in ids

    def test_delete_nonexistent_instruction(self, client, db_session):
        token = _get_admin_token(client, db_session)
        fake_id = str(uuid.uuid4())
        resp = client.delete(f"/api/knowledge/instructions/{fake_id}",
                             headers=_auth_header(token))
        assert resp.status_code == 404


# ======================================================================
# INTEGRATION FLOW
# ======================================================================

class TestInstructionFullFlow:
    def test_create_list_update_delete(self, client, db_session):
        """Full CRUD flow for an instruction."""
        token = _get_admin_token(client, db_session)

        # Create
        create_resp = client.post("/api/knowledge/instructions", headers=_auth_header(token),
                                  json={"type": "global", "text": "Flow rule"})
        assert create_resp.status_code == 201
        inst_id = create_resp.json()["id"]

        # List
        list_resp = client.get("/api/knowledge/instructions", headers=_auth_header(token))
        assert len(list_resp.json()) >= 1
        assert any(i["id"] == inst_id for i in list_resp.json())

        # Update
        update_resp = client.put(f"/api/knowledge/instructions/{inst_id}",
                                 headers=_auth_header(token),
                                 json={"text": "Updated flow rule",
                                       "type": "topic", "topic": "orders"})
        assert update_resp.status_code == 200
        assert update_resp.json()["text"] == "Updated flow rule"
        assert update_resp.json()["type"] == "topic"
        assert update_resp.json()["topic"] == "orders"

        # Delete
        delete_resp = client.delete(f"/api/knowledge/instructions/{inst_id}",
                                    headers=_auth_header(token))
        assert delete_resp.status_code == 200

        # Verify gone
        list_resp2 = client.get("/api/knowledge/instructions", headers=_auth_header(token))
        assert not any(i["id"] == inst_id for i in list_resp2.json())


# ======================================================================
# INSTRUCTION INJECTION TESTS
# ======================================================================

class TestInstructionInjection:
    """Test that instructions are properly fetched and matched."""

    def test_fetch_instructions_global(self, db_session):
        """Global instructions are always matched."""
        from app.services.chat_orchestrator import ChatOrchestrator

        # Create a global instruction directly in DB
        inst = Instruction(
            id=uuid.uuid4(),
            type=InstructionType.global_,
            topic=None,
            text="Always limit results to 100 rows",
        )
        db_session.add(inst)
        db_session.flush()

        # Mock the system session factory to return our test session
        with patch("app.services.chat_orchestrator.get_system_session_factory") as mock_factory:
            mock_session = MagicMock()
            mock_session.query.return_value.all.return_value = [inst]
            mock_factory.return_value = lambda: mock_session

            orchestrator = ChatOrchestrator.__new__(ChatOrchestrator)
            matched = orchestrator._fetch_instructions("Show me all sales data")

            assert len(matched) == 1
            assert "Always limit results to 100 rows" in matched[0]

    def test_fetch_instructions_topic_match(self, db_session):
        """Topic instructions match when keyword is in the query."""
        from app.services.chat_orchestrator import ChatOrchestrator

        global_inst = Instruction(
            id=uuid.uuid4(),
            type=InstructionType.global_,
            topic=None,
            text="Global rule",
        )
        topic_inst = Instruction(
            id=uuid.uuid4(),
            type=InstructionType.topic,
            topic="vendite",
            text="Use fact_orders for sales queries",
        )
        db_session.add(global_inst)
        db_session.add(topic_inst)
        db_session.flush()

        with patch("app.services.chat_orchestrator.get_system_session_factory") as mock_factory:
            mock_session = MagicMock()
            mock_session.query.return_value.all.return_value = [global_inst, topic_inst]
            mock_factory.return_value = lambda: mock_session

            orchestrator = ChatOrchestrator.__new__(ChatOrchestrator)
            matched = orchestrator._fetch_instructions("Mostra le vendite totali")

            assert len(matched) == 2
            assert any("Global rule" in m for m in matched)
            assert any("vendite" in m for m in matched)

    def test_fetch_instructions_topic_no_match(self, db_session):
        """Topic instructions don't match when keyword is NOT in the query."""
        from app.services.chat_orchestrator import ChatOrchestrator

        topic_inst = Instruction(
            id=uuid.uuid4(),
            type=InstructionType.topic,
            topic="vendite",
            text="Use fact_orders for sales queries",
        )
        db_session.add(topic_inst)
        db_session.flush()

        with patch("app.services.chat_orchestrator.get_system_session_factory") as mock_factory:
            mock_session = MagicMock()
            mock_session.query.return_value.all.return_value = [topic_inst]
            mock_factory.return_value = lambda: mock_session

            orchestrator = ChatOrchestrator.__new__(ChatOrchestrator)
            matched = orchestrator._fetch_instructions("Show me inventory data")

            assert len(matched) == 0

    def test_fetch_instructions_case_insensitive(self, db_session):
        """Topic matching is case-insensitive."""
        from app.services.chat_orchestrator import ChatOrchestrator

        topic_inst = Instruction(
            id=uuid.uuid4(),
            type=InstructionType.topic,
            topic="Revenue",
            text="Revenue-specific rule",
        )
        db_session.add(topic_inst)
        db_session.flush()

        with patch("app.services.chat_orchestrator.get_system_session_factory") as mock_factory:
            mock_session = MagicMock()
            mock_session.query.return_value.all.return_value = [topic_inst]
            mock_factory.return_value = lambda: mock_session

            orchestrator = ChatOrchestrator.__new__(ChatOrchestrator)
            matched = orchestrator._fetch_instructions("What is the total REVENUE?")

            assert len(matched) == 1
            assert "Revenue-specific rule" in matched[0]

    def test_instructions_included_in_prompt(self):
        """Instructions are included in the system prompt via _build_messages_dynamic."""
        from app.services.vanna_service import HybridVannaService

        # Create a minimal vanna service instance (no __init__)
        vanna = HybridVannaService.__new__(HybridVannaService)
        messages = vanna._build_messages_dynamic(
            question="Show sales",
            schema="CREATE TABLE sales (id INT);",
            instructions=["Always use LIMIT 100", "[Topic: sales] Use SUM for totals"]
        )

        system_msg = messages[0]["content"]
        assert "SQL GENERATION RULES" in system_msg
        assert "Always use LIMIT 100" in system_msg
        assert "Use SUM for totals" in system_msg

    def test_no_instructions_no_rules_block(self):
        """When no instructions, the rules block is not in the prompt."""
        from app.services.vanna_service import HybridVannaService

        vanna = HybridVannaService.__new__(HybridVannaService)
        messages = vanna._build_messages_dynamic(
            question="Show sales",
            schema="CREATE TABLE sales (id INT);",
            instructions=None
        )

        system_msg = messages[0]["content"]
        assert "SQL GENERATION RULES" not in system_msg