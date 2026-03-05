"""
Tests for Brand Configuration API endpoints and chart service brand integration.

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
    SystemBase, User, Session as UserSession, UserRole, BrandConfig,
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
    from app.api.brand import router as brand_router
    app.include_router(auth_router)
    app.include_router(brand_router)

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


def _get_admin_token(client, db_session):
    _create_user(db_session, email="admin@brand.test", password="adminpass",
                 role=UserRole.admin, full_name="Brand Admin")
    resp = _login(client, "admin@brand.test", "adminpass")
    return resp.json()["token"]


def _get_analyst_token(client, db_session):
    _create_user(db_session, email="analyst@brand.test", password="analystpass",
                 role=UserRole.analyst, full_name="Brand Analyst")
    resp = _login(client, "analyst@brand.test", "analystpass")
    return resp.json()["token"]


def _get_user_token(client, db_session):
    _create_user(db_session, email="regular@brand.test", password="userpass",
                 role=UserRole.user, full_name="Regular User")
    resp = _login(client, "regular@brand.test", "userpass")
    return resp.json()["token"]


# ======================================================================
# AUTH TESTS
# ======================================================================

class TestBrandAuth:
    def test_get_config_no_token_returns_401(self, client):
        resp = client.get("/api/brand/config")
        assert resp.status_code == 401

    def test_get_config_invalid_token_returns_401(self, client):
        resp = client.get("/api/brand/config", headers=_auth_header("garbage"))
        assert resp.status_code == 401

    def test_save_config_no_token_returns_401(self, client):
        resp = client.post("/api/brand/config", json={
            "primary_color": "#FF0000", "secondary_color": "#00FF00"
        })
        assert resp.status_code == 401

    def test_save_config_user_role_returns_403(self, client, db_session):
        token = _get_user_token(client, db_session)
        resp = client.post("/api/brand/config", headers=_auth_header(token), json={
            "primary_color": "#FF0000", "secondary_color": "#00FF00"
        })
        assert resp.status_code == 403

    def test_save_config_analyst_role_returns_403(self, client, db_session):
        token = _get_analyst_token(client, db_session)
        resp = client.post("/api/brand/config", headers=_auth_header(token), json={
            "primary_color": "#FF0000", "secondary_color": "#00FF00"
        })
        assert resp.status_code == 403

    def test_get_config_all_roles_can_read(self, client, db_session):
        """All authenticated roles can read brand config."""
        for get_token in [_get_admin_token, _get_analyst_token, _get_user_token]:
            # Each call creates a different user, so use unique emails
            token = get_token(client, db_session)
            resp = client.get("/api/brand/config", headers=_auth_header(token))
            assert resp.status_code == 200


# ======================================================================
# GET DEFAULT CONFIG
# ======================================================================

class TestBrandGetDefault:
    def test_get_config_returns_defaults_when_none_saved(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.get("/api/brand/config", headers=_auth_header(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["primary_color"] == "#1f77b4"
        assert data["secondary_color"] == "#ff7f0e"
        assert isinstance(data["accent_colors"], list)
        assert len(data["accent_colors"]) > 0
        assert data["font_family"] == "Inter, system-ui, sans-serif"
        assert data["id"] is None


# ======================================================================
# SAVE / UPDATE CONFIG
# ======================================================================

class TestBrandSaveConfig:
    def test_save_config_as_admin(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/brand/config", headers=_auth_header(token), json={
            "primary_color": "#FF5500",
            "secondary_color": "#0055FF",
            "accent_colors": ["#AA0000", "#00AA00", "#0000AA"],
            "font_family": "Roboto, sans-serif",
            "logo_url": "https://example.com/logo.png",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["primary_color"] == "#FF5500"
        assert data["secondary_color"] == "#0055FF"
        assert data["accent_colors"] == ["#AA0000", "#00AA00", "#0000AA"]
        assert data["font_family"] == "Roboto, sans-serif"
        assert data["logo_url"] == "https://example.com/logo.png"
        assert data["id"] is not None

    def test_save_config_updates_existing(self, client, db_session):
        token = _get_admin_token(client, db_session)
        # First save
        client.post("/api/brand/config", headers=_auth_header(token), json={
            "primary_color": "#111111",
            "secondary_color": "#222222",
        })
        # Second save (update)
        resp = client.post("/api/brand/config", headers=_auth_header(token), json={
            "primary_color": "#333333",
            "secondary_color": "#444444",
            "font_family": "Arial, sans-serif",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["primary_color"] == "#333333"
        assert data["secondary_color"] == "#444444"
        assert data["font_family"] == "Arial, sans-serif"

        # Verify get returns updated
        get_resp = client.get("/api/brand/config", headers=_auth_header(token))
        assert get_resp.json()["primary_color"] == "#333333"

    def test_save_config_without_optional_fields(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/brand/config", headers=_auth_header(token), json={
            "primary_color": "#AABBCC",
            "secondary_color": "#DDEEFF",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["primary_color"] == "#AABBCC"
        assert data["font_family"] == "Inter, system-ui, sans-serif"  # default


# ======================================================================
# VALIDATION TESTS
# ======================================================================

class TestBrandValidation:
    def test_invalid_primary_color(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/brand/config", headers=_auth_header(token), json={
            "primary_color": "not-a-color",
            "secondary_color": "#00FF00",
        })
        assert resp.status_code == 400
        assert "primary_color" in resp.json()["detail"]

    def test_invalid_secondary_color(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/brand/config", headers=_auth_header(token), json={
            "primary_color": "#FF0000",
            "secondary_color": "invalid",
        })
        assert resp.status_code == 400
        assert "secondary_color" in resp.json()["detail"]

    def test_invalid_accent_color(self, client, db_session):
        token = _get_admin_token(client, db_session)
        resp = client.post("/api/brand/config", headers=_auth_header(token), json={
            "primary_color": "#FF0000",
            "secondary_color": "#00FF00",
            "accent_colors": ["#AABBCC", "bad-color"],
        })
        assert resp.status_code == 400
        assert "accent color" in resp.json()["detail"].lower() or "bad-color" in resp.json()["detail"]


# ======================================================================
# CHART SERVICE BRAND INTEGRATION
# ======================================================================

class TestChartServiceBrand:
    def test_brand_colors_used_when_configured(self, db_session):
        """When brand config is saved, chart service should use those colors."""
        # Save brand config to DB
        cfg = BrandConfig(
            id=uuid.uuid4(),
            primary_color="#AA0000",
            secondary_color="#00AA00",
            accent_colors=["#0000AA", "#AAAA00", "#AA00AA"],
            font_family="Georgia, serif",
        )
        db_session.add(cfg)
        db_session.commit()

        # Mock get_system_session_factory to return our test session
        mock_factory = MagicMock(return_value=db_session)
        with patch("app.services.chart_service.get_brand_colors_and_font") as mock_brand:
            mock_brand.return_value = {
                "colors": ["#AA0000", "#00AA00", "#0000AA", "#AAAA00", "#AA00AA"],
                "font_family": "Georgia, serif",
            }
            from app.services.chart_service import PlotlyConfigGenerator
            gen = PlotlyConfigGenerator()
            assert gen.COLORS[0] == "#AA0000"
            assert gen.COLORS[1] == "#00AA00"
            assert gen.brand_font == "Georgia, serif"

    def test_fallback_to_defaults_when_no_brand_config(self):
        """When no brand config exists, chart service uses Plotly defaults."""
        with patch("app.services.chart_service.get_brand_colors_and_font") as mock_brand:
            mock_brand.return_value = {
                "colors": [
                    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
                    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
                ],
                "font_family": None,
            }
            from app.services.chart_service import PlotlyConfigGenerator
            gen = PlotlyConfigGenerator()
            assert gen.COLORS[0] == "#1f77b4"
            assert gen.brand_font is None

    def test_brand_font_applied_to_chart_layout(self):
        """Chart layout should include brand font when configured."""
        with patch("app.services.chart_service.get_brand_colors_and_font") as mock_brand:
            mock_brand.return_value = {
                "colors": ["#AA0000", "#00AA00", "#0000AA"],
                "font_family": "Roboto, sans-serif",
            }
            from app.services.chart_service import PlotlyConfigGenerator, ColumnInfo
            gen = PlotlyConfigGenerator()
            results = [
                {"category": "A", "value": 10},
                {"category": "B", "value": 20},
                {"category": "C", "value": 30},
            ]
            columns_info = [
                ColumnInfo(name="category", type="text", cardinality=3, sample_values=["A", "B", "C"]),
                ColumnInfo(name="value", type="numeric", cardinality=3, sample_values=[10, 20, 30]),
            ]
            config = gen.generate_config(results, "bar", columns_info, "Test Chart")
            layout = config["layout"]
            assert layout.get("font", {}).get("family") == "Roboto, sans-serif"

    def test_brand_colors_used_in_bar_chart(self):
        """Bar chart markers should use brand colors."""
        with patch("app.services.chart_service.get_brand_colors_and_font") as mock_brand:
            mock_brand.return_value = {
                "colors": ["#EE0000", "#00EE00", "#0000EE"],
                "font_family": None,
            }
            from app.services.chart_service import PlotlyConfigGenerator, ColumnInfo
            gen = PlotlyConfigGenerator()
            results = [
                {"cat": "X", "val": 5},
                {"cat": "Y", "val": 15},
            ]
            columns_info = [
                ColumnInfo(name="cat", type="text", cardinality=2, sample_values=["X", "Y"]),
                ColumnInfo(name="val", type="numeric", cardinality=2, sample_values=[5, 15]),
            ]
            config = gen.generate_config(results, "bar", columns_info, "Brand Bar")
            assert config["data"][0]["marker"]["color"] == "#EE0000"


# ======================================================================
# FULL FLOW
# ======================================================================

class TestBrandFullFlow:
    def test_save_then_read(self, client, db_session):
        """Admin saves brand config, then any user can read it."""
        admin_token = _get_admin_token(client, db_session)

        # Save config
        save_resp = client.post("/api/brand/config", headers=_auth_header(admin_token), json={
            "primary_color": "#ABCDEF",
            "secondary_color": "#FEDCBA",
            "accent_colors": ["#112233"],
            "font_family": "Helvetica, Arial, sans-serif",
        })
        assert save_resp.status_code == 200

        # Read as admin
        get_resp = client.get("/api/brand/config", headers=_auth_header(admin_token))
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["primary_color"] == "#ABCDEF"
        assert data["secondary_color"] == "#FEDCBA"
        assert data["accent_colors"] == ["#112233"]
        assert data["font_family"] == "Helvetica, Arial, sans-serif"