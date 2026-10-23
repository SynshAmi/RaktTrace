"""The planner (AGENT §5): the only decision-maker. Pure: reads state, returns actions; adds only what's missing.

Covers Step 1 (estimate, status), Step 2 (stock first), Step 3 (wait or invite), Step 4 (roles for yes-replies)
and Step 5 (promotion). Closing and escalation (Steps 6–7) come later.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from rakt import config
from rakt.agent.probability import ESTIMATORS, collect_sources, estimate, p_at_least, stock_p, stock_source
from rakt.agent.ranking import candidates
from rakt.domain.blood import compatible_groups
from rakt.domain.geo import km
from rakt.domain.timing import (
    choose_collection_centre, donor_timing, donors_can_help, latest_arrival, stock_on_time, usable_by,
)
from rakt.models import BloodGroup, Centre, Pledge, PledgeStatus, Request, RequestStatus, ReservationStatus, Stock
from rakt.store import Store

FINAL = {RequestStatus.FULFILLED, RequestStatus.FAILED, RequestStatus.CANCELLED}
CERTAIN_STOCK = {ReservationStatus.RESERVED, ReservationStatus.READY}
ACTIVE_LIKE = {PledgeStatus.ACTIVE, PledgeStatus.ARRIVED, PledgeStatus.COLLECTED, PledgeStatus.READY}


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


@dataclass(frozen=True)
class FixCentre:
    centre_id: str


@dataclass(frozen=True)
class Invite:
    donor_ids: tuple[str, ...]
    whys: tuple[str, ...]
    wave: int
    k_star: int  # what the sizing rule wanted before the per-wave cap
    reachable: bool  # whether some k ≤ K reaches TARGET_P
    reaches_target: bool = False  # P(k*) ≥ TARGET_P
    next_gain: float | None = None  # P(k* + 1) − P(k*), None when k* = K


@dataclass(frozen=True)
class Promote:
    pledge_id: str


Action = AskStock | Release | SetStatus | FixCentre | Invite | Promote


@dataclass(frozen=True)
class Plan:
    actions: list[Action] = field(default_factory=list)
    p_before: float = 0.0
    p_after: float = 0.0
    p_firm: float = 0.0
    status: RequestStatus | None = None
    summary: str = ""
    pool_exhausted: bool = False
    waiting_for_stock: bool = False


# --- Step 1: estimate and status ---

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


# --- Step 2: stock first ---

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
    """Ask centres in parallel until stock alone looks ≥ TARGET_P likely, or none are left."""
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


# --- Step 3: wait or invite ---

def choose_k(curve: list[float], tau: float | None = None, target: float | None = None) -> tuple[int, bool]:
    """Expected-cost wave size. curve[k] = P with the first k candidates invited, k = 0..K.
    Returns (k*, reachable): the smallest argmin of J(k) = (1 − P(k)) + τ·k over k ≤ the first k that reaches
    the target, or K if no k reaches it."""
    tau = config.DONOR_BURDEN_TAU if tau is None else tau
    target = config.TARGET_P if target is None else target
    k_cap = next((k for k, p in enumerate(curve) if p >= target), None)
    if k_cap is None:
        return len(curve) - 1, False
    return min(range(k_cap + 1), key=lambda k: ((1 - curve[k]) + tau * k, k)), True


def size_wave(curve: list[float]) -> tuple[int, int, bool]:
    """(donors to invite now, k*, reachable) under the SIZING flag (AGENT §11)."""
    k_max = len(curve) - 1
    k_target = next((k for k, p in enumerate(curve) if p >= config.TARGET_P), None)
    if config.SIZING == "all":
        return k_max, k_max, k_target is not None
    if config.SIZING == "target":
        k = k_max if k_target is None else k_target
        return min(k, config.WAVE_CAP), k, k_target is not None
    k_star, reachable = choose_k(curve)
    return min(k_star, config.WAVE_CAP), k_star, reachable


def request_pledges(store: Store, request: Request) -> list[Pledge]:
    return [p for p in store.pledges.values() if p.request_id == request.id]


def wave_allowed(store: Store, request: Request, now: datetime) -> bool:
    """First wave, or WAVE_INTERVAL_MIN passed and someone from the last wave replied or timed out."""
    pledges = request_pledges(store, request)
    if not pledges:
        return True
    last = max(p.wave for p in pledges)
    last_wave = [p for p in pledges if p.wave == last]
    waited = now - max(p.invited_at for p in last_wave) >= timedelta(minutes=config.WAVE_INTERVAL_MIN)
    resolved = any(p.replied_at is not None or p.status != PledgeStatus.INVITED for p in last_wave)
    return waited and resolved


def should_wait_for_stock(store: Store, request: Request, centre: Centre | None, now: datetime,
                          new_asks: list[AskStock]) -> bool:
    """Slack rule: wait if, after the stock timeout, donors would still have WAIT_SLACK_MIN of go window."""
    if config.WAIT_RULE == "none" or centre is None:
        return False
    if config.WAIT_RULE != "slack":
        raise ValueError(f"WAIT_RULE {config.WAIT_RULE!r} is not implemented (lookahead is a stretch feature)")
    asked = [r.asked_at for r in store.reservations.values()
             if r.request_id == request.id and r.status == ReservationStatus.PENDING]
    asked += [now] * len(new_asks)
    if not asked:
        return False
    due = max(asked) + timedelta(minutes=config.STOCK_REPLY_TIMEOUT_MIN)
    arrival = latest_arrival(centre, store.hospitals[request.hospital_id], request.product, request.deadline_at)
    return arrival - due >= timedelta(minutes=config.WAIT_SLACK_MIN)


def donor_centre(store: Store, request: Request) -> Centre | None:
    """The collection centre: fixed on the request once the first wave is planned."""
    if request.collection_centre_id:
        return store.centres[request.collection_centre_id]
    holders = [r.centre_id for r in store.reservations.values()
               if r.request_id == request.id and r.status in CERTAIN_STOCK]
    return choose_collection_centre(store.hospitals[request.hospital_id], store.centres, request.product, holders)


def p_curve(store: Store, request: Request, now: datetime, asks: list[AskStock], bases: list[float],
            posterior: tuple[float, ...]) -> list[float]:
    """P(k) for k = 0..len(bases): the first k candidates added as fresh invites."""
    src = collect_sources(store, request, now)
    fixed = src.fixed + [ask_source(store, request, a, now) for a in asks]
    combine = ESTIMATORS[config.ESTIMATOR]
    return [combine(fixed, src.unreplied + [(b, 0.0) for b in bases[:k]], posterior, request.units)
            for k in range(len(bases) + 1)]


def plan_invites(store: Store, request: Request, now: datetime, asks: list[AskStock],
                 posterior: tuple[float, ...], p_now: float) -> tuple[list[Action], float, bool, bool]:
    """(actions, P after, pool_exhausted, waiting_for_stock)."""
    centre = donor_centre(store, request)
    if centre is None or should_wait_for_stock(store, request, centre, now, asks):
        return [], p_now, False, centre is not None
    messaged = len(request_pledges(store, request))
    hospital = store.hospitals[request.hospital_id]
    if (p_now >= config.TARGET_P or messaged >= config.REQUEST_DONOR_CAP
            or not wave_allowed(store, request, now)
            or not donors_can_help(hospital, list(store.centres.values()), request.product, now, request.deadline_at)):
        return [], p_now, False, False

    actions: list[Action] = [] if request.collection_centre_id else [FixCentre(centre.id)]
    ranked = candidates(store, request, centre, now)[: config.REQUEST_DONOR_CAP - messaged]
    curve = p_curve(store, request, now, asks, [c.base for c in ranked], posterior)
    send, k_star, reachable = size_wave(curve)
    if send == 0:
        return [], p_now, not ranked, False
    wave = max((p.wave for p in request_pledges(store, request)), default=0) + 1
    chosen = ranked[:send]
    next_gain = curve[k_star + 1] - curve[k_star] if k_star + 1 < len(curve) else None
    actions.append(Invite(tuple(c.donor_id for c in chosen), tuple(c.why for c in chosen), wave, k_star, reachable,
                          curve[k_star] >= config.TARGET_P, next_gain))
    return actions, curve[send], False, False


# --- Steps 4 and 5: roles and promotion ---

def need_from_donors(store: Store, request: Request) -> int:
    return max(0, request.units - reserved_units(store, request))


def outstanding_promotions(store: Store, request: Request) -> list[str]:
    return [pid for pid in store.promotions
            if store.pledges[pid].request_id == request.id and store.pledges[pid].status == PledgeStatus.STANDBY]


def role_for_yes(store: Store, request: Request, pledge: Pledge, now: datetime,
                 available_from: datetime | None) -> PledgeStatus:
    """Step 4: TOO_LATE, ACTIVE, STANDBY or RELEASED for a donor who just said yes."""
    centre = donor_centre(store, request)
    donor, hospital = store.donors[pledge.donor_id], store.hospitals[request.hospital_id]
    timing = donor_timing(donor, centre, hospital, request.product, request.deadline_at, now,
                          available_from=available_from, replied=True)
    if not timing.on_time:
        return PledgeStatus.TOO_LATE
    pledges = request_pledges(store, request)
    need = need_from_donors(store, request)
    active = sum(p.status in ACTIVE_LIKE for p in pledges) + len(outstanding_promotions(store, request))
    if active < need:
        return PledgeStatus.ACTIVE
    standby = sum(p.status == PledgeStatus.STANDBY for p in pledges)
    if estimate(store, request, now).p_firm < config.TARGET_P and standby < config.STANDBY_PER_UNIT * need:
        return PledgeStatus.STANDBY
    return PledgeStatus.RELEASED


def plan_promotions(store: Store, request: Request, now: datetime) -> list[Promote]:
    """Step 5: fill a missing active slot from the best on-time standby (first to say yes first)."""
    pledges = request_pledges(store, request)
    outstanding = outstanding_promotions(store, request)
    gap = need_from_donors(store, request) - sum(p.status in ACTIVE_LIKE for p in pledges) - len(outstanding)
    if gap <= 0:
        return []
    centre, hospital = donor_centre(store, request), store.hospitals[request.hospital_id]
    standby = [
        p for p in pledges
        if p.status == PledgeStatus.STANDBY and p.id not in outstanding
        and donor_timing(store.donors[p.donor_id], centre, hospital, request.product, request.deadline_at, now,
                         available_from=p.available_from, replied=True).on_time
    ]
    standby.sort(key=lambda p: (p.replied_at, p.id))
    return [Promote(p.id) for p in standby[:gap]]


# --- The plan ---

def plan(store: Store, request_id: str, now: datetime) -> Plan:
    request = store.requests[request_id]
    if request.status in FINAL:
        return Plan(status=request.status)

    before = estimate(store, request, now)
    status = status_for(store, request, now, before.p_firm)
    actions: list[Action] = []
    p_after, pool_exhausted, waiting = before.p, False, False

    if certain_units(store, request, now) >= request.units:
        actions += pending_releases(store, request)
    else:
        asks = plan_stock(store, request, now)
        actions += asks
        p_after = p_curve(store, request, now, asks, [], before.posterior)[0]
        actions += plan_promotions(store, request, now)
        invites, p_after, pool_exhausted, waiting = plan_invites(store, request, now, asks, before.posterior, p_after)
        actions += invites

    if status != request.status:
        actions.append(SetStatus(status))
    return Plan(actions, before.p, p_after, before.p_firm, status,
                summarise(store, request, actions, before.p, p_after), pool_exhausted, waiting)


def summarise(store: Store, request: Request, actions: list[Action], p_before: float, p_after: float) -> str:
    """One plain sentence per kind of action, in the order the actions run."""
    invites = [a for a in actions if isinstance(a, Invite)]
    sentences: dict[type, str] = {}
    for a in actions:
        kind = type(a)
        if kind in sentences or kind is FixCentre:
            continue
        if kind is AskStock:
            parts = [f"{store.centres[x.centre_id].name} for {x.units}" for x in actions if isinstance(x, AskStock)]
            tail = "" if invites else f" (P {pct(p_before)} → {pct(p_after)})"
            sentences[kind] = f"Asked {join(parts)}{tail}."
        elif kind is Release:
            names = [store.centres[store.reservations[x.reservation_id].centre_id].name
                     for x in actions if isinstance(x, Release)]
            sentences[kind] = f"Need covered; released the hold at {join(names)}."
        elif kind is Promote:
            names = [store.donors[store.pledges[x.pledge_id].donor_id].display_name
                     for x in actions if isinstance(x, Promote)]
            sentences[kind] = f"Asked standby {join(names)} to go now."
        elif kind is Invite:
            sentences[kind] = invite_sentence(a, p_before, p_after)
        elif kind is SetStatus:
            sentences[kind] = f"Status {request.status} → {a.status}."
    return " ".join(sentences.values())


def invite_sentence(a: Invite, p_before: float, p_after: float) -> str:
    """Says how many were invited and why the wave stopped there."""
    n = len(a.donor_ids)
    text = f"Invited {n} donor{'s' if n != 1 else ''} (P {pct(p_before)} → {pct(p_after)})"
    if a.k_star > n:
        rule = "the cost rule wanted more, capped" if config.SIZING == "cost" else "capped"
        text += f"; {rule} at {config.WAVE_CAP} per wave"
    elif a.reaches_target:
        text += f", enough to reach {pct(config.TARGET_P)}"
    elif a.next_gain is not None and config.SIZING == "cost":
        text += (f"; one more would add +{100 * a.next_gain:.1f}%, below the "
                 f"{100 * config.DONOR_BURDEN_TAU:.1f}% bar")
    if not a.reachable:
        text += f"; {pct(config.TARGET_P)} isn't reachable with the donors available"
    return text + "."


def pct(p: float) -> str:
    return f"{round(100 * p)}%"


def join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
