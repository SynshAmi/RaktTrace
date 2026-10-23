"""Donor candidates (AGENT §5.1): hard filters, then order, each with a `why`."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from rakt import config
from rakt.agent.probability import in_time_share
from rakt.domain.blood import compatible_groups
from rakt.domain.eligibility import is_eligible
from rakt.domain.geo import km, travel_min
from rakt.domain.timing import DonorTiming, donor_timing
from rakt.models import GROUP_LABELS, Centre, Donor, PledgeStatus, Product, Request, RequestStatus
from rakt.store import Store

OPEN_STATUSES = {RequestStatus.OPEN, RequestStatus.COVERED, RequestStatus.SECURED}


@dataclass(frozen=True)
class Candidate:
    donor_id: str
    base: float  # IN_TIME_SHARE × P_SHOW × P_PASS × on_time: the rate-free part of a fresh invite's p
    km: float
    exact: bool
    why: str
    timing: DonorTiming


def quiet_hours_apply(request: Request, now: datetime) -> bool:
    q = config.QUIET_HOURS
    if request.deadline_at - now <= timedelta(hours=q["min_hours_left"]):
        return False
    return now.hour >= q["start_h"] or now.hour < q["end_h"]


def rested(donor: Donor, now: datetime) -> bool:
    recent = [t for t in donor.invites if now - t < timedelta(hours=config.REST_H)]
    month = [t for t in donor.invites if now - t < timedelta(days=30)]
    return not recent and len(month) < config.MAX_ASKS_30D


def busy_elsewhere(store: Store, request: Request) -> set[str]:
    """Donors on this request, or ACTIVE/STANDBY on another open one."""
    busy = set()
    for p in store.pledges.values():
        if p.request_id == request.id:
            busy.add(p.donor_id)
        elif p.status in (PledgeStatus.ACTIVE, PledgeStatus.STANDBY) \
                and store.requests[p.request_id].status in OPEN_STATUSES:
            busy.add(p.donor_id)
    return busy


def candidates(store: Store, request: Request, centre: Centre, now: datetime,
               radius_km: float | None = None) -> list[Candidate]:
    """Ranked, fully filtered candidates. `radius_km` overrides the request's radius (e.g. for P_best)."""
    if quiet_hours_apply(request, now):
        return []
    radius = request.radius_km if radius_km is None else radius_km
    groups = compatible_groups(request.group, request.product, request.escalation_level)
    hospital = store.hospitals[request.hospital_id]
    busy = busy_elsewhere(store, request)

    found = []
    for donor in store.donors.values():
        if not donor.consent or donor.opted_out or donor.group not in groups or donor.id in busy:
            continue
        if request.product == Product.SDP and not donor.apheresis_ok:
            continue
        distance = km(donor, centre)
        if distance > radius or not rested(donor, now):
            continue
        timing = donor_timing(donor, centre, hospital, request.product, request.deadline_at, now)
        if not timing.invitable:
            continue
        arrival = now + timedelta(minutes=config.REPLY_LAG_MIN + travel_min(donor, centre))
        if not is_eligible(donor, request.product, arrival):
            continue
        base = in_time_share(timing.go_window_min) * config.P_SHOW * config.P_PASS[request.product]
        exact = donor.group == request.group
        why = " · ".join(filter(None, [
            f"{GROUP_LABELS[donor.group]} {'exact' if exact else 'compatible'}",
            f"{distance:.1f} km",
            "verified" if donor.donation_verified else "",
            "Telegram" if donor.telegram_demo else "",
        ]))
        found.append(Candidate(donor.id, base, distance, exact, why, timing))

    found.sort(key=lambda c: (
        not c.exact,
        not store.donors[c.donor_id].telegram_demo,
        -c.base,
        not store.donors[c.donor_id].donation_verified,
        c.km,
        c.donor_id,
    ))
    return found
