"""LLM jobs (BUILD §5.4, AGENT §7): read pleas, read replies, write briefs. Every function falls back to the rules
in `llm/rules.py` and never raises. The LLM never sees names or phone numbers: only message text and ids."""

import json
from datetime import datetime, timedelta
from pathlib import Path

from rakt import config
from rakt.config import settings
from rakt.llm import client, rules
from rakt.models import IST, BloodGroup, Intent, PleaDraft, Product, ReplyRead

PLEA_FIELDS = ["group", "product", "units", "hospital_id", "deadline_at"]
CACHE_FILE = Path(__file__).resolve().parents[1] / "sim" / "phrase_cache.json"
NEXT_STEPS = ", ".join(rules.NEXT_STEPS)

PLEA_PROMPT = ("Extract a blood request from this message (English/Hindi/Hinglish). Return JSON with group, product, "
               "units, hospital_id (choose from the list or null), deadline_at (ISO, now is {now}), confidence, "
               "missing. Never guess a field you can't find. group is one of O_POS O_NEG A_POS A_NEG B_POS B_NEG AB_POS "
               "AB_NEG; product is PRBC (\"blood\", red cells) or SDP (platelets).")
REPLY_PROMPT = ("A blood donor replied to a request needed by {deadline}. Now is {now}. Return JSON: intent "
                "(YES/NO/STOP/UNCLEAR), available_from (ISO or null if now), confidence.")
BRIEF_PROMPT = ("Write a 4–6 line handover for a blood-helpline coordinator using only these facts. Plain English, "
                "no speculation. End with up to 3 next steps from this list: " + NEXT_STEPS + ". "
                "Return JSON: {\"brief\": \"...\"}.")

_enabled = settings.llm_enabled
_cache: dict | None = None


def set_enabled(on: bool) -> None:
    global _enabled
    _enabled = on


def reading_with_llm() -> bool:
    """Enabled and at least one chain entry has its API key; otherwise every read falls back to the rules."""
    return _enabled and any(getattr(settings, client.PROVIDERS[p][1]) for p, _ in client.chain())


def status() -> dict:
    names = [f"{p}:{m}" for p, m in client.chain()]
    return {"enabled": _enabled, "chain": [{"name": n, "healthy": client.health.get(n, False)} for n in names]}


# --- Replies ---

def phrase_cache() -> dict:
    """text → {intent, day_offset, time, confidence}, built once by `python -m rakt.sim.phrase_cache`."""
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _cache = {}
    return _cache


def from_cache(entry: dict, now: datetime) -> ReplyRead:
    available = None
    if entry.get("time"):
        hour, minute = map(int, entry["time"].split(":"))
        day = now + timedelta(days=entry.get("day_offset", 0))
        available = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return ReplyRead(intent=Intent(entry["intent"]), available_from=available,
                     confidence=float(entry.get("confidence", 1.0)), read_by="llm")


def as_time(value, now: datetime) -> datetime | None:
    if not value:
        return None
    at = datetime.fromisoformat(str(value))
    return at if at.tzinfo else at.replace(tzinfo=now.tzinfo or IST)


def reading_from(data: dict, now: datetime) -> ReplyRead:
    intent = Intent(str(data["intent"]).upper())
    confidence = float(data.get("confidence", 0.0))
    if confidence < config.LLM_MIN_CONFIDENCE:
        return ReplyRead(intent=Intent.UNCLEAR, confidence=confidence, read_by="llm")
    available = as_time(data.get("available_from"), now) if intent == Intent.YES else None
    if available is not None and available <= now + timedelta(minutes=config.READ_NOW_WINDOW_MIN):
        available = None  # "aa raha hoon, 20 min" is a yes for now, not a later time (AGENT §7.2)
    return ReplyRead(intent=intent, available_from=available, confidence=confidence, read_by="llm")


def read_reply(text: str, deadline: datetime, now: datetime) -> ReplyRead:
    if _enabled:
        try:
            cached = phrase_cache().get(text)
            if cached:
                return from_cache(cached, now)
            data = client.complete_json(REPLY_PROMPT.format(deadline=deadline.isoformat(), now=now.isoformat()), text)
            if data is not None:
                return reading_from(data, now)
        except Exception:
            pass
    try:
        return rules.read_reply(text, deadline, now)
    except Exception:
        return ReplyRead(intent=Intent.UNCLEAR, confidence=0.0, read_by="rules")


# --- Pleas ---

def draft_from(data: dict, hospitals: list[dict], now: datetime) -> PleaDraft:
    ids = {h["id"] for h in hospitals}
    group = data.get("group")
    product = data.get("product")
    draft = PleaDraft(
        group=BloodGroup(group) if group in BloodGroup.__members__ else None,
        product=Product(product) if product in Product.__members__ else None,
        units=int(data["units"]) if str(data.get("units") or "").isdigit() else None,
        hospital_id=data.get("hospital_id") if data.get("hospital_id") in ids else None,
        deadline_at=as_time(data.get("deadline_at"), now),
        confidence=float(data.get("confidence", 0.0)),
        read_by="llm",
    )
    draft.missing = [f for f in PLEA_FIELDS if getattr(draft, f) is None]
    return draft


def read_plea(text: str, hospitals: list[dict], now: datetime) -> PleaDraft:
    if _enabled:
        try:
            listing = json.dumps([{k: h[k] for k in ("id", "name", "area")} for h in hospitals])
            data = client.complete_json(PLEA_PROMPT.format(now=now.isoformat()), f"Hospitals: {listing}\n\n{text}")
            if data is not None:
                return draft_from(data, hospitals, now)
        except Exception:
            pass
    try:
        return rules.read_plea(text, hospitals, now)
    except Exception:
        return PleaDraft(missing=list(PLEA_FIELDS), confidence=0.0, read_by="rules")


# --- Brief ---

def write_brief(facts: dict) -> str:
    if _enabled:
        try:
            data = client.complete_json(BRIEF_PROMPT, json.dumps(facts, default=str))
            brief = data.get("brief") if data else None
            if isinstance(brief, str) and brief.strip():
                return brief.strip()
        except Exception:
            pass
    try:
        return rules.brief_template(facts)
    except Exception:
        return "\n".join(f"{key}: {value}" for key, value in facts.items())
