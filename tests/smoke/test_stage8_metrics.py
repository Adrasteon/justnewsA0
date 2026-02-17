import pathlib
import shutil

from scripts.dev.canary_metrics import read_metrics, reset
from scripts.dev.crawl_canary import main as crawl_main
from scripts.dev.editorial_canary import main as editorial_main
from scripts.dev.normalize_canary import main as normalize_main
from scripts.dev.parse_canary import main as parse_main
from scripts.dev.publish_canary import main as publish_main


def test_metrics_emitted(tmp_path):
    # Reset metrics and run full pipeline
    reset()

    raw_backup = pathlib.Path.cwd() / "output" / "canary_raw"
    parsed_backup = pathlib.Path.cwd() / "output" / "canary_parsed"
    drafts_backup = pathlib.Path.cwd() / "output" / "canary_drafts"
    published_backup = pathlib.Path.cwd() / "output" / "canary_published"

    for d in [raw_backup, parsed_backup, drafts_backup, published_backup]:
        if d.exists():
            shutil.move(str(d), str(tmp_path / d.name))

    try:
        assert any(ok for (_, ok, _) in crawl_main())
        normalize_main()
        parse_main()
        editorial_main()
        publish_main()

        metrics = read_metrics()
        # Ensure each stage emitted at least once
        assert metrics.get("fetch_success", 0) >= 1
        assert metrics.get("normalize_success", 0) >= 1
        assert metrics.get("parse_success", 0) >= 1
        assert metrics.get("draft_created", 0) >= 1
        assert metrics.get("publish_success", 0) >= 1
    finally:
        # cleanup
        for d in [raw_backup, parsed_backup, drafts_backup, published_backup]:
            if d.exists():
                shutil.rmtree(d)
            back = tmp_path / d.name
            if back.exists():
                shutil.move(str(back), str(d))
