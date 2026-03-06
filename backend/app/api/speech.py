"""
Speech-to-Text API router — dual-mode: Azure AI Speech (primary) + Azure Whisper (fallback).
"""

import json
import logging
from typing import Optional, Tuple

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/speech", tags=["speech"])

ALLOWED_CONTENT_TYPES = {
    "audio/webm",
    "audio/wav",
    "audio/wave",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp4",
    "audio/ogg",
    "video/webm",
}

MAX_FILE_SIZE = 25 * 1024 * 1024

EXT_MAP = {
    "audio/webm": "webm",
    "video/webm": "webm",
    "audio/wav": "wav",
    "audio/wave": "wav",
    "audio/x-wav": "wav",
    "audio/mpeg": "mp3",
    "audio/mp4": "m4a",
    "audio/ogg": "ogg",
}


class TranscribeResponse(BaseModel):
    text: str
    language: Optional[str] = None
    provider: Optional[str] = None


def _has_azure_speech() -> bool:
    return bool(settings.azure_speech_endpoint and settings.azure_speech_api_key)


def _has_azure_whisper() -> bool:
    return bool(settings.azure_whisper_endpoint and settings.azure_whisper_api_key)


async def _transcribe_azure_speech(
    audio_data: bytes, filename: str, content_type: str
) -> Tuple[str, Optional[str]]:
    """Azure AI Speech Fast Transcription API."""
    endpoint = settings.azure_speech_endpoint.rstrip("/")
    url = f"{endpoint}/speechtotext/transcriptions:transcribe?api-version=2024-11-15"

    definition = json.dumps({"locales": ["it-IT", "en-US"]})

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            url,
            headers={"Ocp-Apim-Subscription-Key": settings.azure_speech_api_key},
            files={"audio": (filename, audio_data, content_type or "audio/wav")},
            data={"definition": definition},
        )

    if response.status_code != 200:
        error_body = response.text[:500]
        logger.error("Azure Speech API error: status=%d body=%s", response.status_code, error_body)
        raise Exception(f"Azure Speech error {response.status_code}: {error_body}")

    result = response.json()
    combined = result.get("combinedPhrases", [])
    text = combined[0].get("text", "").strip() if combined else ""
    phrases = result.get("phrases", [])
    language = phrases[0].get("locale") if phrases else None
    return text, language


async def _transcribe_azure_whisper(
    audio_data: bytes, filename: str, content_type: str
) -> Tuple[str, Optional[str]]:
    """Azure OpenAI Whisper API (fallback)."""
    endpoint = settings.azure_whisper_endpoint.rstrip("/")
    deployment = settings.azure_whisper_deployment_name
    api_version = settings.azure_whisper_api_version
    url = (
        f"{endpoint}/openai/deployments/{deployment}"
        f"/audio/transcriptions?api-version={api_version}"
    )

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            url,
            headers={"api-key": settings.azure_whisper_api_key},
            files={"file": (filename, audio_data, content_type or "audio/webm")},
            data={"response_format": "verbose_json"},
        )

    if response.status_code != 200:
        error_body = response.text[:500]
        logger.error("Azure Whisper API error: status=%d body=%s", response.status_code, error_body)
        raise Exception(f"Azure Whisper error {response.status_code}: {error_body}")

    result = response.json()
    text = result.get("text", "").strip()
    language = result.get("language")
    return text, language


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(file: UploadFile = File(...)):
    """
    Transcribe audio using Azure AI Speech (primary) with Azure Whisper fallback.
    """
    if not _has_azure_speech() and not _has_azure_whisper():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Speech-to-text service is not configured.",
        )

    content_type = file.content_type or ""
    base_content_type = content_type.split(";")[0].strip()
    if base_content_type and base_content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported audio format: {content_type}. Supported: WAV, WebM, MP3, OGG.",
        )

    audio_data = await file.read()
    if not audio_data or len(audio_data) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty audio file.",
        )
    if len(audio_data) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Audio file too large. Maximum size: {MAX_FILE_SIZE // (1024 * 1024)} MB.",
        )

    file_ext = EXT_MAP.get(base_content_type, "webm")
    filename = file.filename or f"audio.{file_ext}"

    # --- Primary: Azure AI Speech ---
    if _has_azure_speech():
        try:
            logger.info("Transcribing via Azure AI Speech (primary)")
            text, language = await _transcribe_azure_speech(audio_data, filename, base_content_type)
            if text:
                return TranscribeResponse(text=text, language=language, provider="azure-speech")
            logger.warning("Azure Speech returned empty text, trying fallback")
        except Exception as exc:
            logger.warning("Azure Speech failed, trying fallback: %s", exc)

    # --- Fallback: Azure Whisper ---
    if _has_azure_whisper():
        try:
            logger.info("Transcribing via Azure Whisper (fallback)")
            text, language = await _transcribe_azure_whisper(audio_data, filename, base_content_type)
            if text:
                return TranscribeResponse(text=text, language=language, provider="azure-whisper")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No speech detected in the audio.",
            )
        except HTTPException:
            raise
        except httpx.TimeoutException:
            logger.error("Azure Whisper API timeout")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Speech-to-text service timed out.",
            )
        except httpx.RequestError as exc:
            logger.error("Azure Whisper request error: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to connect to speech-to-text service.",
            )
        except Exception as exc:
            logger.error("Azure Whisper unexpected error: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Speech-to-text fallback error: {exc}",
            )

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="All speech-to-text providers failed.",
    )