"""Map projection (BUILD §5.3): where the world's centres, hospitals and donors sit, and what the planner did with them.

Read-only: it reads the same state the planner and the request view read, under store.lock, and decides nothing.
Positions are the coordinates the planner's own distance and travel checks use; every one is synthetic or approximate.
No contact details (chat ids, phones, usernames) are returned.
"""

import math

from fastapi import APIRouter, HTTPException

from rakt import store
from rakt.agent import planner, ranking
from rakt.domain.geo import km, travel_min
from rakt.models import RequestStatus

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
