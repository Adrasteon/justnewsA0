import pathlib
import shutil
import time

from scripts.dev.crawl_canary import main as crawl_main


def test_crawl_creates_output(tmp_path):
    # Prepare environment: ensure output dir is isolated for the test
    out_dir = pathlib.Path.cwd() / "output" / "canary_raw"
    if out_dir.exists():
        # move aside
        tmp = tmp_path / "backup"
        shutil.move(str(out_dir), str(tmp))

    try:
        res = crawl_main()
        assert isinstance(res, list) and len(res) >= 1
        # Give filesystem a moment and check that at least one file was created
        time.sleep(0.5)
        files = list(out_dir.glob("*.json"))
        assert files, "No raw output JSON files created by canary fetch"
    finally:
        # cleanup - remove generated directory
        if out_dir.exists():
            shutil.rmtree(out_dir)
        # restore previous state
        backup = tmp_path / "backup"
        if backup.exists():
            shutil.move(str(backup), str(out_dir))
