"""
Write Operations API router — NL-to-SQL for writes (UPDATE/INSERT),
whitelist management, audit trail, confirmation flow, role enforcement.

Destructive operations (DELETE, TRUNCATE, DROP, ALTER DROP) are ALWAYS blocked.
"""

import logging
import re
import uuid as uuid_module
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_system_db
from app.models.system import AuditLog, User, WriteWhitelist
from app.services.auth_middleware import get_current_user, require_role
from app.services.llm_provider import get_llm_provider_manager
from app.services.mcp_manager import mcp_postgres_client
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["write"])

# ---------------------------------------------------------------------------
# Forbidden SQL patterns — ALWAYS blocked regardless of role
# ---------------------------------------------------------------------------

FORBIDDEN_PATTERNS = [
    re.compile(r"\bDELETE\b", re.IGNORECASE),
    re.compile(r"\bTRUNCATE\b", re.IGNORECASE),
    re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE),
    re.compile(r"\bDROP\s+DATABASE\b", re.IGNORECASE),
    re.compile(r"\bALTER\s+TABLE\s+\w+\s+DROP\b", re.IGNORECASE),
]


def _is_destructive(sql: str) -> bool:
    """Return True if the SQL contains any forbidden destructive operation."""
    for pattern in FORBIDDEN_PATTERNS:
        if pattern.search(sql):
            return True
    return False


def _extract_target_tables(sql: str) -> List[str]:
    """Extract target table names from UPDATE / INSERT SQL."""
    tables: List[str] = []
    for m in re.finditer(r"\bUPDATE\s+(?:\"?(\w+)\"?)", sql, re.IGNORECASE):
        tables.append(m.group(1).lower())
    for m in re.finditer(r"\bINSERT\s+INTO\s+(?:\"?(\w+)\"?)", sql, re.IGNORECASE):
        tables.append(m.group(1).lower())
    return list(set(tables))


def _extract_target_columns(sql: str) -> List[str]:
    """Extract column names from SET clause (UPDATE) or column list (INSERT)."""
    columns: List[str] = []
    set_match = re.search(r"\bSET\s+(.*?)(?:\bWHERE\b|$)", sql, re.IGNORECASE | re.DOTALL)
    if set_match:
        set_clause = set_match.group(1)
        for cm in re.finditer(r"\"?(\w+)\"?\s*=", set_clause):
            columns.append(cm.group(1).lower())
    insert_match = re.search(r"\bINSERT\s+INTO\s+\w+\s*\((.*?)\)", sql, re.IGNORECASE | re.DOTALL)
    if insert_match:
        col_list = insert_match.group(1)
        for cm in re.finditer(r"\"?(\w+)\"?", col_list):
            columns.append(cm.group(1).lower())
    return list(set(columns))


def _is_bulk_operation(sql: str) -> bool:
    """Return True if the SQL is an UPDATE without a specific WHERE clause."""
    sql_upper = sql.upper().strip()
    if sql_upper.startswith("UPDATE"):
        if "WHERE" not in sql_upper:
            return True
        where_match = re.search(r"\bWHERE\s+(.*?)(?:;|$)", sql, re.IGNORECASE | re.DOTALL)
        if where_match:
            condition = where_match.group(1).strip().rstrip(";").strip()
            if condition.upper() in ("1=1", "TRUE", "1 = 1"):
                return True
    return False


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class GenerateWriteRequest(BaseModel):
    nl_text: str = Field(..., min_length=1, description="Natural language description of the write operation")
    llm_provider: Optional[str] = None


class GenerateWriteResponse(BaseModel):
    sql: str
    estimated_rows: Optional[int] = None
    target_tables: List[str] = []
    target_columns: List[str] = []
    is_bulk: bool = False


class ExecuteWriteRequest(BaseModel):
    sql: str = Field(..., min_length=1, description="The SQL to execute (previously generated)")
    extra_confirmation: bool = Field(False, description="Required for bulk operations")


class ExecuteWriteResponse(BaseModel):
    success: bool
    rows_affected: int = 0
    message: str = ""


