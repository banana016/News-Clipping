"""What "전문보기" includes: selected articles rated 도움됨 or not rated at all,
never 별로예요, plus reviewed articles only when explicitly rated 도움됨. The
database is mocked.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from shared import db
from shared.db import full_text_rows
from web.api import index as web


def _row(article_id: str, rating: str | None) -> dict:
    return {"id": article_id, "title": f"제목 {article_id}", "url": f"https://example.com/{article_id}",
            "rating": rating, "evaluations": {"summary": "요약", "interpretation": "해석", "insight_quote": "인용"}}


def test_selected_keeps_good_and_unrated_but_not_bad() -> None:
    selected = [_row("good", "good"), _row("unrated", None), _row("bad", "bad")]
    assert [r["id"] for r in full_text_rows(selected, [])] == ["good", "unrated"]


def test_reviewed_needs_an_explicit_good() -> None:
    reviewed = [_row("good", "good"), _row("unrated", None), _row("bad", "bad")]
    assert [r["id"] for r in full_text_rows([], reviewed)] == ["good"]


def test_selected_come_before_reviewed() -> None:
    rows = full_text_rows([_row("s", None)], [_row("r", "good")])
    assert [r["id"] for r in rows] == ["s", "r"]


def _get(monkeypatch, selected: list[dict]) -> dict:
    monkeypatch.setattr(db, "get_briefing_for_run", lambda run_id: {"selected": selected, "reviewed": []})
    monkeypatch.setattr(db, "get_run_date", lambda run_id: "2026-11-04")
    monkeypatch.setattr(web, "verify_token", lambda token: {"run_id": "run-1"})
    return TestClient(web.app).get("/api/liked-full-text", params={"token": "t"}).json()


def test_endpoint_text_has_only_the_kept_articles(monkeypatch) -> None:
    res = _get(monkeypatch, [_row("good", "good"), _row("unrated", None), _row("bad", "bad")])
    assert res["count"] == 2
    assert "제목 good" in res["text"] and "제목 unrated" in res["text"]
    assert "제목 bad" not in res["text"]


def test_endpoint_reports_nothing_left_when_all_are_bad(monkeypatch) -> None:
    res = _get(monkeypatch, [_row("bad", "bad")])
    assert res["count"] == 0
    assert res["text"] == ""
    assert res["message"]
