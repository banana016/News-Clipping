from __future__ import annotations

from datetime import datetime, timezone

from pipeline.filters import ad_heuristic_flag, keyword_prefilter
from shared.models import Article


def make_article(title: str, description: str = "") -> Article:
    return Article(title=title, source="테스트", url="https://example.com/news/1",
                    published_at=datetime.now(timezone.utc), description=description)


def test_relevant_article_passes_prefilter():
    a = make_article("OO뷰티, 저가 이미지 벗고 클린뷰티로 재포지셔닝",
                      description="표적시장을 2030 가치소비층으로 재설정했다")
    assert keyword_prefilter(a) is True


def test_irrelevant_article_fails_prefilter():
    a = make_article("택배 물류센터 화재, 일부 지역 배송 지연", description="소방당국이 진화 작업을 벌이고 있다")
    assert keyword_prefilter(a) is False


def test_ad_heuristic_flags_discount_event():
    a = make_article("OO브랜드, 여름 프로모션 20% 할인 행사 진행", description="사은품 증정 이벤트도 함께 진행한다")
    assert ad_heuristic_flag(a) is True


def test_ad_heuristic_does_not_flag_strategy_article():
    a = make_article("OO뷰티, 저가 이미지 벗고 클린뷰티로 재포지셔닝",
                      description="표적시장을 재설정하고 가격 전략을 조정했다")
    assert ad_heuristic_flag(a) is False
