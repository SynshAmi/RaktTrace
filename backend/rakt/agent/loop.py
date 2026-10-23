"""The agent loop (AGENT §1): apply an event, re-plan, act, log. Entry points per BUILD §5.4."""

import random
from datetime import datetime, timedelta

from rakt import config, llm, store
from rakt.agent import messages, planner
from rakt.agent.planner import AskStock, FixCentre, Invite, Plan, Promote, Release, SetStatus
from rakt.channels import router
from rakt.clock import Timer
from rakt.domain.geo import km, travel_min
from rakt.domain.timing import donor_timing, stock_ready_at
from rakt.models import (
    Decision, Inbound, Intent, Message, Pledge, PledgeStatus, Product, ReplyRead, Reservation, ReservationStatus,
)

R = ReservationStatus
S = PledgeStatus
AWAITING_REPLY = {S.INVITED, S.NO_REPLY}


def start(request_id: str) -> None:
    replan(request_id, "new request")


def replan(request_id: str, trigger: str, event_changed_state: bool = False) -> Plan:
    """Re-plan after an event. A decision is logged if the plan acts or the event itself changed state."""
    state = store.state
    s, now = state.main, state.clock.now
    result = planner.plan(s, request_id, now)
    request = s.requests[request_id]
    for action in result.actions:
        if isinstance(action, AskStock):
            ask_stock(request_id, action)
        elif isinstance(action, Release):
            release(s.reservations[action.reservation_id])
        elif isinstance(action, FixCentre):
            request.collection_centre_id = action.centre_id
        elif isinstance(action, Invite):
            invite(request_id, action)
        elif isinstance(action, Promote):
            promote(s.pledges[action.pledge_id])
        elif isinstance(action, SetStatus):
            request.status = action.status
    if result.actions or event_changed_state:
        s.decisions.append(Decision(
            id=s.next_id("dec"), request_id=request_id, at=now, trigger=trigger, p_before=result.p_before,
            p_after=result.p_after, status=request.status, actions=[describe(a, s) for a in result.actions],
            summary=result.summary or "Nothing new to do.",
        ))
    return result


def describe(action, s) -> str:
    if isinstance(action, AskStock):
        return f"ask {s.centres[action.centre_id].name}: {action.units} {action.group}"
    if isinstance(action, Release):
        return f"release {s.centres[s.reservations[action.reservation_id].centre_id].name}"
    if isinstance(action, FixCentre):
        return f"collection centre {s.centres[action.centre_id].name}"
    if isinstance(action, Invite):
        return f"invite wave {action.wave}: {len(action.donor_ids)} donors (k* = {action.k_star})"
    if isinstance(action, Promote):
        return f"promote {s.donors[s.pledges[action.pledge_id].donor_id].display_name}"
    return f"status {action.status}"


# --- Acting ---

def ask_stock(request_id: str, ask: AskStock) -> None:
    state = store.state
    s, now = state.main, state.clock.now
    request = s.requests[request_id]
    res = Reservation(id=s.next_id("res"), request_id=request_id, centre_id=ask.centre_id, group=ask.group,
                      units_asked=ask.units, listed_at=ask.listed_at, asked_at=now)
    s.reservations[res.id] = res
    centre, hospital = s.centres[ask.centre_id], s.hospitals[request.hospital_id]
    state.clock.schedule(now + timedelta(minutes=config.STOCK_REPLY_TIMEOUT_MIN), "stock_timeout", request_id,
                         {"reservation_id": res.id})
    router.deliver(messages.staff_hold(request, res, centre, hospital))


def release(res: Reservation) -> None:
    s = store.state.main
    res.status = R.RELEASED
    router.deliver(messages.staff_release(s.requests[res.request_id], s.centres[res.centre_id]))


