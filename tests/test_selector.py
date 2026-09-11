"""
Regression test against the Phase 2 test report — same 20 articles, same
expected outcome (7 selected, 13 rejected, in the same order).
"""
from __future__ import annotations

from pipeline.selector import select


def test_selects_exactly_the_seven_from_phase2(phase2_evaluations):
    result = select(phase2_evaluations)
    selected_ids = [e.article_id for e in result.selected]
    assert selected_ids == ["a1", "a4", "a2", "a5", "a3", "a6", "a7"]


def test_high_scoring_duplicate_is_still_rejected(phase2_evaluations):
    """r2 scores 83 (higher than several selected articles) but must be
    rejected anyway because it's a duplicate of a1 — dedup must win over
    raw score ranking (Phase 2 검증 1)."""
    result = select(phase2_evaluations)
    selected_ids = {e.article_id for e in result.selected}
    assert "r2" not in selected_ids

    rejected_ids = {e.article_id: reason for e, reason in result.rejected}
    assert "r2" in rejected_ids
    assert "중복" in rejected_ids["r2"]


def test_keyword_trap_does_not_clear_the_bar(phase2_evaluations):
    """r13 has '브랜드 전략' literally in the title (+15 bonus) but a base
    score of only 22 — final 37, nowhere near the selection bar. Confirms
    the title-keyword bonus alone can't buy a low-substance article a slot
    (Phase 2 검증 2)."""
    result = select(phase2_evaluations)
    selected_ids = {e.article_id for e in result.selected}
    assert "r13" not in selected_ids

    r13 = next(e for e in phase2_evaluations if e.article_id == "r13")
    assert r13.bonus_score == 15
    assert r13.final_score == 37


def test_rejected_count_matches_phase2(phase2_evaluations):
    result = select(phase2_evaluations)
    assert len(result.selected) == 7
    assert len(result.rejected) == 13
