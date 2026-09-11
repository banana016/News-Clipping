"""
Keyword vocabulary from the approved Phase 1 spec (sections 5-8).

Used two ways:
  1. `SEARCH_QUERIES` — what we actually send to NAVER API HUB.
  2. `RELEVANCE_KEYWORDS` — the full flattened set, used by
     filters.keyword_prefilter() to cheaply decide whether a collected
     article is even worth sending to Claude.
"""

PRIORITY_STRATEGY_KEYWORDS = [
    "마케팅 전략", "브랜드 전략", "브랜딩 전략", "사업 전략", "성장 전략",
    "시장 진입 전략", "경쟁 전략", "리브랜딩", "브랜드 포트폴리오",
    "브랜드 확장", "브랜드 아이덴티티", "브랜드 차별화", "고객가치제안", "경쟁우위",
]

# Title-only match triggers the +15 bonus (spec section 10).
TITLE_BONUS_PHRASES = ["마케팅 전략", "브랜드 전략", "브랜딩 전략"]

SEGMENTATION_KEYWORDS = [
    "시장세분화", "시장 세분화", "고객 세분화", "소비자 세분화",
    "고객군", "세그먼테이션", "Segmentation",
]
TARGETING_KEYWORDS = [
    "표적시장", "표적시장 선정", "타깃 시장", "타깃 고객",
    "핵심 고객", "고객 페르소나", "Targeting",
]
POSITIONING_KEYWORDS = [
    "포지셔닝", "브랜드 포지셔닝", "경쟁 포지셔닝", "리포지셔닝",
    "차별적 포지셔닝", "Positioning",
]
STP_KEYWORDS = SEGMENTATION_KEYWORDS + TARGETING_KEYWORDS + POSITIONING_KEYWORDS

PRODUCT_KEYWORDS = [
    "제품 전략", "상품 전략", "신제품", "제품개발", "상품기획", "제품 차별화",
    "제품 라인업", "제품 포트폴리오", "패키지 전략", "브랜드 확장", "PB 상품",
    "Product Strategy",
]
PRICE_KEYWORDS = [
    "가격 전략", "가격 정책", "가격 인상", "가격 인하", "프리미엄 가격",
    "침투가격", "할인 전략", "구독 가격", "동적 가격", "가격 차별화",
    "수익성", "Pricing", "Price Strategy",
]
PLACE_KEYWORDS = [
    "유통 전략", "채널 전략", "판매 채널", "온라인 유통", "오프라인 유통",
    "옴니채널", "D2C", "자사몰", "리테일", "입점 전략", "해외 유통",
    "이커머스", "플랫폼 전략", "Distribution Strategy", "Place Strategy",
]
PROMOTION_KEYWORDS = [
    "프로모션 전략", "광고 전략", "콘텐츠 전략", "미디어 전략", "캠페인 전략",
    "브랜드 캠페인", "판매촉진", "인플루언서 마케팅", "퍼포먼스 마케팅", "CRM",
    "고객 충성도", "리텐션", "IMC", "통합마케팅커뮤니케이션", "Promotion Strategy",
]
FOUR_P_KEYWORDS = PRODUCT_KEYWORDS + PRICE_KEYWORDS + PLACE_KEYWORDS + PROMOTION_KEYWORDS

ADDITIONAL_FIELDS_KEYWORDS = [
    "마케팅", "브랜딩", "화장품", "뷰티", "K-뷰티", "이커머스", "온라인 유통",
    "네이버", "쿠팡", "올리브영", "소비 트렌드", "Z세대", "AI 마케팅", "콘텐츠 마케팅",
    "인스타그램", "유튜브", "SNS 마케팅", "소상공인 마케팅", "광고 정책", "플랫폼 정책",
    "해외시장 진출", "고객 경험", "소비자 행동", "경쟁사 분석", "시장 분석",
]

RELEVANCE_KEYWORDS = sorted(set(
    PRIORITY_STRATEGY_KEYWORDS + STP_KEYWORDS + FOUR_P_KEYWORDS + ADDITIONAL_FIELDS_KEYWORDS
))

# What we actually send to NAVER API HUB — one query per group keeps each
# call's `display` budget focused instead of one giant OR query.
SEARCH_QUERIES = [
    "마케팅 전략", "브랜드 전략", "브랜딩 전략", "리브랜딩",
    "시장세분화 마케팅", "표적시장 마케팅", "브랜드 포지셔닝",
    "가격 전략 마케팅", "유통 전략 이커머스", "프로모션 전략 캠페인",
    "뷰티 브랜드 전략", "이커머스 유통 전략", "네이버 쿠팡 올리브영",
    "소비 트렌드 Z세대", "AI 마케팅", "소상공인 마케팅",
]

TAGS = [
    "마케팅전략", "브랜드전략", "시장세분화", "표적시장", "포지셔닝",
    "제품전략", "가격전략", "유통전략", "프로모션전략", "고객경험",
    "소비자행동", "경쟁전략", "해외진출", "이커머스", "뷰티", "AI마케팅",
]
