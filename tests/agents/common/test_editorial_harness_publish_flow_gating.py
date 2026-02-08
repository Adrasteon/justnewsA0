from agents.common.editorial_harness_runner import AgentChainRunner

# verify_publish_token is exercised via monkeypatch in tests


class _StubMetrics:
    def __init__(self):
        self.recorded = []
        self.editorial = []

    def record_publish_result(self, result: str) -> None:
        self.recorded.append(result)

    def observe_publish_latency(self, seconds: float) -> None:
        pass

    def record_editorial_result(self, result: str) -> None:
        self.editorial.append(result)

    def observe_editorial_acceptance(self, score: float) -> None:
        pass


class _StubHarness:
    def __init__(self, result):
        self.result = result

    def run_article(self, article):
        return self.result


class _StubRepository:
    def __init__(self, candidates):
        self._candidates = candidates

    def fetch_candidates(self, **_):
        return list(self._candidates)


class _StubPersistence:
    def save(self, article_row, result):
        pass


from agents.common.agent_chain_harness import (  # noqa: E402
    AgentChainResult,
    NormalizedArticle,
)


def test_publish_skipped_when_token_invalid(monkeypatch):
    article = NormalizedArticle(
        article_id="42", url="x", title="T", text="Content" * 100, metadata={}
    )
    candidate = type("C", (), {"row": {"id": 42}, "article": article})
    result = AgentChainResult(
        article_id="42",
        story_brief={},
        fact_checks=[],
        draft={"a": 1},
        acceptance_score=0.9,
        needs_followup=False,
    )

    repository = _StubRepository([candidate])
    harness = _StubHarness(result)
    persistence = _StubPersistence()
    metrics = _StubMetrics()

    # monkeypatch verify_publish_token to always return False
    monkeypatch.setattr(
        "agents.common.publisher_integration.verify_publish_token", lambda t: False
    )

    runner = AgentChainRunner(
        repository=repository,
        harness=harness,
        persistence=persistence,
        metrics=metrics,
        publish_on_accept=True,
        publish_token="badtoken",
    )

    _ = runner.run(limit=1)

    # publishing should be attempted but skipped and metrics recorded as 'skipped'
    assert "skipped" in metrics.recorded
