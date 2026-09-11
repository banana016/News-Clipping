"""
Step 6-7 of the pipeline: cheap, deterministic filtering that runs BEFORE
any Claude call — cuts the collected pool down to a candidate pool worth
paying for.

Two independent filters:
  - keyword_prefilter: is this even about marketing/brand strategy at all?
  - ad_heuristic_flag: soft "looks like a press release" signal, passed to
    Claude as a hint — it does NOT hard-exclude on its own, because a
    genuinely strategic article can still contain promotional language.
    Final ad/PR judgment is Claude's `is_ad` field (spec section 9-10:
    "광고성 기사와 기업 홍보자료를 무조건 배제하지는 않지만 객관적 전략
    정보가 부족하면 낮게 평가").
"""
from __future__ import annotations

import re

from shared.keywords import RELEVANCE_KEYWORDS
from shared.models import Article

_AD_PATTERNS = [
    r"\d{1,2}%\s*할인", r"사은품", r"기념\s*이벤트", r"경품", r"프로모션\s*진행",
    r"출시\s*기념", r"팝업\s*(스토어|이벤트)", r"한정판", r"증정",
    r"창립\s*\d+주년",
]
_AD_RE = re.compile("|".join(_AD_PATTERNS))


def keyword_prefilter(article: Article) -> bool:
    """True if the title or description hits at least one relevance keyword.

    This is intentionally permissive (OR over ~90 terms) — it exists only to
    drop obviously off-topic noise (finance results, weather, unrelated
    politics) before spending Claude tokens, not to do the real scoring.
    """
    haystack = f"{article.title} {article.description}"
    return any(kw in haystack for kw in RELEVANCE_KEYWORDS)


def ad_heuristic_flag(article: Article) -> bool:
    """Soft signal only — see module docstring."""
    return bool(_AD_RE.search(article.title) or _AD_RE.search(article.description))


def prefilter_candidates(articles: list[Article]) -> list[Article]:
    """Step 7: '전략 키워드 1차 스코어링 → 상위 후보만 다음 단계로'."""
    return [a for a in articles if keyword_prefilter(a)]
