"""
SQLAlchemy models for System Database (Neon PostgreSQL).

These models define ALL system tables: auth, sessions, audit, config, KB, etc.
System tables are NEVER created on the client database.
"""

import enum
import uuid as uuid_module
from datetime import datetime

from sqlalchemy import (
    Column, String, Text, Boolean, Integer, DateTime, Enum, ForeignKey,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

SystemBase = declarative_base()


# ============================================================
# ENUMS
# ============================================================

class UserRole(str, enum.Enum):
    """User role levels for access control."""
    admin = "admin"
    analyst = "analyst"
    user = "user"


class InstructionType(str, enum.Enum):
    """Instruction scope type."""
    global_ = "global"
    topic = "topic"


# ============================================================
# AUTH & SESSION TABLES
# ============================================================

class User(SystemBase):
    """System users with role-based access control."""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(
        Enum(UserRole, name="user_role", create_constraint=True),
        nullable=False,
        default=UserRole.user,
    )
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())

    # Relationships
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": str(self.id),
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role.value if self.role else None,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Session(SystemBase):
    """User login sessions with JWT tokens."""
    __tablename__ = "sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token = Column(String(512), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="sessions")


# ============================================================
# AUDIT TABLE
# ============================================================

class AuditLog(SystemBase):
    """Audit trail for all significant user actions."""
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action = Column(String(100), nullable=False)
    resource = Column(String(255), nullable=True)
    details = Column(JSONB, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_audit_log_created_at", "created_at"),
    )


# ============================================================
# BRAND CONFIGURATION
# ============================================================

class BrandConfig(SystemBase):
    """Brand/visual identity configuration for charts and dashboards."""
    __tablename__ = "brand_config"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4)
    primary_color = Column(String(7), nullable=True)
    secondary_color = Column(String(7), nullable=True)
    accent_colors = Column(JSONB, nullable=True)  # JSON array of hex color strings
    font_family = Column(String(100), nullable=True)
    logo_url = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())


# ============================================================
# WRITE OPERATIONS WHITELIST
# ============================================================

class WriteWhitelist(SystemBase):
    """Admin-configurable whitelist of writable tables/columns on client DB."""
    __tablename__ = "write_whitelist"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4)
    table_name = Column(String(255), nullable=False)
    column_name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_write_whitelist_table_column", "table_name", "column_name", unique=True),
    )


# ============================================================
# KNOWLEDGE BASE
# ============================================================

class KBPair(SystemBase):
    """Question-SQL pairs for RAG training / Knowledge Base."""
    __tablename__ = "kb_pairs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4)
    question = Column(Text, nullable=False)
    sql_query = Column(Text, nullable=False)
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())


class Instruction(SystemBase):
    """System instructions (global or per-topic) injected into LLM prompts."""
    __tablename__ = "instructions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4)
    type = Column(
        Enum(InstructionType, name="instruction_type", create_constraint=True,
             values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=InstructionType.global_,
    )
    topic = Column(String(255), nullable=True)
    text = Column(Text, nullable=False)
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())


# ============================================================
# VIEW & DASHBOARD METADATA
# ============================================================

class ViewMetadata(SystemBase):
    """Metadata for SQL views created on the client database."""
    __tablename__ = "view_metadata"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4)
    view_name = Column(String(255), nullable=False)
    sql_query = Column(Text, nullable=False)
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    client_db_id = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DashboardMetadata(SystemBase):
    """Metadata for saved dashboards."""
    __tablename__ = "dashboard_metadata"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4)
    name = Column(String(255), nullable=False)
    layout = Column(JSONB, nullable=True)
    charts = Column(JSONB, nullable=True)
    filters = Column(JSONB, nullable=True)
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())
