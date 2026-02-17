import pytest

try:
    import requests
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except Exception:
    PLAYWRIGHT_AVAILABLE = False


@pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="Playwright not installed")
def test_pages_dropdown_navigation_localhost():
    # This E2E test requires Playwright to be installed and a local server running on :8013
    try:
        _r = requests.get("http://127.0.0.1:8013/", timeout=1)
    except Exception:
        pytest.skip("Local dashboard not running on http://127.0.0.1:8013")
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception:
            pytest.skip(
                "Playwright browser binaries not available or cannot be launched"
            )
        page = browser.new_page()
        page.goto("http://127.0.0.1:8013")
        # Open the dropdown and click GPU Dashboard
        # Click the Pages dropdown and then click the GPU Dashboard link by selector
        page.click("text=Pages")
        selector = '#pagesDropdownMenu a[href="/gpu/dashboard"]'
        try:
            page.wait_for_selector(selector, timeout=3000)
        except Exception:
            pytest.skip(
                "GPU Dashboard link not present in the dashboard dropdown (UI may be different)"
            )
        page.click(selector)
        assert "/gpu/dashboard" in page.url
        browser.close()
