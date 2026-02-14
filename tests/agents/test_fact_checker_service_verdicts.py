from mcp_fact_checker_server.app import service


def test_backend_normalize_verdict_canonical():
    assert service.normalize_verdict("True") == "True"
    assert service.normalize_verdict("likely true") == "Likely True"
    assert service.normalize_verdict("uncertain") == "Uncertain"


def test_backend_normalize_verdict_legacy_and_unknown():
    assert service.normalize_verdict("proven") == "True"
    assert service.normalize_verdict("plausible") == "Likely True"
    assert service.normalize_verdict("unverified") == "Uncertain"
    assert service.normalize_verdict("disproven") == "False"
    assert service.normalize_verdict("something_else") == "Uncertain"
