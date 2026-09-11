"""
Thin Supabase wrapper — the only module that knows the DB row shape
(see sql/schema.sql). Pipeline and web/api/* both import this instead of
talking to Supabase directly, so the row shape can change in one place.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache

from supabase import Client, create_client

from shared.config import settings
from shared.kakao_client import decrypt_token, encrypt_token
from shared.models import Article, Evaluation, TagWeight


@lru_cache(maxsize=1)
def get_client() -> Client:
    if not settings.supabase_url or not settings.supabase_service_key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set")
    return create_client(settings.supabase_url, settings.supabase_service_key)


# --- runs ---------------------------------------------------------------

def create_run(run_id: str, run_date: str) -> None:
    get_client().table("runs").insert({
        "id": run_id, "run_date": run_date, "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }).execute()


def finish_run(run_id: str, *, status: str, collected_n: int, reviewed_n: int,
                selected_n: int, error_message: str | None = None) -> None:
    get_client().table("runs").update({
        "status": status, "collected_n": collected_n, "reviewed_n": reviewed_n,
        "selected_n": selected_n, "error_message": error_message,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", run_id).execute()


# --- resend guard (spec: 최근 7일 이내 동일 기사 재발송 방지) -------------

def was_recently_sent(url_hash: str) -> bool:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=settings.resend_guard_days)).isoformat()
    res = (get_client().table("articles")
           .select("id")
           .eq("url_hash", url_hash)
           .eq("tier", "selected")
           .gte("created_at", cutoff)
           .limit(1).execute())
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
    get_client().table("articles").insert(rows).execute()


def update_article_tier(article_id: str, tier: str) -> None:
    get_client().table("articles").update({"tier": tier}).eq("id", article_id).execute()


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
    get_client().table("evaluations").insert(rows).execute()


def get_briefing_for_date(run_date: str) -> dict:
    """What the web app shows for a given day — selected + reviewed tiers."""
    run = get_client().table("runs").select("*").eq("run_date", run_date).limit(1).execute()
    if not run.data:
        return {"run": None, "selected": [], "reviewed": []}
    run_row = run.data[0]

    articles = (get_client().table("articles")
                .select("*, evaluations(*)")
                .eq("run_id", run_row["id"]).execute())

    selected = [a for a in articles.data if a.get("tier") == "selected"]
    reviewed = [a for a in articles.data if a.get("tier") == "reviewed"]
    return {"run": run_row, "selected": selected, "reviewed": reviewed}


# --- feedback ---------------------------------------------------------------

def get_article_tags(article_id: str) -> list[str]:
    res = get_client().table("evaluations").select("tags").eq("article_id", article_id).limit(1).execute()
    return res.data[0]["tags"] if res.data else []


def record_feedback(article_id: str, rating: str) -> None:
    get_client().table("feedback").insert({
        "article_id": article_id, "rating": rating,
        "rated_at": datetime.now(timezone.utc).isoformat(),
    }).execute()


# --- tag weights (the learning loop) -----------------------------------

def get_all_tag_weights() -> dict[str, TagWeight]:
    res = get_client().table("tag_weights").select("*").execute()
    return {row["tag"]: TagWeight(tag=row["tag"], good_count=row["good_count"],
                                   total_count=row["total_count"],
                                   weight_adjustment=row["weight_adjustment"])
            for row in res.data}


def upsert_tag_weight(w: TagWeight) -> None:
    get_client().table("tag_weights").upsert({
        "tag": w.tag, "good_count": w.good_count, "total_count": w.total_count,
        "weight_adjustment": w.weight_adjustment,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).execute()


# --- kakao ---------------------------------------------------------------

def get_kakao_tokens() -> tuple[str, str] | None:
    """Returns (access_token, refresh_token), decrypted."""
    res = get_client().table("kakao_tokens").select("*").eq("id", 1).limit(1).execute()
    if not res.data:
        return None
    row = res.data[0]
    return decrypt_token(row["access_token"]), decrypt_token(row["refresh_token"])


def save_kakao_tokens(access_token: str, refresh_token: str, expires_at: str) -> None:
    get_client().table("kakao_tokens").upsert({
        "id": 1, "access_token": encrypt_token(access_token),
        "refresh_token": encrypt_token(refresh_token), "expires_at": expires_at,
    }).execute()


def already_kakao_sent_ids() -> set[str]:
    res = get_client().table("kakao_sends").select("article_ids").eq("status", "success").execute()
    sent: set[str] = set()
    for row in res.data:
        sent.update(row.get("article_ids") or [])
    return sent


def get_liked_articles_for_kakao() -> list[dict]:
    """Articles currently rated 'good' that haven't been Kakao-sent yet,
    joined with their evaluation content (quote/title/summary/link)."""
    already_sent = already_kakao_sent_ids()
    feedback = get_client().table("feedback").select("article_id, rating").eq("rating", "good").execute()
    liked_ids = [r["article_id"] for r in feedback.data if r["article_id"] not in already_sent]
    if not liked_ids:
        return []
    articles = (get_client().table("articles")
                .select("*, evaluations(*)")
                .in_("id", liked_ids).execute())
    return articles.data


def record_kakao_send(article_ids: list[str], status: str, error_message: str | None = None) -> None:
    get_client().table("kakao_sends").insert({
        "sent_at": datetime.now(timezone.utc).isoformat(), "article_ids": article_ids,
        "status": status, "error_message": error_message,
    }).execute()
