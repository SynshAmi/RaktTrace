"""Telegram bot (BUILD §5.4, PRODUCT §2.2): long polling, onboarding, deep links, buttons and free text.

The bot only collects answers and relays taps and messages. Matching, invitations and every other decision stay
with the planner. The `on_*` functions hold the logic and return the reply; the async handlers below only run them
(in a worker thread, under the store lock) and send what they return.
"""

import asyncio
import logging
from collections.abc import Callable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from rakt import store
from rakt.agent import live, loop
from rakt.config import settings
from rakt.models import GROUP_LABELS, BloodGroup, Button, Channel, DonorProfile, Inbound
from rakt.sim.world import AREAS

log = logging.getLogger(__name__)

Reply = tuple[str, list[Button]]

QUESTIONS = [  # (field, question, [(button title, value)]); answers only: the planner decides eligibility
    ("group", "Your blood group?", [(GROUP_LABELS[g], g.value) for g in BloodGroup]),
    ("area", "Roughly where are you? (an area is enough, never your address)", [(a, a) for a in AREAS]),
    ("sex", "Sex? (donation intervals differ)", [("Male", "M"), ("Female", "F"), ("Prefer not to say", "-")]),
    ("age", "Age?", [("18–24", "21"), ("25–40", "32"), ("41–60", "50"), ("Over 60", "62")]),
    ("weight_kg", "Weight?", [("Under 45 kg", "42"), ("45–49 kg", "47"), ("50–59 kg", "55"), ("60 kg or more", "70")]),
    ("last_donation", "Last blood donation?", [("Never", "never"), ("Over 4 months ago", "over_4_months"),
                                              ("In the last 4 months", "recent")]),
    ("apheresis_ok", "Can you donate platelets (apheresis)?", [("Yes", "yes"), ("No / not sure", "no")]),
]
SYNTHETIC = "This is a synthetic demo profile, not a medical record; the blood centre always screens donors."

_onboarding: dict[str, dict] = {}  # chat id → answers so far (a half-finished Q&A)
_app = None
_loop: asyncio.AbstractEventLoop | None = None


# --- Replies (no Telegram needed) ---

def choices() -> list[Button]:
    return [Button(id="O:JOIN", title="Join the live demo"), Button(id="O:CREATE", title="Create my profile")]


def question(step: int) -> Reply:
    field, text, options = QUESTIONS[step]
    return f"({step + 1}/{len(QUESTIONS)}) {text}", [Button(id=f"Q:{step}:{value}", title=t) for t, value in options]


def describe(profile: DonorProfile) -> str:
    return f"{GROUP_LABELS[profile.group]} donor near {profile.area}"


def registered_text(profile: DonorProfile, resumed: bool) -> str:
    head = "Welcome back! You're still" if resumed else "You're"
    if live.scenario_running():
        return (f"{head} in the live demo as a synthetic {describe(profile)}. You'll get a message only if a request "
                f"needs someone like you and the agent picks you. {SYNTHETIC}")
    return (f"{head} registered as a synthetic {describe(profile)}. No request is running right now; you'll get a "
            f"message only if one needs someone like you. {SYNTHETIC}")


def on_start(chat_id: str, name: str, param: str, private: bool) -> Reply:
    if not private:
        return "Please message me in a private chat.", []
    if param.startswith("staff_") or param in ("family", "coord"):
        return loop.link_chat(param, chat_id, name), []
    _onboarding.pop(chat_id, None)  # a half-finished Q&A starts again
    person = live.registry.identities.get(chat_id)
    if person is not None and person.role == "donor" and person.profile is not None:
        return (f"Welcome back, you're registered as a synthetic {describe(person.profile)}. Keep it with "
                "\"Join the live demo\", or answer a few questions to change it.", choices())
    return ("Welcome to RaktTrace, a live demo of an agent that coordinates urgent blood requests. "
            "Join with a ready-made synthetic donor profile, or create your own in a few taps.", choices())


def on_callback(chat_id: str, name: str, data: str) -> Reply | None:
    if data == "O:JOIN":
        donor_id, resumed = live.join_demo(chat_id, name)
        return registered_text(live.registry.identities[chat_id].profile, resumed), []
    if data == "O:CREATE":
        _onboarding[chat_id] = {"step": 0}
        return question(0)
    if data.startswith("Q:"):
        return answer(chat_id, name, data)
    loop.handle_inbound(Inbound(channel=Channel.TELEGRAM, sender_id=chat_id, button_id=data, at=store.state.clock.now))
    return None


