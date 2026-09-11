from __future__ import annotations

from datetime import datetime, timezone

from pipeline.dedup import drop_near_exact_duplicates
from shared.models import Article


def make_article(title: str, description: str = "", url_suffix: str = "1") -> Article:
    return Article(
        title=title, source="테스트", url=f"https://example.com/news/{url_suffix}",
        published_at=datetime.now(timezone.utc), description=description,
    )


def test_near_identical_titles_are_merged_keeping_longer_description():
    a = make_article("OO뷰티, 저가 이미지 벗고 클린뷰티로 재포지셔닝", description="짧은 설명", url_suffix="1")
    b = make_article("OO뷰티, 저가 이미지 벗고 클린뷰티로 재포지셔닝", description="훨씬 더 길고 자세한 설명입니다 여기 추가 내용", url_suffix="2")
    result = drop_near_exact_duplicates([a, b])
    assert len(result) == 1
    assert result[0].description == b.description


def test_distinct_titles_are_kept_separate():
    a = make_article("OO뷰티, 클린뷰티로 재포지셔닝")
    b = make_article("A이커머스, 지방 소상공인 입점 프로그램 신설")
    result = drop_near_exact_duplicates([a, b])
    assert len(result) == 2
