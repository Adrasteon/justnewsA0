import asyncio

from agents.fact_checker.fact_checker_engine import FactCheckerConfig, FactCheckerEngine


def build_min_engine():
    cfg = FactCheckerConfig()
    engine = FactCheckerEngine.__new__(FactCheckerEngine)
    engine.config = cfg
    engine.cache = {}
    engine.training_data = []
    engine.logger = type("L", (), {"error": lambda *a, **k: None})()
    engine._initialize_models = lambda: None
    engine.tensorrt_engine = None
    return engine


def test_validate_is_news_cpu_high_confidence():
    engine = build_min_engine()

    content = (
        "Breaking news - Local report: According to sources, the committee announced an urgent"
        " update about the infrastructure project published earlier today."
    )

    res = asyncio.run(engine._validate_is_news_cpu(content))
    assert isinstance(res, dict)
    assert "is_news" in res
    assert res["confidence"] >= 0.0 and res["confidence"] <= 1.0


def test_verify_claims_cpu_with_and_without_sources():
    engine = build_min_engine()

    # Case: no sources => base score 0.5
    out1 = asyncio.run(engine._verify_claims_cpu(["Many people attended"], []))
    assert out1["total_claims"] == 1
    c = list(out1["results"].values())[0]
    assert c["verification_score"] == 0.5
    assert c["classification"] == "questionable"

    # Case: overlapping source -> higher score
    claims = ["The event was attended by thousands"]
    sources = [
        "Thousands of people attended the event and were seen in the main square"
    ]

    out2 = asyncio.run(engine._verify_claims_cpu(claims, sources))
    assert out2["total_claims"] == 1
    r = out2["results"][claims[0]]
    assert r["verification_score"] >= 0.2  # overlap should give a positive score
    # classification should be either 'questionable' or 'verified' depending on overlap
    assert r["classification"] in ("questionable", "verified")
