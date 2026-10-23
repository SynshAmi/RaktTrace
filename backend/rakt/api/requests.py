"""Reference and request endpoints (BUILD §5.3)."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from rakt import llm, store
from rakt.agent import live, loop
from rakt.api.views import iso, minutes_between, request_summary, request_view
from rakt.baseline import policy as today
from rakt.models import BloodGroup, Channel, Contact, Product, RequestStatus

router = APIRouter()


class ParseBody(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class CreateBody(BaseModel):
    group: BloodGroup
    product: Product
    units: int = Field(ge=1, le=10)
    hospital_id: str
    deadline_at: datetime
    family: Literal["telegram", "sim"] | None = None


def found(request_id: str):
    request = store.state.main.requests.get(request_id)
    if request is None:
        raise HTTPException(404, f"No request {request_id}")
    return request


@router.get("/hospitals")
def hospitals() -> list[dict]:
    with store.lock:
        return [{"id": h.id, "name": h.name, "area": h.area} for h in store.state.main.hospitals.values()]


@router.get("/centres")
def centres() -> list[dict]:
    with store.lock:
        s, now = store.state.main, store.state.clock.now
        return [{
            "id": c.id, "name": c.name, "area": c.area, "apheresis": c.apheresis,
            "stock": [{"product": x.product.value, "group": x.group.value, "listed_units": x.listed_units,
                       "listed_age_min": minutes_between(x.listed_at, now)}
                      for x in s.stock if x.centre_id == c.id and x.listed_units > 0],
        } for c in s.centres.values()]


@router.post("/requests/parse")
def parse(body: ParseBody) -> dict:
    with store.lock:
        listing = [{"id": h.id, "name": h.name, "area": h.area} for h in store.state.main.hospitals.values()]
        now = store.state.clock.now
    draft = llm.read_plea(body.text, listing, now)  # outside the lock: the LLM may be slow
    return {
        "draft": {"group": draft.group.value if draft.group else None,
                  "product": draft.product.value if draft.product else None, "units": draft.units,
                  "hospital_id": draft.hospital_id, "deadline_at": iso(draft.deadline_at)},
        "missing": draft.missing, "confidence": draft.confidence, "read_by": draft.read_by,
    }


@router.post("/requests")
def create(body: CreateBody) -> dict:
    with store.lock:
        s, now = store.state.main, store.state.clock.now
        if body.hospital_id not in s.hospitals:
            raise HTTPException(422, f"Unknown hospital {body.hospital_id}")
        if body.deadline_at <= now:
            raise HTTPException(422, "The deadline must be after the sim clock's now")
        request_id, merged = loop.create_request(body.group, body.product, body.units, body.hospital_id,
                                                 body.deadline_at)
        if merged:
            return {"merged_into": request_id}
        request = s.requests[request_id]
        if body.family is not None:
            request.family = Contact(name="Family", channel=Channel.SIM, phone=f"family_{request_id}")
            if body.family == "telegram" and live.family_chat() is not None:
                live.apply_family(live.family_chat())
        return request_view(request_id)


@router.get("/requests")
def list_requests() -> list[dict]:
    with store.lock:
        return [request_summary(r) for r in store.state.main.requests.values()]


@router.get("/requests/{request_id}")
def get_request(request_id: str) -> dict:
    with store.lock:
        found(request_id)
        return request_view(request_id)


@router.get("/requests/{request_id}/baseline")
def baseline(request_id: str) -> dict:
    with store.lock:
        request = found(request_id)
        run = store.state.baselines.get(request_id)
        if run is None:
            raise HTTPException(404, f"No today's-workflow lane for {request_id}")
        return today.view_at(run, store.state.clock.now, request.units, request.deadline_at)


@router.get("/requests/{request_id}/decisions")
def decisions(request_id: str) -> list[dict]:
    with store.lock:
        found(request_id)
        return [d.model_dump(mode="json") for d in store.state.main.decisions if d.request_id == request_id]


@router.post("/requests/{request_id}/cancel")
def cancel(request_id: str) -> dict:
    with store.lock:
        request = found(request_id)
        if request.status not in (RequestStatus.OPEN, RequestStatus.COVERED, RequestStatus.SECURED):
            raise HTTPException(409, f"{request_id} is already {request.status.value}")
        loop.cancel(request_id)
        return request_view(request_id)