def answer(chat_id: str, name: str, data: str) -> Reply:
    _, step_text, value = data.split(":", 2)
    progress = _onboarding.get(chat_id)
    if progress is None or str(progress["step"]) != step_text:  # a stale or replayed button: start again safely
        _onboarding[chat_id] = {"step": 0}
        text, buttons = question(0)
        return "Let's start again. " + text, buttons
    field = QUESTIONS[progress["step"]][0]
    progress[field] = value
    progress["step"] += 1
    if progress["step"] < len(QUESTIONS):
        return question(progress["step"])
    del _onboarding[chat_id]
    profile = DonorProfile(
        group=progress["group"], area=progress["area"], sex=None if progress["sex"] == "-" else progress["sex"],
        age=int(progress["age"]), weight_kg=int(progress["weight_kg"]), last_donation=progress["last_donation"],
        apheresis_ok=progress["apheresis_ok"] == "yes",
    )
    live.register_donor(chat_id, name, profile)
    return registered_text(profile, resumed=False), []


def on_text(chat_id: str, text: str) -> Reply | None:
    if chat_id in _onboarding:
        return "Please tap one of the buttons above, or send /start to begin again.", []
    loop.handle_inbound(Inbound(channel=Channel.TELEGRAM, sender_id=chat_id, text=text, at=store.state.clock.now))
    return None


def on_stop(chat_id: str) -> Reply:
    live.opt_out(chat_id)
    return "Done: you won't get requests any more. Tap \"Join the live demo\" after /start if you change your mind.", []


# --- Sending ---

def is_running() -> bool:
    return _app is not None and _loop is not None


def keyboard(buttons: list[Button]):
    return InlineKeyboardMarkup([[InlineKeyboardButton(b.title, callback_data=b.id)] for b in buttons]) if buttons else None


def send(chat_id: str, text: str, buttons: list[Button], on_fail: Callable[[], None]) -> bool:
    """Queue a message on the bot's event loop. False if the bot isn't running (the caller falls back to sim)."""
    if not is_running():
        return False
    coro = _app.bot.send_message(chat_id=int(chat_id), text=text, reply_markup=keyboard(buttons))

    def done(future) -> None:
        if future.cancelled() or future.exception() is not None:
            log.warning("Telegram send to a chat failed; mirrored to the sim inbox")
            on_fail()

    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is _loop:
        _loop.create_task(coro).add_done_callback(done)
    else:
        asyncio.run_coroutine_threadsafe(coro, _loop).add_done_callback(done)
    return True


# --- Telegram handlers ---

def locked(fn, *args):
    with store.lock:
        if store.state is None:
            return None
        return fn(*args)


def who(update) -> tuple[str, str]:
    user = update.effective_user
    name = user.first_name + (f" {user.last_name[0]}." if user.last_name else "") if user else "Donor"
    return str(update.effective_chat.id), name


async def reply(update, result: Reply | None) -> None:
    if result:
        text, buttons = result
        await update.effective_chat.send_message(text, reply_markup=keyboard(buttons))


async def handle_start(update, context) -> None:
    chat_id, name = who(update)
    param = context.args[0] if context.args else ""
    private = update.effective_chat.type == "private"
    await reply(update, await asyncio.to_thread(locked, on_start, chat_id, name, param, private))


async def handle_stop(update, context) -> None:
    chat_id, _ = who(update)
    await reply(update, await asyncio.to_thread(locked, on_stop, chat_id))


async def handle_button(update, context) -> None:
    query = update.callback_query
    await query.answer()
    chat_id, name = who(update)
    await reply(update, await asyncio.to_thread(locked, on_callback, chat_id, name, query.data or ""))


async def handle_text(update, context) -> None:
    chat_id, _ = who(update)
    await reply(update, await asyncio.to_thread(locked, on_text, chat_id, update.message.text or ""))


async def start() -> None:
    """Start long polling if a token is set. Any failure leaves the bot off; the sim channel carries everything."""
    global _app, _loop
    if not settings.telegram_bot_token:
        return
    try:
        app = Application.builder().token(settings.telegram_bot_token).build()
        app.add_handler(CommandHandler("start", handle_start))
        app.add_handler(CommandHandler("stop", handle_stop))
        app.add_handler(CallbackQueryHandler(handle_button))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        _app, _loop = app, asyncio.get_running_loop()
    except Exception as error:
        log.warning("Telegram bot not started (%s); using the sim channel only", type(error).__name__)
        _app = _loop = None


async def stop() -> None:
    global _app, _loop
    if _app is None:
        return
    try:
        await _app.updater.stop()
        await _app.stop()
        await _app.shutdown()
    except Exception:
        pass
    _app = _loop = None
