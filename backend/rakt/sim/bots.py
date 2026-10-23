"""Simulated people. They answer from the request's pre-drawn truth (AGENT §9), like a person tapping or typing.

Only sim contacts react; real Telegram people answer for themselves.
"""

from datetime import timedelta

from rakt import config, store
from rakt.domain.geo import travel_min
from rakt.models import Channel, Outgoing
from rakt.sim.world import DonorLatent, load_phrases

PHRASES = {p["id"]: p["text"] for p in load_phrases()}


def react(outgoing: Outgoing) -> None:
    if outgoing.to.channel != Channel.SIM or not outgoing.buttons:
        return
    handlers = {
        "staff_hold": answer_stock,
        "donor_invite": answer_invite,
        "donor_promote": answer_promote,
        "staff_incoming": answer_incoming,
        "staff_visit": answer_visit,
        "staff_ready": answer_ready,
    }
    if outgoing.kind in handlers:
        handlers[outgoing.kind](outgoing)


def target_id(outgoing: Outgoing) -> str:
    """The reservation or pledge id inside the first button id, e.g. 'P:pl_3:YES' → 'pl_3'."""
    return outgoing.buttons[0].id.split(":")[1]


def later(minutes: float, sender_id: str, button_id: str | None = None, text: str | None = None,
          request_id: str | None = None) -> None:
    clock = store.state.clock
    clock.schedule(clock.now + timedelta(minutes=minutes), "sim_inbound", request_id,
                   {"channel": Channel.SIM, "sender_id": sender_id, "button_id": button_id, "text": text})


def answer_stock(outgoing: Outgoing) -> None:
    state = store.state
    s = state.main
    res = s.reservations.get(target_id(outgoing))
    if res is None:
        return
    listing = next((x for x in s.stock if (x.centre_id, x.product, x.group)
                    == (res.centre_id, s.requests[res.request_id].product, res.group)), None)
    true_units = listing.true_units if listing else 0
    choice = "ALL" if true_units >= res.units_asked else f"N{true_units}" if true_units > 0 else "NONE"
    draws = state.draws.get(res.request_id)
    delay = draws.staff_delay_min[res.centre_id] if draws else sum(config.SIM_STAFF_REPLY_MIN) / 2
    later(delay, res.centre_id, button_id=f"R:{res.id}:{choice}", request_id=res.request_id)


def latent_for(pledge_id: str) -> DonorLatent | None:
    """The scenario script by invite order of simulated donors, else the request's pre-drawn outcome."""
    state = store.state
    s = state.main
    pledge = s.pledges[pledge_id]
    sim_pledges = [p for p in s.pledges.values()
                   if p.request_id == pledge.request_id and not s.donors[p.donor_id].telegram_demo]
    order = [p.id for p in sim_pledges].index(pledge_id) + 1
    scenario = state.scenario
    if scenario is not None:
        for scripted in scenario.donor_script:
            if scripted.invite_order == order:
                return scripted.latent()
    draws = state.draws.get(pledge.request_id)
    return draws.donors.get(pledge.donor_id) if draws else None


def answer_invite(outgoing: Outgoing) -> None:
    state = store.state
    pledge_id = target_id(outgoing)
    pledge = state.main.pledges.get(pledge_id)
    latent = latent_for(pledge_id) if pledge else None
    if latent is None:
        return
    state.sim_latent[pledge_id] = latent
    if latent.reply_delay_min is not None and latent.phrase_id:
        later(latent.reply_delay_min, pledge.donor_id, text=PHRASES[latent.phrase_id], request_id=pledge.request_id)


def answer_promote(outgoing: Outgoing) -> None:
    state = store.state
    pledge_id = target_id(outgoing)
    pledge, latent = state.main.pledges.get(pledge_id), state.sim_latent.get(pledge_id)
    if pledge is None or latent is None or latent.reply_delay_min is None:
        return  # stays silent; the promotion times out
    choice = "OMW" if latent.will_show else "CANT"
    later(latent.reply_delay_min, pledge.donor_id, button_id=f"P:{pledge_id}:{choice}", request_id=pledge.request_id)


def answer_incoming(outgoing: Outgoing) -> None:
    """Centre staff tap Arrived when the donor walks in, or Didn't show once the grace period passes."""
    state = store.state
    s, now = state.main, state.clock.now
    pledge_id = target_id(outgoing)
    pledge, latent = s.pledges.get(pledge_id), state.sim_latent.get(pledge_id)
    if pledge is None or latent is None:
        return
    request = s.requests[pledge.request_id]
    centre = s.centres[request.collection_centre_id]
    start = max(pledge.available_from or now, now)
    arrive_in = (start - now) / timedelta(minutes=1) + travel_min(s.donors[pledge.donor_id], centre)
    if latent.will_show:
        later(arrive_in, centre.id, button_id=f"V:{pledge_id}:ARRIVED", request_id=request.id)
    else:
        later(arrive_in + config.STAFF_GRACE_MIN, centre.id, button_id=f"V:{pledge_id}:NOSHOW", request_id=request.id)


def answer_visit(outgoing: Outgoing) -> None:
    """After screening and collection: Collected if the donor passes, else Deferred."""
    state = store.state
    s = state.main
    pledge_id = target_id(outgoing)
    pledge, latent = s.pledges.get(pledge_id), state.sim_latent.get(pledge_id)
    if pledge is None or latent is None:
        return
    request = s.requests[pledge.request_id]
    choice = "COLLECTED" if latent.will_pass else "DEFERRED"
    later(config.VISIT_MIN[request.product], request.collection_centre_id, button_id=f"V:{pledge_id}:{choice}",
          request_id=request.id)


def answer_ready(outgoing: Outgoing) -> None:
    """The sim has no post-collection failures (AGENT §10): staff confirm after their usual reply delay."""
    state = store.state
    button = outgoing.buttons[0].id  # D:{P|R}:{id}:READY
    draws = state.draws.get(outgoing.request_id)
    centre_id = outgoing.to.phone
    delay = draws.staff_delay_min.get(centre_id, sum(config.SIM_STAFF_REPLY_MIN) / 2) if draws \
        else sum(config.SIM_STAFF_REPLY_MIN) / 2
    later(delay, centre_id, button_id=button, request_id=outgoing.request_id)
