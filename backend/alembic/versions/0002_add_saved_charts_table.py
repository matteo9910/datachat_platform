"""Add saved_charts table to system database.

Revision ID: 0002
Revises: 4e218d91b455
Create Date: 2026-03-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "4e218d91b455"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "saved_charts",
        sa.Column("chart_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(100), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sql_template", sa.Text(), nullable=False),
        sa.Column("parameters", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("plotly_config", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_saved_charts_created_at", "saved_charts", ["created_at"])
    op.create_index("ix_saved_charts_user_id", "saved_charts", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_saved_charts_user_id")
    op.drop_index("ix_saved_charts_created_at")
    op.drop_table("saved_charts")