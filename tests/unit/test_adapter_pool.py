import sys
from pathlib import Path


def test_adapter_pool_spawn(tmp_path, monkeypatch):
    # run workers in test mode for a very short hold time to ensure script path is sound
    monkeypatch.setenv("RE_RANKER_TEST_MODE", "1")

    # Add scripts/ops to sys.path to ensure the module is importable by child processes (spawn mode requirement)
    # The previous method (spec_from_file_location with fake name) fails pickling
    repo_root = Path(__file__).resolve().parent.parent.parent
    ops_dir = repo_root / "scripts" / "ops"

    # Ensure strict string conversion for sys.path
    ops_path_str = str(ops_dir)

    sys.path.insert(0, ops_path_str)
    try:
        # Import as a proper module so pickle can find it by name
        import adapter_worker_pool

        # spawn a single worker for 1 second and return quickly
        adapter_worker_pool.spawn_pool(num_workers=1, model_id=None, adapter=None, hold_time=1)
    finally:
        if ops_path_str in sys.path:
            sys.path.remove(ops_path_str)
        # Also clean up from sys.modules to prevent pollution
        if "adapter_worker_pool" in sys.modules:
            del sys.modules["adapter_worker_pool"]

    # If we get here without exceptions, test is successful
    assert True
