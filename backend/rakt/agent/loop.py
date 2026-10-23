"""The agent loop (AGENT §1): apply an event, re-plan, act, log. Entry points per BUILD §5.4."""

from datetime import timedelta

from rakt import config, store
from rakt.agent import messages, planner
from rakt.agent.planner import AskStock, Plan, Release, SetStatus
from rakt.channels import router
from rakt.clock import Timer
from rakt.domain.timing import stock_ready_at
from rakt.models import Decision, Inbound, Message, Reservation, ReservationStatus

R = ReservationStatus


def start(request_id: str) -> None:
    replan(request_id, "new request")


def replan(request_id: str, trigger: str, event_changed_state: bool = False) -> Plan:
    """Re-plan after an event. A decision is logged if the plan acts or the event itself changed state."""
    state = store.state
    s, now = state.main, state.clock.now
    result = planner.plan(s, request_id, now)
    request = s.requests[request_id]
    summary = result.summary or "Nothing new to do."
    for action in result.actions:
        if isinstance(action, AskStock):
            ask_stock(request_id, action)
        elif isinstance(action, Release):
            release(s.reservations[action.reservation_id])
        elif isinstance(action, SetStatus):
            request.status = action.status
    if result.actions or event_changed_state:
        s.decisions.append(Decision(
            id=s.next_id("dec"), request_id=request_id, at=now, trigger=trigger, p_before=result.p_before,
            p_after=result.p_after, status=request.status, actions=[describe(a, s) for a in result.actions],
            summary=summary,
        ))
    return result


def describe(action, s) -> str:
    if isinstance(action, AskStock):
        return f"ask {s.centres[action.centre_id].name}: {action.units} {action.group}"
    if isinstance(action, Release):
        return f"release {s.centres[s.reservations[action.reservation_id].centre_id].name}"
    return f"status {action.status}"


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


# --- Events ---

def on_timer(timer: Timer) -> None:
    """Clock handler: pass to Clock.step / Clock.advance."""
    if timer.kind == "stock_timeout":
        res = store.state.main.reservations[timer.payload["reservation_id"]]
        if res.status == R.PENDING:
            res.status = R.EXPIRED
            replan(res.request_id, f"{store.state.main.centres[res.centre_id].name} didn't answer in time", True)
    elif timer.kind == "sim_inbound":
        handle_inbound(Inbound(at=store.state.clock.now, **timer.payload))


def handle_inbound(msg: Inbound) -> None:
    """Called by the bot and by POST /api/sim/reply."""
    record_inbound(msg)
    if msg.button_id and msg.button_id.startswith("R:"):
        _, reservation_id, choice = msg.button_id.split(":", 2)
        stock_reply(reservation_id, choice, msg.sender_id)


def record_inbound(msg: Inbound) -> None:
    state = store.state
    state.message_seq += 1
    state.inbox.setdefault(msg.sender_id, []).append(Message(
        id=f"m_{state.message_seq}", at=msg.at, direction="in", channel=msg.channel, to_name="RaktTrace",
        kind="reply", body=msg.text or msg.button_id or "", read_by="button" if msg.button_id else None,
    ))


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


def link_chat(start_param: str, chat_id: str, display_name: str) -> str:
    return "RaktTrace: chat linking isn't available yet."
