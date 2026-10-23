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
