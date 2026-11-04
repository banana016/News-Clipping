"""POST /api/feedback end to end through the real weight math, with an
in-memory stand-in for the feedback and tag_weights tables. Ratings must keep
tag_weights counting each article once, whatever order they're clicked in.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from shared import db
from shared.config import settings
from shared.db import with_latest_rating
from shared.magic_link import issue_token
from shared.models import TagWeight
from web.api import index as web

RUN_ID = "run-1"
ARTICLE_ID = "article-1"
TAG = "뷰티"


@pytest.fixture()
def store(monkeypatch):
    env = type("Store", (), {"feedback": [], "weights": {}})()
    monkeypatch.setattr(settings, "magic_link_secret", "test-secret")
    monkeypatch.setattr(db, "get_article_run_id", lambda a: RUN_ID if a == ARTICLE_ID else "another-run")
    monkeypatch.setattr(db, "get_article_tags", lambda a: [TAG])
    monkeypatch.setattr(db, "latest_rating_by_article",
                        lambda ids: {ARTICLE_ID: env.feedback[-1]} if env.feedback else {})
    monkeypatch.setattr(db, "record_feedback", lambda a, rating: env.feedback.append(rating))
    monkeypatch.setattr(db, "clear_feedback", lambda a: env.feedback.clear())
    monkeypatch.setattr(db, "get_all_tag_weights", lambda: {
        t: TagWeight(t, w.good_count, w.total_count, w.weight_adjustment) for t, w in env.weights.items()
    })
    monkeypatch.setattr(db, "upsert_tag_weight", lambda w: env.weights.__setitem__(w.tag, w))
    return env


def _post(rating: str, article_id: str = ARTICLE_ID):
    return TestClient(web.app).post("/api/feedback", json={
        "token": issue_token(RUN_ID), "article_id": article_id, "rating": rating,
    })


def _counts(store) -> tuple[int, int]:
    w = store.weights[TAG]
    return w.good_count, w.total_count


def test_changing_a_rating_counts_the_article_once(store):
    assert _post("good").status_code == 200
    assert _post("bad").status_code == 200
    assert _counts(store) == (0, 1)
    assert store.feedback[-1] == "bad"


def test_repeating_a_rating_is_a_no_op(store):
    _post("good")
    _post("good")
    assert _counts(store) == (1, 1)
    assert store.feedback == ["good"]


def test_cancelling_returns_the_article_to_unrated(store):
    _post("good")
    assert _post("none").status_code == 200
    assert _counts(store) == (0, 0)
    assert store.feedback == []


def test_cancelling_an_unrated_article_changes_nothing(store):
    assert _post("none").status_code == 200
    assert store.weights == {}


def test_rejects_unknown_rating_and_other_batches_articles(store):
    assert _post("great").status_code == 400
    assert _post("good", article_id="elsewhere").status_code == 404
    assert store.feedback == []


def test_with_latest_rating_picks_the_newest_row():
    row = {"id": "a", "feedback": [
        {"rating": "bad", "rated_at": "2026-11-04T01:00:00.5+00:00"},
        {"rating": "good", "rated_at": "2026-11-04T02:00:00+00:00"},
        {"rating": "bad", "rated_at": "2026-11-03T23:00:00+00:00"},
    ]}
    assert with_latest_rating(row) == {"id": "a", "rating": "good"}


def test_with_latest_rating_handles_unrated_articles():
    assert with_latest_rating({"id": "a", "feedback": []}) == {"id": "a", "rating": None}
