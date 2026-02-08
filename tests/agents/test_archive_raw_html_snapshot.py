from __future__ import annotations

from pathlib import Path

from agents.archive.raw_html_snapshot import ensure_raw_html_artifact


def test_missing_reference_returns_status_none(tmp_path):
    result = ensure_raw_html_artifact(None, service_dir=tmp_path)
    assert result["status"] == "missing_ref"
    assert result["raw_html_ref"] is None


def test_missing_source_reports_warning(tmp_path):
    result = ensure_raw_html_artifact(
        "archive_storage/raw_html/ghost.html", service_dir=tmp_path
    )
    assert result["status"] == "missing_source"
    assert result["raw_html_ref"] is None


def test_verified_when_already_in_canonical_root(tmp_path):
    canonical = tmp_path / "archive_storage" / "raw_html"
    canonical.mkdir(parents=True)
    artefact = canonical / "sample.html"
    artefact.write_text("<html></html>", encoding="utf-8")

    result = ensure_raw_html_artifact(
        "archive_storage/raw_html/sample.html",
        service_dir=tmp_path,
    )

    assert result["status"] == "verified"
    assert result["raw_html_ref"] == "archive_storage/raw_html/sample.html"


def test_copy_into_canonical_root_when_outside(tmp_path):
    source_dir = tmp_path / "staging"
    source_dir.mkdir()
    source = source_dir / "temp.html"
    source.write_text("<html>snapshot</html>", encoding="utf-8")

    result = ensure_raw_html_artifact(str(source), service_dir=tmp_path)

    assert result["status"] == "copied"
    assert result["raw_html_ref"].startswith("archive_storage/raw_html/")
    copied_path = Path(tmp_path / result["raw_html_ref"])
    assert copied_path.exists()
    assert copied_path.read_text(encoding="utf-8") == "<html>snapshot</html>"
