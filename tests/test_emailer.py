"""send_email must never take down the pipeline run: the results are already
saved by the time it's called. SMTP is mocked - nothing is actually sent.
"""
from __future__ import annotations

import smtplib
import socket

import pytest

from pipeline import emailer
from shared.config import settings


class _FakeSMTP:
    """Stands in for smtplib.SMTP; fails on connect while `failures` remain."""

    failures: list[Exception] = []
    sent = 0

    def __init__(self, *args, **kwargs):
        if _FakeSMTP.failures:
            raise _FakeSMTP.failures.pop(0)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        pass

    def login(self, *args):
        pass

    def sendmail(self, *args):
        _FakeSMTP.sent += 1


@pytest.fixture(autouse=True)
def smtp_env(monkeypatch):
    _FakeSMTP.failures = []
    _FakeSMTP.sent = 0
    monkeypatch.setattr(settings, "dry_run", False)
    monkeypatch.setattr(settings, "gmail_address", "from@example.com")
    monkeypatch.setattr(settings, "gmail_app_password", "password")
    monkeypatch.setattr(settings, "briefing_recipient", "to@example.com")
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    monkeypatch.setattr(emailer.time, "sleep", lambda seconds: None)


@pytest.mark.parametrize("error", [
    TimeoutError("timed out"),
    socket.gaierror("name resolution failed"),
    ConnectionRefusedError("refused"),
    smtplib.SMTPAuthenticationError(535, b"bad credentials"),
])
def test_returns_false_after_retries_instead_of_raising(error):
    _FakeSMTP.failures = [error] * emailer.MAX_RETRIES

    assert emailer.send_email("제목", "<html>") is False
    assert _FakeSMTP.sent == 0


def test_network_error_is_retried():
    _FakeSMTP.failures = [TimeoutError("timed out")]

    assert emailer.send_email("제목", "<html>") is True
    assert _FakeSMTP.sent == 1
