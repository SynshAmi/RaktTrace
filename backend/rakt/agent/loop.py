"""The agent loop (AGENT §1): apply an event, re-plan, act, log. Entry points per BUILD §5.4."""

import random
from datetime import datetime, timedelta

from rakt import config, llm, store
from rakt.agent import messages, planner
from rakt.agent.escalation import Alert, Fail, Widen
from rakt.agent.planner import (
    ACTIVE_LIKE, AskStock, FixCentre, Invite, NotifyFamily, Plan, Promote, Release, SetStatus, StandDown,
)
from rakt.channels import router
from rakt.clock import Timer
from rakt.domain.geo import km, travel_min
from rakt.domain.timing import donor_timing, stock_ready_at
from rakt.models import (
    BloodGroup, Button, Channel, Contact, Decision, Inbound, Intent, Message, Pledge, PledgeStatus, Product, ReplyRead,
    Request, RequestStatus, Reservation, ReservationStatus,
)

R = ReservationStatus
S = PledgeStatus
AWAITING_REPLY = {S.INVITED, S.NO_REPLY}
OPEN_STATUSES = {RequestStatus.OPEN, RequestStatus.COVERED, RequestStatus.SECURED}
COORDINATOR = Contact(name="Coordinator", channel=Channel.SIM, phone="coordinator")


def start(request_id: str) -> None:
    state = store.state
    request = state.main.requests[request_id]
    state.clock.schedule(request.created_at + (request.deadline_at - request.created_at) / 2, "halftime", request_id)
    state.clock.schedule(request.deadline_at, "deadline", request_id)
    replan(request_id, "new request")


def create_request(group: BloodGroup, product: Product, units: int, hospital_id: str, deadline_at: datetime,
                   family: Contact | None = None) -> tuple[str, bool]:
    """A new request, or (open request id, True) when it duplicates an open one (AGENT §5.2): no new search."""
    state = store.state
    s, now = state.main, state.clock.now
    for existing in s.requests.values():
        if existing.status in OPEN_STATUSES and (existing.group, existing.product, existing.hospital_id) \
                == (group, product, hospital_id):
            s.decisions.append(Decision(
                id=s.next_id("dec"), request_id=existing.id, at=now, trigger="duplicate plea",
                p_before=0.0, p_after=0.0, status=existing.status, actions=["merge"],
                summary=f"A duplicate plea was merged into {existing.id}; its details stay unchanged.",
            ))
            return existing.id, True
    number = random.Random(f"{now.isoformat()}:{len(s.requests)}").randint(1000, 9999)
    while f"RT-{number}" in s.requests:
        number += 1
    request = Request(id=f"RT-{number}", group=group, product=product, units=units, hospital_id=hospital_id,
                      deadline_at=deadline_at, created_at=now, radius_km=config.SEARCH_RADII_KM[0], family=family)
    s.requests[request.id] = request
    start(request.id)
    return request.id, False


