"""
One-time manual Kakao OAuth setup (spec: "최초 카카오 인증은 별도의 설정
절차로 구성"). Run this once locally, NOT from GitHub Actions.

Usage:
    python -m scripts.kakao_auth_setup

It prints an authorization URL — open it in a browser, log in, approve
"talk_message" scope, and Kakao will redirect to KAKAO_REDIRECT_URI with
a `?code=...` query param. Paste that code back into this script's prompt.
The resulting access/refresh tokens are saved (encrypted) to Supabase via
shared/db.py, so the pipeline and web app never need manual token handling
again — they auto-refresh from here on.
"""
from __future__ import annotations

import sys
from urllib.parse import urlencode

from shared import db
from shared.config import settings
from shared.kakao_client import KakaoAuthError, exchange_code_for_tokens

AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"


def main() -> int:
    if not (settings.kakao_rest_api_key and settings.kakao_redirect_uri):
        print("KAKAO_REST_API_KEY / KAKAO_REDIRECT_URI must be set in .env first.")
        return 1

    query = urlencode({
        "client_id": settings.kakao_rest_api_key,
        "redirect_uri": settings.kakao_redirect_uri,
        "response_type": "code",
        "scope": "talk_message",
    })
    print("1. 아래 주소를 브라우저에서 열고 카카오 로그인 후 권한을 승인하세요:\n")
    print(f"   {AUTHORIZE_URL}?{query}\n")
    print("2. 리다이렉트된 주소의 ?code=... 부분을 복사해서 아래에 붙여넣으세요.\n")

    auth_code = input("code: ").strip()
    if not auth_code:
        print("code가 비어 있습니다.")
        return 1

    try:
        tokens = exchange_code_for_tokens(auth_code)
    except KakaoAuthError as exc:
        print(f"토큰 발급 실패: {exc}")
        return 1

    db.save_kakao_tokens(tokens.access_token, tokens.refresh_token, str(tokens.expires_at))
    print("\n완료되었습니다. Access/Refresh Token이 Supabase에 암호화되어 저장되었습니다.")
    print("이후로는 파이프라인/웹앱이 자동으로 토큰을 갱신합니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
