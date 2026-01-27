import os
import subprocess
import sys


def test_no_upb_deprecation_warnings():
    """Run the deprecation check script and assert no deprecation warnings for UPB exist.

    This ensures QA agents and CI fail if third-party compiled C extensions are emitting
    PyType_Spec deprecation warnings at import time.
    """
    py = os.environ.get("PYTHON_BIN")
    if py and os.path.exists(py):
        cmd = [py]
    else:
        cmd = [sys.executable]
    res = subprocess.run(cmd + ["scripts/checks/check_deprecation_warnings.py"])

    # Assert that the script returns 0 (no warnings).
    # If it returns non-zero, it means warnings were found, and we want to fail the test
    # (so we can see what they are) rather than skipping it.
    assert res.returncode == 0, "Deprecation warnings detected during imports"
