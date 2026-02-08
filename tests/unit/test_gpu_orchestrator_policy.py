import os
from unittest.mock import MagicMock, patch

from agents.gpu_orchestrator.gpu_orchestrator_engine import GPUOrchestratorEngine


def test_policy_enforcement_eviction(monkeypatch):
    # run everything in test mode (workers are sleepers)
    monkeypatch.setenv("RE_RANKER_TEST_MODE", "1")

    monkeypatch.setenv("ADMIN_API_KEY", "adminkey123")
    # Operate directly on the engine (faster / avoids slow app startup in test env)
    fake_db = MagicMock()
    fake_db.mb_conn = MagicMock()
    with patch(
        "agents.gpu_orchestrator.gpu_orchestrator_engine.create_database_service",
        return_value=fake_db,
    ):
        eng = GPUOrchestratorEngine(bootstrap_external_services=True)

        # ensure policy is permissive initially
        eng.set_pool_policy({"enforce_period_s": 1, "max_total_workers": 10})

        # create three pools each with 2 workers -> total 6
        for i in range(3):
            r = eng.start_worker_pool(
                f"tpool{i}",
                "model-x",
                None,
                num_workers=2,
                hold_seconds=30,
                requestor={"user": "test"},
            )
            assert r.get("status") == "started"

        pools = list(eng._WORKER_POOLS.keys())
        assert len(pools) >= 3

        # now tighten policy to max_total_workers = 3 (should evict at least one pool)
        eng.set_pool_policy({"max_total_workers": 3, "enforce_period_s": 1})

        # enforcement is synchronous inside set_pool_policy; verify total workers
        total_workers = sum(p.get("num_workers", 0) for p in eng._WORKER_POOLS.values())
        assert total_workers <= 3

    # ensure policy audit entry created
    pf = "logs/audit/gpu_orchestrator_pool_policy.jsonl"
    assert os.path.exists(pf)
    with open(pf) as f:
        contents = f.read()
    assert "policy_update" in contents or "max_total_workers" in contents
