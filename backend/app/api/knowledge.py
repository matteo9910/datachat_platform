"""
Knowledge Base API router - CRUD for question-SQL pairs with ChromaDB training,
and system instructions management.
"""

import logging
import uuid as uuid_module
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_system_db
from app.models.system import KBPair, Instruction, InstructionType, User
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


# ===========================================================================
# INSTRUCTIONS SCHEMAS
# ===========================================================================

class InstructionCreate(BaseModel):
    type: str  # "global" or "topic"
    topic: Optional[str] = None
    text: str


class InstructionUpdate(BaseModel):
    type: Optional[str] = None
    topic: Optional[str] = None
    text: Optional[str] = None


class InstructionResponse(BaseModel):
    id: str
    type: str
    topic: Optional[str] = None
    text: str
    created_by: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ===========================================================================
# INSTRUCTIONS HELPERS
# ===========================================================================

def _instruction_to_response(inst: Instruction) -> InstructionResponse:
    return InstructionResponse(
        id=str(inst.id),
        type=inst.type.value if hasattr(inst.type, "value") else str(inst.type),
        topic=inst.topic,
        text=inst.text,
        created_by=str(inst.created_by) if inst.created_by else None,
        created_at=inst.created_at.isoformat() if inst.created_at else None,
        updated_at=inst.updated_at.isoformat() if inst.updated_at else None,
    )


def _validate_instruction_type(type_str: str) -> InstructionType:
    """Validate and convert a type string to InstructionType enum."""
    if type_str == "global":
        return InstructionType.global_
    elif type_str == "topic":
        return InstructionType.topic
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid instruction type. Must be 'global' or 'topic'.",
        )


# ===========================================================================
# INSTRUCTIONS ENDPOINTS
# ===========================================================================

@router.get("/instructions", response_model=List[InstructionResponse])
async def list_instructions(
    current_user: User = Depends(require_role(["admin", "analyst"])),
    db: Session = Depends(get_system_db),
):
    """List all instructions (admin/analyst only)."""
    instructions = db.query(Instruction).order_by(Instruction.created_at.desc()).all()
    return [_instruction_to_response(i) for i in instructions]


@router.post("/instructions", response_model=InstructionResponse, status_code=status.HTTP_201_CREATED)
async def create_instruction(
    body: InstructionCreate,
    current_user: User = Depends(require_role(["admin", "analyst"])),
    db: Session = Depends(get_system_db),
):
    """Create a new instruction."""
    if not body.text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Instruction text cannot be empty",
        )

    inst_type = _validate_instruction_type(body.type)

    # Topic is required when type is "topic"
    if inst_type == InstructionType.topic:
        if not body.topic or not body.topic.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Topic is required for topic-type instructions",
            )

    instruction = Instruction(
        id=uuid_module.uuid4(),
        type=inst_type,
        topic=body.topic.strip() if body.topic else None,
        text=body.text.strip(),
        created_by=current_user.id,
    )
    db.add(instruction)
    db.commit()
    db.refresh(instruction)

    return _instruction_to_response(instruction)


@router.put("/instructions/{instruction_id}", response_model=InstructionResponse)
async def update_instruction(
    instruction_id: str,
    body: InstructionUpdate,
    current_user: User = Depends(require_role(["admin", "analyst"])),
    db: Session = Depends(get_system_db),
):
    """Update an existing instruction."""
    try:
        uid = uuid_module.UUID(instruction_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Instruction not found",
        )

    instruction = db.query(Instruction).filter(Instruction.id == uid).first()
    if not instruction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Instruction not found",
        )

    if body.type is not None:
        instruction.type = _validate_instruction_type(body.type)

    if body.topic is not None:
        instruction.topic = body.topic.strip() if body.topic.strip() else None

    if body.text is not None:
        if not body.text.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Instruction text cannot be empty",
            )
        instruction.text = body.text.strip()

    # Validate topic required for topic-type
    effective_type = instruction.type
    if hasattr(effective_type, "value"):
        effective_type_val = effective_type.value
    else:
        effective_type_val = str(effective_type)
    if effective_type_val == "topic" and not instruction.topic:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Topic is required for topic-type instructions",
        )

    db.commit()
    db.refresh(instruction)

    return _instruction_to_response(instruction)


@router.delete("/instructions/{instruction_id}", response_model=MessageResponse)
async def delete_instruction(
    instruction_id: str,
    current_user: User = Depends(require_role(["admin", "analyst"])),
    db: Session = Depends(get_system_db),
):
    """Delete an instruction."""
    try:
        uid = uuid_module.UUID(instruction_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Instruction not found",
        )

    instruction = db.query(Instruction).filter(Instruction.id == uid).first()
    if not instruction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Instruction not found",
        )

    db.delete(instruction)
    db.commit()

    return MessageResponse(message="Instruction deleted successfully")
