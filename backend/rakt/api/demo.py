"""Demo controls (BUILD §5.3): scenarios, reset, the sim clock (step, advance, auto)."""

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from rakt import store
from rakt.agent import loop
from rakt.sim.scenarios import list_scenarios

router = APIRouter()
AUTO_TICK_S = 1.0  # 1 sim minute per real second


class ResetBody(BaseModel):
    scenario: str


class AdvanceBody(BaseModel):
    minutes: float = Field(gt=0, le=24 * 60)


class AutoBody(BaseModel):
    on: bool


def clock_view() -> dict:
    scenario = store.state.scenario
    return {"now": store.state.clock.now.isoformat(), "auto": store.state.auto,
            "scenario": {"id": scenario.id, "title": scenario.title} if scenario else None}


@router.get("/demo/scenarios")
def scenarios() -> list[dict]:
    return list_scenarios()


@router.post("/demo/reset")
def reset(body: ResetBody) -> dict:
    if body.scenario not in {s["id"] for s in list_scenarios()}:
        raise HTTPException(404, f"No scenario {body.scenario}")
    with store.lock:
        loop.reset_scenario(body.scenario)  # a new world and clock; linked live identities are attached again
        return {**clock_view(), "request_id": store.state.scenario_request_id}


@router.get("/demo/clock")
def clock() -> dict:
    with store.lock:
        return clock_view()


@router.post("/demo/step")
def step() -> dict:
    """Jump to the next timer or scripted event and process only that one."""
    with store.lock:
        timer = store.state.clock.step(loop.on_timer)
        event = None if timer is None else {"kind": timer.kind, "request_id": timer.request_id,
                                            "at": timer.at.isoformat()}
        return {"now": store.state.clock.now.isoformat(), "event": event}


@router.post("/demo/advance")
def advance(body: AdvanceBody) -> dict:
    with store.lock:
        store.state.clock.advance(body.minutes, loop.on_timer)
        return {"now": store.state.clock.now.isoformat()}


@router.post("/demo/auto")
def auto(body: AutoBody) -> dict:
    with store.lock:
        store.state.auto = body.on
        return {"auto": store.state.auto}


def tick() -> None:
    with store.lock:
        if store.state is not None and store.state.auto:
            store.state.clock.advance(1, loop.on_timer)


async def run_auto_clock() -> None:
    """Background task (started with the app): while auto is on, 1 sim minute per real second."""
    while True:
        await asyncio.sleep(AUTO_TICK_S)
        await asyncio.to_thread(tick)
