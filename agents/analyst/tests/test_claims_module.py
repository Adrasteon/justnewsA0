from agents.analyst.claims import extract_claims


def test_extract_claims_heuristic():
    text = "OpenAI released a new model that achieves 90% accuracy on the benchmark. According to the company, the model outperformed previous baselines."
    claims = extract_claims(text)
    assert isinstance(claims, list)
    assert len(claims) >= 1
    assert any("released a new model" in c["claim_text"] for c in claims)


def test_extract_claims_empty():
    claims = extract_claims("")
    assert isinstance(claims, list)
    assert len(claims) == 0
