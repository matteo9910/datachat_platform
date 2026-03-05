"""
SQL Views API router - CRUD for creating/managing SQL views on client DB
with metadata stored in system DB.
"""

import logging
import re
import uuid as uuid_module
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_system_db
from app.models.system import ViewMetadata, User
from app.services.auth_middleware import require_role, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/views", tags=["views"])


# ---------------------------------------------------------------------------
# SQL reserved words (subset covering most common)
# ---------------------------------------------------------------------------

SQL_RESERVED_WORDS = {
    "select", "insert", "update", "delete", "drop", "create", "alter",
    "table", "view", "index", "from", "where", "join", "inner", "outer",
    "left", "right", "on", "and", "or", "not", "null", "is", "in",
    "between", "like", "order", "by", "group", "having", "limit",
    "offset", "union", "all", "distinct", "as", "case", "when", "then",
    "else", "end", "exists", "into", "values", "set", "begin", "commit",
    "rollback", "grant", "revoke", "primary", "key", "foreign",
    "references", "constraint", "check", "default", "unique",
    "cascade", "restrict", "trigger", "procedure", "function",
    "database", "schema", "exec", "execute", "declare", "cursor",
    "fetch", "open", "close", "truncate", "replace", "with",
}

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ViewCreate(BaseModel):
    view_name: str
    sql_query: str


class ViewResponse(BaseModel):
    id: str
    view_name: str
    sql_query: str
    created_by: Optional[str] = None
    client_db_id: Optional[str] = None
    created_at: Optional[str] = None


class MessageResponse(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_view_name(name: str) -> str:
    """
    Validate view name:
    - Only alphanumeric + underscores
    - Cannot be empty
    - Cannot be a SQL reserved word
    Returns cleaned name or raises HTTPException.
    """
    name = name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="View name cannot be empty",
        )

    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="View name must contain only letters, numbers, and underscores, "
                   "and must start with a letter or underscore",
        )

    if name.lower() in SQL_RESERVED_WORDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"View name '{name}' is a SQL reserved word",
        )

    return name


def _get_client_db_connection():
    """Get a direct psycopg2 connection to the client database."""
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from app.api.database import _current_connection

    if not _current_connection.get("connected") or not _current_connection.get("active_database"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client database not connected. Connect via Settings first.",
        )

    conn_string = (
        f"postgresql://{_current_connection['username']}:{_current_connection['password']}"
        f"@{_current_connection['host']}:{_current_connection['port']}"
        f"/{_current_connection['active_database']}"
    )
    conn = psycopg2.connect(conn_string, cursor_factory=RealDictCursor)
    conn.autocommit = True
    return conn


def _view_to_response(view: ViewMetadata) -> ViewResponse:
    return ViewResponse(
        id=str(view.id),
        view_name=view.view_name,
        sql_query=view.sql_query,
        created_by=str(view.created_by) if view.created_by else None,
        client_db_id=view.client_db_id,
        created_at=view.created_at.isoformat() if view.created_at else None,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=List[ViewResponse])
async def list_views(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_system_db),
):
    """List all saved views (all roles can access)."""
    views = db.query(ViewMetadata).order_by(ViewMetadata.created_at.desc()).all()
    return [_view_to_response(v) for v in views]


@router.post("", response_model=ViewResponse, status_code=status.HTTP_201_CREATED)
async def create_view(
    body: ViewCreate,
    current_user: User = Depends(require_role(["admin", "analyst"])),
    db: Session = Depends(get_system_db),
):
    """
    Create a SQL view on the client database and save metadata to system DB.
    Admin and analyst roles only.
    """
    view_name = _validate_view_name(body.view_name)
    sql_query = body.sql_query.strip()

    if not sql_query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SQL query cannot be empty",
        )

    # Check for duplicate in system DB metadata
    existing = db.query(ViewMetadata).filter(
        ViewMetadata.view_name == view_name
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"View '{view_name}' already exists",
        )

    # Execute CREATE OR REPLACE VIEW on client DB
    conn = _get_client_db_connection()
    try:
        with conn.cursor() as cur:
            create_sql = f'CREATE OR REPLACE VIEW "{view_name}" AS {sql_query}'
            cur.execute(create_sql)
        logger.info(f"Created view '{view_name}' on client DB")
    except Exception as e:
        logger.error(f"Failed to create view on client DB: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create view on client database: {str(e)}",
        )
    finally:
        conn.close()

    # Save metadata to system DB
    from app.api.database import _current_connection
    client_db_id = _current_connection.get("active_database")

    view_meta = ViewMetadata(
        id=uuid_module.uuid4(),
        view_name=view_name,
        sql_query=sql_query,
        created_by=current_user.id,
        client_db_id=client_db_id,
    )
    db.add(view_meta)
    db.commit()
    db.refresh(view_meta)

    return _view_to_response(view_meta)


@router.delete("/{view_id}", response_model=MessageResponse)
async def delete_view(
    view_id: str,
    current_user: User = Depends(require_role(["admin", "analyst"])),
    db: Session = Depends(get_system_db),
):
    """
    Drop a SQL view from the client database and remove metadata from system DB.
    Admin and analyst roles only.
    """
    try:
        uid = uuid_module.UUID(view_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="View not found",
        )

    view_meta = db.query(ViewMetadata).filter(ViewMetadata.id == uid).first()
    if not view_meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="View not found",
        )

    # Drop view from client DB (best-effort)
    try:
        conn = _get_client_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(f'DROP VIEW IF EXISTS "{view_meta.view_name}"')
            logger.info(f"Dropped view '{view_meta.view_name}' from client DB")
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"Failed to drop view from client DB (proceeding with metadata removal): {e}")

    # Remove metadata from system DB
    db.delete(view_meta)
    db.commit()

    return MessageResponse(message=f"View '{view_meta.view_name}' deleted successfully")