"""Simulated people. They answer from the request's pre-drawn truth (AGENT §9), like a person tapping a button."""

from datetime import timedelta

from rakt import config, store
from rakt.models import Channel, Outgoing


def react(outgoing: Outgoing) -> None:
    if outgoing.kind == "staff_hold":
        answer_stock(outgoing)


def answer_stock(outgoing: Outgoing) -> None:
    state = store.state
    s = state.main
    reservation_id = outgoing.buttons[0].id.split(":")[1] if outgoing.buttons else None
    res = s.reservations.get(reservation_id)
    if res is None:
        return
    listing = next((x for x in s.stock if (x.centre_id, x.product, x.group)
                    == (res.centre_id, s.requests[res.request_id].product, res.group)), None)
    true_units = listing.true_units if listing else 0

    if true_units >= res.units_asked:
        choice = "ALL"
    elif true_units > 0:
        choice = f"N{true_units}"
    else:
        choice = "NONE"

    draws = state.draws.get(res.request_id)
    delay = draws.staff_delay_min[res.centre_id] if draws else sum(config.SIM_STAFF_REPLY_MIN) / 2
    state.clock.schedule(
        state.clock.now + timedelta(minutes=delay), "sim_inbound", res.request_id,
        {"channel": Channel.SIM, "sender_id": res.centre_id, "button_id": f"R:{reservation_id}:{choice}"},
    )
