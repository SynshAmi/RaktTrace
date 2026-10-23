"""P: the chance enough units are ready by the deadline (AGENT §3)."""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from rakt import config
from rakt.domain.timing import choose_collection_centre, donor_timing, stock_on_time, usable_by
from rakt.models import Centre, Pledge, PledgeStatus, Request, Reservation, ReservationStatus
from rakt.store import Store

S = PledgeStatus
Source = tuple[float, int]  # (chance it delivers, units)

COMMITTED_DONOR = {S.ACTIVE, S.STANDBY, S.ARRIVED, S.COLLECTED, S.READY}
UNREPLIED = {S.INVITED, S.NO_REPLY}


def p_at_least(sources: list[Source], need: int) -> float:
    if need <= 0:
        return 1.0
    dist = [1.0] + [0.0] * need  # dist[k] = P(total = k), capped at need
    for p, units in sources:
        new = [0.0] * (need + 1)
        for k, mass in enumerate(dist):
            if mass:
                new[min(need, k + units)] += mass * p
                new[k] += mass * (1 - p)
        dist = new
    return dist[need]


def stock_p(age_min: float) -> float:
    """STOCK_P: chance a listing of this age is true."""
    return next(p for max_h, p in config.STOCK_P if age_min <= max_h * 60)


# --- Tonight's yes rate ---

def silence(t_min: float) -> float:
    return math.exp(-t_min / config.REPLY_DELAY_MEAN_MIN)


def likelihood(kind: str, r: float, t_min: float) -> float:
    if kind == "yes":
        return r
    if kind in ("no", "stop"):
        return 1 - r
    return (1 - r) + r * silence(t_min)


def posterior(evidence: list[tuple[str, float]]) -> tuple[float, ...]:
    """π over LATENT_RATES from (kind, minutes since invite) per donor invited on this request."""
    weights = [
        prior * math.prod(likelihood(kind, r, t) for kind, t in evidence)
        for r, prior in zip(config.LATENT_RATES, config.LATENT_PRIOR)
    ]
    total = sum(weights)
    return tuple(w / total for w in weights)


def unreplied_p(r: float, base: float, t_min: float) -> float:
    """Chance an unreplied donor is a yes who hasn't answered yet, times the rest of the chain."""
    s = silence(t_min)
    return r * s / ((1 - r) + r * s) * base


def evidence_kind(pledge: Pledge) -> str:
    if pledge.status == S.DECLINED:
        return "no"
    if pledge.status == S.OPTED_OUT:
        return "stop"
    if pledge.status in UNREPLIED or (pledge.status == S.RELEASED and pledge.replied_at is None):
        return "silent"
    return "yes"


# --- Sources ---

@dataclass(frozen=True)
class Sources:
    fixed: list[Source]  # sources whose chance doesn't depend on tonight's rate
    firm: list[Source]  # committed only: reserved/ready stock, committed donors
    unreplied: list[tuple[float, float]]  # (base chance, minutes since invite)
    evidence: list[tuple[str, float]]


def minutes_between(a: datetime, b: datetime) -> float:
    return (b - a) / timedelta(minutes=1)


def stock_source(store: Store, request: Request, res: Reservation, now: datetime) -> Source | None:
    centre, hospital = store.centres[res.centre_id], store.hospitals[request.hospital_id]
    if res.status == ReservationStatus.PENDING:
        on_time = stock_on_time(centre, hospital, now, reserved=False, deadline=request.deadline_at)
        return stock_p(minutes_between(res.listed_at, res.asked_at)) * on_time, res.units_asked
    if res.status == ReservationStatus.RESERVED:
        on_time = stock_on_time(centre, hospital, now, reserved=True, deadline=request.deadline_at)
        return float(on_time), res.units_reserved
    if res.status == ReservationStatus.READY:
        return 1.0, res.units_reserved
    return None


def collection_centre(store: Store, request: Request) -> Centre | None:
    if request.collection_centre_id:
        return store.centres[request.collection_centre_id]
    return choose_collection_centre(store.hospitals[request.hospital_id], store.centres, request.product)


def in_time_share(go_window_min: float) -> float:
    share = config.IN_TIME_SHARE
    return share["short"] if go_window_min < share["window_h"] * 60 else share["long"]