def cancel(request_id: str) -> None:
    """Coordinator cancels: holds released, donors stood down (PRODUCT §3.7)."""
    s = store.state.main
    request = s.requests[request_id]
    if request.status not in OPEN_STATUSES:
        return
    for res in s.reservations.values():
        if res.request_id == request_id and res.status in (R.PENDING, R.RESERVED):
            release(res)
    for pledge in s.pledges.values():
        if pledge.request_id == request_id and pledge.status in (S.INVITED, S.NO_REPLY, S.STANDBY, S.ACTIVE):
            stand_down(pledge, "closed")
    request.status = RequestStatus.CANCELLED
    s.decisions.append(Decision(
        id=s.next_id("dec"), request_id=request_id, at=store.state.clock.now, trigger="cancelled by the coordinator",
        p_before=0.0, p_after=0.0, status=request.status, actions=["cancel"],
        summary="Cancelled; holds released and donors stood down.",
    ))


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
        elif isinstance(action, StandDown):
            stand_down(s.pledges[action.pledge_id], action.reason)
        elif isinstance(action, NotifyFamily):
            notify_family(request, action.kind)
        elif isinstance(action, Widen):
            request.radius_km = action.radius_km
            request.escalation_level = max(request.escalation_level, 1)
        elif isinstance(action, Alert):
            alert(request, action, result.p_after)
        elif isinstance(action, Fail):
            fail(request, action)
        elif isinstance(action, SetStatus):
            request.status = action.status
    if result.actions or event_changed_state:
        s.decisions.append(Decision(
            id=s.next_id("dec"), request_id=request_id, at=now, trigger=trigger, p_before=result.p_before,
            p_after=result.p_after, status=request.status, actions=[describe(a, s) for a in result.actions],
            summary=result.summary or "Nothing new to do.",
        ))
    widened = [a for a in result.actions if isinstance(a, Widen)]
    if widened:
        replan(request_id, f"search widened to {widened[-1].radius_km:g} km")
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
    if isinstance(action, StandDown):
        return f"stand down {s.donors[s.pledges[action.pledge_id].donor_id].display_name}"
    if isinstance(action, NotifyFamily):
        return f"family: {action.kind}"
    if isinstance(action, Widen):
        return f"widen to {action.radius_km:g} km"
    if isinstance(action, Alert):
        return "L2 alert"
    if isinstance(action, Fail):
        return "failed"
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


def stand_down(pledge: Pledge, reason: str) -> None:
    s = store.state.main
    s.promotions.pop(pledge.id, None)
    pledge.status = S.RELEASED
    kind = "donor_stand_down" if reason == "secured" else "donor_closed"
    router.deliver(messages.donor_text(kind, s.requests[pledge.request_id], s.donors[pledge.donor_id]))


def unit_places(request: Request) -> tuple[list[str], datetime | None]:
    """Centres holding this request's certain units, and when the last of them is ready."""
    s = store.state.main
    names, ready = [], []
    for r in s.reservations.values():
        if r.request_id == request.id and r.status in (R.RESERVED, R.READY):
            names.append(s.centres[r.centre_id].name)
            ready.append(r.ready_at)
    for p in s.pledges.values():
        if p.request_id == request.id and p.status in (S.COLLECTED, S.READY):
            names.append(s.centres[request.collection_centre_id].name)
            ready.append(p.ready_at)
    ready = [t for t in ready if t]
    return list(dict.fromkeys(names)), max(ready) if ready else None


def notify_family(request: Request, kind: str) -> None:
    s = store.state.main
    if not request.family or (request.id, kind) in s.notified:
        return
    s.notified.add((request.id, kind))
    centres, ready_by = unit_places(request)
    if kind == "secured":
        router.deliver(messages.family_secured(request, centres, ready_by or store.state.clock.now))
    else:
        router.deliver(messages.family_fulfilled(request, centres))


def brief_facts(request: Request, p: float, call_list: list[dict]) -> dict:
    """Facts only (AGENT §7.3); never names or phone numbers."""
    s = store.state.main
    asked = [r for r in s.reservations.values() if r.request_id == request.id]
    pledges = [x for x in s.pledges.values() if x.request_id == request.id]
    certain = planner.certain_units(s, request, store.state.clock.now)
    return {
        "status": request.status.value,
        "p": round(100 * p),
        "units": request.units,
        "deadline": messages.when(request.deadline_at),
        "tried": (f"asked {len(asked)} centre(s) ({sum(r.units_reserved for r in asked)} unit(s) reserved), "
                  f"invited {len(pledges)} donor(s), searched {request.radius_km:g} km"),
        "active": sum(x.status in ACTIVE_LIKE for x in pledges),
        "standby": sum(x.status == S.STANDBY for x in pledges),
        "missing": max(0, request.units - certain),
        "call_list": [c["centre"] for c in call_list],
        "at_max_radius": request.radius_km >= config.SEARCH_RADII_KM[-1],
        "rare_group": request.group.endswith("NEG"),
    }


