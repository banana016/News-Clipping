"""
Magic-link auth: no login form, no third-party auth provider. A signed,
expiring token in the URL is enough for a single-user personal tool
(Phase 1/3 decision — "본인만 아는 고유 링크").

Token shape: base64url(payload_json) + "." + hex(hmac_sha256(payload_json))
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from shared.config import settings


class InvalidToken(Exception):
    pass


def _secret() -> bytes:
    if not settings.magic_link_secret:
        raise RuntimeError("MAGIC_LINK_SECRET is not set")
    return settings.magic_link_secret.encode("utf-8")


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def issue_token(run_id: str) -> str:
    """run_id: the specific clipping run (batch) this link points to — not a
    calendar date. A date can have more than one run (manual retry, a
    workflow_dispatch re-run after a failure), so the link has to pin the
    exact batch or a retry would silently swap which batch's articles /
    feedback / Kakao summary the link resolves to."""
    payload = {"run_id": run_id, "exp": int(time.time()) + settings.magic_link_ttl_days * 86400}
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(_secret(), payload_bytes, hashlib.sha256).hexdigest()
    return f"{_b64encode(payload_bytes)}.{signature}"


def verify_token(token: str) -> dict:
    """Returns the payload dict, or raises InvalidToken."""
    try:
        payload_b64, signature = token.split(".", 1)
        payload_bytes = _b64decode(payload_b64)
    except (ValueError, Exception) as exc:
        raise InvalidToken("malformed token") from exc

    expected = hmac.new(_secret(), payload_bytes, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise InvalidToken("signature mismatch")

    payload = json.loads(payload_bytes)
    if payload.get("exp", 0) < time.time():
        raise InvalidToken("token expired")
    return payload


def briefing_url(run_id: str) -> str:
    return f"{settings.web_base_url}/briefing?token={issue_token(run_id)}"
