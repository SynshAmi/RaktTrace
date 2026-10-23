"""Gate 7.V and the agreed phase 7 refinements: baseline, benchmark, API, hybrid staff routing, /start, locking."""

import json
import threading
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from rakt import llm, store
from rakt.agent import live, loop
from rakt.baseline import policy as today
from rakt.channels import simulated, telegram_bot as bot
from rakt.llm import reading_from
from rakt.main import app
from rakt.models import IST, Intent, PledgeStatus, RequestStatus, ReservationStatus
from rakt.sim import benchmark as bench
from rakt.sim import bots

S, R, Q = PledgeStatus, ReservationStatus, RequestStatus
JUDGE, STAFF_A, STAFF_B = "7001", "7002", "7003"


def reset(scenario_id: str):
    loop.reset_scenario(scenario_id)
    (rid,) = store.state.main.requests
    return store.state, rid


def run_all(state):
    while state.clock.step(loop.on_timer):
        pass


def run_until(state, condition, limit=3000):
    for _ in range(limit):
        if condition() or state.clock.step(loop.on_timer) is None:
            return
    raise AssertionError("condition never met")


@pytest.fixture
def api():
    with TestClient(app) as client:
        yield client


@pytest.fixture
def delivered(monkeypatch):
    """Telegram delivers every message; returns the (chat id, text) list sent."""
    sent = []
    monkeypatch.setattr(bot, "send", lambda chat_id, text, buttons, on_fail: sent.append((chat_id, text)) or True)
    return sent


# --- 7.1 today's workflow ---

def test_s1_and_s2_today_lane_say_fulfilled_with_the_true_shortfall():
    for scenario, ready, units in (("s1_surgery_tonight", 1, 2), ("s2_dengue_sdp", 0, 1)):
        state, rid = reset(scenario)
        run = state.baselines[rid]
        request = state.main.requests[rid]
        assert run.state.status == "SAYS_FULFILLED", scenario
        assert (run.units_ready, request.units) == (ready, units), scenario
        view = today.view_at(run, request.deadline_at, units, request.deadline_at)
        assert view["truth_at_deadline"] == {"units_ready": ready, "units": units}
        assert view["status"] == "SAYS_FULFILLED"


def test_today_lane_view_follows_the_clock():
    state, rid = reset("s2_dengue_sdp")
    run, request = state.baselines[rid], state.main.requests[rid]
    start = today.view_at(run, request.created_at, 1, request.deadline_at)
    assert start["status"] == "SEARCHING" and start["truth_at_deadline"] is None and start["donors_messaged"] == 0
    assert start["timeline"] == ["22:40 Listing shows 1 at Centre A: blood found"]


def test_policies_do_not_contaminate_each_other():
    state, rid = reset("s2_dengue_sdp")
    before = json.dumps(today.view_at(state.baselines[rid], state.main.requests[rid].deadline_at, 1,
                                      state.main.requests[rid].deadline_at))
    run_all(state)
    after = json.dumps(today.view_at(state.baselines[rid], state.main.requests[rid].deadline_at, 1,
                                     state.main.requests[rid].deadline_at))
    assert before == after  # rakttrace's run changed nothing in the today lane
    assert state.lanes["today"].pledges == {} and state.lanes["today"].reservations == {}
    assert state.main.requests[rid].status == Q.FULFILLED


def test_both_policies_read_the_same_latent_tuple(monkeypatch):
    read = {"today": {}, "rakttrace": {}}
    real_baseline, real_bots = loop.baseline_latent, bots.latent_for

    def spy_baseline(request_id, donor_id, order):
        latent = real_baseline(request_id, donor_id, order)
        read["today"][donor_id] = latent
        return latent

    def spy_bots(pledge_id):
        latent = real_bots(pledge_id)
        read["rakttrace"][store.state.main.pledges[pledge_id].donor_id] = latent
        return latent

    monkeypatch.setattr(loop, "baseline_latent", spy_baseline)
    monkeypatch.setattr(bots, "latent_for", spy_bots)
    world = bench.generate_world(2026, bench.REFERENCE_DAY)
    shared = 0
    for case in bench.make_cases(2026, 30, sorted(world.hospitals)):
        read["today"].clear(), read["rakttrace"].clear()
        bench.run_case(world, 2026, case)
        draws = store.state.draws[case.key].donors
        for donor_id in set(read["today"]) & set(read["rakttrace"]):
            assert read["today"][donor_id] == read["rakttrace"][donor_id] == draws[donor_id]
            shared += 1
    assert shared > 0


