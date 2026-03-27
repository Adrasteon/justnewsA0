import os
import subprocess
import sys


def test_protobuf_version_meets_requirement():
    """Ensure protobuf version meets the minimum requirement via the script.

    The script exits non-zero if protobuf version is older than MIN_PROTOBUF.
    """
    py = os.environ.get("PYTHON_BIN")
    if not py or not os.path.exists(py):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        venv_py = os.path.join(repo_root, ".venv", "bin", "python")
        cmd = [venv_py] if os.path.exists(venv_py) else [sys.executable]
    else:
        cmd = [py]
    res = subprocess.run(cmd + ["scripts/checks/check_protobuf_version.py"])
    assert res.returncode == 0, "Protobuf version is older than required (>=4.24.0)"
