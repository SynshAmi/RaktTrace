"""The donor map: stable, labelled positions for every donor and centre, read-only projection of the planner's state,
and the Telegram profile's location choice (pick an area / simulate). Nothing talks to Telegram."""

import copy
import json

import pytest
from fastapi.testclient import TestClient

from rakt import store
from rakt.agent import live, loop, ranking
from rakt.api.map import map_view
from rakt.channels import telegram_bot as bot
from rakt.domain.geo import haversine_km, travel_min
from rakt.main import app
from rakt.models import PledgeStatus, RequestStatus
from rakt.sim.world import AREAS, generate_world

S, Q = PledgeStatus, RequestStatus
JUDGE, OTHER = "8001", "8002"


def reset(scenario_id: str):
    loop.reset_scenario(scenario_id)
    (rid,) = store.state.main.requests
    return store.state, rid


def run_until(state, condition, limit=3000):
    for _ in range(limit):
        if condition() or state.clock.step(loop.on_timer) is None:
            return
    raise AssertionError("condition never met")


def positions(view: dict) -> dict:
    return {d["id"]: (d["lat"], d["lon"], d["location"], d["location_basis"]) for d in view["donors"]}


def create(chat_id: str, answers: dict, name: str = "Judge B."):
    bot.on_callback(chat_id, name, "O:CREATE")
    reply = None
    for step, (field, _, _) in enumerate(bot.QUESTIONS):
        if bot.applies(step, answers):
            reply = bot.on_callback(chat_id, name, f"Q:{step}:{answers[field]}")
    return live.registry.identities[chat_id].donor_id, reply


PROFILE = {"group": "O_POS", "travel_min": "20", "sex": "M", "age": "32", "weight_kg": "70",
           "last_donation": "never", "apheresis_ok": "yes"}


@pytest.fixture
def api():
    with TestClient(app) as client:
        yield client


# --- Seeded positions ---

def test_seeded_donors_and_centres_have_stable_synthetic_positions():
    state, rid = reset("s2_dengue_sdp")
    first = map_view(rid)
    assert first["unplaced"] == 0 and len(first["donors"]) == len(state.main.donors)
    assert all(d["location"] == "synthetic" and d["location_basis"] == "seeded" for d in first["donors"])
    assert positions(map_view(rid)) == positions(first)  # repeated reads
    state, rid = reset("s2_dengue_sdp")  # a reset rebuilds the same world from the seed
    assert positions(map_view(rid)) == positions(first)
    a, b = generate_world(7, state.clock.now), generate_world(7, state.clock.now)
    assert [(d.lat, d.lon) for d in a.donors.values()] == [(d.lat, d.lon) for d in b.donors.values()]
    assert {c["id"] for c in first["centres"]} == set(state.main.centres)


def test_map_marks_the_requesting_hospital_and_collection_centre():
    state, rid = reset("s2_dengue_sdp")
    run_until(state, lambda: bool(state.main.pledges))
    view = map_view(rid)
    request = state.main.requests[rid]
    assert [h["id"] for h in view["hospitals"] if h["requesting"]] == [request.hospital_id]
    assert [c["id"] for c in view["centres"] if c["collection"]] == [request.collection_centre_id]
    assert view["request"]["radius_km"] == request.radius_km


# --- Telegram donors ---

def test_live_demo_donor_keeps_one_synthetic_position_across_reads_and_resets():
    state, rid = reset("s2_dengue_sdp")
    bot.on_callback(JUDGE, "Judge A.", "O:JOIN")
    donor_id = live.registry.identities[JUDGE].donor_id
    first = positions(map_view(rid))[donor_id]
    assert first[2:] == ("synthetic", "template")
    assert positions(map_view(rid))[donor_id] == first
    state, rid = reset("s1_surgery_tonight")
    assert positions(map_view(rid))[donor_id] == first


def test_picked_area_is_approximate_and_near_that_area():
    state, rid = reset("s2_dengue_sdp")
    donor_id, reply = create(OTHER, {**PROFILE, "location": "area", "area": "Koramangala"})
    donor = store.state.main.donors[donor_id]
    assert (donor.location, donor.location_basis, donor.area) == ("approximate", "area", "Koramangala")
    assert haversine_km((donor.lat, donor.lon), AREAS["Koramangala"]) < 0.5  # the area's centre, jittered
    assert donor.stated_travel_min == 20
    assert "approximate area" in reply[0]


