"""Simulated phones: an inbox per sim phone id."""

from rakt import store
from rakt.models import Contact, Message, Outgoing
from rakt.sim import bots


def phone_id(contact: Contact) -> str:
    return contact.phone or contact.chat_id or contact.name


def append(phone: str, message: Message) -> None:
    store.state.inbox.setdefault(phone, []).append(message)


def deliver(phone: str, message: Message, outgoing: Outgoing) -> None:
    """Show the message on the sim phone; the simulated person behind it may react."""
    append(phone, message)
    bots.react(outgoing)


def inbox(phone: str) -> list[Message]:
    return store.state.inbox.get(phone, [])
