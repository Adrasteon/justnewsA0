import uuid

import pytest
from fastapi.testclient import TestClient

from training_system.core.system_manager import get_system_training_manager
from training_system.core.training_coordinator import initialize_online_training
from training_system.mcp_integration import app


@pytest.fixture(scope="module")
def training_manager():
    initialize_online_training(update_threshold=5)
    manager = get_system_training_manager()
    # Ensure empty buffers before tests
    if manager.coordinator and "scout" in manager.coordinator.training_buffers:
        manager.coordinator.training_buffers["scout"].clear()
    return manager


@pytest.fixture
def hitl_payload():
    candidate_id = f"cand-{uuid.uuid4().hex[:8]}"
    return {
        "label_id": f"label-{uuid.uuid4().hex[:8]}",
        "candidate_id": candidate_id,
        "label": "valid_news",
        "annotator_id": "annotator-1",
        "treat_as_valid": True,
        "needs_cleanup": False,
        "qa_sampled": False,
        "cleaned_text": "Clean summary",
        "candidate": {
            "id": candidate_id,
            "url": "https://news.local/story",
            "site_id": "news.local",
            "extracted_title": "Example Story",
            "extracted_text": "Example extracted body text for testing",
        },
    }


def test_process_hitl_label_enqueues_example(training_manager, hitl_payload):
    coordinator = training_manager.coordinator
    assert coordinator is not None
    coordinator.training_buffers["scout"].clear()
    before = len(coordinator.training_buffers["scout"])

    result = training_manager.process_hitl_label(hitl_payload)

    after = len(coordinator.training_buffers["scout"])
    assert after == before + 1
    assert result["label"] == "valid_news"
    assert result["agent_name"] == "scout"


def test_receive_hitl_label_endpoint(training_manager, hitl_payload):
    coordinator = training_manager.coordinator
    assert coordinator is not None
    coordinator.training_buffers["scout"].clear()

    client = TestClient(app)
    with client:
        response = client.post("/tool/receive_hitl_label", json=hitl_payload)
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "success"
        assert payload["data"]["buffer_size"] >= 1
