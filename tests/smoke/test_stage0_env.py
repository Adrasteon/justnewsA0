import pathlib


def test_required_files_exist():
    repo_root = pathlib.Path(__file__).resolve().parents[2]

    required = [
        repo_root / "environment.yml",
        repo_root / "scripts" / "dev" / "docker-compose.e2e.yml",
        repo_root / "scripts" / "dev" / "db-mariadb" / "Dockerfile",
        repo_root / "scripts" / "dev" / "canary_urls.txt",
        repo_root / "docs" / "dev-setup.md",
    ]

    for f in required:
        assert f.exists(), f"Missing required dev file: {f}"


def test_canary_urls_have_entries():
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    canary = repo_root / "scripts" / "dev" / "canary_urls.txt"
    lines = [line.strip() for line in canary.read_text().splitlines() if line.strip()]
    assert len(lines) >= 1, "canary_urls.txt must have at least 1 URL"
