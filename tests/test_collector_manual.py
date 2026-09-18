"""fetch_article_by_url is the manual-add feature's fetch/parse step: given
an arbitrary URL (not NAVER API HUB), turn its HTML page into an Article
Claude can evaluate the same way as any other candidate. Network access is
mocked - these tests only cover parsing and the invalid-input/failure paths.
"""
from __future__ import annotations

from datetime import timezone

import requests

from pipeline import collector


class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.content = text.encode("utf-8")
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


def test_rejects_non_http_url():
    assert collector.fetch_article_by_url("ftp://example.com/a") is None


def test_extracts_og_title_and_body(monkeypatch):
    html = """
    <html><head>
      <meta property="og:title" content="브랜드, 리포지셔닝 전략 발표">
      <meta property="article:published_time" content="2026-09-10T09:00:00+09:00">
    </head><body>
      <nav>메뉴</nav>
      <article><p>본문 내용입니다.</p><script>ignoreMe()</script></article>
      <footer>푸터</footer>
    </body></html>
    """
    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(html))

    article = collector.fetch_article_by_url("https://example.com/news/1")

    assert article is not None
    assert article.title == "브랜드, 리포지셔닝 전략 발표"
    assert "본문 내용입니다" in article.description
    assert "ignoreMe" not in article.description
    assert "메뉴" not in article.description and "푸터" not in article.description
    assert article.published_at.year == 2026
    assert article.published_at.tzinfo is not None


def test_falls_back_to_title_tag_when_no_og_title(monkeypatch):
    html = "<html><head><title>제목만 있는 페이지</title></head><body><p>내용</p></body></html>"
    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(html))

    article = collector.fetch_article_by_url("https://example.com/x")

    assert article.title == "제목만 있는 페이지"


def test_falls_back_to_now_when_no_published_meta(monkeypatch):
    html = "<html><head><title>t</title></head><body><p>내용</p></body></html>"
    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(html))

    article = collector.fetch_article_by_url("https://example.com/x")

    assert article.published_at.tzinfo == timezone.utc


def test_returns_none_on_http_error(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse("", status_code=404))
    assert collector.fetch_article_by_url("https://example.com/missing") is None


def test_returns_none_on_connection_error(monkeypatch):
    def raise_connection_error(*a, **k):
        raise requests.ConnectionError("boom")
    monkeypatch.setattr(requests, "get", raise_connection_error)
    assert collector.fetch_article_by_url("https://example.com/x") is None
