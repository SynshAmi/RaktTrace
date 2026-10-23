"""Phase 8 API additions the dashboard relies on: the active scenario, and an honest LLM status."""

import pytest
from fastapi.testclient import TestClient

from rakt import llm
from rakt.config import settings
from rakt.main import app

SCENARIOS = ("s1_surgery_tonight", "s2_dengue_sdp", "s3_no_way_in_time")


@pytest.fixture
def api():
    with TestClient(app) as client:
        yield client


def test_clock_and_reset_report_the_world_actually_running(api):
    for scenario_id in SCENARIOS:
        reset = api.post("/api/demo/reset", json={"scenario": scenario_id}).json()
        clock = api.get("/api/demo/clock").json()
        assert reset["scenario"]["id"] == clock["scenario"]["id"] == scenario_id
        assert reset["now"] == clock["now"] and reset["auto"] is False
        (request,) = api.get("/api/requests").json()
        assert request["id"] == reset["request_id"]


def test_switching_scenarios_leaves_nothing_behind(api):
    first = api.post("/api/demo/reset", json={"scenario": "s2_dengue_sdp"}).json()["request_id"]
    for _ in range(12):
        api.post("/api/demo/step")
    second = api.post("/api/demo/reset", json={"scenario": "s1_surgery_tonight"}).json()["request_id"]
    view = api.get(f"/api/requests/{second}").json()
    assert [r["id"] for r in api.get("/api/requests").json()] == [second]
    assert view["donors"] == [] and view["group"] == "B_POS" and view["now"] == "2026-10-24T18:00:00+05:30"
    if first != second:
        assert api.get(f"/api/requests/{first}").status_code == 404


def test_replaying_a_scenario_gives_the_same_story(api):
    def run():
        rid = api.post("/api/demo/reset", json={"scenario": "s2_dengue_sdp"}).json()["request_id"]
        trail = []
        for _ in range(40):
            step = api.post("/api/demo/step").json()
            view = api.get(f"/api/requests/{rid}").json()
            trail.append((step["now"], view["status"], view["p"], view["units_ladder"]["confirmed"]))
        return trail

    assert run() == run()


def test_health_says_llm_off_when_no_provider_is_configured(api, monkeypatch):
    monkeypatch.setattr(llm, "_enabled", True)
    monkeypatch.setattr(settings, "llm_chain", "")
    assert api.get("/api/health").json()["llm"] == "off"
    monkeypatch.setattr(settings, "llm_chain", "groq:some-model")
    monkeypatch.setattr(settings, "groq_api_key", "")
    assert api.get("/api/health").json()["llm"] == "off"
    monkeypatch.setattr(settings, "groq_api_key", "test-key")
    assert api.get("/api/health").json()["llm"] == "on"
    monkeypatch.setattr(llm, "_enabled", False)
    assert api.get("/api/health").json()["llm"] == "off"


# --- "On my way" from an ACTIVE donor (the donor_go card) ---

def active_pledge_in_s2():
    from rakt import store
    from rakt.agent import loop
    from rakt.models import PledgeStatus

    loop.reset_scenario("s2_dengue_sdp")
    state = store.state
    for _ in range(200):
        active = [p for p in state.main.pledges.values() if p.status == PledgeStatus.ACTIVE]
        if active:
            return state, active[0]
        state.clock.step(loop.on_timer)
    raise AssertionError("no donor went active")


def tap(chat_id: str, data: str):
    from rakt.channels import telegram_bot as bot
    return bot.on_callback(chat_id, "Judge", data)


def test_on_my_way_from_an_active_donor_is_recorded_and_acknowledged_once():
    from rakt.channels import simulated
    from rakt.models import PledgeStatus

    state, pledge = active_pledge_in_s2()
    donor = state.main.donors[pledge.donor_id]
    donor.contact.chat_id = "9001"  # the donor's Telegram chat, as for a judge's phone
    phone = simulated.phone_id(donor.contact)
    decisions = len(state.main.decisions)

    tap("9001", f"P:{pledge.id}:OMW")

    assert pledge.status == PledgeStatus.ACTIVE and pledge.on_way_at == state.clock.now  # lifecycle unchanged
    new = state.main.decisions[decisions:]
    assert [d.trigger for d in new] == [f"{donor.display_name} is on the way (via Telegram)"]
    sent = [m for m in simulated.inbox(phone) if m.direction == "out" and m.kind == "donor_on_way"]
    assert len(sent) == 1 and pledge.booking_code in sent[0].body

    tap("9001", f"P:{pledge.id}:OMW")  # a repeated tap changes nothing
    assert len(state.main.decisions) == decisions + 1
    assert len([m for m in simulated.inbox(phone) if m.kind == "donor_on_way"]) == 1


def test_on_my_way_is_ignored_from_a_stranger_or_after_cant():
    from rakt.models import PledgeStatus

    state, pledge = active_pledge_in_s2()
    state.main.donors[pledge.donor_id].contact.chat_id = "9001"
    decisions = len(state.main.decisions)
    tap("9999", f"P:{pledge.id}:OMW")  # not the donor's chat
    assert pledge.on_way_at is None and len(state.main.decisions) == decisions

    tap("9001", f"P:{pledge.id}:CANT")
    assert pledge.status == PledgeStatus.NO_SHOW
    after = len(state.main.decisions)
    tap("9001", f"P:{pledge.id}:OMW")
    assert pledge.status == PledgeStatus.NO_SHOW and pledge.on_way_at is None and len(state.main.decisions) == after


# --- A live (Telegram) donor at a simulated centre: check-in, screening, collection, staff confirmation ---

