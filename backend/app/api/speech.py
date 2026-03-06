"""
Speech-to-Text API router — Azure Whisper transcription.
"""

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/speech", tags=["speech"])

# Allowed audio MIME types
ALLOWED_CONTENT_TYPES = {
    "audio/webm",
    "audio/wav",
    "audio/wave",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp4",
    "audio/ogg",
    "video/webm",  # MediaRecorder on some browsers produces video/webm
}

# Maximum file size: 25 MB (Azure Whisper limit)
MAX_FILE_SIZE = 25 * 1024 * 1024


class TranscribeResponse(BaseModel):
    text: str
    language: Optional[str] = None


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(file: UploadFile = File(...)):
    """
    Transcribe an audio file using Azure Whisper API.

    Accepts WAV, WebM, and other common audio formats.
    Returns the transcribed text and detected language.
    """

    # Validate configuration
    if not settings.azure_whisper_endpoint or not settings.azure_whisper_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Speech-to-text service is not configured.",
        )

    # Validate content type (strip codec params like ";codecs=opus")
    content_type = file.content_type or ""
    base_content_type = content_type.split(";")[0].strip()
    if base_content_type and base_content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported audio format: {content_type}. Supported: WAV, WebM, MP3, OGG.",
        )

    # Read and validate audio data
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

    # Determine file extension from content type
    ext_map = {
        "audio/webm": "webm",
        "video/webm": "webm",
        "audio/wav": "wav",
        "audio/wave": "wav",
        "audio/x-wav": "wav",
        "audio/mpeg": "mp3",
        "audio/mp4": "m4a",
        "audio/ogg": "ogg",
    }
    file_ext = ext_map.get(base_content_type, "webm")
    filename = file.filename or f"audio.{file_ext}"

    # Build Azure Whisper API URL
    endpoint = settings.azure_whisper_endpoint.rstrip("/")
    deployment = settings.azure_whisper_deployment_name
    api_version = settings.azure_whisper_api_version
    url = (
        f"{endpoint}/openai/deployments/{deployment}"
        f"/audio/transcriptions?api-version={api_version}"
    )

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
                headers={"api-key": settings.azure_whisper_api_key},
                files={"file": (filename, audio_data, base_content_type or "audio/webm")},
                data={"response_format": "verbose_json"},
            )

        if response.status_code != 200:
            logger.error(
                "Azure Whisper API error: status=%d body=%s",
                response.status_code,
                response.text[:500],
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Speech-to-text service returned an error.",
            )

        result = response.json()
        text = result.get("text", "").strip()
        language = result.get("language")

        if not text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No speech detected in the audio.",
            )

        return TranscribeResponse(text=text, language=language)

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
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Unexpected error in transcribe: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during transcription.",
        )