def donor_source(store: Store, request: Request, pledge: Pledge, centre: Centre, now: datetime) -> float:
    """Chance for a committed or arrived donor (rate-free rows of the §3.1 table)."""
    product = request.product
    if pledge.status == S.READY:
        return 1.0
    if pledge.status == S.COLLECTED:
        return float(pledge.ready_at is not None and pledge.ready_at <= usable_by(request.deadline_at))
    if pledge.status == S.ARRIVED:
        return config.P_PASS[product]
    donor, hospital = store.donors[pledge.donor_id], store.hospitals[request.hospital_id]
    timing = donor_timing(donor, centre, hospital, product, request.deadline_at, now,
                          available_from=pledge.available_from, replied=True)
    active = config.P_SHOW * config.P_PASS[product] * timing.on_time
    return active * (config.STANDBY_FACTOR if pledge.status == S.STANDBY else 1.0)


def invite_base(store: Store, request: Request, donor_id: str, centre: Centre, now: datetime) -> float:
    """IN_TIME_SHARE × P_SHOW × P_PASS × on_time for a donor who hasn't replied."""
    timing = donor_timing(store.donors[donor_id], centre, store.hospitals[request.hospital_id], request.product,
                          request.deadline_at, now)
    return in_time_share(timing.go_window_min) * config.P_SHOW * config.P_PASS[request.product] * timing.on_time


def collect_sources(store: Store, request: Request, now: datetime) -> Sources:
    fixed, firm, unreplied, evidence = [], [], [], []
    for res in store.reservations.values():
        if res.request_id != request.id:
            continue
        source = stock_source(store, request, res, now)
        if source:
            fixed.append(source)
            if res.status != ReservationStatus.PENDING:
                firm.append(source)

    centre = collection_centre(store, request)
    for pledge in store.pledges.values():
        if pledge.request_id != request.id:
            continue
        t = minutes_between(pledge.invited_at, now)
        evidence.append((evidence_kind(pledge), t))
        if pledge.status in UNREPLIED:
            unreplied.append((invite_base(store, request, pledge.donor_id, centre, now), t))
        elif pledge.status in COMMITTED_DONOR:
            source = (donor_source(store, request, pledge, centre, now), 1)
            fixed.append(source)
            firm.append(source)
    return Sources(fixed, firm, unreplied, evidence)


# --- The three views ---

def mixture_p(fixed: list[Source], unreplied: list[tuple[float, float]], post: tuple[float, ...], need: int) -> float:
    return sum(
        weight * p_at_least(fixed + [(unreplied_p(r, base, t), 1) for base, t in unreplied], need)
        for r, weight in zip(config.LATENT_RATES, post)
    )


def plugin_p(fixed: list[Source], unreplied: list[tuple[float, float]], post: tuple[float, ...], need: int) -> float:
    mean_rate = sum(r * w for r, w in zip(config.LATENT_RATES, post))
    return p_at_least(fixed + [(unreplied_p(mean_rate, base, t), 1) for base, t in unreplied], need)


ESTIMATORS = {"mixture": mixture_p, "plugin": plugin_p}


@dataclass(frozen=True)
class Estimate:
    p: float
    p_firm: float
    posterior: tuple[float, ...]


def estimate(store: Store, request: Request, now: datetime, fresh: list[float] = (),
             estimator: str | None = None) -> Estimate:
    """P and P_firm. `fresh` adds invites sent right now (base chances), e.g. for wave sizing or P_best."""
    src = collect_sources(store, request, now)
    post = posterior(src.evidence)
    combine = ESTIMATORS[estimator or config.ESTIMATOR]
    unreplied = src.unreplied + [(base, 0.0) for base in fresh]
    return Estimate(
        p=combine(src.fixed, unreplied, post, request.units),
        p_firm=p_at_least(src.firm, request.units),
        posterior=post,
    )


def p_best(store: Store, request: Request, now: datetime, candidate_bases: list[float]) -> float:
    """P if every remaining allowed candidate (the caller applies the cap and max radius) were invited now."""
    return estimate(store, request, now, fresh=candidate_bases).p
