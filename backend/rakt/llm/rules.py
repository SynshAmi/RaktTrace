"""Rule fallback for reading donor replies (AGENT §7.2): word lists, case-insensitive."""

import re
from datetime import datetime, timedelta

from rakt.models import BloodGroup, Intent, PleaDraft, Product, ReplyRead

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


# --- Pleas (AGENT §7.1 fallback) ---

GROUP_PATTERN = re.compile(r"\b(ab|a|b|o)\s*(\+|-|−|pos(?:itive)?|neg(?:ative)?|\+ve|-ve)", re.IGNORECASE)
UNITS_PATTERN = re.compile(r"\b(\d{1,2})\s*(?:units?|bottles?|pints?|bags?)\b", re.IGNORECASE)
HOURS_PATTERN = re.compile(r"\b(?:in|within)\s+(\d{1,2})\s*(?:h|hrs?|hours?|ghante)\b", re.IGNORECASE)
SDP_WORDS = ["platelet", "platelets", "sdp", "apheresis"]
PRBC_WORDS = ["blood", "prbc", "red cell", "red cells", "khoon"]


def plea_group(text: str) -> BloodGroup | None:
    match = GROUP_PATTERN.search(text)
    if not match:
        return None
    letters = match.group(1).upper()
    sign = match.group(2).lower()
    positive = sign in ("+", "pos", "positive", "+ve")
    return BloodGroup(f"{letters}_{'POS' if positive else 'NEG'}")


def plea_hospital(text: str, hospitals: list[dict]) -> str | None:
    lowered = text.lower()
    for h in hospitals:
        name_words = [w for w in h["name"].lower().split() if w not in ("hospital", "medical", "centre", "center")]
        if (name_words and " ".join(name_words) in lowered) or h["name"].lower() in lowered:
            return h["id"]
    return None


def read_plea(text: str, hospitals: list[dict], now: datetime) -> PleaDraft:
    lowered = (text or "").lower()
    units = UNITS_PATTERN.search(lowered)
    product = Product.SDP if has_any(lowered, SDP_WORDS) else Product.PRBC if has_any(lowered, PRBC_WORDS) else None
    deadline = tomorrow_time(lowered, now)
    hours = HOURS_PATTERN.search(lowered)
    if deadline is None and hours:
        deadline = now + timedelta(hours=int(hours.group(1)))
    draft = PleaDraft(group=plea_group(text or ""), product=product, units=int(units.group(1)) if units else None,
                      hospital_id=plea_hospital(text or "", hospitals), deadline_at=deadline, read_by="rules")
    fields = ["group", "product", "units", "hospital_id", "deadline_at"]
    draft.missing = [f for f in fields if getattr(draft, f) is None]
    draft.confidence = round(1 - len(draft.missing) / len(fields), 2)
    return draft
