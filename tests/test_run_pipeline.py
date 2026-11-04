"""run_pipeline.main's handling of the scoring step. scorer.evaluate never
raises - a failed batch just yields no evaluations - so main has to notice
when that adds up to nothing at all. Spotted in production: five runs in a row
hit an exhausted API credit balance and were recorded as 'done' with 0 selected.
The database, collection and email are all mocked.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from pipeline import collector, dedup, emailer, run_pipeline, scorer
from shared import db
from shared.models import Article, Evaluation


def _article(i: int) -> Article:
    return Article(
        title=f"브랜드 전략 기사 {i}", source="test", url=f"https://example.com/news/{i}",
        published_at=datetime.now(timezone.utc), description="브랜드 전략 리포지셔닝 사례",
    )


def _evaluation(article: Article) -> Evaluation:
    return Evaluation(
        article_id=article.id, strategic_relevance=30, stp_4p_relevance=25,
        practical_applicability=20, market_impact=10, recency=10, credibility=5,
        tags=[], summary="요약", interpretation="해석", application="적용",
    )


@pytest.fixture()
def pipeline_env(monkeypatch):
    """Returns the mocks a test needs: `finished` collects finish_run calls,
    `emails` collects sent subjects, `articles` is what collection returns."""
    env = type("Env", (), {"finished": [], "emails": [], "articles": [_article(1), _article(2)]})()

    monkeypatch.setattr(collector, "collect", lambda run_id: list(env.articles))
    monkeypatch.setattr(db, "create_run", lambda *a: None)
    monkeypatch.setattr(db, "finish_run", lambda run_id, **kw: env.finished.append(kw))
    monkeypatch.setattr(db, "save_articles", lambda articles: None)
    monkeypatch.setattr(db, "save_evaluations", lambda evaluations: None)
    monkeypatch.setattr(db, "was_recently_sent", lambda url_hash: False)
    monkeypatch.setattr(db, "update_article_tier", lambda *a: None)
    monkeypatch.setattr(db, "get_all_tag_weights", lambda: {})
    monkeypatch.setattr(dedup, "resolve_cross_batch_duplicates", lambda evaluations, by_id: evaluations)
    monkeypatch.setattr(run_pipeline.briefing, "render_notification_email", lambda *a: ("제목", "<html>"))

    def fake_send(subject, html):
        env.emails.append(subject)
        return True

    monkeypatch.setattr(emailer, "send_email", fake_send)
    return env


def test_all_batches_failing_fails_the_run_without_email(pipeline_env, monkeypatch):
    monkeypatch.setattr(scorer, "evaluate", lambda candidates: [])

    assert run_pipeline.main() == 1

    [finished] = pipeline_env.finished
    assert finished["status"] == "failed"
    assert finished["reviewed_n"] == 2
    assert finished["selected_n"] == 0
    assert "2" in finished["error_message"]
    assert pipeline_env.emails == []


def test_partial_batch_failure_still_completes(pipeline_env, monkeypatch):
    monkeypatch.setattr(scorer, "evaluate", lambda candidates: [_evaluation(candidates[0])])

    assert run_pipeline.main() == 0

    [finished] = pipeline_env.finished
    assert finished["status"] == "done"
    assert finished["selected_n"] == 1
    assert len(pipeline_env.emails) == 1


def test_no_candidates_is_not_a_scoring_failure(pipeline_env, monkeypatch):
    # A quiet news day: nothing to evaluate, so an empty result is correct.
    pipeline_env.articles.clear()
    monkeypatch.setattr(scorer, "evaluate", lambda candidates: [])

    assert run_pipeline.main() == 0

    [finished] = pipeline_env.finished
    assert finished["status"] == "done"
    assert len(pipeline_env.emails) == 1
