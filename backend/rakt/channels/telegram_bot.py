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

from rakt import llm, store
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
_cards: set[tuple[str, int]] = set()  # (chat id, message id) of agent cards sent in the current demo run
_app = None
_loop: asyncio.AbstractEventLoop | None = None
AGENT_BUTTONS = ("P:", "R:", "V:", "D:")


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
    """Idempotent: an existing donor, staff, family or coordinator chat is confirmed, never re-onboarded."""
    if not private:
        return "Please message me in a private chat.", []
    if param.startswith("staff_") or param in ("family", "coord"):
        return loop.link_chat(param, chat_id, name), []
    person = live.registry.identities.get(chat_id)
    if person is not None and person.role == "staff":
        centre = store.state.main.centres[person.centre_id]
        return f"You're linked as {centre.name} staff. Send /reset to release this centre.", []
    if person is not None and person.role in ("family", "coord"):
        role = "the family contact" if person.role == "family" else "the coordinator"
        return f"You're linked as {role}.", []
    if chat_id in _onboarding:  # resume the half-finished questions
        text, buttons = question(_onboarding[chat_id]["step"])
        return "Let's carry on where you left off. " + text, buttons
    if person is not None and person.role == "donor" and person.profile is not None:
        if person.opted_out:
            return ("Your donor profile is set up and linked, but you've opted out (STOP), so you won't get "
                    "requests. Send /reset and join again to opt back in.", [])
        return "Your donor profile is already set up and linked. You're all set! Send /reset if you want to start over.", []
    note = " You're opted out (STOP); joining again opts you back in." if person is not None and person.opted_out else ""
    return ("Welcome to RaktTrace, a live demo of an agent that coordinates urgent blood requests. "
            "Join with a ready-made synthetic donor profile, or create your own in a few taps. "
            "Send /reset to start over, or /stop to stop requests." + note, choices())


def on_callback(chat_id: str, name: str, data: str) -> Reply | None:
    if data == "O:JOIN":
        donor_id, resumed = loop.join_demo(chat_id, name)
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
    loop.register_donor(chat_id, name, profile)
    return registered_text(profile, resumed=False), []


def on_text(chat_id: str, text: str) -> Reply | None:
    if chat_id in _onboarding:
        return "Please tap one of the buttons above, or send /start to begin again.", []
    loop.handle_inbound(Inbound(channel=Channel.TELEGRAM, sender_id=chat_id, text=text, at=store.state.clock.now))
    return None


def on_reset(chat_id: str) -> Reply:
    """Account-level: a staff chat releases its centre; a donor chat clears its donor profile. Never the scenario,
    never anyone else."""
    _onboarding.pop(chat_id, None)
    person = live.registry.identities.get(chat_id)
    if person is not None and person.role == "staff":
        centre = store.state.main.centres[person.centre_id]
        loop.reset_staff(chat_id)
        return (f"You're no longer linked as {centre.name} staff; its cards go back to the simulated staff. "
                "Open a centre's staff link to link again.", [])
    if person is not None and person.role in ("family", "coord"):
        return f"This chat is linked as {person.role}; /reset only clears donor and staff links.", []
    had_profile = loop.reset_donor(chat_id)
    head = "Your donor profile is cleared." if had_profile else "You don't have a donor profile yet."
    if person is not None and person.opted_out:
        head += " You're still opted out (STOP); joining again opts you back in."
    return head + " Choose how to take part:", choices()


def on_stop(chat_id: str) -> Reply:
    live.opt_out(chat_id)
    return "Done: you won't get requests any more. Tap \"Join the live demo\" after /start if you change your mind.", []


# --- Sending ---

def is_running() -> bool:
    return _app is not None and _loop is not None


def new_run() -> None:
    """A demo reset: cards sent before it can no longer act (their ids would point at the new run's objects)."""
    _cards.clear()


def is_current_card(chat_id: str, message_id: int | None) -> bool:
    return message_id is not None and (chat_id, message_id) in _cards


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
        elif any(b.id.startswith(AGENT_BUTTONS) for b in buttons):
            _cards.add((chat_id, future.result().message_id))

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


async def handle_reset(update, context) -> None:
    chat_id, _ = who(update)
    await reply(update, await asyncio.to_thread(locked, on_reset, chat_id))


async def handle_button(update, context) -> None:
    query = update.callback_query
    chat_id, name = who(update)
    data = query.data or ""
    if data.startswith(AGENT_BUTTONS) and not is_current_card(chat_id, query.message.message_id if query.message else None):
        await query.answer("This card is from an earlier demo run.")
        return
    await query.answer()
    await reply(update, await asyncio.to_thread(locked, on_callback, chat_id, name, data))


def text_step(chat_id: str, text: str):
    """Under the lock: onboarding chats get a nudge; otherwise (Inbound, pledge id, deadline) or None."""
    if chat_id in _onboarding:
        return on_text(chat_id, text)
    msg = Inbound(channel=Channel.TELEGRAM, sender_id=chat_id, text=text, at=store.state.clock.now)
    target = loop.text_target(msg)
    if target is None:
        loop.handle_inbound(msg)  # recorded only: there is nothing to answer
        return None
    return msg, *target


async def handle_text(update, context) -> None:
    """The reply is read (LLM or rules) outside store.lock, so a slow LLM never blocks the API or the clock."""
    chat_id, _ = who(update)
    step = await asyncio.to_thread(locked, text_step, chat_id, update.message.text or "")
    if step is None or isinstance(step[0], str):
        await reply(update, step)
        return
    msg, pledge_id, deadline = step
    reading = await asyncio.to_thread(llm.read_reply, msg.text, deadline, msg.at)
    await asyncio.to_thread(locked, loop.apply_text, msg, pledge_id, reading)


async def start() -> None:
    """Start long polling if a token is set. Any failure leaves the bot off; the sim channel carries everything."""
    global _app, _loop
    if not settings.telegram_bot_token:
        return
    try:
        app = Application.builder().token(settings.telegram_bot_token).build()
        app.add_handler(CommandHandler("start", handle_start))
        app.add_handler(CommandHandler("stop", handle_stop))
        app.add_handler(CommandHandler("reset", handle_reset))
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
