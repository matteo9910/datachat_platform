"""
conftest.py - Pre-mock chromadb for Python 3.14 compatibility.

ChromaDB 1.5.x uses pydantic.v1 BaseSettings which is broken on Python 3.14.
We mock the chromadb module before any test imports trigger the crash.
"""
import sys
from unittest.mock import MagicMock

# Only apply if chromadb is not already importable
try:
    import chromadb  # noqa: F401
except Exception:
    # Create a mock chromadb module tree so imports don't fail
    mock_chromadb = MagicMock()
    sys.modules["chromadb"] = mock_chromadb
    sys.modules["chromadb.config"] = mock_chromadb.config
    sys.modules["chromadb.api"] = mock_chromadb.api
    sys.modules["chromadb.api.client"] = mock_chromadb.api.client
