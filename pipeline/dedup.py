"""
Step 5 (first pass) of the pipeline: drop near-exact duplicate titles
(syndicated wire copy) before anything reaches Claude.

This is deliberately conservative — it only merges articles whose titles
are near-identical strings. Softer "same real-world issue, different
angle" duplicates (e.g. three outlets covering the same rebrand with
different headlines) are NOT resolved here; that needs actual reading
comprehension, so it's left to Claude during scoring (Evaluation.is_duplicate
/ duplicate_of) and to resolve_cross_batch_duplicates below, then enforced
in selector.py.
"""
from __future__ import annotations

import json
import logging
from difflib import SequenceMatcher

import anthropic

from shared.config import settings
from shared.models import Article, Evaluation

logger = logging.getLogger(__name__)

NEAR_EXACT_TITLE_THRESHOLD = 0.92

# How many of the top-scoring (non-duplicate) candidates to re-check for
# duplicates against EACH OTHER (see resolve_cross_batch_duplicates). Needs
# real headroom above max_select: removing duplicates from the pool backfills
# from lower-ranked candidates that never got compared against anything, so
# the pool has to comfortably outsize the final selection.
CROSS_DEDUP_POOL_MARGIN = 20

CROSS_DEDUP_SYSTEM_PROMPT = """당신은 뉴스 큐레이션 파이프라인의 중복 판별 보조입니다.
아래 기사 목록은 각각 별도 배치에서 채점되어, 같은 실제 이슈를 다루는 기사끼리도
서로를 보지 못한 채 통과된 상태입니다. 지금 전체를 한 번에 보고, 같은 실제
사건/발표를 다루는 기사들을 묶어주세요.

판단 기준:
  - 같은 회사의 같은 발표/이벤트를 다루면 구체적 수치나 강조점이 다르게
    보도되었어도 같은 이슈로 묶으세요 (예: 같은 기자간담회에서 나온 여러
    목표치를 각기 다른 매체가 다른 숫자 위주로 보도한 경우).
  - 같은 회사라도 명백히 다른 사건/발표를 다루면 묶지 마세요.
  - 그룹마다 가장 구체적이고 정보가 많은 기사 1건을 keep_id로 고르세요.
  - 중복이 없으면 duplicate_groups를 빈 배열로 반환하세요."""

CROSS_DEDUP_SCHEMA = {
    "type": "object",
    "properties": {
        "duplicate_groups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "keep_id": {"type": "string"},
                    "duplicate_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["keep_id", "duplicate_ids"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["duplicate_groups"],
    "additionalProperties": False,
}


def _title_similarity(a: Article, b: Article) -> float:
    return SequenceMatcher(None, a.normalized_title, b.normalized_title).ratio()  # type: ignore[attr-defined]


def drop_near_exact_duplicates(articles: list[Article]) -> list[Article]:
    """Cluster by near-identical title; keep the longest description in
    each cluster (a cheap proxy for "more detail") as the representative."""
    kept: list[Article] = []
    for article in articles:
        match = next((k for k in kept if _title_similarity(k, article) >= NEAR_EXACT_TITLE_THRESHOLD), None)
        if match is None:
            kept.append(article)
        elif len(article.description) > len(match.description):
            kept[kept.index(match)] = article  # swap in the more detailed copy
    return kept


def resolve_cross_batch_duplicates(evaluations: list[Evaluation],
                                    articles_by_id: dict[str, Article]) -> list[Evaluation]:
    """Claude's in-batch duplicate check (scorer.py) only ever sees one
    12-article batch at a time, so the same real-world story reported by
    several outlets can land in different batches and pass through as
    several separate "selected" articles (spotted in production: three
    differently-worded Amorepacific stories about the same expansion
    announcement all got selected). This does one extra pass over just the
    top-scoring candidates, so Claude can compare them against each other.

    Never raises - on any failure the evaluations are returned unchanged,
    same error policy as scorer.evaluate()."""
    pool_size = settings.max_select + CROSS_DEDUP_POOL_MARGIN
    pool = sorted(
        (e for e in evaluations if not e.is_duplicate),
        key=lambda e: e.final_score, reverse=True,
    )[:pool_size]
    if len(pool) < 2:
        return evaluations

    items = [
        {"id": e.article_id, "title": articles_by_id[e.article_id].title, "summary": e.summary}
        for e in pool if e.article_id in articles_by_id
    ]
    if len(items) < 2:
        return evaluations

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=4000,
            output_config={
                "effort": settings.claude_effort,
                "format": {"type": "json_schema", "schema": CROSS_DEDUP_SCHEMA},
            },
            system=[{"type": "text", "text": CROSS_DEDUP_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": json.dumps(items, ensure_ascii=False, indent=2)}],
        )
        text = next(b.text for b in response.content if b.type == "text")
        groups = json.loads(text)["duplicate_groups"]
    except Exception:
        logger.exception("cross-batch duplicate resolution failed, skipping")
        return evaluations

    by_id = {e.article_id: e for e in evaluations}
    pool_ids = {e.article_id for e in pool}
    for group in groups:
        keep_id = group["keep_id"]
        for dup_id in group["duplicate_ids"]:
            if dup_id == keep_id or dup_id not in pool_ids:
                continue
            ev = by_id.get(dup_id)
            if ev is None:
                continue
            ev.is_duplicate = True
            ev.duplicate_of = keep_id
            ev.reject_reason = f"중복 (기사 {keep_id}와 동일 이슈, 더 구체적인 쪽만 선정)"

    return evaluations
