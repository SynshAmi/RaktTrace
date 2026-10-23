"""Escalation (AGENT §6): L1 widen, L2 alert, FAILED. Levels only go up. Pure: returns actions."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from rakt import config
from rakt.agent.probability import estimate
from rakt.agent.ranking import candidates
from rakt.domain.blood import compatible_groups
from rakt.domain.geo import km
from rakt.models import GROUP_LABELS, Centre, Request
from rakt.store import Store


@dataclass(frozen=True)
class Widen:
    radius_km: float


@dataclass(frozen=True)
class Alert:
    reasons: tuple[str, ...]
    call_list: tuple[dict, ...]


@dataclass(frozen=True)
class Fail:
    ready: int


@dataclass(frozen=True)
class View:
    """What the planner already knows this pass."""
    p: float
    stock_left: bool  # un-asked compatible stock in the current radius
    stock_at: Callable[[float], bool]  # would this radius add a candidate centre?
    centre: Centre | None
    donors_can_help: bool
    pool_exhausted: bool
    ready: int
    messaged: int
    overdue: bool  # a staff tap overdue by 2 × STAFF_GRACE_MIN


def p_best(store: Store, request: Request, now: datetime, view: View) -> float:
    """P if every remaining allowed candidate (up to the per-request cap, at the max radius) were invited now."""
    if not view.donors_can_help or view.centre is None:
        return view.p
    room = max(0, config.REQUEST_DONOR_CAP - view.messaged)
    found = candidates(store, request, view.centre, now, radius_km=config.SEARCH_RADII_KM[-1])[:room]
    return max(view.p, estimate(store, request, now, fresh=[c.base for c in found]).p)


def call_list(store: Store, request: Request) -> list[dict]:
    """3 nearest centres listing any compatible units (O− included, since L2 unlocks it), asked or not."""
    groups = compatible_groups(request.group, request.product, escalation_level=2)
    hospital = store.hospitals[request.hospital_id]
    best: dict[str, object] = {}
    for s in store.stock:
        if s.product == request.product and s.group in groups and s.listed_units > 0:
            current = best.get(s.centre_id)
            if current is None or groups.index(s.group) < groups.index(current.group):
                best[s.centre_id] = s
    nearest = sorted(best.values(), key=lambda s: (km(store.centres[s.centre_id], hospital), s.centre_id))[:3]
    return [
        {"centre": store.centres[s.centre_id].name, "phone": store.centres[s.centre_id].phone,
         "note": f"lists {s.listed_units} {GROUP_LABELS[s.group]} ({listing_age_h(request, s)} h old)"}
        for s in nearest
    ]


def listing_age_h(request: Request, stock) -> int:
    return max(0, round((request.created_at - stock.listed_at).total_seconds() / 3600))


def widen_to(request: Request, view: View, donors_at: Callable[[float], bool]) -> float:
    """The smallest larger radius that adds any candidate centre or donor (40 km if none)."""
    for radius in config.SEARCH_RADII_KM:
        if radius > request.radius_km and (view.stock_at(radius) or (view.donors_can_help and donors_at(radius))):
            return radius
    return config.SEARCH_RADII_KM[-1]


def plan_escalation(store: Store, request: Request, now: datetime, view: View) -> list[Widen | Alert | Fail]:
    if now >= request.deadline_at and view.ready < request.units:
        return [Fail(view.ready)]

    # L1: nothing left to try at this radius (no stock to ask, and donors can't help or none are left)
    nothing_here = not view.stock_left and (not view.donors_can_help or view.pool_exhausted)
    if view.p < config.TARGET_P and nothing_here and request.radius_km < config.SEARCH_RADII_KM[-1]:
        def donors_at(radius: float) -> bool:
            return view.centre is not None and bool(candidates(store, request, view.centre, now, radius_km=radius))
        return [Widen(widen_to(request, view, donors_at))]

    if request.escalation_level >= 2:
        return []
    reasons = []
    if p_best(store, request, now, view) < config.ESCALATE_P:
        reasons.append(f"even the best plan is below {round(100 * config.ESCALATE_P)}%")
    window = request.deadline_at - request.created_at
    if now - request.created_at >= window / 2 and view.p < config.HALFTIME_ESCALATE_P:
        reasons.append(f"half the time gone and P below {round(100 * config.HALFTIME_ESCALATE_P)}%")
    if request.radius_km >= config.SEARCH_RADII_KM[-1] and view.p < config.TARGET_P:
        reasons.append(f"search at {config.SEARCH_RADII_KM[-1]} km and P below {round(100 * config.TARGET_P)}%")
    if view.overdue:
        reasons.append("a staff tap is overdue")
    return [Alert(tuple(reasons), tuple(call_list(store, request)))] if reasons else []
