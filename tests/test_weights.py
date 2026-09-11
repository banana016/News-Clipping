from __future__ import annotations

from pipeline.weights import apply_weights, compute_adjustment, update_weights_with_feedback
from shared.models import Evaluation, TagWeight


def test_no_adjustment_below_minimum_sample_size():
    # Only 3 ratings, all "good" — should still be 0 (min sample is 5).
    w = TagWeight(tag="뷰티", good_count=3, total_count=3)
    assert compute_adjustment(w) == 0.0


def test_full_positive_ratio_hits_max_adjustment():
    w = TagWeight(tag="뷰티", good_count=10, total_count=10)
    assert compute_adjustment(w) == 5.0  # WEIGHT_MAX_ADJUSTMENT default


def test_full_negative_ratio_hits_min_adjustment():
    w = TagWeight(tag="가격전략", good_count=0, total_count=10)
    assert compute_adjustment(w) == -5.0


def test_neutral_ratio_is_zero():
    w = TagWeight(tag="유통전략", good_count=5, total_count=10)
    assert compute_adjustment(w) == 0.0


def test_apply_weights_averages_across_tags():
    ev = Evaluation(
        article_id="x", strategic_relevance=10, stp_4p_relevance=10,
        practical_applicability=10, market_impact=5, recency=5, credibility=2,
        tags=["뷰티", "가격전략"], summary="", interpretation="", application="",
    )
    weights_by_tag = {
        "뷰티": TagWeight(tag="뷰티", good_count=10, total_count=10, weight_adjustment=5.0),
        "가격전략": TagWeight(tag="가격전략", good_count=0, total_count=10, weight_adjustment=-5.0),
    }
    apply_weights([ev], weights_by_tag)
    assert ev.weight_adjustment == 0.0  # (+5 + -5) / 2


def test_update_weights_with_feedback_increments_counts():
    weights_by_tag: dict[str, TagWeight] = {}
    update_weights_with_feedback(weights_by_tag, ["뷰티"], "good")
    update_weights_with_feedback(weights_by_tag, ["뷰티"], "bad")
    w = weights_by_tag["뷰티"]
    assert w.total_count == 2
    assert w.good_count == 1
