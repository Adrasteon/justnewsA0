import pytest

from agents.synthesizer.tools import (
    aggregate_cluster_tool,
    cluster_articles_tool,
    neutralize_text_tool,
    synthesize_gpu_tool,
)


class FakeResult:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class FakeEngine:
    def __init__(self):
        self._raise = False
        self.feedback = []

    async def cluster_articles(self, article_texts, n_clusters):
        if self._raise:
            raise RuntimeError("cluster failed")
        return FakeResult(
            success=True,
            metadata={
                "clusters": [[0, 1]],
                "n_clusters": 2,
                "articles_processed": len(article_texts),
            },
            method="kmeans",
            model_used="mini",
            confidence=0.8,
        )

    async def neutralize_text(self, text):
        if self._raise:
            raise RuntimeError("neutralize failed")
        return FakeResult(
            success=True,
            content=text.replace("bad", "good"),
            method="neutralize-model",
            model_used="neutralizer",
            confidence=0.9,
        )

    async def aggregate_cluster(self, article_texts):
        if self._raise:
            raise RuntimeError("aggregate failed")
        return FakeResult(
            success=True,
            content="summary",
            method="agg",
            model_used="bart",
            confidence=0.75,
            metadata={
                "key_points": ["kp1"],
            },
        )

    async def synthesize_gpu(self, articles, max_clusters, context):
        if self._raise:
            raise RuntimeError("synthesize failed")
        return FakeResult(
            success=True,
            content="synth",
            method="gpu",
            model_used="flan-t5",
            confidence=0.95,
            metadata={
                "gpu_used": True,
                "articles_processed": len(articles),
                "clusters_found": 1,
            },
        )

    def log_feedback(self, name, data):
        # Simple stub to satisfy tools' calls
        self.feedback.append((name, data))


@pytest.mark.asyncio
async def test_cluster_articles_success():
    engine = FakeEngine()
    res = await cluster_articles_tool(engine, article_texts=["a", "b"], n_clusters=2)
    assert res["success"]
    assert res["n_clusters"] == 2
    assert res["processing_time"] >= 0


@pytest.mark.asyncio
async def test_cluster_articles_failure():
    engine = FakeEngine()
    engine._raise = True
    res = await cluster_articles_tool(engine, article_texts=["a", "b"], n_clusters=2)
    assert not res["success"]
    assert res["processing_time"] >= 0


@pytest.mark.asyncio
async def test_neutralize_text_success():
    engine = FakeEngine()
    res = await neutralize_text_tool(engine, "this is bad")
    assert res["success"]
    assert "neutralized_text" in res
    assert res["processing_time"] >= 0


@pytest.mark.asyncio
async def test_neutralize_text_failure():
    engine = FakeEngine()
    engine._raise = True
    res = await neutralize_text_tool(engine, "this is bad")
    assert not res["success"]
    assert res["neutralized_text"] == "this is bad"
    assert res["processing_time"] >= 0


@pytest.mark.asyncio
async def test_aggregate_cluster_success():
    engine = FakeEngine()
    res = await aggregate_cluster_tool(engine, article_texts=["a", "b"])
    assert res["success"]
    assert "summary" in res
    assert res["processing_time"] >= 0


@pytest.mark.asyncio
async def test_aggregate_cluster_failure():
    engine = FakeEngine()
    engine._raise = True
    res = await aggregate_cluster_tool(engine, article_texts=["a", "b"])
    assert not res["success"]
    assert res["processing_time"] >= 0


@pytest.mark.asyncio
async def test_synthesize_gpu_success():
    engine = FakeEngine()
    res = await synthesize_gpu_tool(
        engine, articles=[{"content": "a"}, {"content": "b"}]
    )
    assert res["success"]
    assert res["gpu_used"]
    assert res["processing_time"] >= 0


@pytest.mark.asyncio
async def test_synthesize_gpu_failure():
    engine = FakeEngine()
    engine._raise = True
    res = await synthesize_gpu_tool(engine, articles=[{"content": "a"}])
    assert not res["success"]
    assert res["processing_time"] >= 0