# --- 7.2 benchmark ---

def test_same_seed_same_results():
    first, second = bench.benchmark(12, 77, "rules"), bench.benchmark(12, 77, "rules")
    first.pop("runtime_s"), second.pop("runtime_s")
    assert first == second
    other = bench.benchmark(12, 78, "rules")
    other.pop("runtime_s")
    assert other != first


def test_rakttrace_never_says_done_when_it_isnt():
    result = bench.benchmark(40, 2026, "rules")
    assert result["rakttrace"]["false_done_pct"] == 0.0
    for product in ("PRBC", "SDP"):
        assert result["by_product"][product]["rakttrace"]["false_done_pct"] == 0.0


def test_paired_ci_and_results_file(tmp_path, monkeypatch):
    monkeypatch.setattr(bench, "BENCH_DIR", tmp_path)
    monkeypatch.setattr("sys.argv", ["benchmark", "--n", "10", "--seed", "5", "--reader", "rules"])
    bench.main()
    saved = json.loads((tmp_path / "results_nominal_5.json").read_text(encoding="utf-8"))
    for diff in ("on_time_diff", "donors_diff"):
        ci = saved["ci"]["today"][diff]
        assert ci["lo"] <= ci["mean"] <= ci["hi"] and isinstance(ci["excludes_zero"], bool)
    assert set(saved) >= {"n", "by_product", "today", "rakttrace", "ci", "runtime_s", "note"}
    assert "not real-world evidence" in saved["note"]


def test_paired_ci_formula():
    ci = bench.paired_ci([1, 0, 1, 1, 0, 1, 0, 1])
    assert ci["mean"] == 0.625 and round(ci["hi"] - ci["mean"], 4) == round(1.96 * 0.5175 / 8 ** 0.5, 4)
    assert bench.paired_ci([0.0, 0.0])["excludes_zero"] is False


def test_committed_artifact_is_the_official_run():
    saved = json.loads(bench.results_path(2026).read_text(encoding="utf-8"))
    assert (saved["n"], saved["seed"], saved["regime"]) == (500, 2026, "nominal")
    assert saved["rakttrace"]["false_done_pct"] == 0.0


# --- 7.3 / 7.4 API ---

VIEW_KEYS = {"id", "status", "group", "product", "units", "hospital", "collection_centre", "created_at",
             "deadline_at", "now", "p", "p_firm", "target", "units_ladder", "stock", "donors", "counts",
             "escalation", "flags"}


def test_reference_endpoints(api):
    assert set(api.get("/api/health").json()) == {"ok", "now", "llm", "telegram"}
    assert set(api.get("/api/hospitals").json()[0]) == {"id", "name", "area"}
    centre = api.get("/api/centres").json()[0]
    assert set(centre) == {"id", "name", "area", "apheresis", "stock"}
    assert set(centre["stock"][0]) == {"product", "group", "listed_units", "listed_age_min"}


