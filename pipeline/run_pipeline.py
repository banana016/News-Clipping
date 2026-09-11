"""
Entry point run by GitHub Actions three times a week
(.github/workflows/briefing.yml). Orchestrates the 13-step flow from the
Phase 3 design doc. Safe to re-run manually (workflow_dispatch) — it
never assumes it's the only run of the day.
"""
from __future__ import annotations

import logging
import sys
import uuid
from zoneinfo import ZoneInfo
from datetime import datetime

from pipeline import briefing, collector, dedup, emailer, filters, scorer, selector, weights
from shared import db
from shared.config import settings
from shared.models import Article, Evaluation

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("run_pipeline")


def _today_kst() -> str:
    return datetime.now(ZoneInfo(settings.timezone)).strftime("%Y-%m-%d")


def main() -> int:
    run_id = str(uuid.uuid4())
    run_date = _today_kst()
    logger.info("=== run %s (%s) start dry_run=%s ===", run_id, run_date, settings.dry_run)

    db.create_run(run_id, run_date)

    # 2-3. collect + normalize
    try:
        collected = collector.collect(run_id)
    except Exception:
        logger.exception("collection failed")
        db.finish_run(run_id, status="failed", collected_n=0, reviewed_n=0, selected_n=0,
                       error_message="collection failed")
        return 1

    for a in collected:
        a.run_id = run_id
    db.save_articles(collected)

    # 4. 7-day resend guard
    not_recently_sent = [a for a in collected if not db.was_recently_sent(a.url_hash)]  # type: ignore[attr-defined]

    # 5. cheap near-exact dedup
    deduped = dedup.drop_near_exact_duplicates(not_recently_sent)

    # 6-7. ad heuristic (soft, informational only) + keyword prefilter
    candidates = filters.prefilter_candidates(deduped)
    for a in candidates:
        db.update_article_tier(a.id, "reviewed")

    # 8. Claude evaluation
    try:
        evaluations = scorer.evaluate(candidates)
    except Exception:
        logger.exception("scoring failed")
        db.finish_run(run_id, status="failed", collected_n=len(collected),
                       reviewed_n=len(candidates), selected_n=0, error_message="scoring failed")
        return 1

    # apply the learned per-tag weight adjustments (the feedback loop)
    tag_weights = db.get_all_tag_weights()
    evaluations = weights.apply_weights(evaluations, tag_weights)

    # 9. select final 7-10
    result = selector.select(evaluations)
    selected_ids = {e.article_id for e in result.selected}
    by_id: dict[str, Article] = {a.id: a for a in candidates}

    for article_id in selected_ids:
        db.update_article_tier(article_id, "selected")

    db.save_evaluations(evaluations)

    logger.info("collected=%d reviewed=%d selected=%d", len(collected), len(candidates), len(result.selected))
    for ev, reason in result.rejected:
        logger.info("rejected %s (%d점): %s", ev.article_id, ev.final_score, reason)

    # 10-12. build + send notification email (DRY_RUN skips the actual send)
    selected_pairs = [(by_id[e.article_id], e) for e in result.selected if e.article_id in by_id]
    subject, html = briefing.render_notification_email(
        run_date, len(collected), len(candidates), len(result.selected),
    )
    email_ok = emailer.send_email(subject, html)

    db.finish_run(
        run_id,
        status="done" if email_ok else "done_email_failed",
        collected_n=len(collected), reviewed_n=len(candidates), selected_n=len(result.selected),
        error_message=None if email_ok else "email send failed after retries",
    )
    logger.info("=== run %s done ===", run_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
