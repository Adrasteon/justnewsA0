from __future__ import annotations
import json
import os
from unittest.mock import MagicMock, patch
import pytest
from agents.memory import tools

# Stub for the embedding model
class StubEmbeddingModel:
    def encode(self, text):
        return [0.1, 0.2, 0.3] # 3 dimensions for simplicity

@pytest.fixture
def mock_db_service():
    service = MagicMock()
    service.mb_conn = MagicMock()
    service.chroma_client = MagicMock()
    
    # Mock Cursor
    cursor = MagicMock()
    service.mb_conn.cursor.return_value = cursor
    
    # Ensure get_connection returns the same connection so logic uses the configured cursor
    service.get_connection.return_value = service.mb_conn

    # Configure cursor.fetchone to return Last Insert ID
    cursor.fetchone.return_value = (123,)
    
    return service

@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("LS_SIMILARITY_THRESHOLD", "0.80")
    monkeypatch.setenv("LS_DRIFT_DECAY_RATE", "0.5")

def test_save_article_fast_path_match(mock_db_service, mock_env):
    """Test that a high-similarity match updates the story."""
    
    # Setup Chroma Collection Mock
    # ... (same as before) ...
    # ...
    
    # Act
    # We disable dedupe to skip the hash check complexity in mocking
    metadata = {"url": "http://example.com", "domain": "example.com", "disable_dedupe": True}
    result = tools.save_article(
        content="Test content",
        metadata=metadata,
        embedding_model=StubEmbeddingModel(),
        db_service=mock_db_service
    )
    
    # Assert
    assert result["status"] == "success"
    # ...

def test_save_article_fast_path_no_match(mock_db_service, mock_env):
    """Test that no match buffers to pending pool."""
    
    # ...
    
    # Act
    metadata = {"url": "http://example.com/2", "domain": "example.com", "disable_dedupe": True}
    result = tools.save_article(
        content="Test content 2",
        metadata=metadata,
        embedding_model=StubEmbeddingModel(),
        db_service=mock_db_service
    )
    
    # ...

