# 마케팅·브랜드 전략 뉴스 브리핑

주 3회(월·수·금 07:00 KST) 마케팅/브랜드 전략 뉴스를 자동으로 수집·평가·선정해
이메일로 알리고, 웹앱에서 읽고 도움됨/별로예요로 평가하면 다음 회차 선정 기준에
자동 반영되며, 도움됨으로 표시한 기사만 모아 카카오톡으로 받아볼 수 있는 개인용
도구입니다.

기획 배경과 설계 근거는 아래 세 문서에 있습니다 (개발을 이어받거나 로직을 바꿀
때는 코드보다 이 문서들을 먼저 읽는 게 빠릅니다):

- [Phase 1 목업 & 카카오톡/이메일/웹앱 화면 설계](docs/PHASE1_MOCKUP.md)
- [Phase 2 테스트 리포트 (가상 기사 20건으로 선정 로직 검증)](docs/PHASE2_TEST_REPORT.md)
- [Phase 3 기술 설계 (아키텍처, DB 스키마, 비용)](docs/PHASE3_TECH_DESIGN.md)

## 구성

```
pipeline/    수집→평가→선정→발송 파이프라인 (GitHub Actions가 실행)
shared/      DB/설정/키워드/매직링크/카카오 클라이언트 — 파이프라인과 웹앱이 공유
web/         Vercel에 배포되는 상시 웹앱 (매직링크 페이지 + API 3개)
tests/       pytest — Phase 2 테스트 리포트의 20건을 fixture로 재사용하는 회귀 테스트 포함
sql/         Supabase에 한 번 적용하는 스키마
scripts/     최초 1회만 실행하는 수동 설정 스크립트 (카카오 OAuth)
docs/        SETUP.md(최초 설정), OPERATIONS.md(운영/장애 대응)
```

## 빠른 시작

```bash
python -m venv .venv && source .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # 값 채우기 — docs/SETUP.md 참고
pytest -q
```

전체 설정 절차(Supabase 스키마 적용, NAVER/Claude/Kakao 키 발급, 카카오 최초
인증, Vercel/GitHub Actions 환경변수 등록)는 `docs/SETUP.md`를 따라가세요.

## 로컬에서 파이프라인 1회 실행

```bash
DRY_RUN=true python -m pipeline.run_pipeline
```

`DRY_RUN=true`는 이메일/카카오 실제 발송만 건너뛰고 나머지(수집~DB 저장)는
그대로 실행합니다 — 즉 NAVER/Claude/Supabase 키는 실제 값이 필요합니다.

## 웹앱 로컬 실행

```bash
uvicorn web.api.index:app --reload
```
