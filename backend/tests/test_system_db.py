"""
Tests for system database models, engine, and session factory.

Uses an in-memory SQLite database to avoid needing a real Neon connection.
"""

import uuid
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import create_engine, inspect, event, JSON
from sqlalchemy.orm import sessionmaker, Session

from app.models.system import (
    SystemBase,
    User,
    Session as UserSession,
    AuditLog,
    BrandConfig,
    WriteWhitelist,
    KBPair,
    Instruction,
    ViewMetadata,
    DashboardMetadata,
    UserRole,
    InstructionType,
)


@pytest.fixture(scope='module')
def engine():
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.ext.compiler import compiles

    # Teach SQLite how to render JSONB (map to TEXT for testing)
    @compiles(JSONB, 'sqlite')
    def compile_jsonb_sqlite(type_, compiler, **kw):
        return 'TEXT'

    eng = create_engine('sqlite://', echo=False)
    SystemBase.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


EXPECTED_TABLES = [
    'users', 'sessions', 'audit_log', 'brand_config',
    'write_whitelist', 'kb_pairs', 'instructions',
    'view_metadata', 'dashboard_metadata',
]


class TestSystemTablesExist:
    """Verify all 9 system tables are created by SystemBase.metadata."""

    def test_all_tables_present(self, engine):
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        for t in EXPECTED_TABLES:
            assert t in tables, f'Table {t} not found. Got: {tables}'

    def test_table_count(self, engine):
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert len(tables) == 9


class TestUserModel:
    def test_create_user(self, db: Session):
        user = User(
            id=uuid.uuid4(),
            email='admin@test.com',
            hashed_password='placeholder_hash',
            full_name='Admin User',
            role=UserRole.admin,
            is_active=True,
        )
        db.add(user)
        db.flush()
        fetched = db.query(User).filter_by(email='admin@test.com').first()
        assert fetched is not None
        assert fetched.full_name == 'Admin User'
        assert fetched.role == UserRole.admin
        assert fetched.is_active is True

    def test_user_to_dict(self, db: Session):
        user = User(
            id=uuid.uuid4(),
            email='dict@test.com',
            hashed_password='pw',
            full_name='Dict User',
            role=UserRole.analyst,
        )
        db.add(user)
        db.flush()
        d = user.to_dict()
        assert d['email'] == 'dict@test.com'
        assert d['role'] == 'analyst'
        assert 'id' in d

    def test_user_roles_enum(self):
        assert UserRole.admin.value == 'admin'
        assert UserRole.analyst.value == 'analyst'
        assert UserRole.user.value == 'user'
        assert len(UserRole) == 3

    def test_unique_email_constraint(self, db: Session):
        user1 = User(id=uuid.uuid4(), email="dup@test.com", hashed_password="pw", full_name="U1")
        db.add(user1)
        db.flush()
        user2 = User(id=uuid.uuid4(), email="dup@test.com", hashed_password="pw", full_name="U2")
        db.add(user2)
        with pytest.raises(Exception):
            db.flush()