def test_request_endpoints(api):
    summary = api.get("/api/requests").json()[0]
    assert set(summary) == {"id", "group", "product", "units", "status", "p", "deadline_at", "hospital_name",
                            "escalation_level"}
    rid = summary["id"]
    view = api.get(f"/api/requests/{rid}").json()
    assert set(view) == VIEW_KEYS
    assert set(view["units_ladder"]) == {"found", "said_yes", "ready_in_time", "collected_or_reserved", "confirmed"}
    assert set(view["counts"]) == {"messaged", "yes", "no", "silent", "active", "standby"}
    assert set(view["flags"]) == {"donors_can_help", "waiting_for_stock"} and view["flags"]["waiting_for_stock"]
    assert set(view["stock"][0]) == {"reservation_id", "centre", "units_asked", "units_reserved", "status",
                                     "listed_age_min", "p"}
    base = api.get(f"/api/requests/{rid}/baseline").json()
    assert set(base) == {"request_id", "status", "said_fulfilled_at", "donors_messaged", "found_units", "timeline",
                         "truth_at_deadline"} and base["truth_at_deadline"] is None
    decision = api.get(f"/api/requests/{rid}/decisions").json()[0]
    assert set(decision) == {"id", "request_id", "at", "trigger", "p_before", "p_after", "status", "actions", "summary"}
    api.post("/api/demo/advance", json={"minutes": 30})
    donor = api.get(f"/api/requests/{rid}").json()["donors"][0]
    assert {"pledge_id", "name", "group", "km", "status", "p", "booking_code", "ready_at", "why", "reply_text",
            "read_by"} <= set(donor)
    assert api.get("/api/requests/RT-0000").status_code == 404


def test_parse_create_merge_and_cancel(api):
    llm.set_enabled(False)
    parsed = api.post("/api/requests/parse", json={"text": "B+ 2 units blood at Lakeview within 20 hours"}).json()
    assert parsed["read_by"] == "rules" and parsed["draft"]["group"] == "B_POS" and parsed["missing"] == []
    body = {k: parsed["draft"][k] for k in ("group", "product", "units", "hospital_id", "deadline_at")}
    created = api.post("/api/requests", json={**body, "family": "sim"}).json()
    assert set(created) == VIEW_KEYS
    assert api.post("/api/requests", json=body).json() == {"merged_into": created["id"]}
    cancelled = api.post(f"/api/requests/{created['id']}/cancel").json()
    assert cancelled["status"] == "CANCELLED"
    assert api.post(f"/api/requests/{created['id']}/cancel").status_code == 409


def test_create_rejects_bad_input(api):
    good = {"group": "O_POS", "product": "PRBC", "units": 1, "hospital_id": "h_lake",
            "deadline_at": "2026-10-25T20:00:00+05:30"}
    assert api.post("/api/requests", json={**good, "hospital_id": "h_nowhere"}).status_code == 422
    assert api.post("/api/requests", json={**good, "deadline_at": "2026-10-24T10:00:00+05:30"}).status_code == 422
    assert api.post("/api/requests", json={**good, "group": "Z_POS"}).status_code == 422
    assert api.post("/api/requests", json={**good, "units": 0}).status_code == 422
    assert api.post("/api/requests/parse", json={"text": ""}).status_code == 422


def test_api_created_request_gets_its_own_reproducible_outcomes(api):
    body = {"group": "B_POS", "product": "PRBC", "units": 1, "hospital_id": "h_lake",
            "deadline_at": "2026-10-25T21:00:00+05:30"}
    first = api.post("/api/requests", json=body).json()["id"]
    draws_1 = store.state.draws[first]
    timers = {t.kind for t in store.state.clock.pending() if t.request_id == first}
    assert {"halftime", "deadline"} <= timers and first in store.state.baselines
    api.post("/api/demo/reset", json={"scenario": "s2_dengue_sdp"})
    second = api.post("/api/requests", json=body).json()["id"]
    assert second == first and store.state.draws[second] == draws_1  # same world, same request → same outcomes
    scenario_id = store.state.scenario_request_id
    assert store.state.draws[second].donors != store.state.draws[scenario_id].donors


def test_sim_phone_endpoints(api):
    phones = api.get("/api/sim/phones").json()
    assert set(phones[0]) == {"id", "name", "role", "unread", "last_at"}
    phone = next(p for p in phones if p["id"] == "c_a")
    assert phone["role"] == "staff" and phone["unread"] == 1
    messages = api.get("/api/sim/phones/c_a/messages").json()
    assert messages[0]["kind"] == "staff_hold" and messages[0]["buttons"]
    assert next(p for p in api.get("/api/sim/phones").json() if p["id"] == "c_a")["unread"] == 0
    tap = api.post("/api/sim/reply", json={"phone_id": "c_a", "button_id": messages[0]["buttons"][2]["id"]})
    assert tap.json() == {"ok": True}
    assert store.state.main.reservations["res_1"].status == R.NONE  # Centre A tapped None from the dashboard
    assert api.post("/api/sim/reply", json={"phone_id": "c_a"}).status_code == 422
    assert api.post("/api/sim/reply", json={"phone_id": "nobody", "text": "hi"}).status_code == 404
    assert api.get("/api/sim/phones/nobody/messages").status_code == 404


