"""The LLM chain (AGENT §7): OpenAI-compatible entries from LLM_CHAIN, tried in order. Never raises."""

import json
import logging

from openai import OpenAI

from rakt import config
from rakt.config import settings

log = logging.getLogger(__name__)

PROVIDERS = {
    "groq": ("https://api.groq.com/openai/v1", "groq_api_key"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", "gemini_api_key"),
    "openrouter": ("https://openrouter.ai/api/v1", "openrouter_api_key"),
}

health: dict[str, bool] = {}  # chain entry → did its last call succeed


def chain() -> list[tuple[str, str]]:
    """[(provider, model)] from LLM_CHAIN, e.g. "groq:llama-x,gemini:flash"."""
    entries = []
    for entry in settings.llm_chain.split(","):
        provider, _, model = entry.strip().partition(":")
        if provider in PROVIDERS and model and "<" not in model:
            entries.append((provider, model))
    return entries


def call_entry(provider: str, model: str, system: str, user: str) -> dict:
    base_url, key_name = PROVIDERS[provider]
    key = getattr(settings, key_name)
    if not key:
        raise RuntimeError(f"no key for {provider}")
    client = OpenAI(base_url=base_url, api_key=key, timeout=config.LLM_TIMEOUT_S, max_retries=0)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(response.choices[0].message.content)


def complete_json(system: str, user: str) -> dict | None:
    """The first entry that returns valid JSON; None if every entry fails (timeout, 429, 5xx, bad JSON, no key)."""
    for provider, model in chain():
        name = f"{provider}:{model}"
        try:
            result = call_entry(provider, model, system, user)
            if not isinstance(result, dict):
                raise ValueError("not a JSON object")
            health[name] = True
            return result
        except Exception as error:  # every failure moves to the next entry
            health[name] = False
            log.warning("LLM %s failed: %s", name, type(error).__name__)
    return None
