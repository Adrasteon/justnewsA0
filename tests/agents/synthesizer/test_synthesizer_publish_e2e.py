import importlib

from fastapi.testclient import TestClient

# Import inside test after monkeypatching so that FastAPI lifespan uses the
# patched SynthesizerEngine class. See tests below.
from config.core import get_config


def test_synthesize_and_publish_auto_publishes_with_flag(monkeypatch):
    # Setup: disable transparency gate and create safe engine
    monkeypatch.setenv("REQUIRE_TRANSPARENCY_AUDIT", "0")
    monkeypatch.setenv("ALLOWED_HOSTS", "testserver,localhost,127.0.0.1")

    # Patch engine creation so startup does not load heavy models
    class FakeEngine:
        def __init__(self, *args, **kwargs):
            pass

        def cleanup(self):
            pass

    monkeypatch.setattr(
        "agents.synthesizer.main.SynthesizerEngine", FakeEngine, raising=False
    )

    synth_main = importlib.import_module("agents.synthesizer.main")
    # Ensure the engine is present & we bypass transparency gate for tests
    synth_main.synthesizer_engine = FakeEngine()
    synth_main.transparency_gate_passed = True

    # Patch synthesize GPU tool: returns a synthetic summary
    async def fake_synthesize_gpu_tool(
        engine, articles, max_clusters, context, cluster_id=None
    ):
        return {
            "success": True,
            "synthesis": "This is an auto-generated synthesis.",
        }

    monkeypatch.setattr(
        "agents.synthesizer.tools.synthesize_gpu_tool", fake_synthesize_gpu_tool
    )
    # Also patch the local reference in the synthesizer main module
    monkeypatch.setattr(
        "agents.synthesizer.main.synthesize_gpu_tool", fake_synthesize_gpu_tool
    )

    # Patch critic to pass
    async def fake_critic(content, op):
        return {"critique_score": 0.95}

    monkeypatch.setattr("agents.critic.tools.process_critique_request", fake_critic)

    # Patch analyst to pass draft-level fact check
    def fake_generate_analysis_report(texts, article_ids=None, cluster_id=None):
        return {
            "per_article": [
                {
                    "source_fact_check": {
                        "fact_check_status": "passed",
                        "overall_score": 0.95,
                    }
                }
            ],
            "cluster_fact_check_summary": {"percent_verified": 100.0},
        }

    monkeypatch.setattr(
        "agents.analyst.tools.generate_analysis_report", fake_generate_analysis_report
    )

    # Patch publisher to accept a story id
    def fake_publish(story_id: str):
        return {"status": "published", "story_id": story_id}

    monkeypatch.setattr("agents.chief_editor.tools.publish_story", fake_publish)

    # Toggle system config to require draft fact-check pass and disable chief-editor-required
    cfg = get_config()
    cfg.agents.publishing.require_draft_fact_check_pass_for_publish = True
    cfg.agents.publishing.chief_editor_review_required = False

    client = TestClient(synth_main.app)

    body = {
        "articles": [{"content": "A short article"}],
        "max_clusters": 1,
        "context": "news",
        "cluster_id": "c-1",
        "publish": True,
    }

    resp = client.post(
        "/synthesize_and_publish", json=body, headers={"Host": "localhost"}
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data.get("status") == "published"
    assert "story_id" in data


def test_synthesize_and_publish_blocks_when_draft_factcheck_fail(monkeypatch):
    # Setup: disable transparency gate and create safe engine
    monkeypatch.setenv("REQUIRE_TRANSPARENCY_AUDIT", "0")
    monkeypatch.setenv("ALLOWED_HOSTS", "testserver,localhost,127.0.0.1")

    class FakeEngine:
        def __init__(self, *args, **kwargs):
            pass

        def cleanup(self):
            pass

    monkeypatch.setattr(
        "agents.synthesizer.main.SynthesizerEngine", FakeEngine, raising=False
    )

    synth_main = importlib.import_module("agents.synthesizer.main")
    # Ensure the engine is present & we bypass transparency gate for tests
    synth_main.synthesizer_engine = FakeEngine()
    synth_main.transparency_gate_passed = True

    async def fake_synthesize_gpu_tool(
        engine, articles, max_clusters, context, cluster_id=None
    ):
        return {"success": True, "synthesis": "This is an auto-generated synthesis."}

    monkeypatch.setattr(
        "agents.synthesizer.tools.synthesize_gpu_tool", fake_synthesize_gpu_tool
    )
    monkeypatch.setattr(
        "agents.synthesizer.main.synthesize_gpu_tool", fake_synthesize_gpu_tool
    )

    async def fake_critic(content, op):
        return {"critique_score": 0.95}

    monkeypatch.setattr("agents.critic.tools.process_critique_request", fake_critic)

    # Analyst returns failed
    def fake_generate_analysis_report(texts, article_ids=None, cluster_id=None):
        return {
            "per_article": [
                {
                    "source_fact_check": {
                        "fact_check_status": "failed",
                        "overall_score": 0.2,
                    }
                }
            ],
            "cluster_fact_check_summary": {"percent_verified": 100.0},
        }

    monkeypatch.setattr(
        "agents.analyst.tools.generate_analysis_report", fake_generate_analysis_report
    )

    # Set config to require pass for publish
    cfg = get_config()
    cfg.agents.publishing.require_draft_fact_check_pass_for_publish = True
    cfg.agents.publishing.chief_editor_review_required = False

    client = TestClient(synth_main.app)

    body = {"articles": [{"content": "A short article"}], "publish": True}

    resp = client.post(
        "/synthesize_and_publish", json=body, headers={"Host": "localhost"}
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data.get("status") == "error"
    assert data.get("error") == "draft_fact_check_failed"
    assert "analysis_report" in data
