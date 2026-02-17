import os
import subprocess
from pathlib import Path


def test_check_processing_time_detects_issue(tmp_path, monkeypatch):
    # Create a file with a suspicious pattern inside tests so script will scan it
    repo_root = Path(os.getcwd())
    test_file = repo_root / "tests" / "_tmp_bad_processing_time.py"
    test_file.write_text("""# Bad pattern
processing_time = time.time() - time.time()
""")

    try:
        result = subprocess.run(
            ["python3", "scripts/check_processing_time.py"],
            capture_output=True,
            text=True,
        )
        # The script should find the issue and exit with non-zero code
        assert result.returncode != 0
        assert "Found suspicious processing_time patterns" in result.stdout
        assert str(test_file.relative_to(repo_root)) in result.stdout
    finally:
        # Cleanup
        if test_file.exists():
            test_file.unlink()


def test_check_processing_time_passes_when_ok(tmp_path):
    # Create a benign python file
    repo_root = Path(os.getcwd())
    test_file = repo_root / "tests" / "_tmp_good.py"
    test_file.write_text("""# Good pattern
start_time = time.time()\nprocessing_time = time.time() - start_time\n""")

    try:
        result = subprocess.run(
            ["python3", "scripts/check_processing_time.py"],
            capture_output=True,
            text=True,
        )
        # No suspicious patterns
        assert result.returncode == 0
        assert "No suspicious processing_time patterns found." in result.stdout
    finally:
        if test_file.exists():
            test_file.unlink()
