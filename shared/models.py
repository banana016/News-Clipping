"""
Shared data structures used across the pipeline and the web app.

Kept as plain dataclasses (not a DB ORM) so the pipeline can run entirely
without a database (unit tests, DRY_RUN) and shared/db.py is the only place
that knows about Supabase's row shape.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

Tier = Literal["collected", "reviewed", "selected", "deleted"]
Rating = Literal["good", "bad"]

# Canonical tag vocabulary (spec section 11) — evaluations must only use these.
VALID_TAGS = {
    "마케팅전략", "브랜드전략", "시장세분화", "표적시장", "포지셔닝",
    "제품전략", "가격전략", "유통전략", "프로모션전략", "고객경험",
    "소비자행동", "경쟁전략", "해외진출", "이커머스", "뷰티", "AI마케팅",
}


def normalize_url(url: str) -> str:
    """Strip tracking params/fragments so the same article isn't re-sent
    under a cosmetically different URL."""
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def url_hash(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()


def normalize_title(title: str) -> str:
    """Collapse whitespace/punctuation for cheap near-duplicate comparison."""
    t = re.sub(r"[\s\W_]+", "", title)
    return t.lower()


@dataclass
class Article:
    """A single collected news item, before or after evaluation."""

    title: str
    source: str
    url: str
    published_at: datetime
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str | None = None
    description: str = ""  # short snippet from NAVER API HUB, not full article text
    tier: Tier = "collected"

    def __post_init__(self) -> None:
        self.url_hash = url_hash(self.url)  # type: ignore[attr-defined]
        self.normalized_title = normalize_title(self.title)  # type: ignore[attr-defined]


@dataclass
class Evaluation:
    """Claude's assessment of one Article, plus the deterministic bonus math."""

    article_id: str
    # base 100-point rubric (spec section 9)
    strategic_relevance: int  # 0-30
    stp_4p_relevance: int  # 0-25
    practical_applicability: int  # 0-20
    market_impact: int  # 0-10
    recency: int  # 0-10
    credibility: int  # 0-5

    tags: list[str]
    summary: str  # 핵심 내용 — facts only
    interpretation: str  # 전략 해석 — Claude's reading, kept separate from summary
    application: str  # 실무 적용 아이디어
    insight_quote: str = ""  # short catchy one-line takeaway, used atop the Kakao message block

    is_ad: bool = False
    is_duplicate: bool = False
    duplicate_of: str | None = None
    reject_reason: str | None = None

    # bonus flags, computed/judged separately from the base rubric
    title_has_strategy_phrase: bool = False  # rule-based, computed in Python
    stp_specific: bool = False  # Claude-judged
    product_specific: bool = False
    price_specific: bool = False
    place_specific: bool = False
    promotion_specific: bool = False

    weight_adjustment: float = 0.0  # filled in by weights.py from tag_weights

    @property
    def base_score(self) -> int:
        return (
            self.strategic_relevance
            + self.stp_4p_relevance
            + self.practical_applicability
            + self.market_impact
            + self.recency
            + self.credibility
        )

    @property
    def bonus_score(self) -> int:
        title_bonus = 15 if self.title_has_strategy_phrase else 0
        stp_bonus = 10 if self.stp_specific else 0
        four_p_hits = sum([
            self.product_specific, self.price_specific,
            self.place_specific, self.promotion_specific,
        ])
        four_p_bonus = min(four_p_hits * 5, 15)
        return title_bonus + stp_bonus + four_p_bonus

    @property
    def final_score(self) -> int:
        raw = self.base_score + self.bonus_score + self.weight_adjustment
        return max(0, min(100, round(raw)))


@dataclass
class Feedback:
    article_id: str
    rating: Rating
    rated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class TagWeight:
    tag: str
    good_count: int = 0
    total_count: int = 0
    weight_adjustment: float = 0.0
