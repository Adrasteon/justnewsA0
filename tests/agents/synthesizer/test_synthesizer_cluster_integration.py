from unittest.mock import patch

import pytest
import pytest_asyncio

from agents.synthesizer.synthesizer_engine import SynthesisResult, SynthesizerEngine


def _make_fake(pre, post):
    def _fake(texts, article_ids=None, cluster_id=None):
        if isinstance(texts, list) and len(texts) > 1:
            return pre(texts, article_ids=article_ids, cluster_id=cluster_id)
        return post(texts, article_ids=article_ids, cluster_id=cluster_id)

    return _fake


class FakeArticle:
    def __init__(self, article_id: str, content: str):
        self.article_id = article_id
        self.content = content

    def to_dict(self):
        return {"article_id": self.article_id, "content": self.content}


@pytest_asyncio.fixture
async def synthesizer_engine(monkeypatch):
    from agents.synthesizer.synthesizer_engine import SynthesizerEngine

    class StubGPUManager:
        def __init__(self):
            self.is_available = True
            self.device = "cuda:0"

        def get_device(self):
            return self.device

        def get_available_memory(self):
            return 8 * 1024 * 1024 * 1024

    mock_gpu_manager = StubGPUManager()

    with (
        patch(
            "agents.synthesizer.synthesizer_engine.GPUManager",
            return_value=mock_gpu_manager,
        ),
        patch("agents.synthesizer.synthesizer_engine.AutoTokenizer"),
        patch("agents.synthesizer.synthesizer_engine.AutoModelForSeq2SeqLM"),
        patch("agents.synthesizer.synthesizer_engine.BERTopic"),
        patch("agents.synthesizer.synthesizer_engine.pipeline"),
        patch("agents.synthesizer.synthesizer_engine.TfidfVectorizer"),
        patch("agents.synthesizer.synthesizer_engine.KMeans"),
    ):
        engine = SynthesizerEngine()
        await engine.initialize()
        yield engine
        await engine.close()


@pytest.mark.asyncio
async def test_synthesize_cluster_fact_check_aborts_when_unverified(
    synthesizer_engine, monkeypatch
):
    engine: SynthesizerEngine = synthesizer_engine

    # Patch cluster fetcher to return sample articles
    fake_articles = [FakeArticle("a1", "Test content")]

    class FakeFetcher:
        def fetch_cluster(
            self, cluster_id=None, article_ids=None, max_results=50, dedupe=True
        ):
            return fake_articles

    monkeypatch.setattr(
        "agents.cluster_fetcher.cluster_fetcher.ClusterFetcher", lambda: FakeFetcher()
    )
    # verify cluster fetcher monkeypatch
    import importlib

    m = importlib.import_module("agents.cluster_fetcher.cluster_fetcher")
    assert isinstance(m.ClusterFetcher(), FakeFetcher)

    # Patch analyst to return low verified percent
    called = {"ok": False}

    def fake_generate(texts, article_ids=None, cluster_id=None):
        called["ok"] = True
        return {"cluster_fact_check_summary": {"percent_verified": 50.0}}

    import importlib

    importlib.import_module("agents.analyst.tools")
    monkeypatch.setattr("agents.analyst.tools.generate_analysis_report", fake_generate)

    # Call synthesis with cluster_id and empty articles to trigger fetch
    res = await engine.synthesize_gpu(
        [], max_clusters=2, context="news", options={"cluster_id": "cluster-abc"}
    )

    assert called["ok"] is True
    assert res.get("status") == "error"
    assert res.get("error") == "fact_check_failed"
    assert "analysis_report" in res


