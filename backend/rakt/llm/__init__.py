"""LLM jobs (BUILD §5.4, AGENT §7). Phase 1 stubs returning rule-fallback values; never raise."""

from datetime import datetime

from rakt.config import settings
from rakt.models import Intent, PleaDraft, ReplyRead

PLEA_FIELDS = ["group", "product", "units", "hospital_id", "deadline_at"]

_enabled = settings.llm_enabled


def read_plea(text: str, hospitals: list[dict], now: datetime) -> PleaDraft:
    return PleaDraft(missing=list(PLEA_FIELDS), confidence=0.0, read_by="rules")


def read_reply(text: str, deadline: datetime, now: datetime) -> ReplyRead:
    return ReplyRead(intent=Intent.UNCLEAR, available_from=None, confidence=0.0, read_by="rules")


def write_brief(facts: dict) -> str:
    return "\n".join(f"{key}: {value}" for key, value in facts.items())


def set_enabled(on: bool) -> None:
    global _enabled
    _enabled = on


def status() -> dict:
    chain = [entry.strip() for entry in settings.llm_chain.split(",") if entry.strip()]
    return {"enabled": _enabled, "chain": [{"name": name, "healthy": False} for name in chain]}
