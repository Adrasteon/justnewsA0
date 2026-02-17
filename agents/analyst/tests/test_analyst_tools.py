import pytest

from agents.analyst import tools as analyst_tools


class FakeAnalystEngine:
    def __init__(self):
        self.spacy_nlp = True
        self.ner_pipeline = True
        self.gpu_analyst = False
        self.processing_stats = {"total_processed": 0}

    def extract_entities(self, text):
        return {
            "entities": [{"text": "OpenAI", "label": "ORG"}],
            "total_entities": 1,
            "method": "spacy",
        }

    def analyze_text_statistics(self, text):
        return {
            "word_count": 4,
            "character_count": len(text),
            "sentence_count": 1,
            "readability_score": 50,
        }

    def extract_key_metrics(self, text, url=None):
        return {
            "metrics": [{"name": "revenue", "value": 100}],
            "total_metrics": 1,
            "text_length": len(text),
            "url": url,
        }

    def analyze_sentiment(self, text):
        return {
            "dominant_sentiment": "positive",
            "confidence": 0.9,
            "intensity": "mild",
            "method": "basic",
        }

    def detect_bias(self, text):
        return {
            "has_bias": False,
            "bias_score": 0.1,
            "bias_level": "low",
            "confidence": 0.6,
        }

    def analyze_sentiment_and_bias(self, text):
        return {
            "sentiment_analysis": self.analyze_sentiment(text),
            "bias_analysis": self.detect_bias(text),
            "combined_assessment": {"reliability": 0.9},
            "recommendations": ["source balance"],
        }

    def extract_claims(self, text):
        # Very simple deterministic return
        if not text or not text.strip():
            return []
        return [
            {
                "claim_text": "OpenAI released model",
                "start": 0,
                "end": 23,
                "confidence": 0.75,
                "claim_type": "assertion",
            }
        ]

    def generate_analysis_report(self, texts, article_ids=None, cluster_id=None):
        # Very small report assembled deterministically for test
        per_article = []
        for i, t in enumerate(texts):
            per_article.append(
                {
                    "article_id": None if not article_ids else article_ids[i],
                    "language": "en",
                    "sentiment": self.analyze_sentiment(t),
                    "bias": self.detect_bias(t),
                    "entities": [{"text": "OpenAI", "label": "ORG"}],
                    "claims": self.extract_claims(t),
                    "processing_time_seconds": 0.01,
                }
            )
        return {
            "cluster_id": cluster_id,
            "language": "en",
            "articles_count": len(texts),
            "aggregate_sentiment": {"average_confidence": 0.9},
            "aggregate_bias": {"average_bias_score": 0.1},
            "entities": [{"text": "OpenAI", "label": "ORG"}],
            "primary_claims": [self.extract_claims(texts[0])[0]] if texts else [],
            "per_article": per_article,
            "generated_at": "test",
        }


@pytest.fixture(autouse=True)
def monkey_engine(monkeypatch):
    engine = FakeAnalystEngine()
    # Monkeypatch the module's internal _engine
    monkeypatch.setattr(analyst_tools, "_engine", engine)
    yield
    monkeypatch.setattr(analyst_tools, "_engine", None)


def test_identify_entities_success():
    res = analyst_tools.identify_entities("OpenAI released a new model")
    assert res["total_entities"] == 1
    assert isinstance(res["entities"], list)


def test_identify_entities_empty():
    res = analyst_tools.identify_entities("   ")
    assert res["total_entities"] == 0


def test_analyze_text_statistics_success():
    res = analyst_tools.analyze_text_statistics("This is a test")
    assert res["word_count"] == 4


def test_analyze_text_statistics_empty():
    res = analyst_tools.analyze_text_statistics("")
    assert res["word_count"] == 0


def test_extract_key_metrics_success():
    res = analyst_tools.extract_key_metrics(
        "Revenue was $100", url="https://example.com"
    )
    assert res["total_metrics"] == 1
    assert res["url"] == "https://example.com"


def test_analyze_sentiment_and_bias():
    res = analyst_tools.analyze_sentiment_and_bias("Neutral content")
    assert "sentiment_analysis" in res
    assert "bias_analysis" in res


def test_process_analysis_request_unknown_type(monkeypatch):
    # Use monkeypatch to set module engine
    monkeypatch.setattr(analyst_tools, "_engine", FakeAnalystEngine())
    # Async function; call via pytest
    import asyncio

    res = asyncio.run(analyst_tools.process_analysis_request("x", "unknown"))
    assert "error" in res and "Unknown analysis type" in res["error"]


def test_extract_claims_success(monkeypatch):
    monkeypatch.setattr(analyst_tools, "_engine", FakeAnalystEngine())
    res = analyst_tools.extract_claims("OpenAI released a new model")
    assert isinstance(res, list)
    assert len(res) == 1
    assert res[0]["claim_text"] == "OpenAI released model"


def test_generate_analysis_report_single(monkeypatch):
    monkeypatch.setattr(analyst_tools, "_engine", FakeAnalystEngine())
    report = analyst_tools.generate_analysis_report(["OpenAI released model"])
    assert isinstance(report, dict)
    assert report["articles_count"] == 1
    assert "primary_claims" in report


def test_generate_analysis_report_with_cluster(monkeypatch):
    # Return two fake ArticleRecord objects from ClusterFetcher
    from agents.cluster_fetcher.cluster_fetcher import ArticleRecord

    def fake_fetcher():
        class Fake:
            def fetch_cluster(self, cluster_id=None):
                return [
                    ArticleRecord(article_id="a1", content="Text 1", url="https://1"),
                    ArticleRecord(article_id="a2", content="Text 2", url="https://2"),
                ]

        return Fake()

    monkeypatch.setattr(analyst_tools, "ClusterFetcher", lambda: fake_fetcher())
    monkeypatch.setattr(analyst_tools, "_engine", FakeAnalystEngine())

    # Generate analysis report with cluster_id and no explicit texts
    report = analyst_tools.generate_analysis_report([], cluster_id="cluster-1")

    assert report["articles_count"] == 2
    assert report["per_article"][0]["article_id"] == "a1"