@pytest.mark.asyncio
async def test_synthesize_cluster_proceeds_when_verified(
    synthesizer_engine, monkeypatch
):
    engine: SynthesizerEngine = synthesizer_engine

    fake_articles = [
        FakeArticle("a1", "Test content"),
        FakeArticle("a2", "Other content"),
    ]

    class FakeFetcher:
        def fetch_cluster(
            self, cluster_id=None, article_ids=None, max_results=50, dedupe=True
        ):
            return fake_articles

    monkeypatch.setattr(
        "agents.cluster_fetcher.cluster_fetcher.ClusterFetcher", lambda: FakeFetcher()
    )

    # Patch analyst to return high verified percent
    called = {"ok": False}

    def fake_generate_ok(texts, article_ids=None, cluster_id=None):
        called["ok"] = True
        return {"cluster_fact_check_summary": {"percent_verified": 80.0}}

    import importlib

    importlib.import_module("agents.analyst.tools")
    monkeypatch.setattr(
        "agents.analyst.tools.generate_analysis_report", fake_generate_ok
    )

    # Patch cluster_articles and aggregate_cluster so we don't require heavy ML dependencies
    async def fake_cluster_articles(texts, max_clusters):
        return {"status": "success", "clusters": [[0, 1]]}

    monkeypatch.setattr(engine, "cluster_articles", fake_cluster_articles)
    called_agg = {"ok": False}

    async def fake_aggregate_cluster(texts):
        called_agg["ok"] = True
        return SynthesisResult(
            success=True,
            content="Combined synthesis",
            method="fake",
            processing_time=0.1,
            model_used="none",
            confidence=0.9,
        )

    monkeypatch.setattr(engine, "aggregate_cluster", fake_aggregate_cluster)

    res = await engine.synthesize_gpu(
        [], max_clusters=2, context="news", options={"cluster_id": "cluster-abc"}
    )

    assert res.get("status") == "success"
    assert "synthesized_content" in res
    assert called_agg["ok"] is True
    assert res["synthesized_content"] == "Combined synthesis"


@pytest.mark.asyncio
async def test_post_synthesis_draft_fact_check_blocks_when_failed(
    synthesizer_engine, monkeypatch
):
    engine: SynthesizerEngine = synthesizer_engine

    # Fake cluster fetch
    fake_articles = [
        FakeArticle("a1", "Test content"),
        FakeArticle("a2", "Other content"),
    ]

    class FakeFetcher:
        def fetch_cluster(
            self, cluster_id=None, article_ids=None, max_results=50, dedupe=True
        ):
            return fake_articles

    monkeypatch.setattr(
        "agents.cluster_fetcher.cluster_fetcher.ClusterFetcher", lambda: FakeFetcher()
    )

    # pre-flight check passes
    def fake_generate_pre(texts, article_ids=None, cluster_id=None):
        return {"cluster_fact_check_summary": {"percent_verified": 100.0}}

    import importlib

    importlib.import_module("agents.analyst.tools")

    def make_fake(pre, post):
        def _fake(texts, article_ids=None, cluster_id=None):
            # distinguish pre-flight cluster call (multiple texts) vs draft call (single text)
            if isinstance(texts, list) and len(texts) > 1:
                return pre(texts, article_ids=article_ids, cluster_id=cluster_id)
            return post(texts, article_ids=article_ids, cluster_id=cluster_id)

        return _fake

    # patch clustering and aggregated synthesis
    async def fake_cluster_articles(texts, max_clusters):
        return {"status": "success", "clusters": [[0, 1]]}

    async def fake_aggregate_cluster(texts):
        return SynthesisResult(
            success=True,
            content="Combined synthesis",
            method="fake",
            processing_time=0.1,
            model_used="none",
            confidence=0.9,
        )

    monkeypatch.setattr(engine, "cluster_articles", fake_cluster_articles)
    monkeypatch.setattr(engine, "aggregate_cluster", fake_aggregate_cluster)

    # post-synthesis fact-check fails
    def fake_generate_post(texts, article_ids=None, cluster_id=None):
        return {
            "per_article": [
                {
                    "source_fact_check": {
                        "fact_check_status": "failed",
                        "overall_score": 0.0,
                        "fact_check_trace": {},
                    }
                }
            ],
            "source_fact_checks": [{"fact_check_status": "failed"}],
        }

    monkeypatch.setattr(
        "agents.analyst.tools.generate_analysis_report",
        _make_fake(fake_generate_pre, fake_generate_post),
    )

    res = await engine.synthesize_gpu(
        [], max_clusters=2, context="news", options={"cluster_id": "cluster-abc"}
    )

    assert res.get("status") == "error"
    assert res.get("error") == "draft_fact_check_failed"
    assert "analysis_report" in res


