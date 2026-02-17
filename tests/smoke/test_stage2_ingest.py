import json
import pathlib
import shutil
import time

from scripts.dev.crawl_canary import main as crawl_main
from scripts.dev.normalize_canary import main as normalize_main


def test_ingest_normalization_roundtrip(tmp_path):
    raw_out = pathlib.Path.cwd() / "output" / "canary_raw"
    norm_out = pathlib.Path.cwd() / "output" / "canary_normalized"

    # Ensure clean state
    if raw_out.exists():
        shutil.move(str(raw_out), str(tmp_path / "raw_backup"))
    if norm_out.exists():
        shutil.move(str(norm_out), str(tmp_path / "norm_backup"))

    try:
        # Stage1: fetch
        r = crawl_main()
        assert any(ok for (_, ok, _) in r), "At least one canary fetch must succeed"

        # Stage2: normalize
        n = normalize_main()
        assert isinstance(n, list) and len(n) >= 1

        time.sleep(0.2)
        files = list(norm_out.glob("*.json"))
        assert files, "No normalized JSON files created"

        # Check structure
        sample = files[0]
        content = json.loads(sample.read_text(encoding="utf-8"))
        assert "normalized_url" in content
        assert content.get("normalized_at")
    finally:
        # cleanup directories
        if raw_out.exists():
            shutil.rmtree(raw_out)
        if norm_out.exists():
            shutil.rmtree(norm_out)
        # restore backups
        if (tmp_path / "raw_backup").exists():
            shutil.move(str(tmp_path / "raw_backup"), str(raw_out))
        if (tmp_path / "norm_backup").exists():
            shutil.move(str(tmp_path / "norm_backup"), str(norm_out))
