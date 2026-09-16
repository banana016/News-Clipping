"""
Step 10 of the pipeline: turn the final selection into
  (a) the data the web app's briefing page reads, and
  (b) an email-safe HTML notification (stats + magic link, no article
      bodies — the full cards live on the page, per the approved design).

Kakao message content is built on demand in web/api/kakao_send.py from
whatever articles are currently marked "good", not here — this module only
prepares what goes out at the scheduled run.
"""
from __future__ import annotations

from dataclasses import dataclass

from shared.magic_link import briefing_url
from shared.models import Article, Evaluation


@dataclass
class BriefingArticle:
    article: Article
    evaluation: Evaluation


def build_briefing(selected: list[tuple[Article, Evaluation]]) -> list[BriefingArticle]:
    return [BriefingArticle(article=a, evaluation=e) for a, e in selected]


def render_notification_email(run_id: str, run_date: str, collected_n: int, reviewed_n: int,
                               selected_n: int) -> tuple[str, str]:
    """Returns (subject, html_body). Kept intentionally simple/table-based —
    email clients don't reliably support modern CSS (flexbox, @import fonts).

    The link is keyed on run_id (the specific batch), not run_date — a date
    can have more than one run, and the link must always resolve to exactly
    the batch this email was actually sent for."""
    link = briefing_url(run_id)
    subject = f"오늘의 마케팅·브랜드 전략 브리핑 — {run_date}"

    html = f"""\
<!doctype html>
<html><body style="margin:0;padding:0;background:#fbfbfd;
  font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#fbfbfd;padding:32px 0;">
    <tr><td align="center">
      <table role="presentation" width="560" cellpadding="0" cellspacing="0"
        style="background:#ffffff;border-radius:20px;overflow:hidden;">
        <tr><td style="padding:28px 32px 8px;">
          <div style="font-size:19px;font-weight:700;color:#1d1d1f;">{subject}</div>
        </td></tr>
        <tr><td style="padding:8px 32px;">
          <div style="background:#f5f5f7;border-radius:12px;padding:12px 16px;
            font-size:13px;font-weight:600;color:#1d1d1f;">
            수집 {collected_n}건 · 검토 {reviewed_n}건 · 최종 선정 {selected_n}건
          </div>
        </td></tr>
        <tr><td style="padding:16px 32px 24px;">
          <p style="font-size:14.5px;color:#6e6e73;line-height:1.6;margin:0 0 20px;">
            오늘 선정된 기사를 브리핑 페이지에서 확인하세요. 기사별로 도움됨 / 별로예요를
            표시하면 다음 브리핑 선정 점수에 자동으로 반영되고, 도움됨으로 표시한
            기사만 모아 카카오톡으로 받아볼 수 있습니다.
          </p>
          <a href="{link}" style="display:inline-block;background:#0071e3;color:#ffffff;
            font-size:15px;font-weight:600;text-decoration:none;padding:12px 26px;
            border-radius:980px;">브리핑 페이지 열기</a>
        </td></tr>
        <tr><td style="padding:14px 32px;border-top:1px solid #d2d2d7;">
          <div style="font-size:11.5px;color:#86868b;">
            이 링크는 {run_date} 기준 발급되었으며 발급 후 일정 기간이 지나면 만료됩니다.
          </div>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""
    return subject, html


def build_kakao_article_payload(evaluation: Evaluation, article: Article) -> dict:
    return {
        "quote": evaluation.insight_quote,
        "title": article.title,
        "body": evaluation.summary + " " + evaluation.interpretation,
        "link": article.url,
    }