def invite(request_id: str, action: Invite) -> None:
    state = store.state
    s, now = state.main, state.clock.now
    request = s.requests[request_id]
    centre, hospital = s.centres[request.collection_centre_id], s.hospitals[request.hospital_id]
    for donor_id, why in zip(action.donor_ids, action.whys):
        donor = s.donors[donor_id]
        pledge = Pledge(id=s.next_id("pl"), request_id=request_id, donor_id=donor_id, wave=action.wave,
                        invited_at=now, why=why)
        s.pledges[pledge.id] = pledge
        donor.invites.append(now)
        timing = donor_timing(donor, centre, hospital, request.product, request.deadline_at, now)
        state.clock.schedule(now + timedelta(minutes=config.DONOR_REPLY_TIMEOUT_MIN), "donor_timeout", request_id,
                             {"pledge_id": pledge.id})
        router.deliver(messages.donor_invite(request, pledge, donor, centre, km(donor, centre), timing.latest_arrival))


def promote(pledge: Pledge) -> None:
    state = store.state
    s, now = state.main, state.clock.now
    s.promotions[pledge.id] = now
    request = s.requests[pledge.request_id]
    centre, donor = s.centres[request.collection_centre_id], s.donors[pledge.donor_id]
    arrival = timing_for(pledge).latest_arrival
    state.clock.schedule(now + timedelta(minutes=config.PROMOTE_TIMEOUT_MIN), "promote_timeout", request.id,
                         {"pledge_id": pledge.id})
    router.deliver(messages.donor_promote(request, pledge, donor, centre, arrival))


def timing_for(pledge: Pledge):
    s, now = store.state.main, store.state.clock.now
    request = s.requests[pledge.request_id]
    return donor_timing(s.donors[pledge.donor_id], s.centres[request.collection_centre_id],
                        s.hospitals[request.hospital_id], request.product, request.deadline_at, now,
                        available_from=pledge.available_from, replied=True)


def make_active(pledge: Pledge) -> None:
    """ACTIVE: booking code + directions to the donor, an incoming card to the collection centre."""
    s, now = store.state.main, store.state.clock.now
    request = s.requests[pledge.request_id]
    centre, hospital, donor = s.centres[request.collection_centre_id], s.hospitals[request.hospital_id], \
        s.donors[pledge.donor_id]
    pledge.status = S.ACTIVE
    pledge.booking_code = pledge.booking_code or str(random.Random(f"{request.id}:{pledge.id}").randint(1000, 9999))
    start = max(pledge.available_from or now, now)
    eta = start + timedelta(minutes=travel_min(donor, centre))
    router.deliver(messages.donor_go(request, pledge, donor, centre, timing_for(pledge).latest_arrival))
    router.deliver(messages.staff_incoming(request, pledge, donor, centre, hospital, eta))


# --- Events ---

def on_timer(timer: Timer) -> None:
    """Clock handler: pass to Clock.step / Clock.advance."""
    s = store.state.main
    if timer.kind == "stock_timeout":
        res = s.reservations[timer.payload["reservation_id"]]
        if res.status == R.PENDING:
            res.status = R.EXPIRED
            replan(res.request_id, f"{s.centres[res.centre_id].name} didn't answer in time", True)
    elif timer.kind == "donor_timeout":
        pledge = s.pledges[timer.payload["pledge_id"]]
        if pledge.status == S.INVITED:
            pledge.status = S.NO_REPLY
            replan(pledge.request_id, f"{name(pledge)} didn't reply in {config.DONOR_REPLY_TIMEOUT_MIN} min", True)
    elif timer.kind == "promote_timeout":
        pledge = s.pledges[timer.payload["pledge_id"]]
        if s.promotions.pop(pledge.id, None) and pledge.status == S.STANDBY:
            pledge.status = S.RELEASED
            replan(pledge.request_id, f"{name(pledge)} didn't answer the call to go", True)
    elif timer.kind == "sim_inbound":
        handle_inbound(Inbound(at=store.state.clock.now, **timer.payload))


def name(pledge: Pledge) -> str:
    return store.state.main.donors[pledge.donor_id].display_name


def handle_inbound(msg: Inbound) -> None:
    """Called by the bot and by POST /api/sim/reply."""
    button = msg.button_id or ""
    kind, _, rest = button.partition(":")
    if kind == "R":
        record_inbound(msg, "button")
        reservation_id, _, choice = rest.partition(":")
        stock_reply(reservation_id, choice, msg.sender_id)
    elif kind == "P":
        record_inbound(msg, "button")
        pledge_id, _, choice = rest.partition(":")
        donor_button(pledge_id, choice, msg.sender_id)
    elif kind == "V":
        record_inbound(msg, "button")
        pledge_id, _, choice = rest.partition(":")
        visit_tap(pledge_id, choice, msg.sender_id)
    elif msg.text:
        donor_text(msg)


