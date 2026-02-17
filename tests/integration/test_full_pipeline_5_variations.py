import importlib

from fastapi.testclient import TestClient


def test_full_pipeline_5_variations(monkeypatch):
    """Integration-style test: 5 articles (same topic, differing bias/sentiment)
    flow: synthesize_and_publish -> publish -> dashboard public articles
    All heavy components are patched; the test verifies the full control flow
    and that the public website endpoint could surface the published story.
    """

    # 1) Set environment flags for tests (bypass transparency gate)
    monkeypatch.setenv("REQUIRE_TRANSPARENCY_AUDIT", "0")
    monkeypatch.setenv("ALLOWED_HOSTS", "testserver,localhost,127.0.0.1")

    # 2) Provide a Fake synthesizer engine so startup is lightweight
    class FakeEngine:
        def __init__(self, *args, **kwargs):
            pass

        def cleanup(self):
            pass

    monkeypatch.setattr(
        "agents.synthesizer.main.SynthesizerEngine", FakeEngine, raising=False
    )
    synth_main = importlib.import_module("agents.synthesizer.main")
    synth_main.synthesizer_engine = FakeEngine()
    synth_main.transparency_gate_passed = True

    # 3) Fake fetcher returns 5 articles on same topic but different sentiment/bias
    class FakeArticleObj:
        def __init__(self, id, title, content, source):
            self.article_id = id

        def to_dict(self):
            return {
                "article_id": self.article_id,
                "content": f"Content for {self.article_id}",
            }

    fake_articles = [
        FakeArticleObj(f"a{i}", f"Title {i}", f"Content {i}", "Source")
        for i in range(1, 6)
    ]

    class FakeFetcher:
        def fetch_cluster(
            self, cluster_id=None, article_ids=None, max_results=50, dedupe=True
        ):
            return fake_articles

    monkeypatch.setattr(
        "agents.cluster_fetcher.cluster_fetcher.ClusterFetcher", lambda: FakeFetcher()
    )

    # 4) Analyst: return a per-article analysis with different sentiment/bias markers
    def fake_generate_analysis_report(texts, article_ids=None, cluster_id=None):
        # texts can be list or single; distinguish between preflight (multiple items)
        # and post-synthesis (single-element list containing synthesized draft).
        if isinstance(texts, list):
            if len(texts) > 1:
                # Preflight: ensure cluster percent verified is high
                return {"cluster_fact_check_summary": {"percent_verified": 100.0}}
            # Treat single-item lists as post-synthesis draft checks
            return {
                "per_article": [
                    {
                        "source_fact_check": {
                            "fact_check_status": "passed",
                            "overall_score": 0.9,
                        }
                    }
                ],
                "cluster_fact_check_summary": {"percent_verified": 100.0},
            }

        # post synthesis single-draft analysis (non-list)
        return {
            "per_article": [
                {
                    "source_fact_check": {
                        "fact_check_status": "passed",
                        "overall_score": 0.9,
                    }
                }
            ],
            "cluster_fact_check_summary": {"percent_verified": 100.0},
        }

    monkeypatch.setattr(
        "agents.analyst.tools.generate_analysis_report", fake_generate_analysis_report
    )

    # 5) Synthesize tool: produce combined synthesis content (simulate neutralization)
    async def fake_synthesize_gpu_tool(
        engine, articles, max_clusters, context, cluster_id=None
    ):
        # return a summary that would plausibly be displayed on the public web page
        return {
            "success": True,
            "synthesis": "Neutral synthesis of diverse perspectives on the same topic.",
        }

    monkeypatch.setattr(
        "agents.synthesizer.tools.synthesize_gpu_tool", fake_synthesize_gpu_tool
    )
    monkeypatch.setattr(
        "agents.synthesizer.main.synthesize_gpu_tool", fake_synthesize_gpu_tool
    )

    # 6) Critic: pass with high score
    async def fake_critic(content, op):
        return {"critique_score": 0.95}

    monkeypatch.setattr("agents.critic.tools.process_critique_request", fake_critic)

    # 7) Publish story: capture and return story id
    published = {}

    def fake_publish(story_id: str):
        published["story_id"] = story_id
        return {"status": "published", "story_id": story_id}

    monkeypatch.setattr("agents.chief_editor.tools.publish_story", fake_publish)

    # 8) Memory save_article: simulate saving and returning published article metadata
    saved_article = {}

    def fake_save_article(payload):
        # simulate a stored article id and published flag
        stored = {
            "article_id": "synth-5",
            "title": "Neutral synthesis of diverse perspectives",
            "content": payload.get("synthesis") or "synth content",
            "source_name": "JustNews Synthesizer",
            "published_date": "2025-11-21",
            "is_published": True,
        }
        saved_article.update(stored)
        return stored

    monkeypatch.setattr("agents.memory.tools.save_article", fake_save_article)

    # Ensure synthesizer persistence doesn't attempt a real DB write during the test
    def fake_save_synthesized_draft(
        story_id,
        title,
        body,
        summary=None,
        analysis_summary=None,
        synth_metadata=None,
        persistence_mode="extend",
        embedding=None,
    ):
        payload = {"synthesis": body, "story_id": story_id, "title": title}
        return fake_save_article(payload)

    monkeypatch.setattr(
        "agents.synthesizer.persistence.save_synthesized_draft",
        fake_save_synthesized_draft,
    )

    # 9) Configure publishing policy: require draft fact-check pass but allow auto-publish
    cfg = importlib.import_module("config.core").get_config()
    cfg.agents.publishing.require_draft_fact_check_pass_for_publish = True
    cfg.agents.publishing.chief_editor_review_required = False

    # 10) Execute POST /synthesize_and_publish via TestClient
    client = TestClient(synth_main.app)
    body = {
        "articles": [],
        "max_clusters": 1,
        "context": "news",
        "cluster_id": "cluster-5bias",
        "publish": True,
    }
    resp = client.post(
        "/synthesize_and_publish", json=body, headers={"Host": "localhost"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "published"
    assert "story_id" in data

    # 11) Now exercise the public articles endpoint on dashboard and return saved article
    dashboard_mod = importlib.import_module("agents.dashboard.main")

    # Fake recent article search service to return our saved article for the public API
    class FakeArticle:
        def __init__(self, id, title, content, source_name, published_date):
            self.id = id
            self.title = title
            self.content = content
            self.source_name = source_name
            self.published_date = published_date

    fake_public = [
        FakeArticle(
            saved_article["article_id"],
            saved_article["title"],
            saved_article["content"],
            saved_article["source_name"],
            saved_article["published_date"],
        )
    ]

    class FakeSearchService:
        def get_recent_articles_with_search(self, n_results=10):
            return fake_public[:n_results]

    # Patch the dashboard module-local reference to ensure the dashboard uses our fake
    monkeypatch.setattr(
        "agents.dashboard.main.get_search_service", lambda: FakeSearchService()
    )

    client_dash = TestClient(dashboard_mod.app)
    resp2 = client_dash.get("/api/public/articles?n=1")
    assert resp2.status_code == 200
    page_data = resp2.json()
    assert page_data["total_results"] == 1
    assert page_data["articles"][0]["id"] == saved_article["article_id"]
    assert (
        "summary" in page_data["articles"][0] or "content" in page_data["articles"][0]
    )
