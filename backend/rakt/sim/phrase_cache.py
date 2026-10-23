"""Build sim/phrase_cache.json: the LLM's reading of every phrase in the bank, once (AGENT §9).

Run: `cd backend && uv run python -m rakt.sim.phrase_cache`. This calls the real LLM chain (one call per phrase);
everything else, including the benchmark and tests, reads the cache and never calls the API.
"""

import json
from datetime import datetime

from rakt.llm import CACHE_FILE, REPLY_PROMPT, client, reading_from
from rakt.models import IST
from rakt.sim.world import load_phrases

REFERENCE_NOW = datetime(2026, 10, 24, 22, 40, tzinfo=IST)  # S2's start: "kal" = 25 Oct
REFERENCE_DEADLINE = datetime(2026, 10, 25, 14, 0, tzinfo=IST)


def build() -> dict:
    cache = {}
    for phrase in load_phrases():
        prompt = REPLY_PROMPT.format(deadline=REFERENCE_DEADLINE.isoformat(), now=REFERENCE_NOW.isoformat())
        data = client.complete_json(prompt, phrase["text"])
        if data is None:
            print(f"skipped (every chain entry failed): {phrase['id']}")
            continue
        reading = reading_from(data, REFERENCE_NOW)
        entry = {"intent": reading.intent.value, "confidence": reading.confidence, "day_offset": 0, "time": None}
        if reading.available_from:
            entry["day_offset"] = (reading.available_from.date() - REFERENCE_NOW.date()).days
            entry["time"] = reading.available_from.strftime("%H:%M")
        cache[phrase["text"]] = entry
    return cache


if __name__ == "__main__":
    result = build()
    CACHE_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"cached {len(result)} of {len(load_phrases())} phrases → {CACHE_FILE}")
