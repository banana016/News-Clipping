"""
The always-on half of the system (Vercel). Three endpoints:

  GET  /api/briefing?token=...   -> today's briefing data (magic-link gated)
  POST /api/feedback             -> record 도움됨/별로예요, update tag_weights
  POST /api/kakao-send           -> send every currently-liked, not-yet-sent
                                     article as Kakao text message(s)

Static page: web/public/index.html (adapted from the approved mockup) reads
`token` from its own URL and calls these.
"""
from __future__ import annotations

import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from pipeline import briefing
from shared import db
from shared.kakao_client import (
    KakaoAuthError, KakaoSendError, refresh_access_token, send_liked_articles,
)
from shared.magic_link import InvalidToken, verify_token
from shared.models import Evaluation
from pipeline import weights as weights_module

app = FastAPI(title="Brand Strategy Briefing API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"])


def _require_token(token: str | None) -> dict:
    if not token:
        raise HTTPException(status_code=401, detail="missing token")
    try:
        return verify_token(token)
    except InvalidToken as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.get("/api/briefing")
def get_briefing(token: str | None = None):
    payload = _require_token(token)
    data = db.get_briefing_for_date(payload["run_date"])
    if data["run"] is None:
        raise HTTPException(status_code=404, detail="no briefing for this date")
    return data


class FeedbackBody(BaseModel):
    token: str
    article_id: str
    rating: str  # "good" | "bad"


@app.post("/api/feedback")
def post_feedback(body: FeedbackBody):
    _require_token(body.token)
    if body.rating not in ("good", "bad"):
        raise HTTPException(status_code=400, detail="rating must be 'good' or 'bad'")

    db.record_feedback(body.article_id, body.rating)

    tags = db.get_article_tags(body.article_id)
    all_weights = db.get_all_tag_weights()
    weights_module.update_weights_with_feedback(all_weights, tags, body.rating)
    for tag in tags:
        db.upsert_tag_weight(all_weights[tag])

    return {"ok": True}


class KakaoSendBody(BaseModel):
    token: str


@app.post("/api/kakao-send")
def post_kakao_send(body: KakaoSendBody):
    _require_token(body.token)

    liked_rows = db.get_liked_articles_for_kakao()
    if not liked_rows:
        return {"ok": True, "sent_count": 0, "message": "도움됨으로 표시된 새 기사가 없습니다."}

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

    intro = f"도움됨 표시하신 기사 {len(payloads)}건입니다."
    try:
        sent_count = send_liked_articles(access_token, intro, payloads)
        db.record_kakao_send([r["id"] for r in liked_rows], "success")
        return {"ok": True, "sent_count": sent_count}
    except KakaoSendError as exc:
        db.record_kakao_send([r["id"] for r in liked_rows], "failed", str(exc))
        raise HTTPException(status_code=502, detail=f"카카오톡 발송 실패: {exc}") from exc
