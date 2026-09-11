from __future__ import annotations

from shared.models import Evaluation


def _base_kwargs(**overrides):
    kwargs = dict(
        article_id="x", strategic_relevance=20, stp_4p_relevance=15,
        practical_applicability=10, market_impact=5, recency=5, credibility=2,
        tags=["뷰티"], summary="", interpretation="", application="",
    )
    kwargs.update(overrides)
    return kwargs


def test_base_score_sums_all_six_criteria():
    ev = Evaluation(**_base_kwargs())
    assert ev.base_score == 20 + 15 + 10 + 5 + 5 + 2


def test_bonus_score_caps_four_p_at_fifteen():
    ev = Evaluation(**_base_kwargs(
        product_specific=True, price_specific=True,
        place_specific=True, promotion_specific=True,  # 4 x 5 = 20, should cap at 15
    ))
    assert ev.bonus_score == 15


def test_bonus_score_includes_title_and_stp():
    ev = Evaluation(**_base_kwargs(title_has_strategy_phrase=True, stp_specific=True))
    assert ev.bonus_score == 15 + 10


def test_final_score_is_capped_at_100():
    ev = Evaluation(**_base_kwargs(
        strategic_relevance=30, stp_4p_relevance=25, practical_applicability=20,
        market_impact=10, recency=10, credibility=5,  # base = 100
        title_has_strategy_phrase=True, stp_specific=True, product_specific=True,
    ))
    assert ev.base_score == 100
    assert ev.final_score == 100  # not 130


def test_final_score_includes_weight_adjustment():
    ev = Evaluation(**_base_kwargs(weight_adjustment=-5))
    assert ev.final_score == ev.base_score - 5