def alert(request: Request, action: Alert, p: float) -> None:
    """L2: brief + call list to the coordinator; O− unlocked (escalation level 2)."""
    s = store.state.main
    request.escalation_level = 2
    call_list = list(action.call_list)
    request.brief = llm.write_brief(brief_facts(request, p, call_list))
    s.call_lists[request.id] = call_list
    s.notified.add((request.id, "alert"))
    router.deliver(messages.coord_alert(request, COORDINATOR, p, request.brief, call_list))


def fail(request: Request, action: Fail) -> None:
    s = store.state.main
    if (request.id, "failed") in s.notified:
        return
    s.notified.add((request.id, "failed"))
    tried = brief_facts(request, 0.0, [])["tried"]
    router.deliver(messages.coord_failed(request, COORDINATOR, action.ready, f"Tried: {tried}."))


def expect_tap(request: Request, card: str, target: str, target_id: str, status: str, expected_at: datetime) -> None:
    """Reminder at expected + STAFF_GRACE_MIN, overdue (→ L2) at + 2 × STAFF_GRACE_MIN, if nobody tapped."""
    clock = store.state.clock
    payload = {"card": card, "target": target, "id": target_id, "status": status}
    clock.schedule(expected_at + timedelta(minutes=config.STAFF_GRACE_MIN), "staff_check", request.id,
                   {**payload, "stage": "remind"})
    clock.schedule(expected_at + timedelta(minutes=2 * config.STAFF_GRACE_MIN), "staff_check", request.id,
                   {**payload, "stage": "overdue"})


def card_target(target: str, target_id: str):
    s = store.state.main
    return s.pledges.get(target_id) if target == "P" else s.reservations.get(target_id)


def open_card(request: Request, card: str, target: str, target_id: str) -> tuple[str, list[Button], object]:
    """(subject, buttons, centre) of a staff card that is still waiting for a tap."""
    s = store.state.main
    if target == "R":
        res = s.reservations[target_id]
        centre = s.centres[res.centre_id]
        return f"the reserved unit at {centre.name}", messages.ready_buttons("R", target_id), centre
    pledge = s.pledges[target_id]
    centre = s.centres[request.collection_centre_id]
    subject = f"booking code {pledge.booking_code}"
    if card == "incoming":
        buttons = [Button(id=f"V:{target_id}:ARRIVED", title="Arrived"),
                   Button(id=f"V:{target_id}:NOSHOW", title="Didn't show")]
    elif card == "visit":
        buttons = [Button(id=f"V:{target_id}:COLLECTED", title="Collected"),
                   Button(id=f"V:{target_id}:DEFERRED", title="Deferred")]
    else:
        buttons = messages.ready_buttons("P", target_id)
    return subject, buttons, centre


def schedule_ready_card(request: Request, target: str, target_id: str, ready_at: datetime) -> None:
    store.state.clock.schedule(ready_at, "staff_ready", request.id, {"target": target, "id": target_id})


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
    expect_tap(request, "incoming", "P", pledge.id, S.ACTIVE.value, eta)


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
    elif timer.kind in ("deadline", "halftime"):
        replan(timer.request_id, "deadline reached" if timer.kind == "deadline" else "half the time has gone")
    elif timer.kind == "staff_ready":
        send_ready_card(timer)
    elif timer.kind == "staff_check":
        staff_check(timer)
    elif timer.kind == "sim_inbound":
        handle_inbound(Inbound(at=store.state.clock.now, **timer.payload))


