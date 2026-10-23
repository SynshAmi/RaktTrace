"""Simulated phones (BUILD §5.3): every inbox the dashboard can show, and replies typed or tapped on them."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from rakt import llm, store
from rakt.agent import live, loop
from rakt.models import Channel, Inbound

router = APIRouter()


class ReplyBody(BaseModel):
    phone_id: str
    button_id: str | None = None
    text: str | None = Field(default=None, max_length=1000)


def phone_info(phone: str) -> tuple[str, str]:
    """(name, role) of an inbox: donor, staff, family or coordinator, sim or linked Telegram chat."""
    s = store.state.main
    if phone in s.donors:
        return s.donors[phone].display_name, "donor"
    if phone in s.centres:
        return f"{s.centres[phone].name} staff", "staff"
    person = live.registry.identities.get(phone)
    if person is not None:
        if person.role == "staff" and person.centre_id in s.centres:
            return f"{s.centres[person.centre_id].name} staff (Telegram)", "staff"
        if person.role == "donor":
            return f"{person.name} (Telegram)", "donor"
        return person.name, "coordinator" if person.role == "coord" else person.role
    if phone.startswith("family_"):
        return "Family", "family"
    return "Coordinator" if phone == "coordinator" else phone, "coordinator" if phone == "coordinator" else "donor"


@router.get("/sim/phones")
def phones() -> list[dict]:
    with store.lock:
        state = store.state
        result = []
        for phone, messages in state.inbox.items():
            name, role = phone_info(phone)
            shown = state.read_upto.get(phone, 0)
            unread = sum(1 for m in messages[shown:] if m.direction == "out")
            result.append({"id": phone, "name": name, "role": role, "unread": unread,
                           "last_at": messages[-1].at.isoformat() if messages else None})
        return result


@router.get("/sim/phones/{phone}/messages")
def messages(phone: str) -> list[dict]:
    with store.lock:
        state = store.state
        if phone not in state.inbox:
            raise HTTPException(404, f"No phone {phone}")
        state.read_upto[phone] = len(state.inbox[phone])
        return [m.model_dump(mode="json") for m in state.inbox[phone]]


def known_phone(phone: str) -> bool:
    s = store.state.main
    return phone in store.state.inbox or phone in s.donors or phone in s.centres or phone == "coordinator"


@router.post("/sim/reply")
def reply(body: ReplyBody) -> dict:
    if not body.button_id and not (body.text and body.text.strip()):
        raise HTTPException(422, "Send a button_id or some text")
    with store.lock:
        if not known_phone(body.phone_id):
            raise HTTPException(404, f"No phone {body.phone_id}")
        msg = Inbound(channel=Channel.SIM, sender_id=body.phone_id, button_id=body.button_id, text=body.text,
                      at=store.state.clock.now)
        if body.button_id:
            loop.handle_inbound(msg)
            return {"ok": True}
        target = loop.text_target(msg)
        if target is None:
            loop.handle_inbound(msg)  # recorded: nothing is waiting for an answer
            return {"ok": True}
    pledge_id, deadline = target
    reading = llm.read_reply(msg.text, deadline, msg.at)  # outside the lock: the LLM may be slow
    with store.lock:
        loop.apply_text(msg, pledge_id, reading)
    return {"ok": True}
