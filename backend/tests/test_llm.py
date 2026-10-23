"""Gate 6.V, reader part: rules accuracy, cached LLM vs rules, network off, toggle off. No real LLM calls."""

from datetime import datetime

import pytest

from rakt import llm
from rakt.llm import client, rules
from rakt.models import IST, Intent
from rakt.sim.world import load_phrases

REAL_COMPLETE_JSON = client.complete_json  # captured before the offline fixture replaces it
NOW = datetime(2026, 10, 24, 22, 40, tzinfo=IST)
DEADLINE = datetime(2026, 10, 25, 14, 0, tzinfo=IST)
HOSPITALS = [{"id": "h_city", "name": "City General Hospital", "area": "Jayanagar"},
             {"id": "h_lake", "name": "Lakeview Hospital", "area": "Indiranagar"}]


def score(reader) -> tuple[int, int, int]:
    """(right, wrong, unclear) over the phrase bank. Unclear asks the donor to tap a button: safe, not wrong."""
    right = wrong = unclear = 0
    for phrase in load_phrases():
        intent = reader(phrase["text"]).intent
        if intent == Intent.UNCLEAR and phrase["intent"] != "UNCLEAR":
            unclear += 1
        elif intent == phrase["intent"]:
            right += 1
        else:
            wrong += 1
    return right, wrong, unclear


def test_rules_reader_accuracy_on_the_phrase_bank():
    right, wrong, unclear = score(lambda text: rules.read_reply(text, DEADLINE, NOW))
    print(f"\nrules reader on {right + wrong + unclear} phrases: {right} right, {wrong} wrong, {unclear} unclear")
    assert wrong == 0  # the rules never misread; when unsure they ask for a button
    assert right >= 25


def test_cached_llm_reads_at_least_as_well_as_rules():
    if not llm.phrase_cache():
        pytest.skip("sim/phrase_cache.json not built yet: run `uv run python -m rakt.sim.phrase_cache` (calls the LLM)")
    llm.set_enabled(True)
    cached = score(lambda text: llm.read_reply(text, DEADLINE, NOW))
    ruled = score(lambda text: rules.read_reply(text, DEADLINE, NOW))
    print(f"\ncached LLM {cached} vs rules {ruled} (right, wrong, unclear)")
    assert cached[0] >= ruled[0]


def test_network_off_falls_back_to_rules_without_raising(monkeypatch):
    def down(*args, **kwargs):
        raise ConnectionError("no network")
    monkeypatch.setattr(client, "call_entry", down)
    monkeypatch.setattr(client, "chain", lambda: [("groq", "m1"), ("gemini", "m2")])
    monkeypatch.setattr(client, "complete_json", REAL_COMPLETE_JSON)  # the real chain, every entry failing
    llm.set_enabled(True)
    reading = llm.read_reply("haan abhi aa sakta hoon (new text)", DEADLINE, NOW)
    assert reading.read_by == "rules" and reading.intent == Intent.YES
    assert client.health == {"groq:m1": False, "gemini:m2": False}
    assert llm.read_plea("O+ platelets 1 unit City General kal 2 baje", HOSPITALS, NOW).read_by == "rules"
    assert "Where it stands" in llm.write_brief(brief_facts())


def test_toggle_off_means_rules(monkeypatch):
    monkeypatch.setattr(client, "complete_json", lambda s, u: {"intent": "NO", "confidence": 0.99})
    llm.set_enabled(False)
    reading = llm.read_reply("haan", DEADLINE, NOW)
    assert reading.read_by == "rules" and reading.intent == Intent.YES
    assert llm.status()["enabled"] is False


def test_llm_reading_is_used_and_checked(monkeypatch):
    llm.set_enabled(True)
    monkeypatch.setattr(client, "complete_json", lambda s, u: {
        "intent": "YES", "available_from": "2026-10-25T11:55:00+05:30", "confidence": 0.9})
    reading = llm.read_reply("free after lunch tomorrow, around 11:55", DEADLINE, NOW)
    assert (reading.read_by, reading.intent) == ("llm", Intent.YES)
    assert reading.available_from.isoformat() == "2026-10-25T11:55:00+05:30"

    monkeypatch.setattr(client, "complete_json", lambda s, u: {"intent": "YES", "confidence": 0.3})
    assert llm.read_reply("maybe", DEADLINE, NOW).intent == Intent.UNCLEAR  # below LLM_MIN_CONFIDENCE

    monkeypatch.setattr(client, "complete_json", lambda s, u: {"intent": "PERHAPS", "confidence": 0.9})
    assert llm.read_reply("nahi yaar, aaj busy hoon", DEADLINE, NOW).read_by == "rules"  # uncached + nonsense JSON → rules


def test_llm_plea_draft_keeps_only_known_values(monkeypatch):
    llm.set_enabled(True)
    monkeypatch.setattr(client, "complete_json", lambda s, u: {
        "group": "O_POS", "product": "SDP", "units": 1, "hospital_id": "h_unknown",
        "deadline_at": "2026-10-25T14:00:00+05:30", "confidence": 0.8})
    draft = llm.read_plea("O+ platelets kal 2 baje", HOSPITALS, NOW)
    assert draft.read_by == "llm" and draft.hospital_id is None and draft.missing == ["hospital_id"]


def test_rules_plea_parser():
    draft = rules.read_plea("Urgent: O+ platelets needed at City General, kal 2 baje, 1 unit", HOSPITALS, NOW)
    assert (draft.group, draft.product, draft.units, draft.hospital_id) == ("O_POS", "SDP", 1, "h_city")
    assert draft.deadline_at.isoformat() == "2026-10-25T14:00:00+05:30" and draft.missing == []
    partial = rules.read_plea("need blood urgently", HOSPITALS, NOW)
    assert partial.product == "PRBC" and "group" in partial.missing and partial.confidence < 0.5


def test_chain_ignores_placeholders(monkeypatch):
    from rakt.config import settings
    monkeypatch.setattr(settings, "llm_chain", "groq:<model>,groq:llama-x, gemini:flash,unknown:m")
    assert client.chain() == [("groq", "llama-x"), ("gemini", "flash")]
    assert [c["name"] for c in llm.status()["chain"]] == ["groq:llama-x", "gemini:flash"]


def brief_facts() -> dict:
    return {"status": "OPEN", "p": 10, "units": 2, "deadline": "02:00, 25 Oct", "tried": "asked 0 centre(s)",
            "active": 0, "standby": 0, "missing": 2, "call_list": [], "at_max_radius": True, "rare_group": True}

