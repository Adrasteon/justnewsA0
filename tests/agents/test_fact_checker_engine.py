"""Compatibility tests for containerized fact-checker runtime.

These tests intentionally validate shim-layer behavior instead of legacy
in-process engine classes.
"""

from agents.fact_checker import shim


def test_shim_normalize_verdict_threshold_mapping():
    assert shim._normalize_verdict("True") == "True"
    assert shim._normalize_verdict("likely true") == "Likely True"
    assert shim._normalize_verdict("uncertain") == "Uncertain"
    assert shim._normalize_verdict("likely false") == "Likely False"
    assert shim._normalize_verdict("false") == "False"


def test_shim_normalize_legacy_aliases():
    assert shim._normalize_verdict("proven") == "True"
    assert shim._normalize_verdict("plausible") == "Likely True"
    assert shim._normalize_verdict("unverified") == "Uncertain"
    assert shim._normalize_verdict("improbable") == "Likely False"
    assert shim._normalize_verdict("disproven") == "False"


def test_status_and_score_from_verdict_contract():
    assert shim._status_from_verdict("True") == "passed"
    assert shim._status_from_verdict("Likely True") == "passed"
    assert shim._status_from_verdict("Uncertain") == "needs_review"
    assert shim._status_from_verdict("Likely False") == "failed"
    assert shim._status_from_verdict("False") == "failed"

    assert shim._score_from_verdict("True") == 1.0
    assert shim._score_from_verdict("Likely True") == 0.75
    assert shim._score_from_verdict("Uncertain") == 0.5
    assert shim._score_from_verdict("Likely False") == 0.25
    assert shim._score_from_verdict("False") == 0.0
