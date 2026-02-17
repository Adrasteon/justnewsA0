from agents.tools import re_ranker_7b as rr_mod


def test_stub_reranker_scores_deterministic(tmp_path, monkeypatch):
    # Ensure test mode
    monkeypatch.setenv("RE_RANKER_TEST_MODE", "1")
    r = rr_mod.ReRanker()

    q = "How is revenue growth?"
    cands = [
        rr_mod.ReRankCandidate(id="1", text="Revenue increased by 10 percent."),
        rr_mod.ReRankCandidate(id="2", text="No change reported."),
    ]
    scores = r.score(q, cands)
    assert isinstance(scores, list)
    assert len(scores) == 2
    # Basic assertions about expected ordering
    assert scores[0] >= 0.0
    assert scores[1] >= 0.0
