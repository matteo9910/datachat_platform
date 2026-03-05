"""
Tests for Speech-to-Text (Azure Whisper) API endpoint.

Mocks the Azure Whisper API to avoid real network calls.
"""

from io import BytesIO
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.speech import router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch):
    """Ensure whisper settings are configured for tests."""
    from app.config import settings
    monkeypatch.setattr(settings, "azure_whisper_endpoint", "https://test-whisper.azure.com")
    monkeypatch.setattr(settings, "azure_whisper_api_key", "test-api-key")
    monkeypatch.setattr(settings, "azure_whisper_deployment_name", "whisper")
    monkeypatch.setattr(settings, "azure_whisper_api_version", "2024-06-01")


@pytest.fixture()
def client():
    """FastAPI TestClient with the speech router."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helper: create fake audio bytes
# ---------------------------------------------------------------------------

def _fake_audio(size: int = 1024) -> bytes:
    return b"\x00" * size


# ---------------------------------------------------------------------------
# Tests: Validation
# ---------------------------------------------------------------------------

class TestTranscribeValidation:
    """Test input validation for the transcribe endpoint."""

    def test_empty_audio_returns_400(self, client):
        """Empty file should return 400."""
        resp = client.post(
            "/api/speech/transcribe",
            files={"file": ("empty.webm", b"", "audio/webm")},
        )
        assert resp.status_code == 400
        assert "Empty audio" in resp.json()["detail"]

    def test_unsupported_format_returns_400(self, client):
        """Unsupported MIME type should return 400."""
        resp = client.post(
            "/api/speech/transcribe",
            files={"file": ("test.txt", b"hello", "text/plain")},
        )
        assert resp.status_code == 400
        assert "Unsupported audio format" in resp.json()["detail"]

    def test_file_too_large_returns_400(self, client):
        """File exceeding 25 MB should return 400."""
        huge = b"\x00" * (26 * 1024 * 1024)
        resp = client.post(
            "/api/speech/transcribe",
            files={"file": ("big.webm", huge, "audio/webm")},
        )
        assert resp.status_code == 400
        assert "too large" in resp.json()["detail"]

    def test_missing_config_returns_503(self, client, monkeypatch):
        """Missing Azure Whisper config should return 503."""
        from app.config import settings
        monkeypatch.setattr(settings, "azure_whisper_endpoint", None)

        resp = client.post(
            "/api/speech/transcribe",
            files={"file": ("test.webm", _fake_audio(), "audio/webm")},
        )
        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"]

    def test_no_file_returns_422(self, client):
        """Missing file parameter should return 422."""
        resp = client.post("/api/speech/transcribe")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Tests: Successful transcription (mocked Azure API)
# ---------------------------------------------------------------------------

class TestTranscribeSuccess:
    """Test successful transcription with mocked Azure responses."""

    @patch("app.api.speech.httpx.AsyncClient")
    def test_webm_transcription(self, mock_client_cls, client):
        """WebM audio should be transcribed successfully."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "text": "Ciao, come stai?",
            "language": "it",
        }

        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_instance

        resp = client.post(
            "/api/speech/transcribe",
            files={"file": ("recording.webm", _fake_audio(), "audio/webm")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["text"] == "Ciao, come stai?"
        assert data["language"] == "it"

    @patch("app.api.speech.httpx.AsyncClient")
    def test_wav_transcription(self, mock_client_cls, client):
        """WAV audio should be transcribed successfully."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "text": "Hello world",
            "language": "en",
        }

        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_instance

        resp = client.post(
            "/api/speech/transcribe",
            files={"file": ("recording.wav", _fake_audio(), "audio/wav")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["text"] == "Hello world"
        assert data["language"] == "en"

    @patch("app.api.speech.httpx.AsyncClient")
    def test_video_webm_accepted(self, mock_client_cls, client):
        """video/webm MIME type (some browsers) should be accepted."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "text": "Test audio",
            "language": "en",
        }

        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_instance

        resp = client.post(
            "/api/speech/transcribe",
            files={"file": ("recording.webm", _fake_audio(), "video/webm")},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Tests: Azure API error handling
# ---------------------------------------------------------------------------

class TestTranscribeErrors:
    """Test error handling for Azure Whisper API failures."""

    @patch("app.api.speech.httpx.AsyncClient")
    def test_azure_api_error_returns_502(self, mock_client_cls, client):
        """Non-200 from Azure should return 502."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_instance

        resp = client.post(
            "/api/speech/transcribe",
            files={"file": ("test.webm", _fake_audio(), "audio/webm")},
        )
        assert resp.status_code == 502

    @patch("app.api.speech.httpx.AsyncClient")
    def test_azure_timeout_returns_502(self, mock_client_cls, client):
        """Timeout connecting to Azure should return 502."""
        import httpx

        mock_instance = AsyncMock()
        mock_instance.post.side_effect = httpx.TimeoutException("timeout")
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_instance

        resp = client.post(
            "/api/speech/transcribe",
            files={"file": ("test.webm", _fake_audio(), "audio/webm")},
        )
        assert resp.status_code == 502
        assert "timed out" in resp.json()["detail"]

    @patch("app.api.speech.httpx.AsyncClient")
    def test_azure_connection_error_returns_502(self, mock_client_cls, client):
        """Connection error to Azure should return 502."""
        import httpx

        mock_instance = AsyncMock()
        mock_instance.post.side_effect = httpx.ConnectError("connection refused")
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_instance

        resp = client.post(
            "/api/speech/transcribe",
            files={"file": ("test.webm", _fake_audio(), "audio/webm")},
        )
        assert resp.status_code == 502
        assert "Failed to connect" in resp.json()["detail"]

    @patch("app.api.speech.httpx.AsyncClient")
    def test_no_speech_detected_returns_400(self, mock_client_cls, client):
        """Empty transcription text should return 400."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "text": "",
            "language": None,
        }

        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_instance

        resp = client.post(
            "/api/speech/transcribe",
            files={"file": ("silence.webm", _fake_audio(), "audio/webm")},
        )
        assert resp.status_code == 400
        assert "No speech detected" in resp.json()["detail"]