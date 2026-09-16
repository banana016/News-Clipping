# 운영 가이드

## 정기 실행

`.github/workflows/briefing.yml`이 월·수·금 07:00 KST(cron `0 22 * * 0,2,4`,
UTC 기준)에 자동 실행됩니다. Actions 탭에서 수동 실행(`workflow_dispatch`)도
가능합니다.

## 실패했을 때

- **어디서 실패했는지**: GitHub Actions 실행 로그가 1차 정보원입니다.
  `runs` 테이블(Supabase)의 `status`/`error_message` 컬럼도 함께 확인하세요.
- **이메일 발송만 실패**: `runs.status = 'done_email_failed'`로 기록되고
  분석 결과는 정상 저장되어 있습니다. `runs` 테이블에서 실패한 실행의 `id`
  (run_id — 즉 그 회차의 batch_id)를 확인한 뒤, 그 값으로 매직링크를 수동
  발급해 확인할 수 있습니다. 링크는 run_id 단위로 발급되므로(같은 날짜에
  재시도로 여러 run이 생겨도 서로 섞이지 않습니다), 반드시 실패한 실행의
  정확한 `id`를 넣어야 합니다:
  ```bash
  python -c "from shared.magic_link import briefing_url; print(briefing_url('<runs.id>'))"
  ```
- **수집/평가 단계 실패**: `runs.status = 'failed'`. NAVER/Claude API 키 만료나
  요청 한도 초과가 가장 흔한 원인입니다. 콘솔에서 키 상태를 먼저 확인하세요.
- **카카오 발송 실패**: 웹앱에서 "전송 실패: ..." 메시지로 바로 표시됩니다.
  Refresh Token 자체가 만료된 경우(장기간 미사용 시 발생 가능) `scripts/kakao_auth_setup.py`를
  다시 실행해 재인증하세요.

## 태그 가중치가 이상하게 움직일 때

`tag_weights` 테이블에서 특정 태그의 `good_count`/`total_count`/`weight_adjustment`를
직접 확인·수정할 수 있습니다. 안전장치(최소 5건 누적, 최대 ±5점)는
`.env`의 `WEIGHT_MIN_SAMPLES`/`WEIGHT_MAX_ADJUSTMENT`로 조정합니다.

## 선정 기준을 조정하고 싶을 때

`.env`(로컬) 또는 GitHub Actions Variables의 아래 값을 바꾸면 코드 수정 없이
조정됩니다:

| 변수 | 기본값 | 의미 |
|---|---|---|
| `MIN_SELECT` | 7 | 최소 선정 건수 (기준 미달 시 더 적게 보낼 수 있음) |
| `MAX_SELECT` | 10 | 최대 선정 건수 |
| `MIN_SCORE_THRESHOLD` | 60 | 이 점수 미만은 선정하지 않음 |
| `RESEND_GUARD_DAYS` | 7 | 이 기간 내 이미 선정된 기사는 재선정하지 않음 |

## 재발급이 필요한 시크릿

- `MAGIC_LINK_SECRET` 교체 시 기존에 발송된 모든 링크가 즉시 무효화됩니다
  (유출이 의심될 때만 교체하세요).
- `KAKAO_TOKEN_ENCRYPTION_KEY` 교체 시 `kakao_tokens` 테이블의 기존 값을
  복호화할 수 없게 되므로, 교체 전에 반드시 `scripts/kakao_auth_setup.py`로
  새 키 기준으로 재저장하세요.

## 로그 보관

GitHub Actions 로그는 기본 90일 보관됩니다. 더 긴 이력이 필요하면 `runs`
테이블을 그대로 보관하면 됩니다 (별도 삭제 로직 없음).
