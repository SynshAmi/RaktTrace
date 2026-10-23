"""
Phase 0 Telegram Bot smoke test and /start gate verification.
Polls getUpdates and replies to /start messages.
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

# Load .env safely without printing secrets
env_path = Path(".env")
if not env_path.exists():
    print("Error: .env file not found.")
    sys.exit(1)

for line in env_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "RaktTraceDemoBot")

if not TOKEN:
    print("Error: TELEGRAM_BOT_TOKEN is missing in .env")
    sys.exit(1)

BASE_URL = f"https://api.telegram.org/bot{TOKEN}"


def telegram_api(method: str, params: dict = None) -> dict:
    url = f"{BASE_URL}/{method}"
    data = None
    headers = {"User-Agent": "RaktTrace/0.2 (Phase 0 Bot Smoke Test)"}
    if params is not None:
        data = json.dumps(params).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=35) as resp:
        return json.loads(resp.read().decode("utf-8"))


def send_message(chat_id: int, text: str) -> bool:
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    res = telegram_api("sendMessage", payload)
    return res.get("ok", False)


def run_bot(exit_on_start: bool = False):
    print("\n--- RaktTrace Phase 0 Telegram Bot Listener ---")
    me = telegram_api("getMe")
    if not me.get("ok"):
        print("Failed to connect to Telegram API:", me)
        return False

    bot_info = me["result"]
    print(f"Connected to bot: @{bot_info.get('username')} ({bot_info.get('first_name')})", flush=True)
    print("Listening for /start from non-team phone...", flush=True)
    print("Press Ctrl+C to stop.\n", flush=True)

    offset = None
    verified = False

    while True:
        try:
            params = {"timeout": 15}
            if offset is not None:
                params["offset"] = offset

            updates = telegram_api("getUpdates", params)
            if not updates.get("ok"):
                print("getUpdates warning:", updates)
                time.sleep(2)
                continue

            for update in updates.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message") or update.get("channel_post")
                if not msg:
                    continue

                text = msg.get("text", "")
                chat = msg.get("chat", {})
                chat_id = chat.get("id")
                from_user = msg.get("from", {})
                user_name = from_user.get("first_name", "")
                username = from_user.get("username", "no_username")

                print(f"[INCOMING] From {user_name} (@{username}, chat_id={chat_id}): '{text}'", flush=True)

                if text.startswith("/start"):
                    # Check for deep link parameter: e.g. /start donor, /start staff_b
                    parts = text.split(maxsplit=1)
                    param = parts[1] if len(parts) > 1 else ""

                    role_desc = "Demo Donor"
                    if param == "donor":
                        role_desc = "Demo Donor (linked via ?start=donor)"
                    elif param.startswith("staff"):
                        role_desc = f"Staff Chat ({param})"
                    elif param == "family":
                        role_desc = "Family Contact"
                    elif param == "coord":
                        role_desc = "Coordinator"

                    reply_text = (
                        "🩸 *Welcome to RaktTrace!*\n\n"
                        f"You are connected as: *{role_desc}*\n\n"
                        "When an urgent blood or platelet request matches your group and area, "
                        "you will receive alerts and coordination cards here.\n\n"
                        "✅ *Phase 0 verification: Bot successfully answered /start!*"
                    )

                    ok = send_message(chat_id, reply_text)
                    if ok:
                        print(f"  -> [REPLY SENT] Successfully answered /start to @{username}!", flush=True)
                        print(f"  -> [GATE STATUS] Received & answered /start!", flush=True)
                        verified = True
                        if exit_on_start:
                            return True
                    else:
                        print(f"  -> [ERROR] Failed to send reply to chat_id={chat_id}", flush=True)

        except KeyboardInterrupt:
            print("\nListener stopped by user.")
            break
        except Exception as e:
            print(f"Listener error: {type(e).__name__}: {e}")
            time.sleep(3)

    return verified


if __name__ == "__main__":
    exit_after = "--once" in sys.argv
    run_bot(exit_on_start=exit_after)
