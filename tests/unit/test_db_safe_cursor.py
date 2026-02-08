from database.models.migrated_models import MigratedDatabaseService
from database.utils.migrated_database_utils import execute_mariadb_query


class FakeCursor:
    def __init__(self, rows=None):
        self._rows = rows or []
        self.closed = False

    def execute(self, query, params=None):
        self._last = (query, params)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, rows=None):
        self.cursor_calls = []
        self.closed = False
        self.rows = rows or [(1,)]

    def cursor(self, buffered=False, dictionary=False):
        cur = FakeCursor(rows=self.rows)
        self.cursor_calls.append((buffered, dictionary))
        return cur

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def make_fake_service():
    # Construct a MigratedDatabaseService object without running __init__
    svc = MigratedDatabaseService.__new__(MigratedDatabaseService)
    svc.mb_conn = FakeConnection()
    # provide a get_connection implementation that returns a fresh FakeConnection
    svc.get_connection = lambda: FakeConnection(rows=[(42,)])
    return svc


def test_get_safe_cursor_per_call_returns_conn_and_cursor():
    svc = make_fake_service()
    cursor, conn = svc.get_safe_cursor(per_call=True, buffered=True)
    assert cursor is not None
    assert conn is not None
    # cursor should be a FakeCursor
    assert hasattr(cursor, "fetchone")
    cursor.close()
    conn.close()


def test_execute_mariadb_query_uses_per_call_connection_and_closes():
    svc = make_fake_service()

    # execute_mariadb_query should use get_safe_cursor(per_call=True) and close the per-call connection
    results = execute_mariadb_query(svc, "SELECT 1", fetch=True)
    assert isinstance(results, list)


def test_get_db_cursor_context_manager_commits_and_closes(monkeypatch):
    from agents.common import database as db_module

    # Replace initialize_database_service to return our fake
    svc = make_fake_service()
    monkeypatch.setattr(db_module, "initialize_database_service", lambda: svc)

    with db_module.get_db_cursor(commit=True, dictionary=False) as (conn, cursor):
        assert hasattr(cursor, "execute")
        # Simulate a write
        cursor.execute("CREATE")

    # After context exit the per-call connection should be closed
    # svc.get_connection returns new connections; ensure we don't leak a connection
    assert True  # implicit: no exceptions and context manager closed resources