def test_simulated_location_is_stable_and_matches_the_stated_travel_time():
    state, rid = reset("s2_dengue_sdp")
    donor_id, reply = create(OTHER, {**PROFILE, "travel_min": "30", "location": "simulate"})
    donor = store.state.main.donors[donor_id]
    assert (donor.location, donor.location_basis, donor.stated_travel_min) == ("synthetic", "simulated", 30)
    assert abs(travel_min(donor, state.main.centres[live.SIMULATED_FROM]) - 30) < 0.5  # the planner's own model
    assert "simulated location" in reply[0]
    again = live.simulated_location(OTHER, 30)
    assert (donor.lat, donor.lon) == again[:2] and donor.area == again[2]
    state, rid = reset("s2_dengue_sdp")
    assert (store.state.main.donors[donor_id].lat, store.state.main.donors[donor_id].lon) == (donor.lat, donor.lon)


def test_simulated_location_skips_the_area_question():
    reset("s2_dengue_sdp")
    bot.on_callback(OTHER, "B", "O:CREATE")
    bot.on_callback(OTHER, "B", "Q:0:O_POS")
    bot.on_callback(OTHER, "B", "Q:1:20")
    text, buttons = bot.on_callback(OTHER, "B", "Q:2:simulate")
    assert buttons[0].id.startswith("Q:4:")  # straight to sex: no area asked
    assert text.startswith("(4/8)")  # 8 questions in all on this route


def test_unsupported_area_or_answer_restarts_safely():
    reset("s2_dengue_sdp")
    bot.on_callback(OTHER, "B", "O:CREATE")
    bot.on_callback(OTHER, "B", "Q:0:O_POS")
    bot.on_callback(OTHER, "B", "Q:1:20")
    bot.on_callback(OTHER, "B", "Q:2:area")
    text, buttons = bot.on_callback(OTHER, "B", "Q:3:Atlantis")  # not one of the supported areas
    assert text.startswith("Let's start again") and buttons[0].id.startswith("Q:0:")
    assert OTHER not in live.registry.identities or live.registry.identities[OTHER].profile is None
    text, _ = bot.on_callback(OTHER, "B", "Q:0:Z_POS")  # an unknown blood group
    assert text.startswith("Let's start again")


# --- A read-only projection of the planner ---

def test_map_reads_never_change_the_run():
    plain_state, rid = reset("s2_dengue_sdp")
    while plain_state.clock.step(loop.on_timer):
        pass
    plain = [d.summary for d in plain_state.main.decisions if d.request_id == rid]

    state, rid = reset("s2_dengue_sdp")
    while True:
        before, timers = copy.deepcopy(state.main), len(state.clock._queue)
        map_view(rid)
        assert state.main == before and len(state.clock._queue) == timers
        if not state.clock.step(loop.on_timer):
            break
    assert [d.summary for d in state.main.decisions if d.request_id == rid] == plain


def test_candidates_are_the_planners_own_and_within_its_radius():
    state, rid = reset("s2_dengue_sdp")
    run_until(state, lambda: bool(state.main.pledges))
    request = state.main.requests[rid]
    centre = state.main.centres[request.collection_centre_id]
    view = map_view(rid)
    flagged = {d["id"] for d in view["donors"] if d["candidate"]}
    assert flagged == {c.donor_id for c in ranking.candidates(state.main, request, centre, state.clock.now)}
    assert all(d["km"] <= request.radius_km for d in view["donors"] if d["candidate"])


def test_pledge_states_on_the_map_follow_the_request():
    state, rid = reset("s2_dengue_sdp")
    run_until(state, lambda: any(p.status == S.ACTIVE for p in state.main.pledges.values()))
    view = {d["id"]: d for d in map_view(rid)["donors"]}
    for p in state.main.pledges.values():
        assert view[p.donor_id]["pledge"]["status"] == p.status.value
    assert state.main.requests[rid].status != Q.FULFILLED  # a yes alone is not blood
    run_until(state, lambda: state.main.requests[rid].status == Q.FULFILLED)
    view = {d["id"]: d for d in map_view(rid)["donors"]}
    assert any(d["pledge"] and d["pledge"]["status"] == "READY" for d in view.values())  # staff confirmed it
    assert any(d["pledge"] and d["pledge"]["status"] == "DEFERRED" for d in view.values())  # S2's screening deferral


def test_map_endpoint_shape_privacy_and_reset(api):
    state, rid = reset("s2_dengue_sdp")
    bot.on_callback(JUDGE, "Judge A.", "O:JOIN")
    body = api.get(f"/api/map?request_id={rid}").json()
    raw = json.dumps(body)
    assert JUDGE not in raw and "+91" not in raw and "chat_id" not in raw and "phone" not in raw
    assert {"centres", "hospitals", "donors", "request", "unplaced", "now"} <= set(body)
    assert any(d["live"] for d in body["donors"])
    assert api.get("/api/map").status_code == 200  # no request: the world only
    api.post("/api/demo/reset", json={"scenario": "s1_surgery_tonight"})
    assert api.get(f"/api/map?request_id={rid}").status_code == 404  # the old request is gone with its world
