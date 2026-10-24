"""JSON views the frontend reads (BUILD §5.3). Plain functions over the store; callers hold store.lock."""

from datetime import datetime, timedelta

from rakt import config, store
from rakt.agent import planner
from rakt.agent.probability import (
    donor_source, estimate, evidence_kind, invite_base, stock_source, unreplied_p,
)
from rakt.channels.simulated import phone_id
from rakt.domain.geo import km
from rakt.domain.timing import donor_timing, donors_can_help
from rakt.models import PledgeStatus, Request, ReservationStatus
from rakt.store import Store

S, R = PledgeStatus, ReservationStatus
ACTIVE_LIKE = {S.ACTIVE, S.ARRIVED, S.COLLECTED, S.READY}


def iso(at: datetime | None) -> str | None:
    return at.isoformat() if at else None


def minutes_between(a: datetime, b: datetime) -> int:
    return round((b - a) / timedelta(minutes=1))


def last_read_by(donor) -> str | None:
    messages = store.state.inbox.get(phone_id(donor.contact), [])
    return next((m.read_by for m in reversed(messages) if m.direction == "in" and m.read_by), None)


def donor_p(s: Store, request: Request, pledge, centre, now: datetime, posterior) -> float:
    if pledge.status in (S.INVITED, S.NO_REPLY) and centre is not None:
        mean_rate = sum(r * w for r, w in zip(config.LATENT_RATES, posterior))
        t = minutes_between(pledge.invited_at, now)
        return unreplied_p(mean_rate, invite_base(s, request, pledge.donor_id, centre, now), t)
    if pledge.status in ACTIVE_LIKE | {S.STANDBY} and centre is not None:
        return donor_source(s, request, pledge, centre, now)
    return 0.0


def units_ladder(s: Store, request: Request, now: datetime) -> dict:
    holds = [r for r in s.reservations.values() if r.request_id == request.id]
    pledges = [p for p in s.pledges.values() if p.request_id == request.id]
    reserved = sum(r.units_reserved for r in holds if r.status in (R.RESERVED, R.READY))
    collected = sum(p.status in (S.COLLECTED, S.READY) for p in pledges)
    centre = planner.donor_centre(s, request)
    on_time_donors = sum(
        1 for p in pledges if p.status in (S.ACTIVE, S.ARRIVED) and centre is not None
        and donor_timing(s.donors[p.donor_id], centre, s.hospitals[request.hospital_id], request.product,
                         request.deadline_at, now, available_from=p.available_from, replied=True).on_time)
    return {
        "found": reserved,  # stock units held for this request
        "said_yes": sum(evidence_kind(p) == "yes" for p in pledges),
        "ready_in_time": planner.certain_units(s, request, now) + on_time_donors,
        "collected_or_reserved": reserved + collected,
        "confirmed": planner.ready_units(s, request),
    }


def request_view(request_id: str) -> dict:
    state = store.state
    s, now = state.main, state.clock.now
    request = s.requests[request_id]
    hospital = s.hospitals[request.hospital_id]
    centre = s.centres.get(request.collection_centre_id) if request.collection_centre_id else None
    est = estimate(s, request, now)
    plan = planner.plan(s, request.id, now)  # pure: read for its flags only
    holds = [r for r in s.reservations.values() if r.request_id == request.id]
    pledges = [p for p in s.pledges.values() if p.request_id == request.id]
    kinds = [evidence_kind(p) for p in pledges]
    donor_centre = planner.donor_centre(s, request)
    return {
        "id": request.id, "status": request.status.value, "group": request.group.value,
        "product": request.product.value, "units": request.units,
        "hospital": {"id": hospital.id, "name": hospital.name, "area": hospital.area},
        "collection_centre": {"id": centre.id, "name": centre.name,  # who answers its cards: linked staff or the sim
                              "staff": "telegram" if centre.contact.chat_id else "simulated"} if centre else None,
        "created_at": iso(request.created_at), "deadline_at": iso(request.deadline_at), "now": iso(now),
        "p": round(est.p, 4), "p_firm": round(est.p_firm, 4), "target": config.TARGET_P,
        "units_ladder": units_ladder(s, request, now),
        "stock": [{
            "reservation_id": r.id, "centre": s.centres[r.centre_id].name, "units_asked": r.units_asked,
            "units_reserved": r.units_reserved, "status": r.status.value,
            "listed_age_min": minutes_between(r.listed_at, r.asked_at),
            "p": round((stock_source(s, request, r, now) or (0.0, 0))[0], 4),
        } for r in holds],
        "donors": [{
            "pledge_id": p.id, "name": s.donors[p.donor_id].display_name, "group": s.donors[p.donor_id].group.value,
            "km": round(km(s.donors[p.donor_id], donor_centre or hospital), 1), "status": p.status.value,
            "p": round(donor_p(s, request, p, donor_centre, now, est.posterior), 4),
            "booking_code": p.booking_code, "ready_at": iso(p.ready_at), "why": p.why,
            "reply_text": p.reply_text, "read_by": last_read_by(s.donors[p.donor_id]),
            "live": s.donors[p.donor_id].telegram_demo,
        } for p in pledges],
        "counts": {
            "messaged": len(pledges), "yes": kinds.count("yes"), "no": kinds.count("no") + kinds.count("stop"),
            "silent": kinds.count("silent"), "active": sum(p.status in ACTIVE_LIKE for p in pledges),
            "standby": sum(p.status == S.STANDBY for p in pledges),
        },
        "escalation": {"level": request.escalation_level, "brief": request.brief,
                       "call_list": s.call_lists.get(request.id, [])},
        "flags": {
            "donors_can_help": donors_can_help(hospital, list(s.centres.values()), request.product, now,
                                               request.deadline_at),
            "waiting_for_stock": plan.waiting_for_stock,
        },
    }


def request_summary(request: Request) -> dict:
    s, now = store.state.main, store.state.clock.now
    return {
        "id": request.id, "group": request.group.value, "product": request.product.value, "units": request.units,
        "status": request.status.value, "p": round(estimate(s, request, now).p, 4),
        "deadline_at": iso(request.deadline_at), "hospital_name": s.hospitals[request.hospital_id].name,
        "escalation_level": request.escalation_level,
    }