def record_inbound(msg: Inbound, read_by: str | None) -> None:
    state = store.state
    state.message_seq += 1
    state.inbox.setdefault(msg.sender_id, []).append(Message(
        id=f"m_{state.message_seq}", at=msg.at, direction="in", channel=msg.channel, to_name="RaktTrace",
        kind="reply", body=msg.text or msg.button_id or "", read_by=read_by,
    ))


# --- Staff: stock ---

def stock_reply(reservation_id: str, choice: str, sender_id: str) -> None:
    """Staff tap: ALL, NONE, SOME (then N{k}). Units are kept in arrival order, trimmed to what's needed."""
    state = store.state
    s = state.main
    res = s.reservations.get(reservation_id)
    if res is None or res.status != R.PENDING:
        return  # late answer for a released or expired hold
    centre = s.centres[res.centre_id]
    if sender_id not in (centre.contact.phone, centre.contact.chat_id):
        return
    request = s.requests[res.request_id]
    if choice == "SOME":
        router.deliver(messages.staff_hold_count(request, res, centre))
        return

    offered = stock_offer(choice, res.units_asked)
    if offered is None:
        return
    if offered <= 0:
        res.status = R.NONE
        replan(request.id, f"{centre.name} has none", True)
        return
    keep = min(offered, res.units_asked, request.units - planner.reserved_units(s, request))
    if keep <= 0:
        release(res)
    else:
        res.status, res.units_reserved = R.RESERVED, keep
        res.ready_at = stock_ready_at(centre, s.hospitals[request.hospital_id], state.clock.now, reserved=True)
    kept = f"kept {keep}" if keep < offered else f"reserved {keep}"
    replan(request.id, f"{centre.name} offered {offered}; {kept}", True)


def stock_offer(choice: str, units_asked: int) -> int | None:
    if choice == "ALL":
        return units_asked
    if choice == "NONE":
        return 0
    if choice.startswith("N") and choice[1:].isdigit():
        return int(choice[1:])
    return None  # unknown button


# --- Donors ---

def sender_owns(pledge: Pledge, sender_id: str) -> bool:
    contact = store.state.main.donors[pledge.donor_id].contact
    return sender_id in (contact.phone, contact.chat_id)


def donor_button(pledge_id: str, choice: str, sender_id: str) -> None:
    s = store.state.main
    pledge = s.pledges.get(pledge_id)
    if pledge is None or not sender_owns(pledge, sender_id):
        return
    if pledge.status in AWAITING_REPLY:
        reading = {"YES": Intent.YES, "NO": Intent.NO, "STOP": Intent.STOP}.get(choice)
        if reading:
            donor_reply(pledge, ReplyRead(intent=reading, confidence=1.0), None)
    elif pledge.status == S.STANDBY:
        if choice == "OMW" and pledge.id in s.promotions:
            s.promotions.pop(pledge.id)
            make_active(pledge)
            replan(pledge.request_id, f"{name(pledge)} is going now", True)
        elif choice == "CANT":
            s.promotions.pop(pledge.id, None)
            pledge.status = S.RELEASED
            replan(pledge.request_id, f"{name(pledge)} (standby) isn't available", True)
    elif pledge.status == S.ACTIVE and choice == "CANT":
        pledge.status = S.NO_SHOW
        replan(pledge.request_id, f"{name(pledge)} can't make it", True)


def donor_text(msg: Inbound) -> None:
    """Free text from a donor: the reader decides what it says; the planner decides what happens."""
    s = store.state.main
    awaiting = [p for p in s.pledges.values() if p.status in AWAITING_REPLY and sender_owns(p, msg.sender_id)]
    if not awaiting:
        record_inbound(msg, None)
        return
    pledge = max(awaiting, key=lambda p: p.invited_at)
    request = s.requests[pledge.request_id]
    reading = llm.read_reply(msg.text, request.deadline_at, msg.at)
    if reading.read_by == "llm" and reading.confidence < config.LLM_MIN_CONFIDENCE:
        reading = ReplyRead(intent=Intent.UNCLEAR, confidence=reading.confidence, read_by="llm")
    record_inbound(msg, reading.read_by)
    donor_reply(pledge, reading, msg.text)


