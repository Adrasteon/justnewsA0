"""
Top-level pytest conftest to ensure a deterministic test environment across all
test discovery paths (not only `tests/` dir). This sets a minimal test
`global.env` and marks `PYTEST_RUNNING` so test runs don't accidentally
read `/etc/justnews/global.env` on development hosts.
"""

import json
import os

# Filter known protobuf upb deprecation (PyType_Spec + custom tp_new) in test runs until
# the system environment is upgraded to a protobuf wheel built with the newer API.
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from shutil import which

# Prefer project-level PYTHON_BIN or a conda env for running preflight scripts; fall
# back to the system python if not available.
project_root = Path(__file__).resolve().parent
project_global_env = project_root / "global.env"


def _conda_env_available(env_name: str) -> bool:
    """Return True if the requested conda env exists on this host."""
    try:
        result = subprocess.run(
            ["conda", "env", "list", "--json"],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(result.stdout or "{}")
    except Exception:
        return False
    env_paths = data.get("envs", [])
    for env_path in env_paths:
        try:
            if Path(env_path).name == env_name:
                return True
        except Exception:
            continue
    return False


py_cmd = None
if os.environ.get("PYTHON_BIN"):
    py_cmd = [os.environ.get("PYTHON_BIN")]
elif project_global_env.exists():
    # parse global.env for a PYTHON_BIN or JUSTNEWS_PYTHON entry
    try:
        for line in project_global_env.read_text().splitlines():
            if not line or line.strip().startswith("#"):
                continue
            if line.strip().startswith("PYTHON_BIN="):
                raw_val = line.split("=", 1)[1].strip().strip('"').strip("'")
                # Handle shell-style defaults like ${PYTHON_BIN:-/path}
                if raw_val.startswith("${") and ":-" in raw_val:
                    raw_val = raw_val.split(":-", 1)[1].rstrip("}")
                val = raw_val
                if val:
                    py_cmd = [val]
                    break
            if line.strip().startswith("JUSTNEWS_PYTHON="):
                raw_val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if raw_val.startswith("${") and ":-" in raw_val:
                    raw_val = raw_val.split(":-", 1)[1].rstrip("}")
                val = raw_val
                if val:
                    py_cmd = [val]
                    break
    except Exception:
        py_cmd = None
if py_cmd is None:
    # fallback to using conda run, if the recommended env exists
    # Support both unified env (justnews-py312) and phased envs (justnews-py312-phaseN)
    canonical_env = os.environ.get("CANONICAL_ENV", "justnews-py312-phase1")
    if which("conda") is not None and _conda_env_available(canonical_env):
        py_cmd = ["conda", "run", "-n", canonical_env, "python"]
    elif which("conda") is not None and _conda_env_available("justnews-py312"):
        # Fallback to unified env if phase env not found
        py_cmd = ["conda", "run", "-n", "justnews-py312", "python"]
    else:
        py_cmd = [os.environ.get("PYTHON_BIN", sys.executable or "python")]

# Enforce environment health: ensure protobuf meets minimum version and no
# upb-related DeprecationWarnings are raised by third-party C extensions.
# Allow tests to skip preflight checks by setting SKIP_PREFLIGHT=1 in the
# environment. This is useful for reproducibly running the full test suite
# while we iterate on fixing environmental deprecation warnings.
if os.environ.get("SKIP_PREFLIGHT", "0") != "1":
    try:
        result = subprocess.run(
            py_cmd + ["scripts/checks/check_protobuf_version.py"], check=False
        )
        if result.returncode != 0:
            raise RuntimeError(
                "protobuf version check failed; please upgrade your environment to protobuf >= 4.24.0 and ensure regenerated wheels for any dependent compiled packages."
            )
        result = subprocess.run(
            py_cmd + ["scripts/checks/check_deprecation_warnings.py"], check=False
        )
        if result.returncode != 0:
            # Treat deprecation warnings as warnings for test runs to avoid
            # failing the CI/test run; tests should still signal via logs
            # for maintainers to upgrade compiled wheels when needed.

            # Include stacklevel so the warning points to the caller in test runs
            # Emit a non-fatal log message for third-party compiled extension
            # deprecation notices so tests don't fail due to external packages
            # while still alerting maintainers to upgrade compiled wheels.
            import logging as _logging
            _logging.getLogger('justnews.preflight').warning(
                "Deprecation warnings detected from third-party compiled extensions (e.g. google._upb._message); please upgrade your environment and reinstall compiled wheels for affected packages."
            )
    except FileNotFoundError:
        # In minimal developer/test environments the scripts may not be available.
        # Print a message and continue; CI should run with the script present to enforce this check.
        print(
            "Warning: preflight check scripts missing. Ensure `scripts/checks/check_protobuf_version.py` and `scripts/checks/check_deprecation_warnings.py` are present in your environment."
        )
    else:
        print("SKIP_PREFLIGHT=1 set; skipping protobuf & deprecation preflight checks")

if "JUSTNEWS_GLOBAL_ENV" not in os.environ:
    tmp_dir = Path(tempfile.gettempdir()) / f"justnews_test_global_env_{os.getpid()}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    env_file = tmp_dir / "global.env"
    if not env_file.exists():
        env_file.write_text(
            textwrap.dedent(f"""
        SERVICE_DIR={Path(__file__).resolve().parent}
        PYTHON_BIN={os.environ.get("PYTHON_BIN", "")}
        # Only minimal environment variables are set for tests to avoid
        # unintentionally overriding saved configuration values on reload.
        # Any database-specific environment vars should be explicitly set
        # by tests that require them or by CI when running integration tests.
        """)
        )
    os.environ["JUSTNEWS_GLOBAL_ENV"] = str(env_file)

# Ensure PYTHONPATH is set so top-level `import agents` resolves; prefer the
# repository root or SERVICE_DIR from global.env if present.
os.environ.setdefault("PYTHONPATH", str(project_root))

# Indicate pytest-run for components that check this flag in `env_loader`.
os.environ["PYTEST_RUNNING"] = "1"

# In test runs, disable fatal canonical Chroma validation by default unless a test
# explicitly sets CHROMADB_REQUIRE_CANONICAL via monkeypatch. This prevents
# unrelated unit tests from failing due to environment-level canonical settings.
os.environ.setdefault("CHROMADB_REQUIRE_CANONICAL", "0")
# Ensure model-scoped ChromaDB collections are enabled by default in tests
# unless a test explicitly disables them using monkeypatch.setenv(...).
os.environ.setdefault("CHROMADB_MODEL_SCOPED_COLLECTION", "1")
# Disable the embedding module's suppression of upstream warnings during tests so
# our stricter 'no warnings' CI policy can detect and fail on them.
os.environ.setdefault("EMBEDDING_SUPPRESS_WARNINGS", "0")

# Prevent tests from opening real MySQL connections during unit tests.
# Tests that intentionally need a live connector can patch it explicitly.
try:
    import mysql.connector as _mysql_connector  # type: ignore

    # Replace the `connect` function with a helper that raises by default
    # to ensure code paths fall back to in-memory behavior unless tests
    # explicitly patch `mysql.connector.connect` to provide a fake client.
    def _test_disabled_connect(*args, **kwargs):
        raise _mysql_connector.Error(
            "Database access disabled in unit tests; patch `mysql.connector.connect` to simulate a connection."
        )

    _mysql_connector.connect = _test_disabled_connect
except Exception:  # pragma: no cover - best-effort during test startup
    pass

# Mock ChromaDB for unit tests to avoid importing the real package and
# pulling in optional telemetry dependencies (opentelemetry/google.rpc).
# Tests that require a real Chroma client (integration tests) should
# explicitly import and patch it in their own scopes.
try:
    import importlib.util
    import sys
    import types
    from unittest.mock import MagicMock as _MagicMock

    _spec = importlib.util.find_spec("chromadb")
    if _spec is not None:
        # Create a lightweight stub module so subsequent `import chromadb`
        # will return the stub (avoids importing real package during test
        # collection and prevents opentelemetry/google.rpc from being loaded).
        chroma_stub = types.ModuleType("chromadb")
        # Provide a mocked HttpClient so code under test that constructs
        # `chromadb.HttpClient` doesn't attempt network calls.
        chroma_stub.HttpClient = _MagicMock(name="chromadb.HttpClient")
        # Provide a minimal api.client.Client stub used in some code paths
        api_mod = types.ModuleType("chromadb.api")
        client_mod = types.ModuleType("chromadb.api.client")
        client_mod.Client = _MagicMock(name="chromadb.api.client.Client")
        api_mod.client = client_mod
        chroma_stub.api = api_mod
        # Install stub in sys.modules to short-circuit real import
        sys.modules["chromadb"] = chroma_stub
except Exception:
    # Best-effort: don't fail test collection if any of these operations error
    # (for example, tests running in minimal environments).
    pass
