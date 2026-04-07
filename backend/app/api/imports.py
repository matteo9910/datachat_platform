"""
File Import API router — upload CSV/Excel, preview schema, confirm import.
"""

import logging
import uuid as uuid_module
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from fastapi import Depends

from app.database import get_system_db
from app.services.import_service import FileImportService, ColumnSchema
from app.services.erp_templates_service import ERPTemplatesService
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/imports", tags=["imports"])

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls"}

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class ColumnSchemaResponse(BaseModel):
    original_name: str
    suggested_name: str
    pg_type: str
    nullable: bool
    sample_values: List[Any] = []


class UploadResponse(BaseModel):
    import_id: str
    filename: str
    file_type: str
    total_rows: int
    columns: List[ColumnSchemaResponse]
    preview_rows: List[Dict[str, Any]]


class ColumnOverride(BaseModel):
    original_name: str
    suggested_name: str
    pg_type: str
    nullable: bool = True


class ConfirmRequest(BaseModel):
    import_id: str
    table_name: str = Field(..., min_length=1, max_length=63)
    columns: List[ColumnOverride]


class ConfirmResponse(BaseModel):
    success: bool
    table_name: str
    rows_imported: int
    errors: List[str] = []


class ImportHistoryItem(BaseModel):
    id: str
    original_filename: str
    table_name: str
    row_count: int
    column_count: int
    source_type: str
    created_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Service singleton
# ---------------------------------------------------------------------------

_service = FileImportService()
_erp_service = ERPTemplatesService()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    """
    Upload a CSV or Excel file. Returns parsed preview + inferred schema.
    The data is held in memory (keyed by import_id) for the confirm step.
    """
    # Validate extension
    filename = file.filename or "unknown"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: .{ext}. Use .csv, .xlsx, or .xls",
        )

    # Read bytes
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file.",
        )
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum: {MAX_FILE_SIZE // (1024*1024)} MB.",
        )

    # Parse
    try:
        parsed = _service.parse_file(file_bytes, filename)
    except Exception as e:
        logger.error(f"File parse error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse file: {e}",
        )

    # Infer schema
    schema = _service.infer_schema(parsed.df)

    # Try LLM column name suggestions (non-blocking)
    try:
        import asyncio
        schema = await _service.suggest_column_names(schema)
    except Exception as e:
        logger.warning(f"LLM suggestion skipped: {e}")

    # Store in memory
    import_id = str(uuid_module.uuid4())
    _service.store_pending(import_id, parsed, schema)

    return UploadResponse(
        import_id=import_id,
        filename=parsed.filename,
        file_type=parsed.file_type,
        total_rows=parsed.total_rows,
        columns=[
            ColumnSchemaResponse(
                original_name=cs.original_name,
                suggested_name=cs.suggested_name,
                pg_type=cs.pg_type,
                nullable=cs.nullable,
                sample_values=cs.sample_values,
            )
            for cs in schema
        ],
        preview_rows=parsed.preview_rows,
    )


@router.post("/confirm", response_model=ConfirmResponse)
async def confirm_import(
    body: ConfirmRequest,
    db: Session = Depends(get_system_db),
):
    """
    Confirm import: CREATE TABLE + INSERT data into the connected client DB.
    Uses the import_id from the upload step.
    """
    pending = _service.get_pending(body.import_id)
    if not pending:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Import session not found or expired. Please re-upload the file.",
        )

    parsed = pending["parsed"]
    # Build ColumnSchema list from user overrides
    columns = [
        ColumnSchema(
            original_name=co.original_name,
            suggested_name=co.suggested_name,
            pg_type=co.pg_type,
            nullable=co.nullable,
        )
        for co in body.columns
    ]

    result = _service.create_table_and_import(
        table_name=body.table_name,
        columns=columns,
        df=parsed.df,
    )

    # Persist to import_history in system DB
    if result.success:
        try:
            from app.models.system import ImportHistory
            history = ImportHistory(
                id=uuid_module.uuid4(),
                original_filename=parsed.filename,
                table_name=result.table_name,
                row_count=result.rows_imported,
                column_count=len(columns),
                schema_json={
                    "columns": [
                        {"name": c.suggested_name, "type": c.pg_type, "nullable": c.nullable}
                        for c in columns
                    ]
                },
                source_type=parsed.file_type,
            )
            db.add(history)
            db.commit()
        except Exception as e:
            logger.warning(f"Failed to save import history (non-blocking): {e}")

    # Clean up pending data
    _service.remove_pending(body.import_id)

    return ConfirmResponse(
        success=result.success,
        table_name=result.table_name,
        rows_imported=result.rows_imported,
        errors=result.errors,
    )


