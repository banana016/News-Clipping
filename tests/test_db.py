"""Batch-isolation logic for the Kakao summary target (shared/db.py).

articles_with_good_feedback is the pure core of get_batch_articles_for_kakao:
given one batch's article ids and the feedback rows for (only) those ids, it
decides which articles the batch's Kakao summary should include. It never
sees another batch's articles at all - that's what makes cross-batch leakage
structurally impossible rather than just filtered out - and it takes no
"already generated / copied / sent" input, so there is nothing in its
signature that could make the result depend on that history.

Only articles whose latest feedback is explicitly '도움됨' (good) survive -
unrated and '별로예요' (bad) articles are both excluded, so the Kakao summary
only ever contains articles the user actually liked.

This mirrors the scenario from the bug report: a Monday batch (A) and a
Wednesday batch (B), where Monday's 도움됨 articles must never appear in
Wednesday's summary, and regenerating Monday's summary later must still
return exactly Monday's own articles.
"""
from __future__ import annotations

from shared.db import articles_with_good_feedback


def _ids(n: int, prefix: str) -> list[str]:
    return [f"{prefix}-{i}" for i in range(n)]


def test_batch_a_only_the_3_good_survive() -> None:
    batch_a = _ids(30, "a")
    ratings = {batch_a[0]: "good", batch_a[1]: "good", batch_a[2]: "good",
               batch_a[3]: "bad", batch_a[4]: "bad"}
    kept = articles_with_good_feedback(batch_a, ratings)
    assert len(kept) == 3
    assert batch_a[3] not in kept and batch_a[4] not in kept
    assert batch_a[0] in kept and batch_a[2] in kept  # good survives
    assert batch_a[10] not in kept  # unrated (neutral) is excluded


def test_batch_b_is_independent_of_batch_a() -> None:
    """Batch B's query only ever sees batch B's ids - batch A's 'good'
    articles have no way to leak in because they are never in the id list
    B's filter is called with."""
    batch_a = _ids(30, "a")
    batch_b = _ids(30, "b")

    # Monday: 3 good, 2 bad, rest unrated.
    ratings_a = {batch_a[0]: "good", batch_a[1]: "good", batch_a[2]: "good",
                 batch_a[3]: "bad", batch_a[4]: "bad"}
    kept_a = articles_with_good_feedback(batch_a, ratings_a)
    assert len(kept_a) == 3

    # Wednesday: 2 good, 4 bad, rest unrated. Feedback lookup is scoped to
    # batch B's ids only (as get_batch_articles_for_kakao does), so batch
    # A's ratings are never even consulted.
    ratings_b = {batch_b[0]: "good", batch_b[1]: "good",
                 batch_b[2]: "bad", batch_b[3]: "bad", batch_b[4]: "bad", batch_b[5]: "bad"}
    kept_b = articles_with_good_feedback(batch_b, ratings_b)

    assert len(kept_b) == 2
    for aid in kept_a:
        assert aid not in kept_b  # batch A's ids can't appear in batch B's result at all
    for aid in batch_a:
        assert aid not in kept_b


def test_regenerating_batch_a_after_batch_b_exists_is_unchanged() -> None:
    """Batch A's own filter call doesn't take batch B's existence as input
    at all, so nothing about creating/summarizing B can change A's result."""
    batch_a = _ids(30, "a")
    ratings_a = {batch_a[0]: "good", batch_a[1]: "good", batch_a[2]: "good",
                 batch_a[3]: "bad", batch_a[4]: "bad"}

    first = articles_with_good_feedback(batch_a, ratings_a)
    # ... batch B gets created and summarized in between, in the real flow ...
    second = articles_with_good_feedback(batch_a, ratings_a)

    assert first == second
    assert len(second) == 3


def test_no_ratings_at_all_excludes_every_article() -> None:
    batch = _ids(30, "x")
    assert articles_with_good_feedback(batch, {}) == []


def test_all_bad_excludes_everything() -> None:
    batch = _ids(5, "x")
    ratings = {aid: "bad" for aid in batch}
    assert articles_with_good_feedback(batch, ratings) == []


def test_all_good_keeps_everything() -> None:
    batch = _ids(5, "x")
    ratings = {aid: "good" for aid in batch}
    assert articles_with_good_feedback(batch, ratings) == batch


def test_function_signature_has_no_sent_or_copied_concept() -> None:
    """Documents the constraint explicitly: the filter only ever takes
    (article_ids, latest_ratings) - there is no parameter through which
    "already copied" or "already sent" history could influence the result,
    so the copy/paste button and the copy-vs-not-copy state described in the
    bug report structurally cannot change which articles are included."""
    import inspect
    params = list(inspect.signature(articles_with_good_feedback).parameters)
    assert params == ["article_ids", "latest_ratings"]
