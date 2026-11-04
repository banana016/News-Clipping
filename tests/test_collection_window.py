from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from pipeline import collector
from shared.config import settings

NOW = datetime(2026, 11, 6, 7, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def cap(monkeypatch):
    monkeypatch.setattr(settings, "collect_max_hours", 96)


def _hours(elapsed_hours: float) -> float:
    return collector.collection_window_hours(NOW - timedelta(hours=elapsed_hours), NOW)


def test_covers_everything_since_the_last_good_run():
    assert _hours(48) == 48  # Mon -> Wed
    assert _hours(72) == 72  # Fri -> Mon


def test_same_day_rerun_still_collects_a_normal_pool():
    assert _hours(2) == collector.MIN_COLLECT_HOURS


def test_long_gap_is_capped():
    assert _hours(24 * 12) == 96


def test_no_previous_run_uses_the_minimum():
    assert collector.collection_window_hours(None, NOW) == collector.MIN_COLLECT_HOURS


def test_strip_html_removes_tags_and_decodes_entities():
    assert collector._strip_html("<b>A</b> &amp; B &lt;C&gt; &#39;D&#39; &quot;E&quot;") == "A & B <C> 'D' \"E\""
