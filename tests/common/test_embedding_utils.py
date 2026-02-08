import inspect
import types

import pytest

from agents.common import embedding as emb


def test_detect_caller_agent_with_fake_stack(monkeypatch):
    # Create fake frame objects with filenames that include agents/<agent>/
    fake_frame = types.SimpleNamespace(filename="/project/agents/memory/somefile.py")
    monkeypatch.setattr(inspect, "stack", lambda: [fake_frame])

    agent = emb._detect_caller_agent()
    assert agent == "memory"


def test_track_and_get_memory_stats(monkeypatch):
    # Ensure a clean slate
    emb._model_memory_tracking.clear()

    # Track two models on different devices
    emb._track_model_memory_usage("modelA", "cpu", 150.0, "memory")
    emb._track_model_memory_usage("modelB", "cuda:0", 300.0, "synthesizer")

    # Access model memory which should increase access_count
    memA = emb._get_model_memory_usage("modelA", "cpu")
    assert memA == 150.0

    memB = emb._get_model_memory_usage("modelB", "cuda:0")
    assert memB == 300.0

    stats = emb.get_embedding_memory_stats()
    assert stats["total_models"] == 2
    assert stats["total_memory_mb"] == pytest.approx(450.0)
    assert stats["gpu_memory_mb"] == pytest.approx(300.0)
    assert stats["cpu_memory_mb"] == pytest.approx(150.0)


def test_get_embedding_cache_info_and_cleanup(monkeypatch):
    # Put synthetic entries into cache and model tracking
    emb._MODEL_CACHE.clear()
    emb._model_memory_tracking.clear()

    emb._MODEL_CACHE[("m1", "/tmp", "cpu")] = object()
    emb._MODEL_CACHE[("m2", "/tmp", "cuda:0")] = object()
    emb._track_model_memory_usage("m1", "cpu", 120.0, "memory")
    emb._track_model_memory_usage("m2", "cuda:0", 240.0, "synth")

    info = emb.get_embedding_cache_info()
    assert info["cached_models"] == 2
    assert info["tracked_models"] == 2

    # Now cleanup and validate empty state
    emb.cleanup_embedding_cache()
    assert len(emb._MODEL_CACHE) == 0
    assert len(emb._model_memory_tracking) == 0


def test_get_optimal_embedding_batch_size_fallback(monkeypatch):
    # Force gpu manager to None to exercise CPU fallback
    monkeypatch.setattr(emb, "_get_gpu_manager", lambda: None)

    # No device specified -> CPU default
    bs_cpu = emb.get_optimal_embedding_batch_size(device=None)
    assert isinstance(bs_cpu, int)
    assert bs_cpu == 4

    # When device startswith 'cuda' fallback should return GPU default
    bs_gpu = emb.get_optimal_embedding_batch_size(device="cuda:0")
    assert bs_gpu == 16