def test_sim_reply_text_moves_the_request(api):
    llm.set_enabled(False)
    api.post("/api/demo/advance", json={"minutes": 16})  # Centre A says None at 22:55; the first wave goes out
    donor = next(p for p in store.state.main.pledges.values() if p.status == S.INVITED)
    for timer in store.state.clock.pending():
        if timer.kind == "sim_inbound" and timer.payload.get("sender_id") == donor.donor_id:
            store.state.clock.cancel(timer)
    assert api.post("/api/sim/reply", json={"phone_id": donor.donor_id, "text": "haan abhi aa sakta hoon"}).json()["ok"]
    assert donor.status in (S.ACTIVE, S.STANDBY, S.RELEASED)


def test_demo_controls(api):
    assert {"id", "title"} == set(api.get("/api/demo/scenarios").json()[0])
    reset_ = api.post("/api/demo/reset", json={"scenario": "s1_surgery_tonight"}).json()
    assert reset_["now"] == "2026-10-24T18:00:00+05:30" and reset_["request_id"] == store.state.scenario_request_id
    assert api.post("/api/demo/reset", json={"scenario": "s9"}).status_code == 404
    assert api.get("/api/demo/clock").json() == {"now": "2026-10-24T18:00:00+05:30", "auto": False}
    step = api.post("/api/demo/step").json()
    assert step["event"]["kind"] == "sim_inbound" and step["now"] == "2026-10-24T18:08:00+05:30"
    assert api.post("/api/demo/advance", json={"minutes": 10}).json()["now"] == "2026-10-24T18:18:00+05:30"
    assert api.post("/api/demo/advance", json={"minutes": 0}).status_code == 422
    assert api.post("/api/demo/auto", json={"on": True}).json() == {"auto": True}
    assert api.post("/api/demo/auto", json={"on": False}).json() == {"auto": False}


def test_llm_and_benchmark_endpoints(api):
    assert set(api.get("/api/llm").json()) == {"enabled", "chain"}
    assert api.post("/api/llm", json={"enabled": False}).json()["enabled"] is False
    assert api.post("/api/benchmark", json={"n": 4, "policies": ["broadcast"]}).status_code == 422
    assert api.post("/api/benchmark", json={"n": 4, "regime": "stress"}).status_code == 422
    cached = api.get("/api/benchmark/cached").json()
    assert {"n", "by_product", "today", "rakttrace", "ci"} <= set(cached)
    assert api.get("/api/benchmark/cached", params={"seed": 9999}).status_code == 404


def test_benchmark_endpoint_runs_out_of_process(api, tmp_path):
    result = api.post("/api/benchmark", json={"n": 4, "seed": 11, "reader": "rules"}).json()
    assert result["n"] == 4 and {"today", "rakttrace", "ci", "by_product"} <= set(result)
    assert store.state.scenario_request_id in store.state.main.requests  # the live demo state wasn't touched
    bench.results_path(11).unlink(missing_ok=True)


def test_reset_rebuilds_without_stale_timers_and_keeps_live_identities(api):
    bot.on_callback(JUDGE, "Judge", "O:JOIN")
    api.post("/api/demo/advance", json={"minutes": 30})
    donor_id = live.registry.identities[JUDGE].donor_id
    old_requests = set(store.state.main.requests)
    api.post("/api/demo/reset", json={"scenario": "s2_dengue_sdp"})
    state = store.state
    assert live.registry.identities[JUDGE].donor_id == donor_id
    assert state.main.donors[donor_id].invites == [] and state.main.pledges == {}
    assert all(t.request_id in state.main.requests for t in state.clock.pending())
    assert set(state.main.requests) == old_requests  # the same scenario request id, a fresh run


