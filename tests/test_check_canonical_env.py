import subprocess


def test_checker_runs_successfully():
    """Run the canonical-env checker script and expect success in the cleaned repo.

    This verifies CI's quick sanity check behaves as expected for this branch.
    """
    res = subprocess.run(
        ["bash", "scripts/dev/check_canonical_env.sh"], capture_output=True, text=True
    )
    assert res.returncode == 0, f"checker failed: {res.stdout}\n{res.stderr}"
