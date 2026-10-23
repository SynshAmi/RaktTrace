
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

# Read .env locally without printing secrets.
for line in Path(".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    name, value = line.split("=", 1)
    value = value.strip().strip('"').strip("'")
    os.environ.setdefault(name.strip(), value)

PROMPT = """
Interpret this donor reply: "kal subah 8 baje aa jaunga"

Return only a JSON object with these fields:
{
  "meaning": "plain English interpretation",
  "intent": "YES_LATER, YES_NOW, NO, STOP, or UNCLEAR",
  "time": "the stated availability time"
}
Do not invent a calendar date. Tomorrow morning at 8 means YES_LATER.
"""

def test_groq():
    key = os.getenv("GROQ_API_KEY")
    model = "qwen/qwen3.8-27b"
    if not key:
        return False, "GROQ_API_KEY is missing"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "RaktTrace/0.2 (Phase 0.2 smoke test)",
        },
    )
    return call_api("Groq", req)


def test_gemini():
    key = os.getenv("GEMINI_API_KEY")
    model = "gemini-3.5-flash-lite"
    if not key:
        return False, "GEMINI_API_KEY is missing"

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={key}"
    )
    payload = {
        "contents": [{"parts": [{"text": PROMPT}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0,
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    return call_api("Gemini", req)


def call_api(provider, req):
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            data = json.loads(response.read().decode())

        if provider == "Groq":
            content = data["choices"][0]["message"]["content"]
        else:
            content = data["candidates"][0]["content"]["parts"][0]["text"]

        parsed = json.loads(content)
        required = {"meaning", "intent", "time"}
        if not required.issubset(parsed):
            return False, f"{provider}: JSON missing required fields: {parsed}"

        elapsed = time.perf_counter() - started
        return True, (
            f"{provider}: PASS ({elapsed:.2f}s)\n"
            f"  Parsed result: {json.dumps(parsed, ensure_ascii=False)}"
        )

    except urllib.error.HTTPError as e:
        # Show sanitized provider error, never the request URL or API key.
        headers_info = []
        if server := e.headers.get("server"):
            headers_info.append(f"server={server}")
        if cf_ray := e.headers.get("cf-ray"):
            headers_info.append(f"cf-ray={cf_ray}")
        header_str = f" [{', '.join(headers_info)}]" if headers_info else ""

        detail = e.read().decode(errors="replace")
        try:
            err_json = json.loads(detail)
            if "error" in err_json:
                detail = json.dumps(err_json["error"])
        except Exception:
            detail = detail.strip()
            if "<title>" in detail:
                start = detail.find("<title>") + 7
                end = detail.find("</title>", start)
                detail = detail[start:end].strip() if end != -1 else detail[:300]
            else:
                detail = detail[:300]

        category = ""
        if e.code == 403 and ("1010" in detail or "Cloudflare" in detail or "cf-ray" in e.headers):
            category = " (Blocked by Cloudflare edge security rule / missing or untrusted User-Agent)"
        elif e.code == 401:
            category = " (Unauthorized / invalid API key)"
        elif e.code == 404:
            category = " (Model or endpoint not found)"
        elif e.code == 400:
            category = " (Bad request / invalid payload or format)"

        return False, f"{provider}: HTTP {e.code}{category}{header_str}: {detail}"
    except Exception as e:
        return False, f"{provider}: {type(e).__name__}: {e}"


if __name__ == "__main__":
    import sys

    # Allow filtering by provider to run single-provider tests:
    # e.g., python test_llm.py --groq
    provider_arg = None
    for arg in sys.argv[1:]:
        if arg.lower() in ("groq", "--groq", "-g"):
            provider_arg = "groq"
        elif arg.lower() in ("gemini", "--gemini"):
            provider_arg = "gemini"

    tests = []
    if provider_arg == "groq":
        tests = [test_groq]
    elif provider_arg == "gemini":
        tests = [test_gemini]
    else:
        tests = [test_groq, test_gemini]

    results = [test() for test in tests]
    print("\n--- RaktTrace Phase 0.2 LLM test ---")
    for passed, message in results:
        print(message)
    passed_count = sum(passed for passed, _ in results)
    print(f"\nResult: {passed_count}/{len(results)} providers passed")
