from __future__ import annotations

import time

import pytest

from shared import magic_link
from shared.config import settings


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setattr(settings, "magic_link_secret", "test-secret-do-not-use-in-prod")
    monkeypatch.setattr(settings, "magic_link_ttl_days", 14)


def test_issued_token_verifies_successfully():
    token = magic_link.issue_token("11111111-1111-1111-1111-111111111111")
    payload = magic_link.verify_token(token)
    assert payload["run_id"] == "11111111-1111-1111-1111-111111111111"


def test_tampered_token_is_rejected():
    token = magic_link.issue_token("11111111-1111-1111-1111-111111111111")
    tampered = token[:-1] + ("0" if token[-1] != "0" else "1")
    with pytest.raises(magic_link.InvalidToken):
        magic_link.verify_token(tampered)


def test_expired_token_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "magic_link_ttl_days", 0)
    token = magic_link.issue_token("11111111-1111-1111-1111-111111111111")
    time.sleep(1.1)
    with pytest.raises(magic_link.InvalidToken):
        magic_link.verify_token(token)


def test_malformed_token_is_rejected():
    with pytest.raises(magic_link.InvalidToken):
        magic_link.verify_token("not-a-real-token")


def test_two_runs_on_the_same_date_get_distinct_tokens():
    """A retry (workflow_dispatch re-run after a failure) can create a second
    run for the same calendar date - the token must resolve to the exact
    run it was issued for, not "today's" run."""
    token_a = magic_link.issue_token("batch-a")
    token_b = magic_link.issue_token("batch-b")
    assert magic_link.verify_token(token_a)["run_id"] == "batch-a"
    assert magic_link.verify_token(token_b)["run_id"] == "batch-b"
