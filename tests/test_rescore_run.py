"""scripts/rescore_run.py recovers runs in place in production, so what matters
most is that it refuses what it shouldn't touch and writes nothing on a bad
evaluation. The database, NAVER and Claude are all mocked.
"""
from __future__ import annotations

import pytest

from pipeline import dedup, scorer
from scripts import rescore_run
from shared import db
from shared.models import Evaluation, TagWeight, url_hash

RUN_ID = "run-1"


def _row(i: int) -> dict:
    url = f"https://example.com/news/{i}"
    return {"id": f"a{i}", "run_id": RUN_ID, "title": f"기사 {i}", "source": "s", "url": url,
            "url_hash": url_hash(url), "published_at": "2026-11-04T00:00:00+00:00", "tier": "reviewed"}


def _evaluation(article_id: str) -> Evaluation:
    return Evaluation(article_id=article_id, strategic_relevance=30, stp_4p_relevance=25,
                      practical_applicability=20, market_impact=10, recency=10, credibility=5,
                      tags=["뷰티"], summary="요약", interpretation="해석", application="적용")


@pytest.fixture()
def env(monkeypatch):
    state = type("Env", (), {"rows": [_row(i) for i in range(10)], "existing_evals": 0, "selected_n": 0,
                             "saved": [], "tiers": [], "recovered": [], "weights": {}, "ratings": {},
                             "evaluated": None})()
    monkeypatch.setattr(db, "get_run", lambda r: {"id": r, "run_date": "2026-11-04", "selected_n": state.selected_n})
    monkeypatch.setattr(db, "get_articles_for_rescore", lambda r: state.rows)
    monkeypatch.setattr(db, "count_evaluations", lambda ids: state.existing_evals)
    monkeypatch.setattr(db, "get_all_tag_weights", lambda: state.weights)
    monkeypatch.setattr(db, "save_evaluations", lambda e: state.saved.extend(e))
    monkeypatch.setattr(db, "update_article_tier", lambda a, t: state.tiers.append((a, t)))
    monkeypatch.setattr(db, "mark_run_recovered", lambda r, n: state.recovered.append((r, n)))
    monkeypatch.setattr(db, "latest_rating_by_article",
                        lambda ids: {i: state.ratings[i] for i in ids if i in state.ratings})
    monkeypatch.setattr(db, "upsert_tag_weight", lambda w: state.weights.__setitem__(w.tag, w))
    monkeypatch.setattr(rescore_run, "lookup_description", lambda title, url: ("요약문", "naver"))
    monkeypatch.setattr(dedup, "resolve_cross_batch_duplicates", lambda e, by_id: e)

    def evaluate(articles):
        state.evaluated = articles
        return [_evaluation(a.id) for a in articles]

    monkeypatch.setattr(scorer, "evaluate", evaluate)
    return state


def _assert_nothing_written(env) -> None:
    assert (env.saved, env.tiers, env.recovered) == ([], [], [])


def test_recovers_a_run_in_place(env):
    assert rescore_run.rescore(RUN_ID, set()) == 10
    assert len(env.saved) == 10
    assert all(tier == "selected" for _, tier in env.tiers)
    assert env.recovered == [(RUN_ID, 10)]
    # Keeps the ids the existing feedback and email links point at.
    assert {a.id for a in env.evaluated} == {r["id"] for r in env.rows}
    assert env.evaluated[0].description == "요약문"


@pytest.mark.parametrize("field,value", [("selected_n", 30), ("existing_evals", 5), ("rows", [])])
def test_refuses_runs_it_should_not_touch(env, monkeypatch, field, value):
    called = []
    monkeypatch.setattr(scorer, "evaluate", lambda a: called.append(a) or [])
    setattr(env, field, value)

    with pytest.raises(rescore_run.CannotRescore):
        rescore_run.rescore(RUN_ID, set())

    assert called == []  # no credit spent
    _assert_nothing_written(env)


def test_low_coverage_writes_nothing(env, monkeypatch):
    monkeypatch.setattr(scorer, "evaluate", lambda articles: [_evaluation(a.id) for a in articles[:8]])

    with pytest.raises(rescore_run.CannotRescore):
        rescore_run.rescore(RUN_ID, set())

    _assert_nothing_written(env)


def test_article_selected_by_an_earlier_run_is_not_evaluated_again(env):
    already = {env.rows[0]["url_hash"]}

    assert rescore_run.rescore(RUN_ID, already) == 9

    assert env.rows[0]["id"] not in {a.id for a in env.evaluated}
    assert env.rows[1]["url_hash"] in already  # carried to the next run


def test_ratings_given_before_evaluation_now_count(env):
    env.ratings = {"a0": "bad", "a1": "good"}
    env.weights = {"뷰티": TagWeight("뷰티", 10, 20)}

    rescore_run.rescore(RUN_ID, set())

    assert (env.weights["뷰티"].good_count, env.weights["뷰티"].total_count) == (11, 22)
