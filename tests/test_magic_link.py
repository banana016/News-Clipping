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
    token = magic_link.issue_token("2026-09-11")
    payload = magic_link.verify_token(token)
    assert payload["run_date"] == "2026-09-11"


def test_tampered_token_is_rejected():
    token = magic_link.issue_token("2026-09-11")
    tampered = token[:-1] + ("0" if token[-1] != "0" else "1")
    with pytest.raises(magic_link.InvalidToken):
        magic_link.verify_token(tampered)


def test_expired_token_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "magic_link_ttl_days", 0)
    token = magic_link.issue_token("2026-09-11")
    time.sleep(1.1)
    with pytest.raises(magic_link.InvalidToken):
        magic_link.verify_token(token)


def test_malformed_token_is_rejected():
    with pytest.raises(magic_link.InvalidToken):
        magic_link.verify_token("not-a-real-token")
