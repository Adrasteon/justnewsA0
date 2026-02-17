from agents.analyst import audit


def test_normalize_verdict_canonical_values():
    assert audit.normalize_verdict("True") == "True"
    assert audit.normalize_verdict("likely true") == "Likely True"
    assert audit.normalize_verdict("Likely False") == "Likely False"
    assert audit.normalize_verdict("false") == "False"


def test_normalize_verdict_legacy_values_become_uncertain():
    assert audit.normalize_verdict("proven") == "Uncertain"
    assert audit.normalize_verdict("plausible") == "Uncertain"
    assert audit.normalize_verdict("unverified") == "Uncertain"


def test_normalize_verdict_unknown_becomes_uncertain():
    assert audit.normalize_verdict("n/a") == "Uncertain"