# --- Hybrid staff routing ---

def test_centre_a_linked_gets_its_cards_on_telegram_and_b_stays_simulated(delivered):
    reset("s1_surgery_tonight")  # asks B and A at t = 0, before anyone links
    bot.on_start(STAFF_A, "Judge A", "staff_c_a", private=True)
    state = store.state
    a = next(r for r in state.main.reservations.values() if r.centre_id == "c_a")
    assert any(chat == STAFF_A for chat, _ in delivered)  # A's open card was handed to the linked staff
    assert not any(t.payload.get("sender_id") == "c_a" for t in state.clock.pending() if t.kind == "sim_inbound")
    assert any(t.payload.get("sender_id") == "c_b" for t in state.clock.pending() if t.kind == "sim_inbound")
    bot.on_callback(STAFF_A, "Judge A", f"R:{a.id}:N1")  # the real staff answers
    assert a.status == R.RESERVED and state.main.decisions[-1].trigger.endswith("(via Telegram)")


def test_centre_b_linked_routes_new_cards_to_telegram(delivered):
    reset("s1_surgery_tonight")
    bot.on_start(STAFF_B, "Judge B", "staff_c_b", private=True)
    delivered.clear()
    state, rid = reset("s1_surgery_tonight")  # a new run: the link is re-applied and new cards go to Telegram
    assert any(chat == STAFF_B and "RaktTrace" in text for chat, text in delivered)
    assert not any(t.payload.get("sender_id") == "c_b" for t in state.clock.pending() if t.kind == "sim_inbound")


def test_staff_reset_hands_open_cards_back_to_the_simulated_staff(delivered):
    reset("s1_surgery_tonight")
    bot.on_start(STAFF_A, "Judge A", "staff_c_a", private=True)
    text, _ = bot.on_reset(STAFF_A)
    assert "no longer linked as Centre A staff" in text
    state = store.state
    assert any(t.payload.get("sender_id") == "c_a" for t in state.clock.pending() if t.kind == "sim_inbound")
    run_until(state, lambda: state.main.requests[state.scenario_request_id].status == Q.SECURED)


def test_failed_telegram_send_is_taken_over_by_the_simulated_staff_once():
    reset("s1_surgery_tonight")
    bot.on_start(STAFF_A, "Judge A", "staff_c_a", private=True)  # the bot is off in tests: every send fails
    state = store.state
    a = next(r for r in state.main.reservations.values() if r.centre_id == "c_a")
    run_until(state, lambda: a.status != R.PENDING)
    assert a.status == R.RESERVED  # answered by the simulated staff from the sim phone
    assert any(m.channel == "sim" and m.kind == "staff_hold" for m in simulated.inbox(STAFF_A))
    before = (a.status, a.units_reserved, len(state.main.decisions))
    bot.on_callback(STAFF_A, "Judge A", f"R:{a.id}:ALL")  # a late real tap on the same card
    assert (a.status, a.units_reserved, len(state.main.decisions)) == before  # nothing processed twice
    run_all(state)
    assert state.main.requests[state.scenario_request_id].status == Q.FULFILLED


def test_staff_cannot_silently_switch_centres():
    reset("s1_surgery_tonight")
    bot.on_start(STAFF_A, "Judge A", "staff_c_a", private=True)
    text, _ = bot.on_start(STAFF_A, "Judge A", "staff_c_b", private=True)
    assert "Send /reset to release it first" in text
    assert store.state.main.centres["c_b"].contact.channel == "sim"
    assert bot.on_start(STAFF_A, "Judge A", "staff_c_a", private=True)[0].startswith("You're already linked")


def test_donor_reset_does_not_touch_staff_and_staff_reset_does_not_touch_donors():
    reset("s2_dengue_sdp")
    bot.on_start(STAFF_B, "Judge B", "staff_c_b", private=True)
    bot.on_callback(JUDGE, "Judge", "O:JOIN")
    bot.on_reset(JUDGE)
    assert store.state.main.centres["c_b"].contact.chat_id == STAFF_B
    bot.on_callback(JUDGE, "Judge", "O:JOIN")
    bot.on_reset(STAFF_B)
    assert live.registry.identities[JUDGE].role == "donor"