class TestSessionModel:
    def test_create_session(self, db: Session):
        user = User(
            id=uuid.uuid4(), email='sess@test.com',
            hashed_password='pw', full_name='S User',
        )
        db.add(user)
        db.flush()
        sess = UserSession(
            id=uuid.uuid4(),
            user_id=user.id,
            token='placeholder_test_token',
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        db.add(sess)
        db.flush()
        fetched = db.query(UserSession).filter_by(token='placeholder_test_token').first()
        assert fetched is not None
        assert fetched.user_id == user.id


class TestAuditLogModel:
    def test_create_audit_entry(self, db: Session):
        entry = AuditLog(
            id=uuid.uuid4(),
            action='login',
            resource='auth',
            ip_address='127.0.0.1',
        )
        db.add(entry)
        db.flush()
        fetched = db.query(AuditLog).filter_by(action='login').first()
        assert fetched is not None
        assert fetched.ip_address == '127.0.0.1'


class TestBrandConfigModel:
    def test_create_brand_config(self, db: Session):
        config = BrandConfig(
            id=uuid.uuid4(),
            primary_color='#1E40AF',
            secondary_color='#F59E0B',
            font_family='Inter',
            logo_url='https://example.com/logo.png',
        )
        db.add(config)
        db.flush()
        fetched = db.query(BrandConfig).first()
        assert fetched.primary_color == '#1E40AF'
        assert fetched.font_family == 'Inter'


class TestWriteWhitelistModel:
    def test_create_whitelist_entry(self, db: Session):
        entry = WriteWhitelist(
            id=uuid.uuid4(),
            table_name='products',
            column_name='price',
        )
        db.add(entry)
        db.flush()
        fetched = db.query(WriteWhitelist).first()
        assert fetched.table_name == 'products'
        assert fetched.column_name == 'price'


class TestKBPairModel:
    def test_create_kb_pair(self, db: Session):
        pair = KBPair(
            id=uuid.uuid4(),
            question='What is total revenue?',
            sql_query='SELECT SUM(sales) FROM orders',
        )
        db.add(pair)
        db.flush()
        fetched = db.query(KBPair).first()
        assert fetched.question == 'What is total revenue?'
        assert 'SUM' in fetched.sql_query


class TestInstructionModel:
    def test_create_global_instruction(self, db: Session):
        inst = Instruction(
            id=uuid.uuid4(),
            type=InstructionType.global_,
            text='Always use LEFT JOIN',
        )
        db.add(inst)
        db.flush()
        fetched = db.query(Instruction).first()
        assert fetched.type == InstructionType.global_
        assert fetched.topic is None

    def test_create_topic_instruction(self, db: Session):
        inst = Instruction(
            id=uuid.uuid4(),
            type=InstructionType.topic,
            topic='revenue',
            text='Use SUM(sales) for revenue calculations',
        )
        db.add(inst)
        db.flush()
        fetched = db.query(Instruction).filter_by(topic='revenue').first()
        assert fetched.type == InstructionType.topic
        assert fetched.topic == 'revenue'


class TestViewMetadataModel:
    def test_create_view_metadata(self, db: Session):
        view = ViewMetadata(
            id=uuid.uuid4(),
            view_name='v_monthly_sales',
            sql_query='SELECT date_trunc(...) ...',
            client_db_id='supabase_abc',
        )
        db.add(view)
        db.flush()
        fetched = db.query(ViewMetadata).first()
        assert fetched.view_name == 'v_monthly_sales'
        assert fetched.client_db_id == 'supabase_abc'


class TestDashboardMetadataModel:
    def test_create_dashboard(self, db: Session):
        dash = DashboardMetadata(
            id=uuid.uuid4(),
            name='Sales Overview',
            layout={'rows': 2, 'cols': 3},
            charts=[{'chart_id': 'abc', 'position': [0, 0]}],
            filters={'date_range': '2025-01-01/2025-12-31'},
        )
        db.add(dash)
        db.flush()
        fetched = db.query(DashboardMetadata).first()
        assert fetched.name == 'Sales Overview'


class TestDatabaseModule:
    """Test the database.py module functions."""

    def test_reset_system_engine(self):
        from app.database import reset_system_engine
        reset_system_engine()

    def test_get_system_engine_raises_without_url(self, monkeypatch):
        from app.database import reset_system_engine
        from app import database as db_module
        from app.config import settings
        reset_system_engine()
        monkeypatch.setattr(settings, 'system_database_url', None)
        with pytest.raises(RuntimeError, match='SYSTEM_DATABASE_URL is not configured'):
            db_module.get_system_engine()
        reset_system_engine()

    def test_get_system_engine_with_url(self, monkeypatch):
        from app.database import reset_system_engine, get_system_engine
        from app.config import settings
        reset_system_engine()
        monkeypatch.setattr(settings, 'system_database_url', 'sqlite://')
        engine = get_system_engine()
        assert engine is not None
        reset_system_engine()

    def test_get_system_db_yields_session(self, monkeypatch):
        from app.database import reset_system_engine, get_system_db
        from app.config import settings
        reset_system_engine()
        monkeypatch.setattr(settings, 'system_database_url', 'sqlite://')
        gen = get_system_db()
        session = next(gen)
        assert isinstance(session, Session)
        try:
            next(gen)
        except StopIteration:
            pass
        reset_system_engine()


class TestSystemTablesNotOnClientDB:
    """Verify system tables use SystemBase, not the client DB Base."""

    def test_system_base_separate_from_client_base(self):
        from app.models.database import Base as ClientBase
        system_tables = set(SystemBase.metadata.tables.keys())
        client_tables = set(ClientBase.metadata.tables.keys())
        overlap = system_tables & client_tables
        assert not overlap, (
            f'System tables overlap with client DB tables: {overlap}. '
            f'System tables must NEVER be created on the client DB.'
        )
