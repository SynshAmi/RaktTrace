"""Every test runs offline: no LLM calls, no Telegram bot, an empty live registry, rule-based reading."""

import pytest

from rakt import llm
from rakt.agent import live
from rakt.config import settings
from rakt.llm import client


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(client, "complete_json", lambda system, user: None)  # the network is "down"
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    llm.set_enabled(False)
    live.clear()
    yield
    llm.set_enabled(False)
    live.clear()
