import os
import subprocess


def test_backup_script_dryrun_creates_expected_filenames(tmp_path, monkeypatch):
    # Run the backup script in dry-run mode with a fixed date and capture output
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    script = os.path.join(repo_root, "scripts", "backup_conda_env.sh")

    env = os.environ.copy()
    env["DRY_RUN"] = "1"

    # Use a fixed date for predictable output
    date_str = "20251123"

    env_name = os.environ.get("CANONICAL_ENV", "justnews-py312")

    result = subprocess.run(
        ["bash", script, env_name, str(tmp_path), date_str],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    out = result.stdout

    # Expect the dry-run messages to reference the date-stamped artifact names
    assert f"{tmp_path}/{env_name}-{date_str}.yml" in out
    assert f"{tmp_path}/{env_name}-{date_str}.explicit.txt" in out
    assert f"{tmp_path}/{env_name}-{date_str}.pip.txt" in out
    assert (
        f"{tmp_path}/{env_name}-{date_str}.tar.gz" in out
        or "conda-pack not installed" in out
    )
