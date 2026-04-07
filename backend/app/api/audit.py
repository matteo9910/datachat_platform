"""
Database Audit API router — trigger audit, retrieve results, history.
"""

import logging
import uuid as uuid_module
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_system_db
from app.services.data_quality_service import DataQualityService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/database/audit", tags=["audit"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class AuditRunRequest(BaseModel):
    llm_provider: Optional[str] = None


class AuditReportResponse(BaseModel):
    id: Optional[str] = None
    overall_score: int
    dimensions: Dict[str, Any]
    recommendations: List[str]
    summary: str
    table_count: int
    generated_at: str


class AuditHistoryItem(BaseModel):
    id: str
    overall_score: int
    table_count: int
    summary: str
    created_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/run", response_model=AuditReportResponse)
async def run_audit(body: AuditRunRequest = AuditRunRequest()):
    """Trigger a full data quality audit on the connected database."""
    try:
        service = DataQualityService()
        result = service.run_full_audit(llm_provider=body.llm_provider)

        # Persist to system DB
        report_id = _save_report(result)

        return AuditReportResponse(
            id=report_id,
            overall_score=result.overall_score,
            dimensions=result.dimensions,
            recommendations=result.recommendations,
            summary=result.summary,
            table_count=result.table_count,
            generated_at=result.generated_at,
        )
    except Exception as e:
        logger.error(f"Audit run failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Audit failed: {str(e)}")


@router.get("/latest", response_model=Optional[AuditReportResponse])
async def get_latest_audit(db: Session = Depends(get_system_db)):
    """Return the most recent audit report."""
    try:
        from app.models.system import AuditReport
        report = (
            db.query(AuditReport)
            .order_by(AuditReport.created_at.desc())
            .first()
        )
        if not report:
            return None
        return AuditReportResponse(
            id=str(report.id),
            overall_score=report.overall_score,
            dimensions=report.dimensions or {},
            recommendations=report.recommendations or [],
            summary=report.summary or "",
            table_count=report.table_count or 0,
            generated_at=report.created_at.isoformat() if report.created_at else "",
        )
    except Exception as e:
        logger.error(f"Get latest audit failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history", response_model=List[AuditHistoryItem])
async def get_audit_history(
    limit: int = Query(default=20, le=100),
    db: Session = Depends(get_system_db),
):
    """Return audit history (last N reports)."""
    try:
        from app.models.system import AuditReport
        reports = (
            db.query(AuditReport)
            .order_by(AuditReport.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            AuditHistoryItem(
                id=str(r.id),
                overall_score=r.overall_score,
                table_count=r.table_count or 0,
                summary=r.summary or "",
                created_at=r.created_at.isoformat() if r.created_at else None,
            )
            for r in reports
        ]
    except Exception as e:
        logger.error(f"Get audit history failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _save_report(result) -> str:
    """Persist an AuditResult into the system database."""
    try:
        from app.database import get_system_session_factory
        from app.models.system import AuditReport

        SessionFactory = get_system_session_factory()
        db = SessionFactory()
        try:
            report = AuditReport(
                id=uuid_module.uuid4(),
                overall_score=result.overall_score,
                dimensions=result.dimensions,
                recommendations=result.recommendations,
                summary=result.summary,
                table_count=result.table_count,
            )
            db.add(report)
            db.commit()
            return str(report.id)
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Failed to persist audit report: {e}")
        return str(uuid_module.uuid4())
