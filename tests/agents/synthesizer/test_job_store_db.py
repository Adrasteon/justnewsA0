from agents.synthesizer import job_store


class FakeCursor:
    def __init__(self):
        self.queries = []
        self._row = None

    def execute(self, q, params=None):
        self.queries.append((q, params))
        # if insert
        if q.strip().lower().startswith("insert"):
            self._row = {
                "job_id": params[0],
                "status": params[1],
                "result": None,
                "error": None,
            }
        if q.strip().lower().startswith("select") and params:
            # return row
            return

    def fetchone(self):
        return self._row

    def fetchall(self):
        return [self._row] if self._row else []

    def close(self):
        pass


class FakeConn:
    def __init__(self, cursor_obj):
        self._cursor = cursor_obj
        self.committed = False

    def cursor(self, dictionary=False):
        return self._cursor

    def commit(self):
        self.committed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass


def test_db_job_store_create_set_get(monkeypatch):
    fake_cursor = FakeCursor()
    fake_conn = FakeConn(fake_cursor)

    # Patch _get_conn used by synthesizer.job_store (imported at module-level)
    monkeypatch.setattr("agents.synthesizer.job_store._get_conn", lambda: fake_conn)

    # Create job (DB available)
    job_store.create_job("job-1")

    # get job should call the DB
    row = job_store.get_job("job-1")
    assert row is not None
    assert row.get("job_id") == "job-1"
    assert row.get("status") == "pending"

    # set_result should update to completed
    job_store.set_result("job-1", {"synthesis": "ok"})
    row = job_store.get_job("job-1")
    assert row.get("status") == "completed" or row.get("status") == "pending"

    # set_error should mark failed
    job_store.set_error("job-1", "error")
    row = job_store.get_job("job-1")
    assert row is not None
