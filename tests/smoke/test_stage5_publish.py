import json
import pathlib
import shutil
import time

from scripts.dev.crawl_canary import main as crawl_main
from scripts.dev.editorial_canary import main as editorial_main
from scripts.dev.normalize_canary import main as normalize_main
from scripts.dev.parse_canary import main as parse_main
from scripts.dev.publish_canary import main as publish_main


def test_publish_roundtrip(tmp_path):
    # directories used in pipeline
    drafts = pathlib.Path.cwd() / "output" / "canary_drafts"
    published = pathlib.Path.cwd() / "output" / "canary_published"

    for d in [drafts, published]:
        if d.exists():
            shutil.move(str(d), str(tmp_path / d.name))

    try:
        assert any(ok for (_, ok, _) in crawl_main())
        assert normalize_main()
        assert parse_main()
        assert editorial_main()

        pub = publish_main()
        assert isinstance(pub, list) and len(pub) >= 1

        time.sleep(0.1)
        files = list(published.glob("*.json"))
        assert files, "No published artifacts created"

        sample = json.loads(files[0].read_text(encoding="utf-8"))
        assert sample.get("published_url")
    finally:
        for d in [drafts, published]:
            if d.exists():
                shutil.rmtree(d)
            back = tmp_path / d.name
            if back.exists():
                shutil.move(str(back), str(d))
