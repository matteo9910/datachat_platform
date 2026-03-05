"""add_missing_brand_config_columns

Revision ID: 4e218d91b455
Revises: 0001
Create Date: 2026-03-05 15:52:26.485747

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '4e218d91b455'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    # Only add columns that don't already exist
    result = conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns WHERE table_name='brand_config'"
    ))
    existing = {row[0] for row in result}

    if "accent_colors" not in existing:
        op.add_column("brand_config", sa.Column("accent_colors", postgresql.JSONB, nullable=True))
    if "created_at" not in existing:
        op.add_column("brand_config", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()))
    if "updated_at" not in existing:
        op.add_column("brand_config", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("brand_config", "updated_at")
    op.drop_column("brand_config", "created_at")
    op.drop_column("brand_config", "accent_colors")
