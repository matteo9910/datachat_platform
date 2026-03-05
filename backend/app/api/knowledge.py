"""
Knowledge Base API router - CRUD for question-SQL pairs with ChromaDB training.
"""

import logging
import uuid as uuid_module
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_system_db
from app.models.system import KBPair, User
from app.services.auth_middleware import require_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class KBPairCreate(BaseModel):
    question: str
    sql_query: str


class KBPairUpdate(BaseModel):
    question: Optional[str] = None
    sql_query: Optional[str] = None


class KBPairResponse(BaseModel):
    id: str
    question: str
    sql_query: str
    created_by: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class MessageResponse(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _train_chromadb(question: str, sql_query: str) -> None:
    """Train ChromaDB with a question-SQL pair (best-effort)."""
    try:
        from app.services.vanna_service import get_vanna_service
        service = get_vanna_service()
        service.train_on_sql(question, sql_query)
        logger.info(f"ChromaDB trained: {question[:50]}...")
    except Exception as e:
        logger.warning(f"ChromaDB training failed (non-blocking): {e}")


def _pair_to_response(pair: KBPair) -> KBPairResponse:
    return KBPairResponse(
        id=str(pair.id),
        question=pair.question,
        sql_query=pair.sql_query,
        created_by=str(pair.created_by) if pair.created_by else None,
        created_at=pair.created_at.isoformat() if pair.created_at else None,
        updated_at=pair.updated_at.isoformat() if pair.updated_at else None,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/pairs", response_model=List[KBPairResponse])
async def list_pairs(
    current_user: User = Depends(require_role(["admin", "analyst"])),
    db: Session = Depends(get_system_db),
):
    """List all KB pairs (admin/analyst only)."""
    pairs = db.query(KBPair).order_by(KBPair.created_at.desc()).all()
    return [_pair_to_response(p) for p in pairs]


@router.post("/pairs", response_model=KBPairResponse, status_code=status.HTTP_201_CREATED)
async def create_pair(
    body: KBPairCreate,
    current_user: User = Depends(require_role(["admin", "analyst"])),
    db: Session = Depends(get_system_db),
):
    """Create a new KB pair and train ChromaDB."""
    if not body.question.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question cannot be empty",
        )
    if not body.sql_query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SQL query cannot be empty",
        )

    pair = KBPair(
        id=uuid_module.uuid4(),
        question=body.question.strip(),
        sql_query=body.sql_query.strip(),
        created_by=current_user.id,
    )
    db.add(pair)
    db.commit()
    db.refresh(pair)

    # Train ChromaDB (best-effort, non-blocking for DB commit)
    _train_chromadb(pair.question, pair.sql_query)

    return _pair_to_response(pair)


@router.put("/pairs/{pair_id}", response_model=KBPairResponse)
async def update_pair(
    pair_id: str,
    body: KBPairUpdate,
    current_user: User = Depends(require_role(["admin", "analyst"])),
    db: Session = Depends(get_system_db),
):
    """Update a KB pair and retrain ChromaDB."""
    try:
        uid = uuid_module.UUID(pair_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="KB pair not found",
        )

    pair = db.query(KBPair).filter(KBPair.id == uid).first()
    if not pair:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="KB pair not found",
        )

    if body.question is not None:
        if not body.question.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Question cannot be empty",
            )
        pair.question = body.question.strip()

    if body.sql_query is not None:
        if not body.sql_query.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="SQL query cannot be empty",
            )
        pair.sql_query = body.sql_query.strip()

    db.commit()
    db.refresh(pair)

    # Retrain ChromaDB with updated pair
    _train_chromadb(pair.question, pair.sql_query)

    return _pair_to_response(pair)


@router.delete("/pairs/{pair_id}", response_model=MessageResponse)
async def delete_pair(
    pair_id: str,
    current_user: User = Depends(require_role(["admin", "analyst"])),
    db: Session = Depends(get_system_db),
):
    """Delete a KB pair. Note: ChromaDB removal is best-effort."""
    try:
        uid = uuid_module.UUID(pair_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="KB pair not found",
        )

    pair = db.query(KBPair).filter(KBPair.id == uid).first()
    if not pair:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="KB pair not found",
        )

    # Attempt to remove from ChromaDB (best-effort)
    try:
        from app.services.vanna_service import get_vanna_service
        service = get_vanna_service()
        doc_id = f"sql_{hash(pair.question + pair.sql_query) % 10**8}"
        service.sql_collection.delete(ids=[doc_id])
        logger.info(f"Removed from ChromaDB: {doc_id}")
    except Exception as e:
        logger.warning(f"ChromaDB removal failed (non-blocking): {e}")

    db.delete(pair)
    db.commit()

    return MessageResponse(message="KB pair deleted successfully")