def send_ready_card(timer: Timer) -> None:
    s = store.state.main
    request = s.requests[timer.request_id]
    target, target_id = timer.payload["target"], timer.payload["id"]
    item = card_target(target, target_id)
    waiting = S.COLLECTED if target == "P" else R.RESERVED
    if request.status not in OPEN_STATUSES or item is None or item.status != waiting:
        return
    centre = s.centres[item.centre_id] if target == "R" else s.centres[request.collection_centre_id]
    code = item.booking_code if target == "P" else None
    router.deliver(messages.staff_ready(request, centre, target, target_id, code))
    expect_tap(request, "ready", target, target_id, waiting.value, store.state.clock.now)


def staff_check(timer: Timer) -> None:
    s = store.state.main
    request = s.requests[timer.request_id]
    payload = timer.payload
    item = card_target(payload["target"], payload["id"])
    if request.status not in OPEN_STATUSES or item is None or item.status != payload["status"]:
        return  # tapped in time, or no longer relevant
    subject, buttons, centre = open_card(request, payload["card"], payload["target"], payload["id"])
    if payload["stage"] == "remind":
        router.deliver(messages.staff_reminder(request, centre, subject, buttons))
    else:
        s.overdue.add((request.id, f"{payload['card']}:{payload['id']}"))
        replan(request.id, f"{centre.name} hasn't tapped for {subject}", True)


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
    elif kind == "D":
        record_inbound(msg, "button")
        target, _, rest = rest.partition(":")
        target_id, _, choice = rest.partition(":")
        ready_tap(target, target_id, choice, msg.sender_id)
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
        schedule_ready_card(request, "R", res.id, res.ready_at)
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
        expect_tap(request, "visit", "P", pledge.id, S.ARRIVED.value,
                   now + timedelta(minutes=config.VISIT_MIN[request.product]))
    elif pledge.status == S.ACTIVE and choice == "NOSHOW":
        pledge.status = S.NO_SHOW
    elif pledge.status == S.ARRIVED and choice == "COLLECTED":
        pledge.status = S.COLLECTED
        hospital = s.hospitals[request.hospital_id]
        pledge.ready_at = now + timedelta(minutes=config.TEST_MIN[request.product] + travel_min(centre, hospital))
        record_donation(donor, request.product, now)
        schedule_ready_card(request, "P", pledge.id, pledge.ready_at)
        router.deliver(messages.donor_text("donor_thanks_collected", request, donor,
                                           next_date=next_donation(donor, request.product, now).strftime("%d %b")))
    elif pledge.status == S.ARRIVED and choice == "DEFERRED":
        pledge.status = S.DEFERRED
        donor.deferred_until = now + timedelta(days=config.DEFAULT_DEFERRAL_DAYS)
    else:
        return
    clear_overdue(request.id, pledge.id)
    replan(request.id, f"{centre.name}: {donor.display_name} {pledge.status}", True)


def clear_overdue(request_id: str, target_id: str) -> None:
    s = store.state.main
    s.overdue = {(rid, card) for rid, card in s.overdue if not (rid == request_id and card.endswith(f":{target_id}"))}


def ready_tap(target: str, target_id: str, choice: str, sender_id: str) -> None:
    """Ready for patient / Failed testing, from the centre holding the unit. Only staff can make a unit READY."""
    s = store.state.main
    item = card_target(target, target_id)
    if item is None or choice not in ("READY", "FAILED"):
        return
    request = s.requests[item.request_id]
    centre = s.centres[item.centre_id] if target == "R" else s.centres[request.collection_centre_id]
    if sender_id not in (centre.contact.phone, centre.contact.chat_id):
        return
    if target == "P" and item.status == S.COLLECTED:
        item.status = S.READY if choice == "READY" else S.FAILED_TEST
    elif target == "R" and item.status == R.RESERVED:
        item.status = R.READY if choice == "READY" else R.NONE  # a failed unit is no longer usable supply
        if choice == "FAILED":
            s.failed_reservations.add(item.id)  # not a "none" answer: the centre may be asked for another unit
    else:
        return
    clear_overdue(request.id, target_id)
    replan(request.id, f"{centre.name}: unit {'ready' if choice == 'READY' else 'failed testing'}", True)


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