class WhitelistEntry(BaseModel):
    id: Optional[str] = None
    table_name: str
    column_name: str
    created_at: Optional[str] = None


class WhitelistSaveRequest(BaseModel):
    entries: List[Dict[str, str]] = Field(
        ..., description="Array of {table_name, column_name}"
    )


class TableColumnsResponse(BaseModel):
    tables: List[Dict[str, Any]]


class AuditLogEntry(BaseModel):
    id: str
    user_id: Optional[str] = None
    action: str
    resource: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    created_at: Optional[str] = None


class AuditLogListResponse(BaseModel):
    logs: List[AuditLogEntry]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_client_tables_and_columns() -> List[Dict[str, Any]]:
    """Fetch tables and columns from the connected client database."""
    if not mcp_postgres_client._connected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client database not connected. Connect via Settings first.",
        )

    sql = """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
    """
    rows = mcp_postgres_client.execute_query(sql)

    tables_dict: Dict[str, List[Dict[str, str]]] = {}
    for row in rows:
        tname = row.get("table_name", "")
        cname = row.get("column_name", "")
        dtype = row.get("data_type", "")
        if tname not in tables_dict:
            tables_dict[tname] = []
        tables_dict[tname].append({"column_name": cname, "data_type": dtype})

    return [
        {"table_name": t, "columns": cols}
        for t, cols in sorted(tables_dict.items())
    ]


def _get_client_schema_ddl() -> str:
    """Build a DDL-like schema description for the LLM prompt."""
    tables = _get_client_tables_and_columns()
    parts: List[str] = []
    for t in tables:
        cols = ", ".join(
            f"{c['column_name']} {c['data_type']}" for c in t["columns"]
        )
        parts.append(f"TABLE {t['table_name']} ({cols})")
    return "\n".join(parts)


def _log_audit(
    db: Session,
    user: User,
    action: str,
    resource: Optional[str],
    details: Optional[Dict[str, Any]],
    ip_address: Optional[str] = None,
):
    entry = AuditLog(
        id=uuid_module.uuid4(),
        user_id=user.id,
        action=action,
        resource=resource,
        details=details,
        ip_address=ip_address,
    )
    db.add(entry)
    db.commit()


# ===================================================================
# WRITE GENERATION & EXECUTION
# ===================================================================

