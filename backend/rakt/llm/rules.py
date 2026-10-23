"""Rule fallback for reading donor replies (AGENT §7.2): word lists, case-insensitive."""

import re
from datetime import datetime, timedelta

from rakt.models import Intent, ReplyRead

STOP_WORDS = ["stop", "unsubscribe", "band karo", "बंद"]
NO_WORDS = ["no", "nahi", "nahin", "nai", "not today", "busy", "नहीं"]
YES_WORDS = ["yes", "haan", "han", "ha", "ok", "okay", "sure", "coming", "aa raha", "aa rahi", "aaunga", "aaungi",
             "हाँ", "जी"]

TOMORROW = re.compile(r"\b(kal|tomorrow)\b")
CLOCK = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|baje)\b|\b(\d{1,2}):(\d{2})\b")
EVENING = re.compile(r"\b(shaam|sham|raat|evening|night)\b")


def has_any(text: str, words: list[str]) -> bool:
    for word in words:
        if word.isascii():
            if re.search(rf"\b{re.escape(word)}\b", text):
                return True
        elif word in text:
            return True
    return False


def tomorrow_time(text: str, now: datetime) -> datetime | None:
    """'kal 11:55', 'kal subah 8 baje', 'tomorrow after 10 AM' → that time on the next day."""
    if not TOMORROW.search(text):
        return None
    match = CLOCK.search(text)
    if not match:
        return None
    hour = int(match.group(1) or match.group(4))
    minute = int(match.group(2) or match.group(5) or 0)
    marker = match.group(3)
    if marker == "pm" or (marker != "am" and EVENING.search(text)):
        hour = hour % 12 + 12
    elif marker == "am":
        hour %= 12
    elif hour < 7:  # "kal 2 baje" with no am/pm means the afternoon
        hour += 12
    if hour > 23 or minute > 59:
        return None
    return (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)


def read_reply(text: str, deadline: datetime, now: datetime) -> ReplyRead:
    lowered = (text or "").lower()
    if has_any(lowered, STOP_WORDS):
        return ReplyRead(intent=Intent.STOP, confidence=1.0, read_by="rules")
    later = tomorrow_time(lowered, now)
    says_yes = has_any(lowered, YES_WORDS) or later is not None  # a time tomorrow is an offer (AGENT §7.2)
    says_no = has_any(lowered, NO_WORDS)
    if says_yes == says_no:
        return ReplyRead(intent=Intent.UNCLEAR, confidence=0.0, read_by="rules")
    if says_no:
        return ReplyRead(intent=Intent.NO, confidence=1.0, read_by="rules")
    return ReplyRead(intent=Intent.YES, available_from=later, confidence=1.0, read_by="rules")


NEXT_STEPS = ["call these centres", "try a neighbouring district", "rare-donor registry",
              "ask the hospital's transfusion officer"]


def brief_template(facts: dict) -> str:
    """AGENT §7.3 fallback: where things stand, what was tried, who is coming, what's missing, next steps."""
    steps = []
    if facts.get("call_list"):
        steps.append(NEXT_STEPS[0])
    if facts.get("at_max_radius"):
        steps.append(NEXT_STEPS[1])
    if facts.get("rare_group"):
        steps.append(NEXT_STEPS[2])
    steps.append(NEXT_STEPS[3])
    return "\n".join([
        f"Where it stands: {facts['status']}, {facts['p']}% chance of {facts['units']} unit(s) by {facts['deadline']}.",
        f"Tried: {facts['tried']}.",
        f"Coming: {facts['active']} donor(s) active, {facts['standby']} on standby.",
        f"Missing: {facts['missing']} unit(s).",
        f"Next: {' · '.join(steps[:3])}.",
    ])
