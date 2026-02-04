from agents.crawler import job_store


def test_job_store_create_read_update(monkeypatch):
    # Ensure DB is not required in unit tests (if MySQL not present)
    # We will rely on in-memory fallback
    monkeypatch.setenv("MARIADB_HOST", "invalid-host-for-tests")
    job_id = "testjob123"
    job_store.create_job(job_id, status="pending")
    job = job_store.get_job(job_id)
    assert job is not None
    assert job.get("status") == "pending"
    job_store.update_status(job_id, "running")
    job = job_store.get_job(job_id)
    assert job.get("status") == "running"
    job_store.set_result(job_id, {"articles": []})
    job = job_store.get_job(job_id)
    assert job.get("status") == "completed"
    assert job.get("result") is not None