# --- /start ---

def test_start_confirms_roles_and_respects_stop():
    reset("s2_dengue_sdp")
    bot.on_start(STAFF_B, "Judge B", "staff_c_b", private=True)
    assert bot.on_start(STAFF_B, "Judge B", "", private=True) == ("You're linked as Centre B staff. Send /reset "
                                                                   "to release this centre.", [])
    bot.on_callback(JUDGE, "Judge", "O:JOIN")
    bot.on_stop(JUDGE)
    text, buttons = bot.on_start(JUDGE, "Judge", "", private=True)
    assert "opted out" in text and buttons == []
    assert live.registry.identities[JUDGE].opted_out  # /start alone never opts back in
    count = len(live.registry.identities)
    for _ in range(3):
        bot.on_start(JUDGE, "Judge", "", private=True)
    assert len(live.registry.identities) == count


# --- Arrival feasibility and reading ---

def test_a_yes_that_cannot_make_the_deadline_is_not_supply():
    state, rid = reset("s2_dengue_sdp")
    run_until(state, lambda: bool(state.main.pledges))
    for timer in state.clock.pending():
        if timer.kind == "sim_inbound":
            state.clock.cancel(timer)
    request = state.main.requests[rid]
    request.deadline_at = state.clock.now + timedelta(hours=3)  # platelets now can't be tested in time
    pledge = next(iter(state.main.pledges.values()))
    loop.handle_inbound(bots_inbound(pledge.donor_id, f"P:{pledge.id}:YES"))
    assert pledge.status == S.TOO_LATE and request.status == Q.OPEN


def bots_inbound(sender, button):
    from rakt.models import Channel, Inbound
    return Inbound(channel=Channel.SIM, sender_id=sender, button_id=button, at=store.state.clock.now)


def test_llm_time_within_an_hour_means_now():
    now = datetime(2026, 10, 24, 22, 40, tzinfo=IST)
    soon = reading_from({"intent": "YES", "available_from": "2026-10-24T23:00:00+05:30", "confidence": 0.9}, now)
    later = reading_from({"intent": "YES", "available_from": "2026-10-25T11:55:00+05:30", "confidence": 0.9}, now)
    assert soon.intent == Intent.YES and soon.available_from is None
    assert later.available_from.isoformat() == "2026-10-25T11:55:00+05:30"


def test_cards_from_an_earlier_run_are_stale():
    bot._cards.add(("1", 10))
    assert bot.is_current_card("1", 10)
    reset("s1_surgery_tonight")  # a demo reset starts a new run
    assert not bot.is_current_card("1", 10) and not bot.is_current_card("1", None)


# --- Locking ---

def test_api_and_telegram_mutations_under_one_lock(api):
    llm.set_enabled(False)
    bot.on_callback(JUDGE, "Judge", "O:JOIN")
    errors = []

    def clock_driver():
        try:
            for _ in range(40):
                api.post("/api/demo/step")
        except Exception as error:  # noqa: BLE001
            errors.append(error)

    def telegram_side():
        try:
            for _ in range(40):
                with store.lock:
                    bot.on_text(JUDGE, "haan abhi aa sakta hoon")
                    bot.on_start(JUDGE, "Judge", "", private=True)
        except Exception as error:  # noqa: BLE001
            errors.append(error)

    threads = [threading.Thread(target=clock_driver), threading.Thread(target=telegram_side)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    with store.lock:
        s = store.state.main
        for request in s.requests.values():  # one pledge per donor per request, whatever the interleaving
            donors = [p.donor_id for p in s.pledges.values() if p.request_id == request.id]
            assert len(donors) == len(set(donors))
        request_id = store.state.scenario_request_id
    view = api.get(f"/api/requests/{request_id}").json()  # never call the API while holding the lock
    assert set(view) == VIEW_KEYS
