"""Re-evaluate runs whose scoring failed outright (e.g. an exhausted API credit
balance), in place, so their existing email links show the recovered briefing.

articles doesn't store NAVER's description, so it's looked up again: by
searching the article's title, then from the page itself, then title only.

    python -m scripts.rescore_run <run_id> [<run_id> ...]          # list only
    python -m scripts.rescore_run <run_id> [<run_id> ...] --apply  # spends credit

Pass several runs oldest first: an article selected by one isn't selected again
by the next. No email is sent. Nothing is written for a run if under
MIN_COVERAGE of its articles got evaluated.
"""
from __future__ import annotations

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from pipeline import collector, dedup, scorer, selector, weights
from shared import db
from shared.models import Article, url_hash

logger = logging.getLogger("rescore_run")

MIN_COVERAGE = 0.9
PAGE_DESCRIPTION_MAX_CHARS = 500  # about a NAVER snippet's cost, not the whole page
LOOKUP_WORKERS = 5


class CannotRescore(Exception):
    pass


def lookup_description(title: str, url: str) -> tuple[str, str]:
    """Returns (description, where it came from: 'naver' / 'page' / 'none')."""
    target = url_hash(url)
    data = collector._request_with_retry({
        "query": title[:60], "display": 10, "start": 1, "sort": "sim", "format": "json",
    })
    for item in (data or {}).get("items", []):
        if url_hash(item.get("originallink") or item.get("link", "")) == target:
            return collector._strip_html(item.get("description", "")), "naver"
    fetched = collector.fetch_article_by_url(url)
    if fetched and fetched.description:
        return fetched.description[:PAGE_DESCRIPTION_MAX_CHARS], "page"
    return "", "none"


def _to_article(row: dict, description: str) -> Article:
    return Article(
        id=row["id"], run_id=row["run_id"], title=row["title"], source=row["source"], url=row["url"],
        published_at=datetime.fromisoformat(row["published_at"]), description=description, tier=row["tier"],
    )


def check_rescorable(run: dict | None, rows: list[dict]) -> None:
    if run is None:
        raise CannotRescore("no such run")
    if run["selected_n"]:
        raise CannotRescore(f"already has {run['selected_n']} selected articles")
    if not rows:
        raise CannotRescore("no reviewed articles")
    if db.count_evaluations([r["id"] for r in rows]):
        raise CannotRescore("already has evaluations")


def _count_existing_ratings(evaluations: list) -> None:
    """Ratings given while an article had no evaluation counted toward no tag,
    since it had none. Now that it has tags, they count like any other."""
    ids = [e.article_id for e in evaluations]
    ratings: dict[str, str] = {}
    for start in range(0, len(ids), 100):
        ratings.update(db.latest_rating_by_article(ids[start:start + 100]))
    tag_weights = db.get_all_tag_weights()
    touched: set[str] = set()
    for ev in evaluations:
        if ev.article_id in ratings:
            weights.apply_rating_change(tag_weights, ev.tags, None, ratings[ev.article_id])
            touched.update(ev.tags)
    for tag in touched:
        db.upsert_tag_weight(tag_weights[tag])


def rescore(run_id: str, already_selected: set[str]) -> int:
    """Returns how many articles were selected. Adds them to already_selected."""
    rows = db.get_articles_for_rescore(run_id)
    check_rescorable(db.get_run(run_id), rows)
    rows = [r for r in rows if r["url_hash"] not in already_selected]

    with ThreadPoolExecutor(max_workers=LOOKUP_WORKERS) as pool:
        lookups = list(pool.map(lambda r: lookup_description(r["title"], r["url"]), rows))
    sources = [source for _, source in lookups]
    logger.info("%s: descriptions for %d articles: naver=%d page=%d none=%d", run_id, len(rows),
                sources.count("naver"), sources.count("page"), sources.count("none"))
    articles = [_to_article(r, description) for r, (description, _) in zip(rows, lookups)]

    evaluations = scorer.evaluate(articles)
    if len(evaluations) < len(articles) * MIN_COVERAGE:
        raise CannotRescore(f"only {len(evaluations)} of {len(articles)} evaluated - nothing written")

    evaluations = weights.apply_weights(evaluations, db.get_all_tag_weights())
    evaluations = dedup.resolve_cross_batch_duplicates(evaluations, {a.id: a for a in articles})
    result = selector.select(evaluations)

    # Evaluations first: a failure here leaves the run as it was, ready to retry.
    db.save_evaluations(evaluations)
    for ev in result.selected:
        db.update_article_tier(ev.article_id, "selected")
    db.mark_run_recovered(run_id, len(result.selected))
    _count_existing_ratings(evaluations)

    by_id = {a.id: a for a in articles}
    already_selected.update(by_id[e.article_id].url_hash for e in result.selected)
    return len(result.selected)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_ids", nargs="+")
    parser.add_argument("--apply", action="store_true", help="call Claude and save (default: list only)")
    args = parser.parse_args()

    runs = [db.get_run(run_id) for run_id in args.run_ids]
    if not args.apply:
        for run_id, run in zip(args.run_ids, runs):
            rows = db.get_articles_for_rescore(run_id)
            try:
                check_rescorable(run, rows)
                print(f"{run['run_date']} {run_id}: {len(rows)} articles would be evaluated")
            except CannotRescore as exc:
                print(f"{run_id}: skip - {exc}")
        return 0

    started = [run["started_at"] for run in runs if run]
    already_selected = db.selected_url_hashes_since(min(started)) if started else set()
    failed = False
    for run_id in args.run_ids:
        try:
            logger.info("%s: selected %d", run_id, rescore(run_id, already_selected))
        except CannotRescore as exc:
            logger.error("%s: %s", run_id, exc)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
