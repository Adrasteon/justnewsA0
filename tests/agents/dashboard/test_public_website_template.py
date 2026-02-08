from pathlib import Path


def test_public_website_template_exists_and_contains_pages():
    # parents[3] resolves to the repository root for our test layout
    path = Path(__file__).parents[3] / "agents" / "dashboard" / "public_website.html"
    assert path.exists(), f"public_website.html not found at {path}"
    content = path.read_text(encoding="utf-8")
    assert "dropdown" in content
    assert "/api/crawl/status" in content
    assert "/gpu/dashboard" in content
    # Check for DataTables and Chart.js presence for enhanced UI
    assert "dataTables.bootstrap5.min.css" in content
    assert "chart.js" in content or "Chart" in content
    # Ensure the dynamic dropdown placeholder and the JSON modal are present
    assert 'id="pagesDropdownMenu"' in content
    assert 'id="jsonModal"' in content
    assert 'id="crawlerJobsTable"' in content
    assert 'id="gpuChart"' in content
    # Ensure publishing UI controls exist
    assert 'id="requireDraftFactCheckSwitch"' in content
    assert 'id="chiefEditorReviewSwitch"' in content
    assert 'id="synthesizedArticleStorageSelect"' in content
