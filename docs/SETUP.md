# 최초 설정 절차

순서대로 진행하세요. 이미 Vercel·Supabase 계정이 있다고 하셨으니 3, 6단계는
새 프로젝트만 만들면 됩니다.

## 1. 저장소 받기

```bash
git clone https://github.com/banana016/News-Clipping.git
cd News-Clipping
python -m venv .venv && source .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env
```

## 2. NAVER API HUB 키

이미 발급받은 Client ID/Secret을 `.env`의 `NAVER_API_HUB_CLIENT_ID` /
`NAVER_API_HUB_CLIENT_SECRET`에 채우세요.

## 3. Anthropic API 키

콘솔에서 발급 후 `.env`의 `ANTHROPIC_API_KEY`에 채우세요. 기본 모델은
`claude-opus-5`입니다 — 비용을 낮추고 싶으면 `.env`의 `CLAUDE_MODEL`을
`claude-sonnet-5`나 `claude-haiku-4-5`로 바꾸면 됩니다 (코드 수정 불필요).

## 4. Supabase 프로젝트

1. 새 Supabase 프로젝트 생성
2. SQL Editor에서 `sql/schema.sql` 전체 실행
3. Project Settings → API에서 `Project URL`과 `service_role` 키를 복사해
   `.env`의 `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY`에 채우기
   (⚠️ `anon` 키가 아니라 `service_role` 키입니다 — 이 프로젝트는 브라우저에서
   Supabase에 직접 접속하지 않고 항상 백엔드를 거칩니다)

## 5. 매직링크 시크릿

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
출력값을 `.env`의 `MAGIC_LINK_SECRET`에 채우세요. (Vercel과 GitHub Actions에도
**같은 값**을 넣어야 서로 발급/검증이 맞습니다.)

## 6. Kakao Developers 앱

1. [Kakao Developers](https://developers.kakao.com)에서 애플리케이션 생성
2. 카카오 로그인 활성화, 동의항목에서 `카카오톡 메시지 전송(talk_message)` 활성화
3. Redirect URI에 `.env`의 `KAKAO_REDIRECT_URI`와 동일한 주소 등록
4. REST API 키를 `KAKAO_REST_API_KEY`에, 앱 설정의 Client Secret을
   `KAKAO_CLIENT_SECRET`에 채우기
5. 토큰 암호화 키 생성 후 `KAKAO_TOKEN_ENCRYPTION_KEY`에 채우기:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
6. **최초 1회만** 수동 인증 실행 (spec: "최초 카카오 인증은 별도의 설정 절차"):
   ```bash
   python -m scripts.kakao_auth_setup
   ```
   안내에 따라 브라우저에서 로그인·승인하고 코드를 붙여넣으면 토큰이 Supabase에
   암호화되어 저장됩니다. 이후로는 파이프라인/웹앱이 자동으로 갱신합니다.

## 7. Gmail 발신 설정

1. Google 계정 → 보안 → 2단계 인증 켜기 (앱 비밀번호는 2단계 인증이 켜져 있어야
   발급됩니다)
2. 앱 비밀번호 생성 → `.env`의 `GMAIL_APP_PASSWORD`에 채우기
3. `GMAIL_ADDRESS`(보내는 계정)와 `BRIEFING_RECIPIENT_EMAIL`(받는 계정, 본인
   메일 주소) 채우기

## 8. Vercel 배포

1. Vercel에서 이 저장소를 새 프로젝트로 import (Framework Preset: Other)
2. Project Settings → Environment Variables에 아래를 등록:
   `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `MAGIC_LINK_SECRET`,
   `MAGIC_LINK_TTL_DAYS`, `KAKAO_REST_API_KEY`, `KAKAO_CLIENT_SECRET`,
   `KAKAO_TOKEN_ENCRYPTION_KEY`, `WEB_BASE_URL`(배포된 주소 그대로)
3. 배포 후 `.env`와 GitHub Actions Secrets의 `WEB_BASE_URL`도 이 주소로 맞추기
4. ⚠️ **미검증 항목**: `vercel.json`은 `@vercel/python`이 FastAPI(ASGI) 앱을
   인식하는 표준 구성으로 작성했지만, `web/api/index.py`가 저장소 루트의
   `pipeline`/`shared`를 import하는 부분은 Vercel의 Python 런타임이 리포지토리
   루트를 함수 번들에 포함하는지에 따라 배포 후 추가 조정이 필요할 수 있습니다.
   첫 배포 후 `/api/briefing` 호출이 `ModuleNotFoundError`를 내면 이 부분부터
   확인하세요.

## 9. GitHub Actions Secrets

저장소 Settings → Secrets and variables → Actions에 다음을 등록:
`NAVER_API_HUB_CLIENT_ID`, `NAVER_API_HUB_CLIENT_SECRET`, `ANTHROPIC_API_KEY`,
`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `GMAIL_ADDRESS`,
`GMAIL_APP_PASSWORD`, `BRIEFING_RECIPIENT_EMAIL`, `MAGIC_LINK_SECRET`.

Variables(선택, 없으면 기본값 사용)로 `CLAUDE_MODEL`, `WEB_BASE_URL`도
등록해두면 편합니다.

## 10. 동작 확인

```bash
pytest -q                                    # 단위테스트 27개
DRY_RUN=true python -m pipeline.run_pipeline  # 실제 키로 1회 전체 실행 (발송만 생략)
```

Actions 탭 → `Marketing Briefing Pipeline` → `Run workflow`로 수동 실행도
가능합니다 (`dry_run` 입력을 `true`로 주면 발송 없이 점검만 됩니다).
