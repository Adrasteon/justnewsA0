import os
import subprocess


def test_bootstrap_conda_wrapper_deprecation_message():
    """Legacy script name still exists as wrapper and emits deprecation guidance."""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    script = os.path.join(repo_root, "scripts", "bootstrap_conda_env.sh")

    result = subprocess.run(
        ["bash", script, "--help"],
        capture_output=True,
        text=True,
    )

    combined = (result.stdout or "") + (result.stderr or "")
    assert "DEPRECATED" in combined or "deprecated" in combined.lower()
