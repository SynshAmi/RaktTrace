"""Delivers outgoing messages (BUILD §5.4): Telegram for live contacts, the sim inbox for everyone else.

Every message is also kept in the inbox under the contact's id, so the dashboard can show it. A live contact whose
message can't go out on Telegram (bot off, network down) gets it on the sim phone instead. Never raises.
"""

from rakt import store
from rakt.channels import simulated, telegram_bot
from rakt.models import Channel, Message, Outgoing


def deliver(msg: Outgoing) -> Message:
    state = store.state
    state.message_seq += 1
    phone = simulated.phone_id(msg.to)
    live = msg.to.channel == Channel.TELEGRAM and msg.to.chat_id is not None
    message = Message(
        id=f"m_{state.message_seq}", at=state.clock.now, direction="out",
        channel=Channel.TELEGRAM if live else Channel.SIM, to_name=msg.to.name, request_id=msg.request_id,
        kind=msg.kind, body=msg.body, buttons=msg.buttons,
    )
    if live and telegram_bot.send(msg.to.chat_id, msg.body, msg.buttons, on_fail=lambda: mirror(phone, message)):
        simulated.append(phone, message)  # a record for the dashboard; simulated people never react to it
    elif live:
        mirror(phone, message)
    else:
        simulated.deliver(phone, message, msg)
    return message


def mirror(phone: str, message: Message) -> None:
    """A Telegram message that couldn't be sent shows on the sim phone instead."""
    with store.lock:
        simulated.append(phone, message.model_copy(update={"channel": Channel.SIM}))
