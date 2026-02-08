import agents.common.embedding as embedding


def test_track_and_get_model_memory_usage():
    # Clean state
    with embedding._memory_tracking_lock:
        embedding._model_memory_tracking.clear()

    embedding._track_model_memory_usage("m1", "cpu", 150.0, agent_name="agentx")
    # First access should return 150 and increment access_count
    val = embedding._get_model_memory_usage("m1", "cpu")
    assert val == 150.0
    # Access again -> access_count will increase, still returns same memory
    val2 = embedding._get_model_memory_usage("m1", "cpu")
    assert val2 == 150.0


def test_get_embedding_memory_stats_grouping():
    with embedding._memory_tracking_lock:
        embedding._model_memory_tracking.clear()

    embedding._track_model_memory_usage("m1", "cpu", 100.0, agent_name="a1")
    embedding._track_model_memory_usage("m2", "cuda:0", 250.0, agent_name="a2")

    stats = embedding.get_embedding_memory_stats()
    assert stats["total_models"] == 2
    assert stats["total_memory_mb"] == 350.0
    assert stats["gpu_memory_mb"] == 250.0
    assert stats["cpu_memory_mb"] == 100.0
    assert isinstance(stats["models_by_agent"], dict)


def test_estimate_model_memory_usage_by_name():
    # Strings indicating large/base map to expected estimates
    class Dummy:
        def __init__(self, name):
            self.__repr__ = lambda self=name: name

        def __str__(self):
            return self.__repr__()

    # Use 'auto' device_key so name-based fallback logic is exercised rather than CPU cutoff
    assert embedding._estimate_model_memory_usage(Dummy("LargeModel"), "auto") >= 500
    assert embedding._estimate_model_memory_usage(Dummy("base"), "auto") >= 300
    assert embedding._estimate_model_memory_usage(Dummy("tiny"), "auto") >= 200


def test_get_optimal_embedding_batch_size_with_gpu_manager(monkeypatch):
    class FakeManager:
        def request_gpu_allocation(self, **kwargs):
            return {"status": "allocated", "batch_size": 32}

        def release_gpu_allocation(self, name):
            pass

    monkeypatch.setattr(embedding, "_get_gpu_manager", lambda: FakeManager())
    bs = embedding.get_optimal_embedding_batch_size(device="cuda:0")
    assert bs == 32


def test_embedding_cache_info_and_cleanup():
    # Populate cache and tracking
    with embedding._memory_tracking_lock:
        embedding._model_memory_tracking.clear()
        embedding._model_memory_tracking["a_cpu"] = {
            "memory_mb": 50,
            "device": "cpu",
            "model_name": "a",
            "agent": "x",
            "access_count": 0,
            "loaded_at": 0,
        }

    embedding._MODEL_CACHE.clear()
    embedding._MODEL_CACHE[("name", "cache", "cpu")] = object()

    info = embedding.get_embedding_cache_info()
    assert info["cached_models"] >= 1
    assert info["tracked_models"] >= 1

    embedding.cleanup_embedding_cache()
    # After cleanup both tracking and cache should be empty
    assert len(embedding._MODEL_CACHE) == 0
    assert len(embedding._model_memory_tracking) == 0


def test_ensure_agent_model_exists_returns_existing(tmp_path):
    # Create an agent cache directory and a fake model dir inside
    agent_cache = tmp_path / "agent_models"
    agent_cache.mkdir()
    model_dir = agent_cache / "all-MiniLM-L6-v2"
    model_dir.mkdir()
    # put a dummy file inside to make directory non-empty
    f = model_dir / "modules.json"
    f.write_text("{}")

    res = embedding.ensure_agent_model_exists("all-MiniLM-L6-v2", str(agent_cache))
    assert str(model_dir) == res
