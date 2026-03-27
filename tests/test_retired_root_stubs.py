import glob
import os
import subprocess


def _repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _is_retired_stub(path: str) -> bool:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            head = "\n".join(f.read().splitlines()[:20]).lower()
    except OSError:
        return False
    return (
        "retired from active repo paths" in head
        or "retired root utility script" in head
    )


def test_retired_root_stubs_fail_fast_with_archive_pointer():
    """Retired root scripts must fail non-zero and point to archive_local.

    This hard-blocks regressions where retired compatibility stubs accidentally
    return success and hide incorrect workflow usage.
    """
    root = _repo_root()
    candidates = sorted(glob.glob(os.path.join(root, "*.py")))

    retired = [p for p in candidates if _is_retired_stub(p)]
    assert retired, "Expected at least one retired root stub to validate"

    failures = []
    for script in retired:
        result = subprocess.run(
            ["python3", script],
            capture_output=True,
            text=True,
        )
        combined = (result.stdout or "") + (result.stderr or "")

        if result.returncode == 0:
            failures.append(f"{os.path.basename(script)} returned 0")
            continue

        if "archive_local/" not in combined:
            failures.append(
                f"{os.path.basename(script)} missing archive_local pointer"
            )

    assert not failures, "\n".join(failures)
