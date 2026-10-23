"""Build sim/phrase_cache.json: the LLM's reading of every phrase in the bank, once (AGENT §9).

Run: `cd backend && uv run python -m rakt.sim.phrase_cache`. One bounded pass: each phrase tries the chain entries
in order (at most one call per entry), calls are paced, and the whole run stops at the first rate-limit (429) or if
the provider's remaining quota can't be read or is too low. Keys are never printed. Everything else, including the
benchmark and tests, reads the cache and never calls the API.
"""

import json
import time
from datetime import datetime

from openai import OpenAI, RateLimitError

from rakt import config
from rakt.config import settings
from rakt.llm import CACHE_FILE, REPLY_PROMPT, client, reading_from
from rakt.models import IST
from rakt.sim.world import load_phrases

REFERENCE_NOW = datetime(2026, 10, 24, 22, 40, tzinfo=IST)  # S2's start: "kal" = 25 Oct
REFERENCE_DEADLINE = datetime(2026, 10, 25, 14, 0, tzinfo=IST)
PACE_S = 2.5  # ≤ 24 calls a minute, under common free-tier per-minute limits


class Stop(Exception):
    pass


def call(provider: str, model: str, text: str) -> tuple[dict, dict]:
    """(JSON reply, rate-limit headers). Raises on any failure."""
    base_url, key_name = client.PROVIDERS[provider]
    api = OpenAI(base_url=base_url, api_key=getattr(settings, key_name), timeout=config.LLM_TIMEOUT_S, max_retries=0)
    prompt = REPLY_PROMPT.format(deadline=REFERENCE_DEADLINE.isoformat(), now=REFERENCE_NOW.isoformat())
    raw = api.chat.completions.with_raw_response.create(
        model=model, temperature=0, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": prompt}, {"role": "user", "content": text}],
    )
    limits = {k: v for k, v in raw.headers.items() if k.lower().startswith("x-ratelimit-")}
    return json.loads(raw.parse().choices[0].message.content), limits


def check_quota(limits: dict, still_to_do: int) -> None:
    remaining = limits.get("x-ratelimit-remaining-requests")
    if remaining is None:
        raise Stop("the provider sent no request-quota headers, so the limits can't be confirmed")
    if int(remaining) < still_to_do:
        raise Stop(f"only {remaining} requests left in the provider's quota for {still_to_do} phrases")


def build() -> tuple[dict, dict]:
    phrases = load_phrases()
    cache, counts, limits_seen = {}, {"attempted": 0, "succeeded": 0, "failed": 0}, None
    try:
        for i, phrase in enumerate(phrases):
            for provider, model in client.chain():
                if counts["attempted"]:
                    time.sleep(PACE_S)
                counts["attempted"] += 1
                try:
                    data, limits = call(provider, model, phrase["text"])
                    reading = reading_from(data, REFERENCE_NOW)
                except RateLimitError:
                    counts["failed"] += 1
                    raise Stop(f"{provider} rate-limited the run (429) at phrase {i + 1}")
                except Exception as error:
                    counts["failed"] += 1
                    print(f"  {phrase['id']}: {provider} failed ({type(error).__name__}); trying the next entry")
                    continue
                counts["succeeded"] += 1
                if limits_seen is None:
                    limits_seen = limits
                    print("  quota: " + ", ".join(f"{k.removeprefix('x-ratelimit-')}={v}" for k, v in limits.items()))
                    check_quota(limits, len(phrases) - i - 1)
                entry = {"intent": reading.intent.value, "confidence": reading.confidence, "day_offset": 0, "time": None}
                if reading.available_from:
                    entry["day_offset"] = (reading.available_from.date() - REFERENCE_NOW.date()).days
                    entry["time"] = reading.available_from.strftime("%H:%M")
                cache[phrase["text"]] = entry
                break
    except Stop as reason:
        counts["stopped"] = str(reason)
    return cache, counts


if __name__ == "__main__":
    result, counts = build()
    if result:
        CACHE_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"calls: {counts['attempted']} attempted, {counts['succeeded']} succeeded, {counts['failed']} failed")
    print(f"cached {len(result)} of {len(load_phrases())} phrases → {CACHE_FILE.name}")
    if "stopped" in counts:
        print(f"stopped early: {counts['stopped']}")
