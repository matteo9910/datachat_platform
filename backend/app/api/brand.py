"""
Brand Configuration API router - GET/POST brand settings for charts/dashboards.

All authenticated users can read the brand config (needed for frontend styling).
Only admins can save/update the brand config.
"""

import logging
import re
import uuid as uuid_module
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_system_db
from app.models.system import BrandConfig, User
from app.services.auth_middleware import require_role, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/brand", tags=["brand"])


# ---------------------------------------------------------------------------
# Default brand values (used when no config saved)
# ---------------------------------------------------------------------------

DEFAULT_BRAND = {
    "primary_color": "#1f77b4",
    "secondary_color": "#ff7f0e",
    "accent_colors": [
        "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    ],
    "font_family": "Inter, system-ui, sans-serif",
    "logo_url": None,
}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class BrandConfigResponse(BaseModel):
    id: Optional[str] = None
    primary_color: str
    secondary_color: str
    accent_colors: List[str]
    font_family: str
    logo_url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class BrandConfigSave(BaseModel):
    primary_color: str
    secondary_color: str
    accent_colors: Optional[List[str]] = None
    font_family: Optional[str] = None
    logo_url: Optional[str] = None


class MessageResponse(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _config_to_response(cfg: BrandConfig) -> BrandConfigResponse:
    return BrandConfigResponse(
        id=str(cfg.id),
        primary_color=cfg.primary_color or DEFAULT_BRAND["primary_color"],
        secondary_color=cfg.secondary_color or DEFAULT_BRAND["secondary_color"],
        accent_colors=cfg.accent_colors if cfg.accent_colors else DEFAULT_BRAND["accent_colors"],
        font_family=cfg.font_family or DEFAULT_BRAND["font_family"],
        logo_url=cfg.logo_url,
        created_at=cfg.created_at.isoformat() if cfg.created_at else None,
        updated_at=cfg.updated_at.isoformat() if cfg.updated_at else None,
    )


def _default_response() -> BrandConfigResponse:
    return BrandConfigResponse(
        id=None,
        primary_color=DEFAULT_BRAND["primary_color"],
        secondary_color=DEFAULT_BRAND["secondary_color"],
        accent_colors=DEFAULT_BRAND["accent_colors"],
        font_family=DEFAULT_BRAND["font_family"],
        logo_url=None,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/config", response_model=BrandConfigResponse)
async def get_brand_config(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_system_db),
):
    """
    Get current brand configuration. Returns defaults if none saved.
    All authenticated roles can read (admin, analyst, user).
    """
    cfg = db.query(BrandConfig).first()
    if cfg is None:
        return _default_response()
    return _config_to_response(cfg)


@router.post("/config", response_model=BrandConfigResponse)
async def save_brand_config(
    body: BrandConfigSave,
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_system_db),
):
    """
    Save or update brand configuration. Admin only.
    Upserts: if a config row already exists, it is updated; otherwise created.
    """
    # Validate hex colors
    hex_pattern = re.compile(r"^#[0-9a-fA-F]{6}$")

    if not hex_pattern.match(body.primary_color):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="primary_color must be a valid hex color (e.g. #FF5500)",
        )
    if not hex_pattern.match(body.secondary_color):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="secondary_color must be a valid hex color (e.g. #FF5500)",
        )

    accent = body.accent_colors or []
    for color in accent:
        if not hex_pattern.match(color):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid accent color: {color}. Must be hex (e.g. #FF5500)",
            )

    # Upsert: update existing or create new
    cfg = db.query(BrandConfig).first()
    if cfg is None:
        cfg = BrandConfig(
            id=uuid_module.uuid4(),
            primary_color=body.primary_color,
            secondary_color=body.secondary_color,
            accent_colors=accent if accent else None,
            font_family=body.font_family or DEFAULT_BRAND["font_family"],
            logo_url=body.logo_url,
        )
        db.add(cfg)
    else:
        cfg.primary_color = body.primary_color
        cfg.secondary_color = body.secondary_color
        cfg.accent_colors = accent if accent else None
        cfg.font_family = body.font_family or DEFAULT_BRAND["font_family"]
        cfg.logo_url = body.logo_url

    db.commit()
    db.refresh(cfg)

    logger.info(f"Brand config saved by user {current_user.email}")
    return _config_to_response(cfg)