@pytest.mark.asyncio
async def test_post_synthesis_draft_fact_check_needs_review(
    synthesizer_engine, monkeypatch
):
    engine: SynthesizerEngine = synthesizer_engine

    fake_articles = [
        FakeArticle("a1", "Test content"),
        FakeArticle("a2", "Other content"),
    ]

    class FakeFetcher:
        def fetch_cluster(
            self, cluster_id=None, article_ids=None, max_results=50, dedupe=True
        ):
            return fake_articles

    monkeypatch.setattr(
        "agents.cluster_fetcher.cluster_fetcher.ClusterFetcher", lambda: FakeFetcher()
    )

    # pre-flight check passes
    def fake_generate_pre(texts, article_ids=None, cluster_id=None):
        return {"cluster_fact_check_summary": {"percent_verified": 100.0}}

    import importlib

    importlib.import_module("agents.analyst.tools")
    monkeypatch.setattr(
        "agents.analyst.tools.generate_analysis_report", fake_generate_pre
    )

    # patch clustering and aggregated synthesis
    async def fake_cluster_articles(texts, max_clusters):
        return {"status": "success", "clusters": [[0, 1]]}

    async def fake_aggregate_cluster(texts):
        return SynthesisResult(
            success=True,
            content="Combined synthesis",
            method="fake",
            processing_time=0.1,
            model_used="none",
            confidence=0.9,
        )

    monkeypatch.setattr(engine, "cluster_articles", fake_cluster_articles)
    monkeypatch.setattr(engine, "aggregate_cluster", fake_aggregate_cluster)

    # post-synthesis fact-check needs review
    def fake_generate_post(texts, article_ids=None, cluster_id=None):
        return {
            "per_article": [
                {
                    "source_fact_check": {
                        "fact_check_status": "needs_review",
                        "overall_score": 0.5,
                        "fact_check_trace": {},
                    }
                }
            ],
            "source_fact_checks": [{"fact_check_status": "needs_review"}],
        }

    monkeypatch.setattr(
        "agents.analyst.tools.generate_analysis_report",
        _make_fake(fake_generate_pre, fake_generate_post),
    )

    res = await engine.synthesize_gpu(
        [], max_clusters=2, context="news", options={"cluster_id": "cluster-abc"}
    )

    assert res.get("status") == "error"
    assert res.get("error") == "draft_fact_check_needs_review"
    assert "analysis_report" in res


@pytest.mark.asyncio
async def test_post_synthesis_draft_fact_check_allows_on_pass(
    synthesizer_engine, monkeypatch
):
    engine: SynthesizerEngine = synthesizer_engine

    fake_articles = [
        FakeArticle("a1", "Test content"),
        FakeArticle("a2", "Other content"),
    ]

    class FakeFetcher:
        def fetch_cluster(
            self, cluster_id=None, article_ids=None, max_results=50, dedupe=True
        ):
            return fake_articles

    monkeypatch.setattr(
        "agents.cluster_fetcher.cluster_fetcher.ClusterFetcher", lambda: FakeFetcher()
    )

    # pre-flight check passes
    def fake_generate_pre(texts, article_ids=None, cluster_id=None):
        return {"cluster_fact_check_summary": {"percent_verified": 100.0}}

    import importlib

    importlib.import_module("agents.analyst.tools")
    monkeypatch.setattr(
        "agents.analyst.tools.generate_analysis_report", fake_generate_pre
    )

    # patch clustering and aggregated synthesis
    async def fake_cluster_articles(texts, max_clusters):
        return {"status": "success", "clusters": [[0, 1]]}

    async def fake_aggregate_cluster(texts):
        return SynthesisResult(
            success=True,
            content="Combined synthesis",
            method="fake",
            processing_time=0.1,
            model_used="none",
            confidence=0.9,
        )

    monkeypatch.setattr(engine, "cluster_articles", fake_cluster_articles)
    monkeypatch.setattr(engine, "aggregate_cluster", fake_aggregate_cluster)

    # post-synthesis fact-check passes
    def fake_generate_post(texts, article_ids=None, cluster_id=None):
        return {
            "per_article": [
                {
                    "source_fact_check": {
                        "fact_check_status": "passed",
                        "overall_score": 0.95,
                        "fact_check_trace": {},
                    }
                }
            ],
            "source_fact_checks": [{"fact_check_status": "passed"}],
        }

    monkeypatch.setattr(
        "agents.analyst.tools.generate_analysis_report",
        _make_fake(fake_generate_pre, fake_generate_post),
    )

    res = await engine.synthesize_gpu(
        [], max_clusters=2, context="news", options={"cluster_id": "cluster-abc"}
    )

    assert res.get("status") == "success"
    assert "synthesized_content" in res
    assert res["synthesized_content"] == "Combined synthesis"
