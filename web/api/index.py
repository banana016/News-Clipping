"""
The always-on half of the system (Vercel). Endpoints:

  GET  /api/briefing?token=...   -> this batch's briefing data (magic-link
                                     gated - the token pins one specific
                                     clipping run, not a calendar date)
  POST /api/feedback             -> record 도움됨/별로예요, update tag_weights
  POST /api/kakao-send           -> send this batch's not-yet-sent, liked
                                     (도움됨) articles as Kakao text message(s)
  GET  /api/liked-full-text      -> this batch's liked (도움됨) articles as
                                     one copy/paste-able text block
  POST /api/manual-article       -> fetch + evaluate one URL the user picked
                                     by hand and add it to this batch as a
                                     "selected" card, same shape as the other
                                     30
  POST /api/delete-article       -> hide one article from this batch (tier
                                     -> "deleted") - never a hard delete, so
                                     feedback/kakao_sends history stays intact

Every one of these is scoped to a single clipping run (batch): the token
carries the batch's run_id, and every query below filters by that run_id
first before looking at feedback status. A batch's Kakao summary must never
include another batch's articles, and regenerating it must never depend on
whether it (or a previous batch) was already viewed, copied, or sent.

Static page: web/public/index.html (adapted from the approved mockup) reads
`token` from its own URL and calls these.
"""
from __future__ import annotations

import logging
import time

import anthropic
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from pipeline import briefing, collector, scorer
from shared import db
from shared.config import settings
from shared.kakao_client import (
    KakaoAuthError, KakaoSendError, build_full_text, refresh_access_token, send_liked_articles,
)
from shared.magic_link import InvalidToken, verify_token
from shared.models import Evaluation, url_hash as compute_url_hash
from pipeline import weights as weights_module

logger = logging.getLogger(__name__)

app = FastAPI(title="Brand Strategy Briefing API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"])


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Starlette's default for an uncaught exception is a plain-text 500 body,
    # which breaks the frontend's response.json() parsing (it just throws
    # "not valid JSON" with no useful detail). Every endpoint here always
    # returns JSON instead, even when something we didn't anticipate blows up.
    logger.exception("unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": f"서버 오류가 발생했습니다: {exc}"})


def _require_token(token: str | None) -> dict:
    if not token:
        raise HTTPException(status_code=401, detail="missing token")
    try:
        payload = verify_token(token)
    except InvalidToken as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    if "run_id" not in payload:
        # Pre-migration links carried {"run_date": ...} instead of a batch
        # id - still cryptographically valid, but there's no run_id to scope
        # queries by. Treat as expired; they age out within magic_link_ttl_days.
        raise HTTPException(status_code=401, detail="outdated link format - use the latest email")
    return payload


@app.get("/api/briefing")
def get_briefing(token: str | None = None):
    payload = _require_token(token)
    data = db.get_briefing_for_run(payload["run_id"])
    if data["run"] is None:
        raise HTTPException(status_code=404, detail="no briefing for this run")
    return data


class FeedbackBody(BaseModel):
    token: str
    article_id: str
    rating: str  # "good" | "bad"


@app.post("/api/feedback")
def post_feedback(body: FeedbackBody):
    payload = _require_token(body.token)
    if body.rating not in ("good", "bad"):
        raise HTTPException(status_code=400, detail="rating must be 'good' or 'bad'")
    if db.get_article_run_id(body.article_id) != payload["run_id"]:
        raise HTTPException(status_code=404, detail="article does not belong to this batch")

    db.record_feedback(body.article_id, body.rating)

    tags = db.get_article_tags(body.article_id)
    all_weights = db.get_all_tag_weights()
    weights_module.update_weights_with_feedback(all_weights, tags, body.rating)
    for tag in tags:
        db.upsert_tag_weight(all_weights[tag])

    return {"ok": True}


class DeleteArticleBody(BaseModel):
    token: str
    article_id: str


@app.post("/api/delete-article")
def post_delete_article(body: DeleteArticleBody):
    payload = _require_token(body.token)
    if db.get_article_run_id(body.article_id) != payload["run_id"]:
        raise HTTPException(status_code=404, detail="article does not belong to this batch")

    db.update_article_tier(body.article_id, "deleted")
    return {"ok": True}


class KakaoSendBody(BaseModel):
    token: str


def _build_kakao_payloads(liked_rows: list[dict]) -> list[dict]:
    payloads = []
    for row in liked_rows:
        evaluation_row = row.get("evaluations") or {}
        ev = Evaluation(
            article_id=row["id"], strategic_relevance=0, stp_4p_relevance=0,
            practical_applicability=0, market_impact=0, recency=0, credibility=0,
            tags=evaluation_row.get("tags", []), summary=evaluation_row.get("summary", ""),
            interpretation=evaluation_row.get("interpretation", ""), application="",
            insight_quote=evaluation_row.get("insight_quote", ""),
        )
        article_stub = type("A", (), {"title": row["title"], "url": row["url"]})()
        payloads.append(briefing.build_kakao_article_payload(ev, article_stub))
    return payloads


