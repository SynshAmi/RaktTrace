"""Map projection (BUILD §5.3): where the world's centres, hospitals and donors sit, and what the planner did with them.

Read-only: it reads the same state the planner and the request view read, under store.lock, and decides nothing.
Positions are the coordinates the planner's own distance and travel checks use; every one is synthetic or approximate.
No contact details (chat ids, phones, usernames) are returned.
"""

import math
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException

from rakt import config, store
from rakt.agent import planner, ranking
from rakt.domain.eligibility import eligibility_failures
from rakt.domain.geo import km, travel_min
from rakt.models import PledgeStatus, RequestStatus

router = APIRouter()
INVITING = {RequestStatus.OPEN, RequestStatus.COVERED}


def placed(lat: float, lon: float) -> bool:
    return math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180


@router.get("/map")
def map_view(request_id: str | None = None) -> dict:
    with store.lock:
        state = store.state
        s, now = state.main, state.clock.now
        request = None
        if request_id is not None:
            request = s.requests.get(request_id)
            if request is None:
                raise HTTPException(404, f"No request {request_id}")

        centre = planner.donor_centre(s, request) if request else None
        holds = [r for r in s.reservations.values() if request and r.request_id == request.id]
        pledges = {p.donor_id: p for p in s.pledges.values() if request and p.request_id == request.id}
        candidate_ids = (
            {c.donor_id for c in ranking.candidates(s, request, centre, now)}
            if request and centre and request.status in INVITING else set()
        )

        centres = [{
            "id": c.id, "name": c.name, "area": c.area, "lat": c.lat, "lon": c.lon,
            "apheresis": c.apheresis, "accepts_donors": c.accepts_donors,
            "staff": "telegram" if c.contact.chat_id else "simulated",
            "collection": centre is not None and c.id == centre.id,
            "holds": [{"status": r.status.value, "units_asked": r.units_asked, "units_reserved": r.units_reserved}
                      for r in holds if r.centre_id == c.id],
        } for c in s.centres.values() if placed(c.lat, c.lon)]

        hospitals = [{
            "id": h.id, "name": h.name, "area": h.area, "lat": h.lat, "lon": h.lon,
            "requesting": request is not None and h.id == request.hospital_id,
        } for h in s.hospitals.values() if placed(h.lat, h.lon)]

        donors, unplaced = [], 0
        for d in s.donors.values():
            if not placed(d.lat, d.lon):
                unplaced += 1
                continue
            p = pledges.get(d.id)
            donors.append({
                "id": d.id, "name": d.display_name, "group": d.group.value, "lat": d.lat, "lon": d.lon,
                "area": d.area, "location": d.location, "location_basis": d.location_basis, "live": d.telegram_demo,
                "stated_travel_min": d.stated_travel_min, "opted_out": d.opted_out,
                "km": round(km(d, centre), 1) if centre else None,
                "travel_min": round(travel_min(d, centre)) if centre else None,
                "candidate": d.id in candidate_ids,
                "pledge": None if p is None else {
                    "status": p.status.value, "booking_code": p.booking_code, "on_way": p.on_way_at is not None,
                    "why": p.why,
                },
            })

        return {
            "now": now.isoformat(),
            "request": None if request is None else {
                "id": request.id, "status": request.status.value, "group": request.group.value,
                "product": request.product.value, "units": request.units, "radius_km": request.radius_km,
                "collection_centre_id": centre.id if centre else None,
            },
            "centres": centres, "hospitals": hospitals, "donors": donors, "unplaced": unplaced,
        }


# DOMAIN_RULES §2, in words. The check is the planner's own; screening is always the blood centre's call.
RULES = {
    "E1": "under 18", "E2": "over the whole-blood age limit", "E3": "outside the apheresis age range (18–60)",
    "E4": "under 45 kg", "E5": "under 50 kg (apheresis)", "E6": "whole-blood interval not over (90/120 days)",
    "E7": "apheresis interval or count limit", "E8": "whole blood in the last 28 days (before apheresis)",
    "E9": "apheresis in the last 28 days (before whole blood)", "E10": "deferred by a centre", "E11": "opted out",
}
COMING = {PledgeStatus.ACTIVE, PledgeStatus.ARRIVED, PledgeStatus.COLLECTED, PledgeStatus.READY}


def iso(at: datetime | None) -> str | None:
    return at.isoformat() if at else None


