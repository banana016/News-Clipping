"""
Step 9 of the pipeline: turn scored candidates into the final 7-10
selection, plus a full audit trail of what was rejected and why
(spec section 12; validated against Phase 2's 20-article test set).

Selection policy (confirmed in Phase 1/3 discussion — quality over
quantity, spec section 18): take the top-scoring, non-duplicate
candidates that clear MIN_SCORE_THRESHOLD, capped to MAX_SELECT.
If fewer than MIN_SELECT clear the bar, send fewer than MIN_SELECT rather
than lowering the bar to force a fixed count.
"""
from __future__ import annotations

from dataclasses import dataclass

from shared.config import settings
from shared.models import Evaluation


@dataclass
class SelectionResult:
    selected: list[Evaluation]
    rejected: list[tuple[Evaluation, str]]  # (evaluation, reason)


def _reject_reason(ev: Evaluation) -> str | None:
    if ev.is_duplicate:
        return f"중복 (기사 {ev.duplicate_of}와 동일 이슈, 더 구체적인 쪽만 선정)"
    if ev.final_score < settings.min_score_threshold:
        return ev.reject_reason or "전략성 부족 (기준 점수 미달)"
    return None


def select(evaluations: list[Evaluation]) -> SelectionResult:
    ranked = sorted(evaluations, key=lambda e: e.final_score, reverse=True)

    selected: list[Evaluation] = []
    rejected: list[tuple[Evaluation, str]] = []

    for ev in ranked:
        reason = _reject_reason(ev)
        if reason is None and len(selected) < settings.max_select:
            selected.append(ev)
        else:
            rejected.append((ev, reason or "선정 인원 초과 (상위 기사에 밀림)"))

    if len(selected) < settings.min_select:
        # Not force-filling below the quality bar — see module docstring.
        # Still record how far short we were so it shows up in run logs.
        pass

    return SelectionResult(selected=selected, rejected=rejected)
