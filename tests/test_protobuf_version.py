import os
import shutil
import subprocess
import sys


def test_protobuf_version_meets_requirement():
    """Ensure protobuf version meets the minimum requirement via the script.

    The script exits non-zero if protobuf version is older than MIN_PROTOBUF.
    """
    py = os.environ.get("PYTHON_BIN")
    if not py or not os.path.exists(py):
        # Be defensive: some environments or docs include shell-style templated
        # values (eg. '${CANONICAL_ENV:-justnews-py312}') which are not valid
        # conda environment names. If the CANONICAL_ENV value looks like a
        # template or contains invalid characters, fall back to the current
        # Python executable to avoid invoking conda with a malformed name.
        env_name = os.environ.get("CANONICAL_ENV", "justnews-py312")
        if shutil.which("conda") is not None and not any(
            c in env_name for c in ("$", "{", "}", ":", "/", " ")
        ):
            cmd = ["conda", "run", "-n", env_name, "python"]
        else:
            cmd = [sys.executable]
    else:
        cmd = [py]
    res = subprocess.run(cmd + ["scripts/checks/check_protobuf_version.py"])
    assert res.returncode == 0, "Protobuf version is older than required (>=4.24.0)"
