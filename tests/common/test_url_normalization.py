from __future__ import annotations

import hashlib

import pytest

from common.url_normalization import hash_article_url, normalize_article_url


@pytest.mark.parametrize(
    "url, canonical, expected",
    [
        (
            "https://Example.com/news/Focus/?utm_source=feed&ref=homepage",
            "https://example.com/news/focus/",
            "https://example.com/news/focus",
        ),
        (
            "https://example.com/a/b//c?fbclid=abc",
            None,
            "https://example.com/a/b/c",
        ),
    ],
)
def test_normalize_article_url_strict(url, canonical, expected, monkeypatch):
    monkeypatch.setenv("ARTICLE_URL_NORMALIZATION", "strict")
    assert normalize_article_url(url, canonical) == expected


def test_normalize_article_url_lenient_keeps_query(monkeypatch):
    monkeypatch.setenv("ARTICLE_URL_NORMALIZATION", "lenient")
    url = "https://example.com/path?utm_source=feed&foo=bar"
    assert normalize_article_url(url, None).endswith("foo=bar")
    assert "utm_source" in normalize_article_url(url, None)


def test_hash_article_url_uses_env_algorithm(monkeypatch):
    monkeypatch.setenv("ARTICLE_URL_HASH_ALGO", "md5")
    normalized = "https://example.com/path"
    expected = hashlib.md5(normalized.encode("utf-8")).hexdigest()
    assert hash_article_url(normalized) == expected


def test_hash_article_url_invalid_algorithm(monkeypatch):
    monkeypatch.setenv("ARTICLE_URL_HASH_ALGO", "bogus")
    with pytest.raises(ValueError):
        hash_article_url("https://example.com/path")