JUDGE, STAFF = "9001", "9003"


def live_judge_says_yes(on_my_way: bool = True, link_staff: bool = False):
    from rakt import store
    from rakt.agent import live, loop
    from rakt.channels import telegram_bot as bot

    loop.reset_scenario("s2_dengue_sdp")
    state = store.state
    if link_staff:
        bot.on_start(STAFF, "Aditya", "staff_c_b", private=True)
    tap(JUDGE, "O:JOIN")
    donor_id = live.registry.identities[JUDGE].donor_id
    while not state.main.pledges:
        state.clock.step(loop.on_timer)
    judge = next(p for p in state.main.pledges.values() if p.donor_id == donor_id)
    tap(JUDGE, f"P:{judge.id}:YES")
    if on_my_way:
        tap(JUDGE, f"P:{judge.id}:OMW")
    return state, judge


def run_to_end(state):
    from rakt.agent import loop
    while state.clock.step(loop.on_timer):
        pass


def test_live_donor_goes_from_yes_to_ready_through_the_simulated_centre():
    from datetime import timedelta

    from rakt.domain.geo import travel_min
    from rakt.models import PledgeStatus, RequestStatus

    state, judge = live_judge_says_yes()
    request = state.main.requests[judge.request_id]
    yes_at = state.clock.now
    assert judge.status == PledgeStatus.ACTIVE and judge.on_way_at == yes_at  # on the way is not arrival
    name = state.main.donors[judge.donor_id].display_name
    run_to_end(state)
    by_trigger = {d.trigger: d for d in state.main.decisions}
    arrived = by_trigger[f"Centre B: {name} ARRIVED (simulated staff)"]
    travel = travel_min(state.main.donors[judge.donor_id], state.main.centres["c_b"])
    assert arrived.at == yes_at + timedelta(minutes=travel)  # the centre checks them in at their travel time
    assert f"Centre B: {name} COLLECTED (simulated staff)" in by_trigger
    assert "Centre B: unit ready (simulated staff)" in by_trigger  # only staff make the unit ready
    assert judge.status == PledgeStatus.READY and request.status == RequestStatus.FULFILLED
    assert request.escalation_level == 0
    assert not any("hasn't tapped" in d.trigger for d in state.main.decisions)


def test_live_donor_check_in_and_screening_replay_the_same_way():
    def trail():
        state, _ = live_judge_says_yes()
        run_to_end(state)
        return [(d.at, d.trigger) for d in state.main.decisions]

    assert trail() == trail()


def test_live_donor_deferred_at_screening_promotes_a_standby(monkeypatch):
    from rakt.models import PledgeStatus
    from rakt.sim import bots

    monkeypatch.setattr(bots, "live_screening_passes", lambda pledge, product: False)
    state, judge = live_judge_says_yes()
    run_to_end(state)
    name = state.main.donors[judge.donor_id].display_name
    deferral = next(d for d in state.main.decisions if d.trigger == f"Centre B: {name} DEFERRED (simulated staff)")
    assert judge.status == PledgeStatus.DEFERRED and "Asked standby" in deferral.summary


def test_linked_centre_staff_take_precedence_over_the_simulated_centre(monkeypatch):
    from rakt.channels import telegram_bot as bot
    from rakt.models import PledgeStatus

    monkeypatch.setattr(bot, "send", lambda chat_id, text, buttons, on_fail: True)  # Telegram delivers
    state, judge = live_judge_says_yes(on_my_way=False, link_staff=True)
    pending = [t for t in state.clock.pending() if t.kind == "sim_inbound" and t.payload.get("sender_id") == "c_b"]
    assert not pending  # the simulated centre stands aside; Centre B's linked staff tap for themselves
    tap(STAFF, f"V:{judge.id}:ARRIVED")
    assert judge.status == PledgeStatus.ARRIVED
    tap(STAFF, f"V:{judge.id}:ARRIVED")  # a repeated tap changes nothing
    assert judge.status == PledgeStatus.ARRIVED


def test_on_my_way_after_check_in_gets_one_reply_and_changes_nothing():
    from rakt.agent import loop
    from rakt.channels import simulated
    from rakt.models import PledgeStatus

    state, judge = live_judge_says_yes(on_my_way=False)
    while judge.status == PledgeStatus.ACTIVE:
        state.clock.step(loop.on_timer)
    assert judge.status == PledgeStatus.ARRIVED
    decisions = len(state.main.decisions)
    tap(JUDGE, f"P:{judge.id}:OMW")
    tap(JUDGE, f"P:{judge.id}:OMW")
    phone = simulated.phone_id(state.main.donors[judge.donor_id].contact)
    assert [m.kind for m in simulated.inbox(phone) if m.kind == "donor_checked_in"] == ["donor_checked_in"]
    assert judge.status == PledgeStatus.ARRIVED and len(state.main.decisions) == decisions


def test_request_view_says_who_staffs_the_collection_centre(api, monkeypatch):
    from rakt.channels import telegram_bot as bot

    rid = api.post("/api/demo/reset", json={"scenario": "s2_dengue_sdp"}).json()["request_id"]
    for _ in range(3):
        api.post("/api/demo/step")
    assert api.get(f"/api/requests/{rid}").json()["collection_centre"]["staff"] == "simulated"
    monkeypatch.setattr(bot, "send", lambda chat_id, text, buttons, on_fail: True)
    bot.on_start(STAFF, "Aditya", "staff_c_b", private=True)
    assert api.get(f"/api/requests/{rid}").json()["collection_centre"]["staff"] == "telegram"
