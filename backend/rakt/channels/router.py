"""Delivers outgoing messages (BUILD §5.4). Phase 1 stub: everything goes to the sim inbox."""

from rakt import store
from rakt.channels import simulated
from rakt.models import Channel, Message, Outgoing


def deliver(msg: Outgoing) -> Message:
    """Never raises."""
    state = store.state
    state.message_seq += 1
    message = Message(
        id=f"m_{state.message_seq}", at=state.clock.now, direction="out", channel=Channel.SIM,
        to_name=msg.to.name, request_id=msg.request_id, kind=msg.kind, body=msg.body, buttons=msg.buttons,
    )
    simulated.deliver(simulated.phone_id(msg.to), message, msg)
    return message
