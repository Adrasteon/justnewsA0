from unittest.mock import MagicMock, patch

from agents.gpu_orchestrator.gpu_orchestrator_engine import GPUOrchestratorEngine


def test_submit_job_persists_and_pushes(monkeypatch):
    # prepare fake DB cursor
    cursor = MagicMock()
    cursor.execute = MagicMock()
    cursor.close = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.commit = MagicMock()

    fake_service = MagicMock()
    fake_service.mb_conn = conn

    fake_redis = MagicMock()
    # patch create_database_service and redis client during engine init
    with patch(
        "agents.gpu_orchestrator.gpu_orchestrator_engine.create_database_service",
        return_value=fake_service,
    ):
        engine = GPUOrchestratorEngine(bootstrap_external_services=True)
        # ensure redis client present
        engine.redis_client = fake_redis
        # call submit_job
        job_id = "j1"
        resp = engine.submit_job(job_id, "inference_jobs", {"foo": "bar"})
        assert resp["job_id"] == job_id
        # DB insert attempted
        assert any(
            "INSERT INTO orchestrator_jobs" in str(call)
            for call in cursor.execute.call_args_list
        )
        # Redis xadd attempted
        assert fake_redis.xadd.called


def test_api_submit_and_get_job(monkeypatch):
    from agents.gpu_orchestrator import main as orchestrator_main

    # Patch engine.submit_job and engine.get_job
    with (
        patch.object(
            orchestrator_main.engine,
            "submit_job",
            return_value={"job_id": "jid", "status": "submitted"},
        ) as _sj,
        patch.object(
            orchestrator_main.engine,
            "get_job",
            return_value={
                "job_id": "jid",
                "type": "inference_jobs",
                "payload": {"a": 1},
                "status": "pending",
            },
        ) as _gj,
    ):
        from fastapi.testclient import TestClient

        tc = TestClient(orchestrator_main.app)
        r = tc.post(
            "/jobs/submit",
            json={"job_id": "jid", "type": "inference_jobs", "payload": {"a": 1}},
        )
        assert r.status_code == 200
        assert r.json()["job_id"] == "jid"

        # GET requires admin key
        monkeypatch.setenv("ADMIN_API_KEY", "adminkey123")
        r2 = tc.get("/jobs/jid", headers={"X-Admin-API-Key": "adminkey123"})
        assert r2.status_code == 200
        assert r2.json()["job_id"] == "jid"
