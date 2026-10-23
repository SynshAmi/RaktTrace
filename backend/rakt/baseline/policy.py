"""Today's workflow (AGENT §8), run on its own lane copy with the request's pre-drawn outcomes (AGENT §9).

1. Trust the listing with the most units ("blood found").
2. After FAMILY_TRIP_MIN the family reaches that centre and gets what is actually there.
3. If short, forward the plea to the BASELINE_WAVE nearest compatible donors every BASELINE_INTERVAL_MIN
   (no timing check, no rest rules, no O− protection).
4. "Fulfilled" as soon as stock found + yes-replies ≥ need: any yes counts, even a late one; the search stops.
5. No deferral tracking, no backups, no stand-down, no warning.

It doesn't react to anyone, so the whole run is worked out at once; the API shows it up to the sim clock.
The true outcome at the deadline counts only units really ready in time.
"""

import heapq
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from rakt import config
from rakt.domain.blood import compatible_groups
from rakt.domain.eligibility import is_eligible
from rakt.domain.geo import km, travel_min
from rakt.domain.timing import choose_collection_centre
from rakt.models import BaselineState, BaselineStatus, Product, Request
from rakt.sim.world import DonorLatent
from rakt.store import Store


@dataclass
class BaselineRun:
    state: BaselineState  # as of the deadline
    events: list[tuple[datetime, str]] = field(default_factory=list)
    messaged_at: list[datetime] = field(default_factory=list)
    units_ready: int = 0
    stock_ready: int = 0
    trip_at: datetime | None = None  # when the family learns what the centre really has


def minutes(m: float) -> timedelta:
    return timedelta(minutes=m)


def best_listing(store: Store, request: Request):
    groups = compatible_groups(request.group, request.product, escalation_level=2)
    listings = [s for s in store.stock if s.product == request.product and s.group in groups and s.listed_units > 0]
    hospital = store.hospitals[request.hospital_id]
    return min(listings, key=lambda s: (-s.listed_units, -s.listed_at.timestamp(),
                                        km(store.centres[s.centre_id], hospital), s.centre_id), default=None)


def forward_order(store: Store, request: Request) -> list[str]:
    """Nearest compatible donors to the hospital: no timing check, no rest rules."""
    groups = compatible_groups(request.group, request.product, escalation_level=2)
    hospital = store.hospitals[request.hospital_id]
    donors = [d for d in store.donors.values() if d.group in groups and d.consent and not d.opted_out]
    return [d.id for d in sorted(donors, key=lambda d: (km(d, hospital), d.id))]


def donor_unit_ready(store: Store, request: Request, donor_id: str, latent: DonorLatent, replied_at: datetime) -> bool:
    """A donor who said yes goes to donate; is their unit really ready in time?"""
    if not (latent.will_show and latent.will_pass):
        return False
    donor, hospital = store.donors[donor_id], store.hospitals[request.hospital_id]
    centre = choose_collection_centre(hospital, store.centres, request.product)
    if centre is None or (request.product == Product.SDP and not donor.apheresis_ok):
        return False
    start = max(replied_at, latent.available_from or replied_at)
    arrival = start + minutes(travel_min(donor, centre))
    if not is_eligible(donor, request.product, arrival):  # screening at the centre turns them away
        return False
    ready = arrival + minutes(config.VISIT_MIN[request.product] + config.TEST_MIN[request.product]
                              + travel_min(centre, hospital))
    return ready <= request.deadline_at  # truth: ready by the deadline (the margin is only a planning buffer)


def run(store: Store, request: Request, latent_for) -> BaselineRun:
    """latent_for(donor_id, invite_order) → DonorLatent | None: the request's pre-drawn outcome for that donor."""
    t0, deadline = request.created_at, request.deadline_at
    hospital = store.hospitals[request.hospital_id]
    result = BaselineRun(state=BaselineState(request_id=request.id))
    events = result.events
    found = 0

    listing = best_listing(store, request)
    first_wave = t0
    if listing is not None:
        centre = store.centres[listing.centre_id]
        events.append((t0, f"Listing shows {listing.listed_units} at {centre.name}: blood found"))
        trip = t0 + minutes(config.FAMILY_TRIP_MIN)
        if trip < deadline:
            result.trip_at = trip
            found = min(listing.true_units, request.units)
            events.append((trip, f"{centre.name} has {listing.true_units}"))
            ready_at = trip + minutes(config.ISSUE_FROM_STOCK_MIN + travel_min(centre, hospital))
            result.stock_ready = found if ready_at <= deadline else 0
        first_wave = trip
    else:
        events.append((t0, "No listing found; forwarding the plea"))
    result.state.found_units = found

    said_at = first_wave if found >= request.units else None
    if said_at is not None:
        events.append((said_at, "Blood found: marked fulfilled"))

    order, sent, yeses = forward_order(store, request), 0, []
    queue = [(first_wave, 0, "wave", None)] if said_at is None and first_wave < deadline else []
    while queue and said_at is None:
        at, _, kind, item = heapq.heappop(queue)
        if at >= deadline:
            break
        if kind == "wave" and sent < len(order):
            batch = order[sent: sent + config.BASELINE_WAVE]
            for i, donor_id in enumerate(batch, start=sent + 1):
                latent = latent_for(donor_id, i)
                if latent is not None and latent.says_yes and latent.reply_delay_min is not None:
                    heapq.heappush(queue, (at + minutes(latent.reply_delay_min), 1, "yes", (donor_id, latent)))
            sent += len(batch)
            result.messaged_at += [at] * len(batch)
            events.append((at, f"Plea forwarded to {len(batch)} donors"))
            heapq.heappush(queue, (at + minutes(config.BASELINE_INTERVAL_MIN), 0, "wave", None))
        elif kind == "yes":
            donor_id, latent = item
            yeses.append((at, donor_id, latent))
            if found + len(yeses) >= request.units:
                said_at = at
                events.append((at, f"{store.donors[donor_id].display_name} said yes: marked fulfilled"))

    # the first yes-donors still needed go and donate (no backups); count what is really ready in time
    going = yeses[: request.units - found]
    donor_ready = sum(donor_unit_ready(store, request, d, lat, at) for at, d, lat in going)
    result.units_ready = min(request.units, result.stock_ready + donor_ready)

    state = result.state
    state.donors_messaged = sent
    state.said_fulfilled_at = said_at
    state.status = BaselineStatus.SAYS_FULFILLED if said_at else BaselineStatus.SEARCHING
    events.sort(key=lambda e: e[0])
    state.timeline = [f"{at.strftime('%H:%M')} {text}" for at, text in events]
    return result


def view_at(run_: BaselineRun, now: datetime, units: int, deadline: datetime) -> dict:
    """BaselineView (BUILD §5.3) as of `now`: truth only once the deadline has passed."""
    shown = [f"{at.strftime('%H:%M')} {text}" for at, text in run_.events if at <= now]
    said = run_.state.said_fulfilled_at
    return {
        "request_id": run_.state.request_id,
        "status": (BaselineStatus.SAYS_FULFILLED if said and said <= now else BaselineStatus.SEARCHING).value,
        "said_fulfilled_at": said.isoformat() if said and said <= now else None,
        "donors_messaged": sum(1 for at in run_.messaged_at if at <= now),
        "found_units": run_.state.found_units if run_.trip_at and run_.trip_at <= now else 0,
        "timeline": shown,
        "truth_at_deadline": {"units_ready": run_.units_ready, "units": units} if now >= deadline else None,
    }
