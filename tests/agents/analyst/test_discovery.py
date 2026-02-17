import json
import uuid
import pytest
from unittest.mock import MagicMock, patch
from agents.analyst import discovery

@pytest.fixture
def mock_db_service():
    service = MagicMock()
    service.mb_conn = MagicMock()
    service.chroma_client = MagicMock()
    return service

@patch("agents.analyst.discovery.hdbscan")
@patch("agents.analyst.discovery.create_database_service")
def test_discovery_cycle_creates_story(mock_create_db, mock_hdbscan_mod, mock_db_service):
    """Test that discovery cycle finds a cluster and creates a story."""
    
    mock_create_db.return_value = mock_db_service
    
    # Mock Pending Articles
    cursor = mock_db_service.mb_conn.cursor.return_value
    cursor.fetchall.return_value = [
        {"article_id": 1, "vector_blob": "[0.1, 0.1]", "source_domain": "cnn.com"},
        {"article_id": 2, "vector_blob": "[0.1, 0.15]", "source_domain": "bbc.com"},
        {"article_id": 3, "vector_blob": "[0.1, 0.12]", "source_domain": "reuters.com"},
        {"article_id": 4, "vector_blob": "[0.9, 0.9]", "source_domain": "spam.com"}, # Noise
    ]
    
    # Mock HDBSCAN Clustering
    mock_clusterer = MagicMock()
    # Labels: 0, 0, 0, -1 (3 in cluster 0, 1 noise)
    mock_clusterer.fit_predict.return_value = [0, 0, 0, -1] 
    mock_hdbscan_mod.HDBSCAN.return_value = mock_clusterer
    
    # Act
    discovery.run_discovery_cycle()
    
    # Assert
    # 1. Fetched pending
    assert cursor.execute.call_count >= 1
    
    # 2. HDBSCAN called
    mock_hdbscan_mod.HDBSCAN.assert_called()
    
    # 3. Story Created (INSERT INTO living_stories)
    calls = cursor.execute.call_args_list
    story_insert = [args for args, _ in calls if "INSERT INTO living_stories" in args[0]]
    assert len(story_insert) == 1
    
    # 4. Pending Purged (DELETE FROM pending...)
    purge = [args for args, _ in calls if "DELETE FROM pending_articles_pool" in args[0]]
    assert len(purge) == 1
    # Check that IDs 1, 2, 3 were purged (passed as tuple/list in args)
    assert 1 in purge[0][1]
    assert 4 not in purge[0][1] # Noise item should remain

@patch("agents.analyst.discovery.hdbscan")
@patch("agents.analyst.discovery.create_database_service")
def test_discovery_cycle_insufficient_diversity(mock_create_db, mock_hdbscan_mod, mock_db_service):
    """Test that clusters with low source diversity are skipped."""
    
    mock_create_db.return_value = mock_db_service
    
    # Mock Pending Articles (All from same domain)
    cursor = mock_db_service.mb_conn.cursor.return_value
    cursor.fetchall.return_value = [
        {"article_id": 1, "vector_blob": "[0.1, 0.1]", "source_domain": "same.com"},
        {"article_id": 2, "vector_blob": "[0.1, 0.1]", "source_domain": "same.com"},
        {"article_id": 3, "vector_blob": "[0.1, 0.1]", "source_domain": "same.com"},
    ]
    
    # Mock HDBSCAN Results (All in one cluster)
    mock_clusterer = MagicMock()
    mock_clusterer.fit_predict.return_value = [0, 0, 0]
    mock_hdbscan_mod.HDBSCAN.return_value = mock_clusterer
    
    # Act
    discovery.run_discovery_cycle()
    
    # Assert
    # Should NOT insert a story
    calls = cursor.execute.call_args_list
    story_insert = [args for args, _ in calls if "INSERT INTO living_stories" in args[0]]
    assert len(story_insert) == 0
