"""
The feedback learning loop (Phase 1 decision: reflected automatically in
the next run's scoring, not just shown as a dashboard).

Safety rails confirmed with the user in Phase 3:
  - a tag needs at least WEIGHT_MIN_SAMPLES ratings before it's allowed to
    move the score at all (protects against 1-2 clicks swinging a tag)
  - the adjustment is capped at +/- WEIGHT_MAX_ADJUSTMENT points

good_ratio 0.5 (neutral) -> adjustment 0. 1.0 -> +max. 0.0 -> -max.
Linear in between.
"""
from __future__ import annotations

from shared.config import settings
from shared.models import Evaluation, TagWeight


def compute_adjustment(weight: TagWeight) -> float:
    if weight.total_count < settings.weight_min_samples:
        return 0.0
    good_ratio = weight.good_count / weight.total_count
    return round((good_ratio - 0.5) * 2 * settings.weight_max_adjustment, 2)


def recompute_all(weights: list[TagWeight]) -> list[TagWeight]:
    for w in weights:
        w.weight_adjustment = compute_adjustment(w)
    return weights


def apply_weights(evaluations: list[Evaluation], weights_by_tag: dict[str, TagWeight]) -> list[Evaluation]:
    """Average the relevant tags' adjustments onto each evaluation's score.

    Averaging (rather than summing) keeps an article with three tags from
    getting 3x the adjustment of one with a single tag.
    """
    for ev in evaluations:
        relevant = [weights_by_tag[t].weight_adjustment for t in ev.tags if t in weights_by_tag]
        ev.weight_adjustment = round(sum(relevant) / len(relevant), 2) if relevant else 0.0
    return evaluations


def apply_rating_change(weights_by_tag: dict[str, TagWeight], tags: list[str],
                         previous: str | None, new: str | None) -> None:
    """Called once per feedback event (web app POST /api/feedback). previous
    and new are 'good', 'bad', or None (unrated). Counts the change rather
    than the click, so each article counts once toward its tags however many
    times it's re-rated or cancelled."""
    for tag in tags:
        w = weights_by_tag.setdefault(tag, TagWeight(tag=tag))
        w.total_count = max(0, w.total_count + (new is not None) - (previous is not None))
        w.good_count = max(0, w.good_count + (new == "good") - (previous == "good"))
        w.weight_adjustment = compute_adjustment(w)
