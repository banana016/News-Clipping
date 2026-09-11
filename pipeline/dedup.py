"""
Step 5 (first pass) of the pipeline: drop near-exact duplicate titles
(syndicated wire copy) before anything reaches Claude.

This is deliberately conservative — it only merges articles whose titles
are near-identical strings. Softer "same real-world issue, different
angle" duplicates (e.g. three outlets covering the same rebrand with
different headlines) are NOT resolved here; that needs actual reading
comprehension, so it's left to Claude during scoring (Evaluation.is_duplicate
/ duplicate_of), then enforced in selector.py.
"""
from __future__ import annotations

from difflib import SequenceMatcher

from shared.models import Article

NEAR_EXACT_TITLE_THRESHOLD = 0.92


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
