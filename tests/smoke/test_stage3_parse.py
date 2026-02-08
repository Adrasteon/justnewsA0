import json
import pathlib
import shutil
import time

from scripts.dev.crawl_canary import main as crawl_main
from scripts.dev.normalize_canary import main as normalize_main
from scripts.dev.parse_canary import main as parse_main


def test_parse_roundtrip(tmp_path):
    raw_out = pathlib.Path.cwd() / "output" / "canary_raw"
    norm_out = pathlib.Path.cwd() / "output" / "canary_normalized"
    parsed_out = pathlib.Path.cwd() / "output" / "canary_parsed"

    # backup existing dirs
    for dname in [raw_out, norm_out, parsed_out]:
        if dname.exists():
            shutil.move(str(dname), str(tmp_path / dname.name))

    try:
        # fetch -> normalize -> parse
        crawl_res = crawl_main()
        assert any(ok for (_, ok, _) in crawl_res)

        norm_res = normalize_main()
        assert len(norm_res) >= 1

        parse_res = parse_main()
        assert isinstance(parse_res, list) and len(parse_res) >= 1

        time.sleep(0.1)
        parses = list(parsed_out.glob("*.json"))
        assert parses, "No parsed output files found"

        sample = json.loads(parses[0].read_text(encoding="utf-8"))
        assert "title" in sample
        assert "word_count" in sample
    finally:
        # cleanup and restore
        for dname in [raw_out, norm_out, parsed_out]:
            if dname.exists():
                shutil.rmtree(dname)
            back = tmp_path / dname.name
            if back.exists():
                shutil.move(str(back), str(dname))
