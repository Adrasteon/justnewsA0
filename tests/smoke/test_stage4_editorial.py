import json
import pathlib
import shutil
import time

from scripts.dev.crawl_canary import main as crawl_main
from scripts.dev.editorial_canary import main as editorial_main
from scripts.dev.normalize_canary import main as normalize_main
from scripts.dev.parse_canary import main as parse_main


def test_editorial_pipeline(tmp_path):
    # Prepare / cleanup
    parsed_out = pathlib.Path.cwd() / "output" / "canary_parsed"
    drafts_out = pathlib.Path.cwd() / "output" / "canary_drafts"
    # backup existing dirs
    for d in [parsed_out, drafts_out]:
        if d.exists():
            shutil.move(str(d), str(tmp_path / d.name))

    try:
        # run convergence: crawl -> normalize -> parse -> editorial
        crawl_res = crawl_main()
        assert any(ok for (_, ok, _) in crawl_res)

        normalize_res = normalize_main()
        assert len(normalize_res) >= 1

        parse_res = parse_main()
        assert len(parse_res) >= 1

        draft_res = editorial_main()
        assert len(draft_res) >= 1

        time.sleep(0.1)
        drafts = list(drafts_out.glob("*.json"))
        assert drafts, "No draft files created"

        sample = json.loads(drafts[0].read_text(encoding="utf-8"))
        assert "title" in sample and "fact_check" in sample
    finally:
        for d in [parsed_out, drafts_out]:
            if d.exists():
                shutil.rmtree(d)
            back = tmp_path / d.name
            if back.exists():
                shutil.move(str(back), str(d))
