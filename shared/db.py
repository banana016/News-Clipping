"""
Thin Supabase wrapper — the only module that knows the DB row shape
(see sql/schema.sql). Pipeline and web/api/* both import this instead of
talking to Supabase directly, so the row shape can change in one place.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, TypeVar

from supabase import Client, create_client

from shared.config import settings
from shared.kakao_client import decrypt_token, encrypt_token
from shared.models import Article, Evaluation, TagWeight

logger = logging.getLogger(__name__)

T = TypeVar("T")

MAX_RETRIES = 3


@lru_cache(maxsize=1)
def get_client() -> Client:
    if not settings.supabase_url or not settings.supabase_service_key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set")
    return create_client(settings.supabase_url, settings.supabase_service_key)


def _run(query: Any) -> T:
    """Execute a Supabase query builder, retrying on transient failures
    (e.g. the 504 Gateway Timeout that took down a whole run in
    production - a single flaky call shouldn't kill a multi-minute
    pipeline)."""
    delay = 2.0
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return query.execute()
        except Exception as exc:
            if attempt == MAX_RETRIES:
                raise
            logger.warning("Supabase call failed (attempt %d/%d): %s", attempt, MAX_RETRIES, exc)
            time.sleep(delay)
            delay *= 2


# --- runs ---------------------------------------------------------------

def create_run(run_id: str, run_date: str) -> None:
    _run(get_client().table("runs").insert({
        "id": run_id, "run_date": run_date, "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }))


def finish_run(run_id: str, *, status: str, collected_n: int, reviewed_n: int,
                selected_n: int, error_message: str | None = None) -> None:
    _run(get_client().table("runs").update({
        "status": status, "collected_n": collected_n, "reviewed_n": reviewed_n,
        "selected_n": selected_n, "error_message": error_message,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", run_id))


# --- resend guard (spec: 최근 7일 이내 동일 기사 재발송 방지) -------------

def was_recently_sent(url_hash: str) -> bool:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=settings.resend_guard_days)).isoformat()
    res = _run(get_client().table("articles")
               .select("id")
               .eq("url_hash", url_hash)
               .eq("tier", "selected")
               .gte("created_at", cutoff)
               .limit(1))
    return len(res.data) > 0


# --- articles / evaluations ----------------------------------------------

def save_articles(articles: list[Article]) -> None:
    if not articles:
        return
    rows = [{
        "id": a.id, "run_id": a.run_id, "title": a.title, "source": a.source,
        "published_at": a.published_at.isoformat(), "url": a.url,
        "url_hash": a.url_hash, "tier": a.tier,  # type: ignore[attr-defined]
    } for a in articles]
    _run(get_client().table("articles").insert(rows))


def update_article_tier(article_id: str, tier: str) -> None:
    _run(get_client().table("articles").update({"tier": tier}).eq("id", article_id))


def save_evaluations(evaluations: list[Evaluation]) -> None:
    if not evaluations:
        return
    rows = [{
        "article_id": e.article_id, "base_score": e.base_score, "bonus_score": e.bonus_score,
        "final_score": e.final_score, "tags": e.tags, "is_duplicate": e.is_duplicate,
        "duplicate_of": e.duplicate_of, "is_ad": e.is_ad, "summary": e.summary,
        "interpretation": e.interpretation, "application": e.application,
        "insight_quote": e.insight_quote, "reject_reason": e.reject_reason,
    } for e in evaluations]
    _run(get_client().table("evaluations").insert(rows))


def get_run_date(run_id: str) -> str | None:
    """Just the 'YYYY-MM-DD' this batch was analyzed/emailed on, for display
    (e.g. the Kakao summary's intro line) - a lighter query than
    get_briefing_for_run when the article lists aren't needed."""
    res = _run(get_client().table("runs").select("run_date").eq("id", run_id).limit(1))
    return res.data[0]["run_date"] if res.data else None


def get_briefing_for_run(run_id: str) -> dict:
    """What the web app shows for one specific clipping run (batch) — selected
    + reviewed tiers. Looked up by run_id, never by calendar date: a date can
    have more than one run (manual retry, workflow_dispatch re-run after a
    failure), so a date-keyed lookup could silently resolve to the wrong
    batch."""
    run = _run(get_client().table("runs").select("*").eq("id", run_id).limit(1))
    if not run.data:
        return {"run": None, "selected": [], "reviewed": []}
    run_row = run.data[0]

    articles = _run(get_client().table("articles")
                    .select("*, evaluations!article_id(*)")
                    .eq("run_id", run_id))

    selected = [a for a in articles.data if a.get("tier") == "selected"]
    reviewed = [a for a in articles.data if a.get("tier") == "reviewed"]
    return {"run": run_row, "selected": selected, "reviewed": reviewed}


# --- feedback ---------------------------------------------------------------

def get_article_tags(article_id: str) -> list[str]:
    res = _run(get_client().table("evaluations").select("tags").eq("article_id", article_id).limit(1))
    return res.data[0]["tags"] if res.data else []


def get_article_run_id(article_id: str) -> str | None:
    """Which batch (run) an article belongs to — used to reject a feedback
    request whose article_id doesn't actually belong to the batch its magic
    link (token) was issued for."""
    res = _run(get_client().table("articles").select("run_id").eq("id", article_id).limit(1))
    return res.data[0]["run_id"] if res.data else None


def record_feedback(article_id: str, rating: str) -> None:
    _run(get_client().table("feedback").insert({
        "article_id": article_id, "rating": rating,
        "rated_at": datetime.now(timezone.utc).isoformat(),
    }))


# --- tag weights (the learning loop) -----------------------------------

def get_all_tag_weights() -> dict[str, TagWeight]:
    res = _run(get_client().table("tag_weights").select("*"))
    return {row["tag"]: TagWeight(tag=row["tag"], good_count=row["good_count"],
                                   total_count=row["total_count"],
                                   weight_adjustment=row["weight_adjustment"])
            for row in res.data}


def upsert_tag_weight(w: TagWeight) -> None:
    _run(get_client().table("tag_weights").upsert({
        "tag": w.tag, "good_count": w.good_count, "total_count": w.total_count,
        "weight_adjustment": w.weight_adjustment,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }))


# --- kakao ---------------------------------------------------------------

def get_kakao_tokens() -> tuple[str, str] | None:
    """Returns (access_token, refresh_token), decrypted."""
    res = _run(get_client().table("kakao_tokens").select("*").eq("id", 1).limit(1))
    if not res.data:
        return None
    row = res.data[0]
    return decrypt_token(row["access_token"]), decrypt_token(row["refresh_token"])


def save_kakao_tokens(access_token: str, refresh_token: str, expires_at: str) -> None:
    _run(get_client().table("kakao_tokens").upsert({
        "id": 1, "access_token": encrypt_token(access_token),
        "refresh_token": encrypt_token(refresh_token), "expires_at": expires_at,
    }))


def already_kakao_sent_ids() -> set[str]:
    res = _run(get_client().table("kakao_sends").select("article_ids").eq("status", "success"))
    sent: set[str] = set()
    for row in res.data:
        sent.update(row.get("article_ids") or [])
    return sent


def _articles_with_evaluations(article_ids: list[str]) -> list[dict]:
    if not article_ids:
        return []
    res = _run(get_client().table("articles")
               .select("*, evaluations!article_id(*)")
               .in_("id", article_ids))
    return res.data


def get_batch_article_ids(batch_id: str) -> list[str]:
    """The articles actually selected (emailed) in one specific clipping run
    - a batch's Kakao summary is scoped to exactly these, never anything from
    another run."""
    res = _run(get_client().table("articles").select("id")
               .eq("run_id", batch_id).eq("tier", "selected"))
    return [row["id"] for row in res.data]


def latest_rating_by_article(article_ids: list[str]) -> dict[str, str]:
    """Most recent feedback rating ('good'/'bad') per article id, restricted
    to the given ids. feedback is an append-only log (record_feedback always
    inserts), so a later 'bad' must override an earlier 'good' - checking
    for "any 'good' row ever" would treat an article as liked forever, even
    after the user changed their mind. An id with no feedback row at all is
    simply absent from the result (= unrated / neutral)."""
    if not article_ids:
        return {}
    res = _run(get_client().table("feedback").select("article_id, rating")
               .in_("article_id", article_ids).order("rated_at"))
    latest: dict[str, str] = {}
    for row in res.data:
        latest[row["article_id"]] = row["rating"]  # later rows overwrite earlier ones
    return latest


def articles_excluding_bad_feedback(article_ids: list[str], latest_ratings: dict[str, str]) -> list[str]:
    """Pure filter: keep every id whose latest rating isn't 'bad' - 'good'
    and unrated (no entry in latest_ratings) both pass through untouched.
    Split out from get_batch_articles_for_kakao so the batch-isolation rule
    is unit-testable without a database."""
    return [aid for aid in article_ids if latest_ratings.get(aid) != "bad"]


def get_batch_articles_for_kakao(batch_id: str) -> list[dict]:
    """Kakao summary target for exactly one clipping run: articles selected
    in *this* batch whose latest feedback isn't '별로예요' (bad). '도움됨'
    and unrated articles are both included.

    Deliberately does not consult kakao_sends / any "already generated,
    copied, or sent" history - regenerating this batch's summary any number
    of times must always return the same batch-scoped result, and a
    previous batch's articles must never leak in regardless of whether that
    batch's summary was ever viewed or copied."""
    article_ids = get_batch_article_ids(batch_id)
    if not article_ids:
        return []
    latest = latest_rating_by_article(article_ids)
    keep_ids = articles_excluding_bad_feedback(article_ids, latest)
    return _articles_with_evaluations(keep_ids)


def record_kakao_send(article_ids: list[str], status: str, error_message: str | None = None) -> None:
    _run(get_client().table("kakao_sends").insert({
        "sent_at": datetime.now(timezone.utc).isoformat(), "article_ids": article_ids,
        "status": status, "error_message": error_message,
    }))
