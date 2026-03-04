"""
SQLAlchemy models - Database tables
"""

from sqlalchemy import Column, String, Text, Boolean, Integer, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import uuid as uuid_module

Base = declarative_base()


class SavedChart(Base):
    """Tabella poc_metadata.saved_charts"""
    __tablename__ = "saved_charts"
    __table_args__ = {"schema": "poc_metadata"}

    chart_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4)
    user_id = Column(String(100), nullable=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    sql_template = Column(Text, nullable=False)
    parameters = Column(JSONB, nullable=False, default={})
    plotly_config = Column(JSONB, nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=True, onupdate=func.now())

    def to_dict(self):
        """Serialize to dict"""
        return {
            "chart_id": str(self.chart_id),
            "user_id": self.user_id,
            "title": self.title,
            "description": self.description,
            "sql_template": self.sql_template,
            "parameters": self.parameters,
            "plotly_config": self.plotly_config,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class QueryHistory(Base):
    """Tabella poc_metadata.query_history"""
    __tablename__ = "query_history"
    __table_args__ = {"schema": "poc_metadata"}

    query_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4)
    session_id = Column(String(100), nullable=False, index=True)
    nl_query = Column(Text, nullable=False)
    sql_generated = Column(Text, nullable=True)
    llm_provider = Column(String(20), nullable=True)
    success = Column(Boolean, nullable=False, default=False, index=True)
    error_message = Column(Text, nullable=True)
    execution_time_ms = Column(Integer, nullable=True)
    result_rows = Column(Integer, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), index=True)

    def to_dict(self):
        """Serialize to dict"""
        return {
            "query_id": str(self.query_id),
            "session_id": self.session_id,
            "nl_query": self.nl_query,
            "sql_generated": self.sql_generated,
            "llm_provider": self.llm_provider,
            "success": self.success,
            "error_message": self.error_message,
            "execution_time_ms": self.execution_time_ms,
            "result_rows": self.result_rows,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }