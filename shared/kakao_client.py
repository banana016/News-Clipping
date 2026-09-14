"""
Kakao Developers — "나에게 보내기" (send-to-self) client.

Sends the approved single-message format (quote / bold-styled title / body
/ link, one block per liked article, numbered ①②③...). Kakao's plain
`text` default template has a per-message length cap. Verified directly
against the real API (2026-09-14): single messages of 4384, 11000, and
15000 characters were all accepted, so KAKAO_TEXT_MAX_CHARS is set with
headroom above what a full 30-article selection (MAX_SELECT) produces in
practice, while still splitting **only at article boundaries** as a
safety net (spec section 14: "기사 중간에서 메시지가 잘리지 않도록") if it's
ever exceeded.

Token lifecycle:
  - First authorization is a one-time manual step (scripts/kakao_auth_setup.py)
  - After that, this module refreshes the access token automatically using
    the stored refresh token and persists the new pair via shared/db.py
  - Tokens are encrypted at rest with Fernet (KAKAO_TOKEN_ENCRYPTION_KEY)
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

import requests
from cryptography.fernet import Fernet

from shared.config import settings

logger = logging.getLogger(__name__)

KAUTH_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
KAPI_SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
KAKAO_TEXT_MAX_CHARS = 12000  # verified safe against the real API - see module docstring


def _circled_digits() -> list[str]:
    """① .. ㊿ — circled digits 1-50, spanning the two Unicode blocks that
    define them (Enclosed Alphanumerics for 1-20, then CJK-compatibility
    Enclosed Letters/Months for 21-50). 50 comfortably covers MAX_SELECT
    (30) with room to grow before ever falling back to plain "(N)"."""
    return (
        [chr(0x2460 + i) for i in range(20)]  # ① .. ⑳ (1-20)
        + [chr(0x3251 + i) for i in range(15)]  # ㉑ .. ㉟ (21-35)
        + [chr(0x32B1 + i) for i in range(15)]  # ㊱ .. ㊿ (36-50)
    )


CIRCLED_DIGITS = _circled_digits()


class KakaoAuthError(Exception):
    pass


class KakaoSendError(Exception):
    pass


def _fernet() -> Fernet:
    if not settings.kakao_token_encryption_key:
        raise RuntimeError("KAKAO_TOKEN_ENCRYPTION_KEY is not set")
    return Fernet(settings.kakao_token_encryption_key.encode("utf-8"))


def encrypt_token(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_token(cipher: str) -> str:
    return _fernet().decrypt(cipher.encode("utf-8")).decode("utf-8")


@dataclass
class KakaoTokens:
    access_token: str
    refresh_token: str
    expires_at: float  # unix timestamp


def exchange_code_for_tokens(auth_code: str) -> KakaoTokens:
    """One-time step run from scripts/kakao_auth_setup.py after the user
    approves the OAuth consent screen in a browser."""
    resp = requests.post(KAUTH_TOKEN_URL, data={
        "grant_type": "authorization_code",
        "client_id": settings.kakao_rest_api_key,
        "client_secret": settings.kakao_client_secret,
        "redirect_uri": settings.kakao_redirect_uri,
        "code": auth_code,
    }, timeout=10)
    if resp.status_code != 200:
        raise KakaoAuthError(f"code exchange failed: {resp.status_code} {resp.text}")
    data = resp.json()
    return KakaoTokens(
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        expires_at=time.time() + data.get("expires_in", 21599),
    )


def refresh_access_token(refresh_token: str) -> KakaoTokens:
    resp = requests.post(KAUTH_TOKEN_URL, data={
        "grant_type": "refresh_token",
        "client_id": settings.kakao_rest_api_key,
        "client_secret": settings.kakao_client_secret,
        "refresh_token": refresh_token,
    }, timeout=10)
    if resp.status_code != 200:
        raise KakaoAuthError(f"token refresh failed: {resp.status_code} {resp.text}")
    data = resp.json()
    return KakaoTokens(
        access_token=data["access_token"],
        # Kakao only rotates the refresh token sometimes — keep the old one if absent.
        refresh_token=data.get("refresh_token", refresh_token),
        expires_at=time.time() + data.get("expires_in", 21599),
    )


def _render_article(i: int, art: dict) -> str:
    num = CIRCLED_DIGITS[i] if i < len(CIRCLED_DIGITS) else f"({i + 1})"
    return f"{num} '{art['quote']}'\n{art['title']}\n\n{art['body']}\n\n{art['link']}"


def build_full_text(intro: str, liked_articles: list[dict]) -> str:
    """One combined block, never split - for the "전문 보기" copy/paste flow,
    where the user pastes into KakaoTalk themselves, so none of the
    default-template length/rendering limits that build_message_blocks
    works around apply."""
    parts = [intro] + [_render_article(i, art) for i, art in enumerate(liked_articles)]
    return "\n\n".join(parts)


def build_message_blocks(intro: str, liked_articles: list[dict]) -> list[str]:
    """liked_articles: [{quote, title, body, link}, ...] in send order.
    Returns one or more message strings, split only between articles.
    """
    blocks: list[str] = []
    current = intro
    for i, art in enumerate(liked_articles):
        piece = _render_article(i, art)
        candidate = f"{current}\n\n{piece}"
        if len(candidate) > KAKAO_TEXT_MAX_CHARS and current != intro:
            blocks.append(current)
            current = f"{intro}\n\n{piece}"
        else:
            current = candidate
    blocks.append(current)
    return blocks


def send_text_message(access_token: str, text: str) -> None:
    template_object = {
        "object_type": "text",
        "text": text,
        "link": {
            "web_url": settings.web_base_url,
            "mobile_web_url": settings.web_base_url,
        },
    }
    resp = requests.post(
        KAPI_SEND_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        data={"template_object": json.dumps(template_object, ensure_ascii=False)},
        timeout=10,
    )
    if resp.status_code != 200:
        raise KakaoSendError(f"send failed: {resp.status_code} {resp.text}")


def send_liked_articles(access_token: str, intro: str, liked_articles: list[dict]) -> int:
    """Returns the number of Kakao messages actually sent."""
    blocks = build_message_blocks(intro, liked_articles)
    for block in blocks:
        send_text_message(access_token, block)
    return len(blocks)
