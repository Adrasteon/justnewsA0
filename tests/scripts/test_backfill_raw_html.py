import importlib
from pathlib import Path


def test_backfill_dry_run(monkeypatch, tmp_path):
    repo_root = Path(tmp_path)
    # simulate SERVICE_DIR environment
    monkeypatch.setenv("SERVICE_DIR", str(repo_root))
    raw_dir = repo_root / "archive_storage" / "raw_html"
    raw_dir.mkdir(parents=True)
    file = raw_dir / "test.html"
    file.write_text("<html><body>Test</body></html>", encoding="utf-8")

    backfill = importlib.import_module("scripts.ops.backfill_raw_html")
    # Ensure dry run runs without raising
    backfill.backfill_file(file, dry_run=True)


def test_backfill_post(monkeypatch, tmp_path):
    repo_root = Path(tmp_path)
    monkeypatch.setenv("SERVICE_DIR", str(repo_root))
    raw_dir = repo_root / "archive_storage" / "raw_html"
    raw_dir.mkdir(parents=True)
    file = raw_dir / "test.html"
    file.write_text("<html><body>Test2</body></html>", encoding="utf-8")

    calls = []

    def fake_post(url, json=None, timeout=30):
        calls.append({"url": url, "json": json})

        class Resp:
            def raise_for_status(self):
                pass

        return Resp()

    monkeypatch.setattr("requests.post", fake_post)
    backfill = importlib.import_module("scripts.ops.backfill_raw_html")
    # When not dry-run, should call requests.post
    backfill.backfill_file(file, dry_run=False)
    assert len(calls) == 1
    assert calls[0]["url"].endswith("/call")
