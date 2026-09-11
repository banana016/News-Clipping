"""
Step 8 of the pipeline: Claude evaluates each candidate article against the
100-point rubric (spec section 9) and flags the bonus conditions (section 10).

Design notes:
  - Evaluated in batches (Claude sees several candidates from the same run
    together) so it can also flag duplicates it notices *within the batch*
    (Evaluation.is_duplicate / duplicate_of) — this is on top of, not
    instead of, the cheap pre-dedup in dedup.py.
  - The title-phrase bonus ('마케팅 전략'/'브랜드 전략'/'브랜딩 전략' in the
    title, +15) is rule-based and computed in Python, NOT judged by Claude —
    it's a literal string match, no judgment call involved.
  - Everything else Claude returns (base 6 criteria + stp/4p booleans +
    is_ad/is_duplicate + summary/interpretation/application) comes back as
    validated JSON via output_config.format, batch-by-batch.
"""
from __future__ import annotations

import json
import logging

import anthropic

from shared.config import settings
from shared.keywords import TAGS, TITLE_BONUS_PHRASES
from shared.models import Article, Evaluation

logger = logging.getLogger(__name__)

BATCH_SIZE = 12

SYSTEM_PROMPT = f"""당신은 마케팅·브랜드 전략 뉴스 큐레이션 에이전트의 평가자입니다.
사용자는 마케팅/브랜드 전략 수립, 소비재·뷰티·이커머스 브랜드 운영, 온라인 판매채널
운영, 소상공인 마케팅 콘텐츠 제작, 브랜드 컨설팅/창업강의를 하는 실무자입니다.

각 기사를 아래 6개 기준(100점 만점)으로 채점하세요.
① 전략적 관련성 (0-30): 마케팅/브랜드/브랜딩 전략을 직접 다루는가? '무엇을 했는지'가
   아니라 '왜 그런 선택을 했는지'를 설명하는가? 경쟁우위·차별화 방향이 보이는가?
② STP·4P 관련성 (0-25): 시장세분화/표적시장/포지셔닝, 또는 제품/가격/유통/프로모션
   전략 중 하나 이상을 구체적으로 다루는가?
③ 실무 활용 가능성 (0-20): 실제 브랜드·마케팅 업무에 적용 가능한가? 참고할 사례·수치·
   방법·결과가 있는가?
④ 시장 영향력 (0-10): 업계·경쟁사·소비자 행동에 미치는 영향이 큰가?
⑤ 최신성 (0-10): 최근 24시간 이내, 현재 시장 변화와 관련이 있는가?
⑥ 정보 신뢰성 (0-5): 신뢰할 수 있는 언론/조사기관/기업 공식 발표에 근거하는가?

중요 원칙 — 키워드가 있다는 이유만으로 점수를 주지 마세요:
  - '신제품을 출시했다'는 사실만 있으면 낮게 평가하세요.
  - 표적 고객, 포지셔닝, 가격·유통 설계까지 설명해야 높게 평가하세요.
  - 단순 매출 발표나 기업 동정보다 전략의 배경과 선택 이유를 설명하는 기사를
    우선하세요.
  - 광고성/보도자료는 무조건 배제하지 않되, 객관적 전략 정보가 부족하면 낮게
    평가하세요 (is_ad=true로 표시).

추가로 판단해 주세요 (가산점 계산은 이 값들을 바탕으로 별도 로직이 처리합니다.
당신은 아래 불리언만 정확히 판단하면 됩니다):
  - stp_specific: 본문에 시장세분화/표적시장/포지셔닝 중 하나 이상이 "구체적으로"
    설명되어 있는가 (단어만 언급된 경우는 false)
  - product_specific / price_specific / place_specific / promotion_specific:
    4P 각 요소에 대해 "구체적인 전략 변화"가 확인되는가 (역시 단어만 언급된 경우는 false)

같은 배치 안에 동일한 이슈를 다루는 기사가 여러 건 있으면(예: 같은 리브랜딩을
여러 언론사가 보도) 가장 구체적이고 신뢰도 높은 1건만 is_duplicate=false로 두고
나머지는 is_duplicate=true, duplicate_of에 그 기사의 id를 적으세요.

summary(핵심 내용)는 기사에 직접 나온 사실만 2-3문장으로 쓰고, interpretation
(전략 해석)은 당신의 해석임을 분명히 하는 2-3문장으로 쓰세요 — 이 둘을 절대
섞지 마세요. application(실무 적용 아이디어)은 1-2문장. 기사에 없는 사실을
추측해서 추가하지 마세요.

insight_quote는 이 기사의 전략적 시사점을 한 문장으로 압축한 인용구 스타일
문구입니다 (예: "가격이 아니라 정체성을 바꾼다", "같은 브랜드로는 남성을 못
잡는다"). 카카오톡 메시지 맨 위에 그대로 노출되니 15자 내외로 짧고 인상적으로
쓰세요.

tags는 다음 목록에서만 1~3개 고르세요: {", ".join(TAGS)}

reject_reason은 최종적으로 탈락할 것 같은 기사에만 짧게 채우고(예: "광고성·보도자료",
"단순 실적 발표", "전략성 부족"), 그렇지 않으면 null로 두세요."""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "evaluations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "strategic_relevance": {"type": "integer"},
                    "stp_4p_relevance": {"type": "integer"},
                    "practical_applicability": {"type": "integer"},
                    "market_impact": {"type": "integer"},
                    "recency": {"type": "integer"},
                    "credibility": {"type": "integer"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "summary": {"type": "string"},
                    "interpretation": {"type": "string"},
                    "application": {"type": "string"},
                    "insight_quote": {"type": "string"},
                    "is_ad": {"type": "boolean"},
                    "is_duplicate": {"type": "boolean"},
                    "duplicate_of": {"type": ["string", "null"]},
                    "reject_reason": {"type": ["string", "null"]},
                    "stp_specific": {"type": "boolean"},
                    "product_specific": {"type": "boolean"},
                    "price_specific": {"type": "boolean"},
                    "place_specific": {"type": "boolean"},
                    "promotion_specific": {"type": "boolean"},
                },
                "required": [
                    "id", "strategic_relevance", "stp_4p_relevance",
                    "practical_applicability", "market_impact", "recency",
                    "credibility", "tags", "summary", "interpretation",
                    "application", "insight_quote", "is_ad", "is_duplicate", "duplicate_of",
                    "reject_reason", "stp_specific", "product_specific",
                    "price_specific", "place_specific", "promotion_specific",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["evaluations"],
    "additionalProperties": False,
}


