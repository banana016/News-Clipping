"""
Step 2-3 of the pipeline: collect raw articles from NAVER API HUB and
normalize them into Article objects.

Docs (Phase 1 spec section 4):
  GET https://naverapihub.apigw.ntruss.com/search/v1/news
  headers: X-NCP-APIGW-API-KEY-ID, X-NCP-APIGW-API-KEY
  params:  query, display, start, sort=date, format=json
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone

import requests

from shared.config import settings
from shared.keywords import SEARCH_QUERIES
from shared.models import Article

logger = logging.getLogger(__name__)

NAVER_ENDPOINT = "https://naverapihub.apigw.ntruss.com/search/v1/news"
DISPLAY_PER_QUERY = 30
MAX_RETRIES = 3

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return _TAG_RE.sub("", text).replace("&quot;", '"').replace("&amp;", "&")


def _parse_pubdate(pubdate: str) -> datetime:
    # NAVER returns RFC 822, e.g. "Wed, 11 Sep 2026 07:00:00 +0900"
    return datetime.strptime(pubdate, "%a, %d %b %Y %H:%M:%S %z")


def _request_with_retry(params: dict) -> dict | None:
    headers = {
        "X-NCP-APIGW-API-KEY-ID": settings.naver_client_id or "",
        "X-NCP-APIGW-API-KEY": settings.naver_client_secret or "",
    }
    delay = 2.0
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(NAVER_ENDPOINT, headers=headers, params=params, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            logger.warning("NAVER API HUB %s -> %s: %s", params.get("query"), resp.status_code, resp.text[:200])
            if resp.status_code < 500 and resp.status_code != 429:
                return None  # client error, retrying won't help
        except requests.RequestException as exc:
            logger.warning("NAVER API HUB request failed (attempt %d/%d): %s", attempt, MAX_RETRIES, exc)
        if attempt < MAX_RETRIES:
            time.sleep(delay)
            delay *= 2
    return None


def search_one(query: str, run_id: str, since: datetime) -> list[Article]:
    """One keyword query -> normalized Articles published after `since`."""
    data = _request_with_retry({
        "query": query,
        "display": DISPLAY_PER_QUERY,
        "start": 1,
        "sort": "date",
        "format": "json",
    })
    if not data:
        return []

    articles: list[Article] = []
    for item in data.get("items", []):
        try:
            published_at = _parse_pubdate(item["pubDate"])
        except (KeyError, ValueError):
            continue
        if published_at < since:
            continue
        articles.append(Article(
            title=_strip_html(item.get("title", "")),
            source=item.get("originallink") or item.get("link", ""),
            url=item.get("originallink") or item.get("link", ""),
            published_at=published_at,
            run_id=run_id,
            description=_strip_html(item.get("description", "")),
        ))
    return articles


def collect(run_id: str, hours: int = 24) -> list[Article]:
    """Run every configured keyword query and merge + dedupe by URL hash."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    seen_hashes: set[str] = set()
    merged: list[Article] = []

    for query in SEARCH_QUERIES:
        for article in search_one(query, run_id, since):
            if article.url_hash in seen_hashes:  # type: ignore[attr-defined]
                continue
            seen_hashes.add(article.url_hash)  # type: ignore[attr-defined]
            merged.append(article)

    logger.info("collected %d unique articles across %d queries", len(merged), len(SEARCH_QUERIES))
    return merged