def donor_profile(s, d, request, now: datetime) -> dict:
    centre = planner.donor_centre(s, request) if request else None
    pledge = next((p for p in s.pledges.values() if request and p.request_id == request.id and p.donor_id == d.id), None)
    check = None
    if request:
        travel = travel_min(d, centre) if centre else 0
        at = now + timedelta(minutes=config.REPLY_LAG_MIN + travel)
        failures = eligibility_failures(d, request.product, at)
        check = {"product": request.product.value, "passes": not failures, "reasons": [RULES.get(f, f) for f in failures]}
    candidate = None
    if request and centre and request.status in INVITING:
        candidate = next((c.why for c in ranking.candidates(s, request, centre, now) if c.donor_id == d.id), None)
    year_ago = now - timedelta(days=365)
    return {
        "kind": "donor", "id": d.id, "name": d.display_name, "group": d.group.value, "sex": d.sex, "age": d.age,
        "weight_kg": d.weight_kg, "area": d.area, "live": d.telegram_demo, "apheresis_ok": d.apheresis_ok,
        "donation_verified": d.donation_verified, "last_whole_blood_at": iso(d.last_whole_blood_at),
        "apheresis_last_year": sum(t >= year_ago for t in d.apheresis_dates),
        "last_apheresis_at": iso(max(d.apheresis_dates)) if d.apheresis_dates else None,
        "deferred_until": iso(d.deferred_until), "opted_out": d.opted_out,
        "invites_last_72h": sum(now - t < timedelta(hours=config.REST_H) for t in d.invites),
        "location": d.location, "location_basis": d.location_basis, "stated_travel_min": d.stated_travel_min,
        "km": round(km(d, centre), 1) if centre else None,
        "travel_min": round(travel_min(d, centre)) if centre else None,
        "centre": centre.name if centre else None,
        "rule_check": check, "candidate_why": candidate,
        "pledge": None if pledge is None else {
            "status": pledge.status.value, "wave": pledge.wave, "invited_at": iso(pledge.invited_at),
            "replied_at": iso(pledge.replied_at), "reply_text": pledge.reply_text,
            "available_from": iso(pledge.available_from), "booking_code": pledge.booking_code,
            "on_way_at": iso(pledge.on_way_at), "ready_at": iso(pledge.ready_at), "why": pledge.why,
        },
    }


def centre_profile(s, c, request, now: datetime) -> dict:
    coming = [p for p in s.pledges.values() if p.status in COMING and s.requests[p.request_id].collection_centre_id == c.id]
    return {
        "kind": "centre", "id": c.id, "name": c.name, "area": c.area, "address": c.address, "phone": c.phone,
        "apheresis": c.apheresis, "accepts_donors": c.accepts_donors,
        "staff": "telegram" if c.contact.chat_id else "simulated",
        "listed_stock": [{"product": x.product.value, "group": x.group.value, "listed_units": x.listed_units,
                          "listed_age_min": round((now - x.listed_at) / timedelta(minutes=1))}
                         for x in s.stock if x.centre_id == c.id and x.listed_units > 0],
        "holds": [{"request_id": r.request_id, "status": r.status.value, "units_asked": r.units_asked,
                   "units_reserved": r.units_reserved}
                  for r in s.reservations.values() if r.centre_id == c.id and (not request or r.request_id == request.id)],
        "donors_coming": [{"donor_id": p.donor_id, "name": s.donors[p.donor_id].display_name,
                           "group": s.donors[p.donor_id].group.value, "status": p.status.value,
                           "booking_code": p.booking_code, "request_id": p.request_id}
                          for p in coming],
    }


def hospital_profile(s, h) -> dict:
    own = s.centres.get(h.centre_id) if h.centre_id else None
    return {
        "kind": "hospital", "id": h.id, "name": h.name, "area": h.area, "own_centre": own.name if own else None,
        "requests": [{"id": r.id, "group": r.group.value, "product": r.product.value, "units": r.units,
                      "status": r.status.value, "deadline_at": iso(r.deadline_at)}
                     for r in s.requests.values() if r.hospital_id == h.id],
    }


@router.get("/map/profile/{kind}/{item_id}")
def profile(kind: Literal["donor", "centre", "hospital"], item_id: str, request_id: str | None = None) -> dict:
    """One marker's profile. Synthetic data only; never contact details (no chat ids, Telegram names are display
    names already shown on the dashboard). Medical screening stays with the blood centre."""
    with store.lock:
        s, now = store.state.main, store.state.clock.now
        request = s.requests.get(request_id) if request_id else None
        if request_id and request is None:
            raise HTTPException(404, f"No request {request_id}")
        found = {"donor": s.donors, "centre": s.centres, "hospital": s.hospitals}[kind].get(item_id)
        if found is None:
            raise HTTPException(404, f"No {kind} {item_id}")
        if kind == "donor":
            return donor_profile(s, found, request, now)
        if kind == "centre":
            return centre_profile(s, found, request, now)
        return hospital_profile(s, found)