@router.post("/api/write/generate", response_model=GenerateWriteResponse)
async def generate_write_sql(
    body: GenerateWriteRequest,
    current_user: User = Depends(require_role(["admin", "analyst"])),
    db: Session = Depends(get_system_db),
):
    """
    Accept NL text and generate UPDATE/INSERT SQL.
    - Detects destructive ops and returns 400.
    - Checks whitelist; returns 403 if target not whitelisted.
    """
    try:
        schema_ddl = _get_client_schema_ddl()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot read client DB schema: {e}",
        )

    provider = body.llm_provider or settings.default_llm_provider
    system_prompt = f"""You are a SQL expert. Generate ONLY a single SQL statement based on the user request.

RULES:
- ONLY UPDATE or INSERT statements are allowed.
- NEVER generate DELETE, TRUNCATE, DROP TABLE, DROP DATABASE, or ALTER TABLE DROP COLUMN.
- Reference the database schema below.
- Return ONLY the raw SQL statement, nothing else (no markdown, no explanation).
- If the user request cannot be expressed as UPDATE or INSERT, respond with exactly: ERROR: Only UPDATE and INSERT operations are supported.

DATABASE SCHEMA:
{schema_ddl}
"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": body.nl_text},
    ]

    try:
        llm_manager = get_llm_provider_manager()
        result = llm_manager.complete(messages, provider=provider, temperature=0.1)
        generated_sql = result["content"].strip()
    except Exception as e:
        logger.error(f"LLM generation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"SQL generation failed: {e}",
        )

    # Strip markdown fences if present
    if generated_sql.startswith("```"):
        lines = generated_sql.split("\n")
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        generated_sql = "\n".join(lines).strip()

    # Check for ERROR response from LLM
    if generated_sql.upper().startswith("ERROR:"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=generated_sql,
        )

    # Block destructive operations (hardcoded)
    if _is_destructive(generated_sql):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Destructive operations (DELETE, TRUNCATE, DROP, ALTER DROP) are not allowed.",
        )

    # Verify it starts with UPDATE or INSERT
    sql_trimmed = generated_sql.strip().upper()
    if not (sql_trimmed.startswith("UPDATE") or sql_trimmed.startswith("INSERT")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only UPDATE and INSERT operations are supported.",
        )

    # Extract targets and check whitelist
    target_tables = _extract_target_tables(generated_sql)
    target_columns = _extract_target_columns(generated_sql)

    whitelist_entries = db.query(WriteWhitelist).all()
    if not whitelist_entries:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tables/columns are whitelisted. Admin must configure the whitelist first.",
        )

    whitelisted = {
        (e.table_name.lower(), e.column_name.lower()) for e in whitelist_entries
    }
    whitelisted_tables = {e.table_name.lower() for e in whitelist_entries}

    for table in target_tables:
        if table not in whitelisted_tables:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Table '{table}' is not in the write whitelist.",
            )

    for table in target_tables:
        for col in target_columns:
            if (table, col) not in whitelisted:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Column '{col}' on table '{table}' is not in the write whitelist.",
                )

    estimated_rows = None
    is_bulk = _is_bulk_operation(generated_sql)

    return GenerateWriteResponse(
        sql=generated_sql,
        estimated_rows=estimated_rows,
        target_tables=target_tables,
        target_columns=target_columns,
        is_bulk=is_bulk,
    )


@router.post("/api/write/execute", response_model=ExecuteWriteResponse)
async def execute_write_sql(
    body: ExecuteWriteRequest,
    request: Request,
    current_user: User = Depends(require_role(["admin", "analyst"])),
    db: Session = Depends(get_system_db),
):
    """
    Execute confirmed SQL on the client DB.
    - Re-validates destructive ops and whitelist.
    - For bulk ops, requires extra_confirmation=true.
    - Logs everything to audit_log.
    """
    sql = body.sql.strip()

    if _is_destructive(sql):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Destructive operations (DELETE, TRUNCATE, DROP, ALTER DROP) are not allowed.",
        )

    sql_upper = sql.upper()
    if not (sql_upper.startswith("UPDATE") or sql_upper.startswith("INSERT")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only UPDATE and INSERT operations are supported.",
        )

    target_tables = _extract_target_tables(sql)
    target_columns = _extract_target_columns(sql)

    whitelist_entries = db.query(WriteWhitelist).all()
    whitelisted = {
        (e.table_name.lower(), e.column_name.lower()) for e in whitelist_entries
    }
    whitelisted_tables = {e.table_name.lower() for e in whitelist_entries}

    for table in target_tables:
        if table not in whitelisted_tables:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Table '{table}' is not in the write whitelist.",
            )
    for table in target_tables:
        for col in target_columns:
            if (table, col) not in whitelisted:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Column '{col}' on table '{table}' is not in the write whitelist.",
                )

    if _is_bulk_operation(sql) and not body.extra_confirmation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This is a bulk operation (UPDATE without specific WHERE). Set extra_confirmation=true to proceed.",
        )

    if not mcp_postgres_client._connected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client database not connected.",
        )

    ip_address = request.client.host if request.client else None

    try:
        result = mcp_postgres_client.execute_query(sql)
        rows_affected = len(result) if isinstance(result, list) else 0
        message = f"Successfully executed. Rows affected: {rows_affected}"
    except Exception as e:
        _log_audit(
            db=db,
            user=current_user,
            action="write_execute_failed",
            resource=", ".join(target_tables) if target_tables else None,
            details={"sql": sql, "error": str(e)},
            ip_address=ip_address,
        )
        logger.error(f"Write execution failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"SQL execution failed: {e}",
        )

    _log_audit(
        db=db,
        user=current_user,
        action="write_execute",
        resource=", ".join(target_tables) if target_tables else None,
        details={
            "sql": sql,
            "rows_affected": rows_affected,
            "target_tables": target_tables,
            "target_columns": target_columns,
        },
        ip_address=ip_address,
    )

    return ExecuteWriteResponse(
        success=True,
        rows_affected=rows_affected,
        message=message,
    )


# ===================================================================
# WHITELIST MANAGEMENT
# ===================================================================

@router.get("/api/write/whitelist", response_model=List[WhitelistEntry])
async def get_whitelist(
    current_user: User = Depends(require_role(["admin", "analyst"])),
    db: Session = Depends(get_system_db),
):
    """List current whitelist entries. Admin and analyst can read."""
    entries = db.query(WriteWhitelist).order_by(
        WriteWhitelist.table_name, WriteWhitelist.column_name
    ).all()
    return [
        WhitelistEntry(
            id=str(e.id),
            table_name=e.table_name,
            column_name=e.column_name,
            created_at=e.created_at.isoformat() if e.created_at else None,
        )
        for e in entries
    ]


@router.post("/api/write/whitelist", response_model=List[WhitelistEntry])
async def save_whitelist(
    body: WhitelistSaveRequest,
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_system_db),
):
    """Save whitelist configuration. Admin only."""
    created: List[WhitelistEntry] = []

    for entry_data in body.entries:
        table_name = entry_data.get("table_name", "").strip()
        column_name = entry_data.get("column_name", "").strip()

        if not table_name or not column_name:
            continue

        existing = (
            db.query(WriteWhitelist)
            .filter(
                WriteWhitelist.table_name == table_name,
                WriteWhitelist.column_name == column_name,
            )
            .first()
        )
        if existing:
            created.append(
                WhitelistEntry(
                    id=str(existing.id),
                    table_name=existing.table_name,
                    column_name=existing.column_name,
                    created_at=existing.created_at.isoformat() if existing.created_at else None,
                )
            )
            continue

        new_entry = WriteWhitelist(
            id=uuid_module.uuid4(),
            table_name=table_name,
            column_name=column_name,
        )
        db.add(new_entry)
        db.flush()
        created.append(
            WhitelistEntry(
                id=str(new_entry.id),
                table_name=new_entry.table_name,
                column_name=new_entry.column_name,
                created_at=new_entry.created_at.isoformat() if new_entry.created_at else None,
            )
        )

    db.commit()
    logger.info(f"Whitelist updated by {current_user.email}: {len(created)} entries")
    return created


@router.delete("/api/write/whitelist/{entry_id}")
async def delete_whitelist_entry(
    entry_id: str,
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_system_db),
):
    """Remove a whitelist entry. Admin only."""
    try:
        uid = uuid_module.UUID(entry_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid entry ID",
        )

    entry = db.query(WriteWhitelist).filter(WriteWhitelist.id == uid).first()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Whitelist entry not found",
        )

    db.delete(entry)
    db.commit()
    logger.info(
        f"Whitelist entry deleted by {current_user.email}: "
        f"{entry.table_name}.{entry.column_name}"
    )
    return {"message": f"Whitelist entry '{entry.table_name}.{entry.column_name}' deleted."}


@router.get("/api/write/whitelist/available-tables", response_model=TableColumnsResponse)
async def get_available_tables(
    current_user: User = Depends(require_role(["admin"])),
):
    """Get tables/columns from connected client DB schema. Admin only."""
    try:
        tables = _get_client_tables_and_columns()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read client DB schema: {e}",
        )
    return TableColumnsResponse(tables=tables)


# ===================================================================
# AUDIT LOG
# ===================================================================

@router.get("/api/audit/logs", response_model=AuditLogListResponse)
async def get_audit_logs(
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_system_db),
):
    """List audit log entries with pagination. Admin only."""
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    total = db.query(AuditLog).count()
    offset = (page - 1) * page_size

    entries = (
        db.query(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    logs = [
        AuditLogEntry(
            id=str(e.id),
            user_id=str(e.user_id) if e.user_id else None,
            action=e.action,
            resource=e.resource,
            details=e.details,
            ip_address=e.ip_address,
            created_at=e.created_at.isoformat() if e.created_at else None,
        )
        for e in entries
    ]

    return AuditLogListResponse(
        logs=logs,
        total=total,
        page=page,
        page_size=page_size,
    )