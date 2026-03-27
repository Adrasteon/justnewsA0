import types

import pytest
from agents.fact_checker.fact_checker_engine import FactCheckerConfig, FactCheckerEngine


@pytest.mark.parametrize(
    "text,expected",
    [
        ("According to the official report, results were verified.", True),
        ("This is allegedly fake and unconfirmed.", False),
        ("some speculative claim possibly", False),
    ],
)
def test_heuristic_verification_thresholds(text, expected):
    cfg = FactCheckerConfig()
    # Avoid heavy initialization
    engine = FactCheckerEngine.__new__(FactCheckerEngine)
    engine.config = cfg
    # Minimal runtime attributes to avoid destructor warnings
    engine.cache = {}
    engine.training_data = []
    engine.logger = type("L", (), {"error": lambda *a, **k: None})()
    # Use the real method
    score = FactCheckerEngine._heuristic_verification(engine, text)
    # If expected True then score should be > 0.6 -> likely verified
    if expected:
        assert score > 0.6
    else:
        assert score <= 0.6


def test_verify_facts_no_claims(monkeypatch):
    cfg = FactCheckerConfig()
    engine = FactCheckerEngine.__new__(FactCheckerEngine)
    engine.config = cfg
    engine.cache = {}
    engine.training_data = []
    engine.logger = type("L", (), {"error": lambda *a, **k: None})()
    engine._initialize_models = lambda: None
    engine.extract_claims = lambda c: {"claims": []}
    # initialize minimal structures used by method
    engine.processing_stats = {
        "total_requests": 0,
        "gpu_requests": 0,
        "cpu_requests": 0,
        "average_processing_time": 0.0,
        "error_count": 0,
    }
    engine.cache = {}
    engine.cache_timestamps = {}

    result = FactCheckerEngine.verify_facts(engine, "no claims text")
    assert result["classification"] == "no_claims_found"


def test_verify_facts_with_claims_aggregation(monkeypatch):
    cfg = FactCheckerConfig()
    engine = FactCheckerEngine.__new__(FactCheckerEngine)
    engine.config = cfg
    engine.cache = {}
    engine.training_data = []
    engine.logger = type("L", (), {"error": lambda *a, **k: None})()
    engine._initialize_models = lambda: None
    # provide two claims
    engine.extract_claims = lambda c: {"claims": ["claim1", "claim2"]}

    # monkeypatch _verify_single_claim to return deterministic values
    def fake_verify(claim, context=None):
        return {
            "score": 0.9 if "1" in claim else 0.1,
            "classification": "verified" if "1" in claim else "refuted",
        }

    engine._verify_single_claim = fake_verify
    engine.processing_stats = {
        "total_requests": 0,
        "gpu_requests": 0,
        "cpu_requests": 0,
        "average_processing_time": 0.0,
        "error_count": 0,
    }
    engine.cache = {}
    engine.cache_timestamps = {}

    out = FactCheckerEngine.verify_facts(engine, "x")
    assert out["claims_analyzed"] == 2
    assert len(out["individual_scores"]) == 2
    # average should be (0.9 + 0.1)/2 = 0.5
    assert abs(out["verification_score"] - 0.5) < 1e-6


def test_verify_single_claim_with_mistral_adapter(monkeypatch):
    cfg = FactCheckerConfig()
    engine = FactCheckerEngine.__new__(FactCheckerEngine)
    engine.config = cfg
    engine.cache = {}
    engine.training_data = []
    engine.logger = type("L", (), {"error": lambda *a, **k: None})()
    engine._initialize_models = lambda: None
    # create fake assessment object
    assessment = types.SimpleNamespace(
        verdict="verified",
        score=0.88,
        confidence=0.9,
        rationale="ok",
        evidence_needed=False,
    )
    engine.mistral_adapter = types.SimpleNamespace()
    engine._mistral_cache = {}
    # monkeypatch method to return assessment
    engine._evaluate_with_mistral = lambda claim, context=None: assessment

    res = FactCheckerEngine._verify_single_claim(engine, "a claim")
    assert res["method"] == "mistral_adapter"
    assert res["score"] == 0.88


def test_assess_credibility_domain_and_content(monkeypatch):
    cfg = FactCheckerConfig()
    engine = FactCheckerEngine.__new__(FactCheckerEngine)
    engine.config = cfg
    engine.cache = {}
    engine.training_data = []
    engine.logger = type("L", (), {"error": lambda *a, **k: None})()
    engine._initialize_models = lambda: None
    # No roberta model -> content_score will be default 0.5
    engine.roberta_model = None

    res = FactCheckerEngine.assess_credibility(
        engine, content=None, domain=None, source_url="https://www.bbc.com/news/1"
    )

    assert "credibility_score" in res
    assert res["domain"] == "www.bbc.com"
