import sys

import pytest


def run_script_main(monkeypatch, **env):
    # Import the script fresh to avoid cached sys.modules side-effects
    if "scripts.chroma_bootstrap" in sys.modules:
        del sys.modules["scripts.chroma_bootstrap"]
    monkeypatch.setenv("PYTEST_RUNNING", "1")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import scripts.chroma_bootstrap as cb

    # Clear sys.argv so argparse doesn't pick test runner args
    monkeypatch.setattr("sys.argv", ["chroma_bootstrap.py", "--require-canonical"])
    with pytest.raises(SystemExit) as excinfo:
        cb.main()
    return excinfo.value.code


def test_chroma_bootstrap_requires_canonical(monkeypatch):
    # Simulate canonical validation failing
    def fake_validate_chroma_is_canonical(
        host, port, canonical_host, canonical_port, raise_on_fail=False
    ):
        if raise_on_fail:
            from database.utils.chromadb_utils import ChromaCanonicalValidationError

            raise ChromaCanonicalValidationError("fail")
        return {"ok": False}

    monkeypatch.setattr(
        "database.utils.chromadb_utils.validate_chroma_is_canonical",
        fake_validate_chroma_is_canonical,
    )
    # Use a non-canonical port (not 8000) to simulate mismatch detection
    code = run_script_main(
        monkeypatch,
        CHROMADB_HOST="localhost",
        CHROMADB_PORT="3310",
        CHROMADB_CANONICAL_HOST="localhost",
        CHROMADB_CANONICAL_PORT="3307",
    )
    assert code == 2


def test_chroma_bootstrap_create_success(monkeypatch):
    # Simulate a Chroma instance that accepts create tenant and collection
    monkeypatch.setattr(
        "database.utils.chromadb_utils.get_root_info",
        lambda h, p: {"status_code": 200, "text": "Chroma vX"},
    )
    monkeypatch.setattr(
        "database.utils.chromadb_utils.discover_chroma_endpoints",
        lambda h, p: {"/": {"ok": True}},
    )
    monkeypatch.setattr(
        "database.utils.chromadb_utils.create_tenant", lambda *args, **kwargs: True
    )
    monkeypatch.setattr(
        "database.utils.chromadb_utils.ensure_collection_exists_using_http",
        lambda *args, **kwargs: True,
    )
    code = run_script_main(monkeypatch, CHROMADB_HOST="localhost", CHROMADB_PORT="3307")
    assert code == 0