def donor_reply(pledge: Pledge, reading: ReplyRead, text: str | None) -> None:
    state = store.state
    s, now = state.main, state.clock.now
    request, donor = s.requests[pledge.request_id], s.donors[pledge.donor_id]
    if reading.intent == Intent.UNCLEAR:
        pledge.reply_text = text
        router.deliver(messages.donor_text("donor_unclear", request, donor))
        replan(request.id, f"{donor.display_name}'s reply was unclear", True)
        return

    pledge.replied_at, pledge.reply_text = now, text
    if reading.intent == Intent.NO:
        pledge.status = S.DECLINED
        router.deliver(messages.donor_text("donor_thanks_no", request, donor))
    elif reading.intent == Intent.STOP:
        pledge.status = S.OPTED_OUT
        donor.opted_out = True
    else:
        pledge.available_from = reading.available_from
        role = planner.role_for_yes(s, request, pledge, now, reading.available_from)
        if role == S.TOO_LATE:
            pledge.status = S.TOO_LATE
            router.deliver(messages.donor_text("donor_too_late", request, donor))
        elif role == S.ACTIVE:
            make_active(pledge)
        elif role == S.STANDBY:
            pledge.status = S.STANDBY
            router.deliver(messages.donor_standby(request, pledge, donor, timing_for(pledge).latest_arrival))
        else:
            pledge.status = S.RELEASED
            router.deliver(messages.donor_text("donor_not_needed", request, donor))
    replan(request.id, f"{donor.display_name} replied: {pledge.status}", True)


# --- Staff: donor visit ---

def visit_tap(pledge_id: str, choice: str, sender_id: str) -> None:
    """Arrived / Didn't show on ACTIVE; Collected / Deferred on ARRIVED. Anything else is ignored."""
    state = store.state
    s, now = state.main, state.clock.now
    pledge = s.pledges.get(pledge_id)
    if pledge is None:
        return
    request = s.requests[pledge.request_id]
    centre, donor = s.centres[request.collection_centre_id], s.donors[pledge.donor_id]
    if sender_id not in (centre.contact.phone, centre.contact.chat_id):
        return

    if pledge.status == S.ACTIVE and choice == "ARRIVED":
        pledge.status = S.ARRIVED
        router.deliver(messages.staff_visit(request, pledge, donor, centre))
    elif pledge.status == S.ACTIVE and choice == "NOSHOW":
        pledge.status = S.NO_SHOW
    elif pledge.status == S.ARRIVED and choice == "COLLECTED":
        pledge.status = S.COLLECTED
        hospital = s.hospitals[request.hospital_id]
        pledge.ready_at = now + timedelta(minutes=config.TEST_MIN[request.product] + travel_min(centre, hospital))
        record_donation(donor, request.product, now)
        router.deliver(messages.donor_text("donor_thanks_collected", request, donor,
                                           next_date=next_donation(donor, request.product, now).strftime("%d %b")))
    elif pledge.status == S.ARRIVED and choice == "DEFERRED":
        pledge.status = S.DEFERRED
        donor.deferred_until = now + timedelta(days=config.DEFAULT_DEFERRAL_DAYS)
    else:
        return
    replan(request.id, f"{centre.name}: {donor.display_name} {pledge.status}", True)


def record_donation(donor, product: Product, at: datetime) -> None:
    if product == Product.PRBC:
        donor.last_whole_blood_at = at
    else:
        donor.apheresis_dates.append(at)


def next_donation(donor, product: Product, at: datetime) -> datetime:
    """DOMAIN_RULES §2: after whole blood 90/120 days; after platelets the earliest next donation (48 h)."""
    if product == Product.PRBC:
        return at + timedelta(days=config.WHOLE_BLOOD_INTERVAL_DAYS[donor.sex])
    return at + timedelta(hours=config.APHERESIS_GAP_H)


def link_chat(start_param: str, chat_id: str, display_name: str) -> str:
    return "RaktTrace: chat linking isn't available yet."
