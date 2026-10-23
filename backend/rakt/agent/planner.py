"""The planner (AGENT §5): the only decision-maker. Pure: reads state, returns actions; adds only what's missing.

Phase 3 covers Step 1 (estimate, status) and Step 2 (stock first).
"""

from dataclasses import dataclass, field
from datetime import datetime

from rakt import config
from rakt.agent.probability import ESTIMATORS, collect_sources, estimate, p_at_least, stock_p, stock_source
from rakt.domain.blood import compatible_groups
from rakt.domain.geo import km
from rakt.domain.timing import stock_on_time, usable_by
from rakt.models import (
    BloodGroup, PledgeStatus, Request, RequestStatus, ReservationStatus, Stock,
)
from rakt.store import Store

FINAL = {RequestStatus.FULFILLED, RequestStatus.FAILED, RequestStatus.CANCELLED}
CERTAIN_STOCK = {ReservationStatus.RESERVED, ReservationStatus.READY}


@dataclass(frozen=True)
class AskStock:
    centre_id: str
    group: BloodGroup
    units: int
    listed_at: datetime


@dataclass(frozen=True)
class Release:
    reservation_id: str


@dataclass(frozen=True)
class SetStatus:
    status: RequestStatus


Action = AskStock | Release | SetStatus


@dataclass(frozen=True)
class Plan:
    actions: list[Action] = field(default_factory=list)
    p_before: float = 0.0
    p_after: float = 0.0
    p_firm: float = 0.0
    status: RequestStatus | None = None
    summary: str = ""


def reserved_units(store: Store, request: Request) -> int:
    return sum(r.units_reserved for r in store.reservations.values()
               if r.request_id == request.id and r.status in CERTAIN_STOCK)


def certain_units(store: Store, request: Request, now: datetime) -> int:
    """Reserved stock that is on time + collected units ready before the deadline."""
    hospital = store.hospitals[request.hospital_id]
    units = 0
    for r in store.reservations.values():
        if r.request_id != request.id:
            continue
        if r.status == ReservationStatus.READY or (
            r.status == ReservationStatus.RESERVED
            and stock_on_time(store.centres[r.centre_id], hospital, now, reserved=True, deadline=request.deadline_at)
        ):
            units += r.units_reserved
    for p in store.pledges.values():
        if p.request_id == request.id and (
            p.status == PledgeStatus.READY
            or (p.status == PledgeStatus.COLLECTED and p.ready_at and p.ready_at <= usable_by(request.deadline_at))
        ):
            units += 1
    return units


def status_for(store: Store, request: Request, now: datetime, p_firm: float) -> RequestStatus:
    if certain_units(store, request, now) >= request.units:
        return RequestStatus.SECURED
    return RequestStatus.COVERED if p_firm >= config.TARGET_P else RequestStatus.OPEN


def stock_candidates(store: Store, request: Request) -> list[Stock]:
    """Un-asked compatible listings in radius, exact group → fresher → nearer; one ask per centre."""
    groups = compatible_groups(request.group, request.product, request.escalation_level)
    hospital = store.hospitals[request.hospital_id]
    asked = {r.centre_id for r in store.reservations.values() if r.request_id == request.id}
    listings = [
        s for s in store.stock
        if s.product == request.product and s.group in groups and s.listed_units > 0
        and s.centre_id not in asked and km(store.centres[s.centre_id], hospital) <= request.radius_km
    ]
    listings.sort(key=lambda s: (groups.index(s.group), -s.listed_at.timestamp(),
                                 km(store.centres[s.centre_id], hospital), s.centre_id))
    best_per_centre = {}
    for s in listings:
        best_per_centre.setdefault(s.centre_id, s)
    return list(best_per_centre.values())


def stock_sources(store: Store, request: Request, now: datetime) -> list[tuple[float, int]]:
    reservations = [r for r in store.reservations.values() if r.request_id == request.id]
    return [src for r in reservations if (src := stock_source(store, request, r, now))]


def ask_source(store: Store, request: Request, ask: AskStock, now: datetime) -> tuple[float, int]:
    centre, hospital = store.centres[ask.centre_id], store.hospitals[request.hospital_id]
    on_time = stock_on_time(centre, hospital, now, reserved=False, deadline=request.deadline_at)
    return stock_p((now - ask.listed_at).total_seconds() / 60) * on_time, ask.units


def plan_stock(store: Store, request: Request, now: datetime) -> list[AskStock]:
    """Step 2: ask centres in parallel until stock alone looks ≥ TARGET_P likely, or none are left."""
    sources = stock_sources(store, request, now)
    to_ask = request.units - reserved_units(store, request)
    asks = []
    for listing in stock_candidates(store, request):
        if p_at_least(sources, request.units) >= config.TARGET_P or to_ask <= 0:
            break
        ask = AskStock(listing.centre_id, listing.group, min(listing.listed_units, to_ask), listing.listed_at)
        asks.append(ask)
        sources.append(ask_source(store, request, ask, now))
    return asks


def pending_releases(store: Store, request: Request) -> list[Release]:
    return [Release(r.id) for r in store.reservations.values()
            if r.request_id == request.id and r.status == ReservationStatus.PENDING]


def plan(store: Store, request_id: str, now: datetime) -> Plan:
    request = store.requests[request_id]
    if request.status in FINAL:
        return Plan(status=request.status)

    before = estimate(store, request, now)
    status = status_for(store, request, now, before.p_firm)
    actions: list[Action] = []

    if certain_units(store, request, now) >= request.units:
        actions += pending_releases(store, request)
    else:
        actions += plan_stock(store, request, now)
    if status != request.status:
        actions.append(SetStatus(status))

    asks = [a for a in actions if isinstance(a, AskStock)]
    p_after = before.p
    if asks:
        src = collect_sources(store, request, now)
        fixed = src.fixed + [ask_source(store, request, a, now) for a in asks]
        p_after = ESTIMATORS[config.ESTIMATOR](fixed, src.unreplied, before.posterior, request.units)
    return Plan(actions, before.p, p_after, before.p_firm, status,
                summarise(store, request, actions, before.p, p_after))


def summarise(store: Store, request: Request, actions: list[Action], p_before: float, p_after: float) -> str:
    sentences = []
    asks = [a for a in actions if isinstance(a, AskStock)]
    if asks:
        parts = [f"{store.centres[a.centre_id].name} for {a.units}" for a in asks]
        sentences.append(f"Asked {join(parts)} (P {pct(p_before)} → {pct(p_after)}).")
    releases = [a for a in actions if isinstance(a, Release)]
    if releases:
        names = [store.centres[store.reservations[a.reservation_id].centre_id].name for a in releases]
        sentences.append(f"Need covered; released the hold at {join(names)}.")
    for a in actions:
        if isinstance(a, SetStatus):
            sentences.append(f"Status {request.status} → {a.status}.")
    return " ".join(sentences)


def pct(p: float) -> str:
    return f"{round(100 * p)}%"


def join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
