from datetime import datetime

from database.models.migrated_models import SynthesizedArticle


def test_synthesized_article_init_and_serialization():
    created = datetime.now()
    sa = SynthesizedArticle(
        id=1,
        story_id="s1",
        cluster_id="c1",
        input_articles=["a1", "a2"],
        title="Test",
        body="Body text",
        summary="Short summary",
        reasoning_plan={"outline": ["intro", "body"]},
        analysis_summary={"entities": []},
        synth_metadata={"model": "gpt-test"},
        created_at=created,
        updated_at=created,
        is_published=False,
    )

    d = sa.to_dict()
    assert d["story_id"] == "s1"
    assert d["cluster_id"] == "c1"
    assert d["input_articles"] == ["a1", "a2"]
    assert d["title"] == "Test"

    row_like = (
        1,
        "s1",
        "c1",
        '["a1", "a2"]',
        "Test",
        "Body text",
        "Short summary",
        '{"outline": ["intro", "body"]}',
        '{"entities": []}',
        '{"model": "gpt-test"}',
        created,
        created,
        False,
        None,
        None,
    )

    sa2 = SynthesizedArticle.from_row(row_like)
    assert sa2.story_id == "s1"
    assert sa2.input_articles == ["a1", "a2"]