@router.get("/history", response_model=List[ImportHistoryItem])
async def get_import_history(db: Session = Depends(get_system_db)):
    """Return recent import history from system DB."""
    try:
        from app.models.system import ImportHistory
        entries = (
            db.query(ImportHistory)
            .order_by(ImportHistory.created_at.desc())
            .limit(50)
            .all()
        )
        return [
            ImportHistoryItem(
                id=str(e.id),
                original_filename=e.original_filename,
                table_name=e.table_name,
                row_count=e.row_count,
                column_count=e.column_count,
                source_type=e.source_type or "csv",
                created_at=e.created_at.isoformat() if e.created_at else None,
            )
            for e in entries
        ]
    except Exception as e:
        logger.warning(f"Import history query failed: {e}")
        return []


# ---------------------------------------------------------------------------
# ERP Template endpoints
# ---------------------------------------------------------------------------


class ERPTemplateItem(BaseModel):
    id: str
    erp_name: str
    export_type: str
    description: str
    instructions: str
    column_count: int


class ERPColumnMatch(BaseModel):
    original_name: str
    matched_erp_column: Optional[str] = None
    suggested_name: str
    pg_type: str
    nullable: bool = True
    confidence: float = 0.0


class ERPUploadResponse(BaseModel):
    import_id: str
    filename: str
    file_type: str
    total_rows: int
    template_id: str
    erp_name: str
    columns: List[ERPColumnMatch]
    preview_rows: List[Dict[str, Any]]


@router.get("/erp/templates", response_model=List[ERPTemplateItem])
async def list_erp_templates():
    """List all available ERP export templates."""
    return _erp_service.list_templates()


@router.post("/erp/upload", response_model=ERPUploadResponse)
async def upload_erp_file(
    template_id: str,
    file: UploadFile = File(...),
):
    """
    Upload a CSV/Excel file with an ERP template.
    Columns are auto-matched against the template's expected columns.
    """
    template = _erp_service.get_template(template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown template: {template_id}",
        )

    # Validate extension
    filename = file.filename or "unknown"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: .{ext}. Use .csv, .xlsx, or .xls",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file.")
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum: {MAX_FILE_SIZE // (1024*1024)} MB.",
        )

    try:
        parsed = _service.parse_file(file_bytes, filename)
    except Exception as e:
        logger.error(f"ERP file parse error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse file: {e}",
        )

    # Match columns against template
    matched = _erp_service.match_columns(template_id, list(parsed.df.columns))

    # Build schema from matched columns (for the confirm step)
    schema = [
        ColumnSchema(
            original_name=m["original_name"],
            suggested_name=m["suggested_name"],
            pg_type=m["pg_type"],
            nullable=m["nullable"],
        )
        for m in matched
    ]

    import_id = str(uuid_module.uuid4())
    _service.store_pending(import_id, parsed, schema)

    return ERPUploadResponse(
        import_id=import_id,
        filename=parsed.filename,
        file_type=parsed.file_type,
        total_rows=parsed.total_rows,
        template_id=template_id,
        erp_name=template.erp_name,
        columns=[
            ERPColumnMatch(
                original_name=m["original_name"],
                matched_erp_column=m.get("matched_erp_column"),
                suggested_name=m["suggested_name"],
                pg_type=m["pg_type"],
                nullable=m["nullable"],
                confidence=m.get("confidence", 0.0),
            )
            for m in matched
        ],
        preview_rows=parsed.preview_rows,
    )
