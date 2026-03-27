
from agents.dashboard.transparency_repository import TransparencyRepository


def test_get_article_includes_traceability_payload(tmp_path, monkeypatch):
    base = tmp_path / 'transparency'
    (base / 'facts').mkdir(parents=True)
    (base / 'articles').mkdir(parents=True)
    (base / 'clusters').mkdir(parents=True)
    (base / 'evidence').mkdir(parents=True)

    (base / 'index.json').write_text('{"facts": [], "clusters": []}', encoding='utf-8')
    (base / 'articles' / '101.json').write_text('{"article_id": 101}', encoding='utf-8')

    repo = TransparencyRepository(base)

    monkeypatch.setattr(
        TransparencyRepository,
        '_load_article_traceability',
        lambda self, article_id: {'article_id': int(article_id), 'statement_count': 2, 'quote_count': 1},
    )

    payload = repo.get_article('101')

    assert payload['traceability']['statement_count'] == 2
    assert payload['traceability']['quote_count'] == 1
