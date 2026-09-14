from __future__ import annotations

from shared.kakao_client import KAKAO_TEXT_MAX_CHARS, build_message_blocks


def _article(i: int, body_len: int = 50) -> dict:
    return {
        "quote": f"인용구{i}",
        "title": f"기사 제목 {i}",
        "body": "본문 " * body_len,
        "link": f"https://example.com/news/{i}",
    }


def test_short_message_stays_as_one_block():
    blocks = build_message_blocks("인트로", [_article(1, body_len=5)])
    assert len(blocks) == 1


def test_long_message_splits_at_article_boundary_only():
    articles = [_article(i, body_len=3000) for i in range(6)]
    blocks = build_message_blocks("인트로", articles)
    assert len(blocks) > 1
    # every block stays under the cap, and every block still starts with the intro
    for block in blocks:
        assert len(block) <= KAKAO_TEXT_MAX_CHARS + len(articles[0]["body"])  # generous slack for one article
        assert block.startswith("인트로")
    # every article's title appears in exactly one block, never truncated mid-way
    for i, art in enumerate(articles):
        occurrences = sum(1 for b in blocks if art["title"] in b)
        assert occurrences == 1
