from __future__ import annotations

import json
from pathlib import Path

import pytest

from shared.models import Evaluation

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "phase2_test_articles.json"


def _to_evaluation(row: dict) -> Evaluation:
    return Evaluation(
        article_id=row["id"],
        strategic_relevance=row["strategic_relevance"],
        stp_4p_relevance=row["stp_4p_relevance"],
        practical_applicability=row["practical_applicability"],
        market_impact=row["market_impact"],
        recency=row["recency"],
        credibility=row["credibility"],
        tags=row["tags"],
        summary="(테스트용 가상 데이터)",
        interpretation="(테스트용 가상 데이터)",
        application="(테스트용 가상 데이터)",
        insight_quote="(테스트용 가상 데이터)",
        is_ad=row["is_ad"],
        is_duplicate=row["is_duplicate"],
        duplicate_of=row["duplicate_of"],
        reject_reason=row["reject_reason"],
        title_has_strategy_phrase=row["title_has_strategy_phrase"],
        stp_specific=row["stp_specific"],
        product_specific=row["product_specific"],
        price_specific=row["price_specific"],
        place_specific=row["place_specific"],
        promotion_specific=row["promotion_specific"],
    )


@pytest.fixture()
def phase2_evaluations() -> list[Evaluation]:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return [_to_evaluation(row) for row in data["evaluations"]]