def _title_bonus(title: str) -> bool:
    return any(phrase in title for phrase in TITLE_BONUS_PHRASES)


def _build_user_message(batch: list[Article]) -> str:
    items = [
        {
            "id": a.id,
            "title": a.title,
            "source": a.source,
            "published_at": a.published_at.isoformat(),
            "description": a.description,
        }
        for a in batch
    ]
    return "다음 기사들을 평가하세요:\n" + json.dumps(items, ensure_ascii=False, indent=2)


def _call_claude(client: anthropic.Anthropic, batch: list[Article]) -> list[dict]:
    response = client.messages.create(
        model=settings.claude_model,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        output_config={
            "effort": settings.claude_effort,
            "format": {"type": "json_schema", "schema": RESPONSE_SCHEMA},
        },
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": _build_user_message(batch)}],
    )
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)["evaluations"]


def evaluate(candidates: list[Article]) -> list[Evaluation]:
    """Evaluate every candidate, batch by batch. Never raises on a single
    batch failure — that batch's articles are simply dropped from
    consideration and the run continues (see run_pipeline.py error policy)."""
    if not candidates:
        return []

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    by_id = {a.id: a for a in candidates}
    evaluations: list[Evaluation] = []

    for start in range(0, len(candidates), BATCH_SIZE):
        batch = candidates[start:start + BATCH_SIZE]
        try:
            raw_results = _call_claude(client, batch)
        except anthropic.RateLimitError as exc:
            logger.error("Claude rate limited on batch starting %d: %s", start, exc)
            continue
        except anthropic.APIStatusError as exc:
            logger.error("Claude API error on batch starting %d: %s", start, exc)
            continue
        except anthropic.APIConnectionError as exc:
            logger.error("Claude connection error on batch starting %d: %s", start, exc)
            continue
        except (json.JSONDecodeError, KeyError, StopIteration) as exc:
            logger.error("Malformed Claude response on batch starting %d: %s", start, exc)
            continue

        for item in raw_results:
            article = by_id.get(item["id"])
            if article is None:
                continue  # Claude echoed an id we didn't send; ignore defensively
            evaluations.append(Evaluation(
                article_id=article.id,
                strategic_relevance=item["strategic_relevance"],
                stp_4p_relevance=item["stp_4p_relevance"],
                practical_applicability=item["practical_applicability"],
                market_impact=item["market_impact"],
                recency=item["recency"],
                credibility=item["credibility"],
                tags=[t for t in item["tags"] if t in TAGS][:3],
                summary=item["summary"],
                interpretation=item["interpretation"],
                application=item["application"],
                insight_quote=item["insight_quote"],
                is_ad=item["is_ad"],
                is_duplicate=item["is_duplicate"],
                duplicate_of=item["duplicate_of"],
                reject_reason=item["reject_reason"],
                title_has_strategy_phrase=_title_bonus(article.title),
                stp_specific=item["stp_specific"],
                product_specific=item["product_specific"],
                price_specific=item["price_specific"],
                place_specific=item["place_specific"],
                promotion_specific=item["promotion_specific"],
            ))

    return evaluations