@app.get("/api/liked-full-text")
def get_liked_full_text(token: str | None = None):
    payload = _require_token(token)

    # Scoped to this one batch only - see get_batch_articles_for_kakao.
    # Always regenerable: never filtered by whether it (or any other batch)
    # was already viewed, copied, or sent.
    batch_rows = db.get_batch_articles_for_kakao(payload["run_id"])
    if not batch_rows:
        return {"ok": True, "count": 0, "text": "",
                "message": "이 회차에는 도움됨으로 표시된 기사가 없습니다."}

    payloads = _build_kakao_payloads(batch_rows)
    run_date = db.get_run_date(payload["run_id"]) or ""
    intro = f"{run_date[2:]} 마케팅 뉴스 클리핑"  # "2026-09-16" -> "26-09-16"
    return {"ok": True, "count": len(payloads), "text": build_full_text(intro, payloads)}


@app.post("/api/kakao-send")
def post_kakao_send(body: KakaoSendBody):
    payload = _require_token(body.token)

    batch_rows = db.get_batch_articles_for_kakao(payload["run_id"])
    already_sent = db.already_kakao_sent_ids()
    liked_rows = [row for row in batch_rows if row["id"] not in already_sent]
    if not liked_rows:
        return {"ok": True, "sent_count": 0, "message": "이 회차에는 새로 발송할 기사가 없습니다."}

    tokens = db.get_kakao_tokens()
    if tokens is None:
        raise HTTPException(status_code=500, detail="Kakao가 아직 연동되지 않았습니다. scripts/kakao_auth_setup.py를 먼저 실행하세요.")
    access_token, refresh_token = tokens

    try:
        refreshed = refresh_access_token(refresh_token)
        access_token = refreshed.access_token
        db.save_kakao_tokens(refreshed.access_token, refreshed.refresh_token,
                              str(time.time() + 21599))
    except KakaoAuthError:
        pass  # fall back to the existing access token; it may still be valid

    payloads = _build_kakao_payloads(liked_rows)
    intro = f"도움됨 표시하신 기사 {len(payloads)}건입니다."
    try:
        sent_count = send_liked_articles(access_token, intro, payloads)
        db.record_kakao_send([r["id"] for r in liked_rows], "success")
        return {"ok": True, "sent_count": sent_count}
    except KakaoSendError as exc:
        db.record_kakao_send([r["id"] for r in liked_rows], "failed", str(exc))
        raise HTTPException(status_code=502, detail=f"카카오톡 발송 실패: {exc}") from exc


class ManualArticleBody(BaseModel):
    token: str
    url: str


@app.post("/api/manual-article")
def post_manual_article(body: ManualArticleBody):
    payload = _require_token(body.token)
    run_id = payload["run_id"]

    url = body.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="올바른 URL이 아닙니다 (http/https로 시작해야 합니다).")

    existing = db.find_batch_article_by_url_hash(run_id, compute_url_hash(url))
    if existing is not None:
        return {"ok": True, "duplicate": True, "article": existing}

    article = collector.fetch_article_by_url(url)
    if article is None:
        raise HTTPException(status_code=502, detail="기사를 가져오지 못했습니다. URL을 확인하고 다시 시도해주세요.")

    if not settings.anthropic_api_key:
        raise HTTPException(status_code=500, detail="서버에 ANTHROPIC_API_KEY가 설정되어 있지 않습니다.")

    try:
        evaluation = scorer.evaluate_single(article)
    except anthropic.AuthenticationError as exc:
        logger.error("manual-article auth error: %s", exc)
        raise HTTPException(status_code=500, detail="Claude API 인증에 실패했습니다. ANTHROPIC_API_KEY를 확인해주세요.") from exc
    except anthropic.RateLimitError as exc:
        logger.error("manual-article rate limited: %s", exc)
        raise HTTPException(status_code=502, detail="Claude API 사용량 한도에 걸렸습니다. 잠시 후 다시 시도해주세요.") from exc
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
        logger.error("manual-article Claude API error: %s", exc)
        raise HTTPException(status_code=502, detail=f"Claude API 오류: {exc}") from exc
    except Exception as exc:
        logger.error("manual-article evaluation failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"기사 요약에 실패했습니다: {exc}") from exc

    tag_weights = db.get_all_tag_weights()
    [evaluation] = weights_module.apply_weights([evaluation], tag_weights)

    article.run_id = run_id
    article.tier = "selected"
    db.save_articles([article])
    db.save_evaluations([evaluation])

    return {"ok": True, "duplicate": False, "article": db.get_article_with_evaluation(article.id)}
