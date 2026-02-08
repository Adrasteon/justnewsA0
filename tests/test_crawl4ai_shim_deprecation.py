import importlib
import warnings


def test_crawl4ai_shim_does_not_warn_on_import():
    """Import the legacy scout shim and assert it does not emit DeprecationWarning in tests.

    The compatibility shim is intentionally present for backwards compatibility but
    must not trigger `DeprecationWarning` during test runs, as tests treat warnings
    as errors under the CI policy.
    """
    # Import the shim fresh and capture any warnings raised during import.
    module_name = "agents.scout.crawl4ai_server"
    with warnings.catch_warnings(record=True) as warns:
        warnings.simplefilter("always")
        try:
            importlib.reload(importlib.import_module(module_name))
        except Exception:
            # Missing optional heavy dependencies like FastAPI or crawl4ai are
            # acceptable in a test environment; we only assert absence of
            # DeprecationWarning, not presence of successful import.
            pass

    # Ensure no DeprecationWarning has been generated; we accept other warnings as infra
    assert not any(
        isinstance(w.message, DeprecationWarning) or w.category is DeprecationWarning
        for w in warns
    ), "Importing the crawl4ai shim emitted a DeprecationWarning"
