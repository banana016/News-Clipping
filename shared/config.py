"""
Centralized environment/config loading.

Every credential and tunable knob lives here so the rest of the codebase
never reads os.environ directly. Values are read lazily (module import must
not fail just because .env hasn't been created yet, e.g. during `pytest
--collect-only`).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is a dev convenience, not a hard requirement
    pass


def _get(name: str, default: str | None = None) -> str | None:
    val = os.environ.get(name)
    return val if val else default


def _get_bool(name: str, default: bool = False) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _get_int(name: str, default: int) -> int:
    val = os.environ.get(name)
    return int(val) if val else default


@dataclass
class Settings:
    # --- run mode -----------------------------------------------------
    dry_run: bool = field(default_factory=lambda: _get_bool("DRY_RUN", False))
    timezone: str = field(default_factory=lambda: _get("TIMEZONE", "Asia/Seoul"))

    # --- NAVER API HUB --------------------------------------------------
    naver_client_id: str | None = field(default_factory=lambda: _get("NAVER_API_HUB_CLIENT_ID"))
    naver_client_secret: str | None = field(default_factory=lambda: _get("NAVER_API_HUB_CLIENT_SECRET"))

    # --- Claude -----------------------------------------------------
    anthropic_api_key: str | None = field(default_factory=lambda: _get("ANTHROPIC_API_KEY"))
    claude_model: str = field(default_factory=lambda: _get("CLAUDE_MODEL", "claude-opus-5"))
    claude_effort: str = field(default_factory=lambda: _get("CLAUDE_EFFORT", "medium"))

    # --- Supabase -----------------------------------------------------
    supabase_url: str | None = field(default_factory=lambda: _get("SUPABASE_URL"))
    supabase_service_key: str | None = field(default_factory=lambda: _get("SUPABASE_SERVICE_ROLE_KEY"))

    # --- Kakao -----------------------------------------------------
    kakao_rest_api_key: str | None = field(default_factory=lambda: _get("KAKAO_REST_API_KEY"))
    kakao_client_secret: str | None = field(default_factory=lambda: _get("KAKAO_CLIENT_SECRET"))
    kakao_redirect_uri: str | None = field(default_factory=lambda: _get("KAKAO_REDIRECT_URI"))
    kakao_token_encryption_key: str | None = field(default_factory=lambda: _get("KAKAO_TOKEN_ENCRYPTION_KEY"))

    # --- Email -----------------------------------------------------
    gmail_address: str | None = field(default_factory=lambda: _get("GMAIL_ADDRESS"))
    gmail_app_password: str | None = field(default_factory=lambda: _get("GMAIL_APP_PASSWORD"))
    briefing_recipient: str | None = field(default_factory=lambda: _get("BRIEFING_RECIPIENT_EMAIL"))

    # --- Web app / magic link -----------------------------------------
    web_base_url: str = field(default_factory=lambda: _get("WEB_BASE_URL", "http://localhost:3000"))
    magic_link_secret: str | None = field(default_factory=lambda: _get("MAGIC_LINK_SECRET"))
    magic_link_ttl_days: int = field(default_factory=lambda: _get_int("MAGIC_LINK_TTL_DAYS", 14))

    # --- Selection tuning -----------------------------------------------
    min_select: int = field(default_factory=lambda: _get_int("MIN_SELECT", 7))
    max_select: int = field(default_factory=lambda: _get_int("MAX_SELECT", 10))
    min_score_threshold: int = field(default_factory=lambda: _get_int("MIN_SCORE_THRESHOLD", 60))

    # --- Weight-adjustment safety rails ---------------------------------
    weight_min_samples: int = field(default_factory=lambda: _get_int("WEIGHT_MIN_SAMPLES", 5))
    weight_max_adjustment: int = field(default_factory=lambda: _get_int("WEIGHT_MAX_ADJUSTMENT", 5))

    # --- Re-send guard -----------------------------------------------
    resend_guard_days: int = field(default_factory=lambda: _get_int("RESEND_GUARD_DAYS", 7))


settings = Settings()
