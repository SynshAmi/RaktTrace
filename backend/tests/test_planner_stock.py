from datetime import timedelta

import pytest

from rakt import store
from rakt.agent import loop, planner
from rakt.agent.planner import SetStatus
from rakt.channels import simulated
from rakt.models import BloodGroup, Channel, Inbound, PledgeStatus, Pledge, RequestStatus, ReservationStatus, Stock
from rakt.sim.scenarios import load_scenario

R = ReservationStatus


def start(scenario_id: str):
    store.set_state(load_scenario(scenario_id))
    state = store.state
    (request_id,) = state.main.requests
    loop.start(request_id)
    return state, request_id


def run_all(state) -> None:
    while state.clock.step(loop.on_timer):
        pass


def by_centre(state, request_id):
    return {r.centre_id: r for r in state.main.reservations.values() if r.request_id == request_id}


def tap(state, centre_id, button_id):
    loop.handle_inbound(Inbound(channel=Channel.SIM, sender_id=centre_id, button_id=button_id, at=state.clock.now))


# --- S1 ---

def test_s1_first_asks_are_b_and_a_in_parallel():
    state, rid = start("s1_surgery_tonight")
    first = state.main.decisions[0]
    assert first.trigger == "new request"
    assert set(by_centre(state, rid)) == {"c_b", "c_a"}  # D not asked at t = 0
    assert by_centre(state, rid)["c_b"].units_asked == 2 and by_centre(state, rid)["c_a"].units_asked == 2
    assert first.p_before == 0 and first.p_after == pytest.approx(1 - 0.15 * 0.35)
    assert [m.kind for m in simulated.inbox("c_b") if m.direction == "out"] == ["staff_hold"]
    assert simulated.inbox("c_b")[0].body.startswith(f"RaktTrace · {rid}: can you reserve 2 unit(s) of B+ Red cells")


def test_s1_secured_with_a1_b1_and_zero_donors():
    state, rid = start("s1_surgery_tonight")
    run_all(state)
    request = state.main.requests[rid]
    res = by_centre(state, rid)
    assert request.status == RequestStatus.SECURED
    assert (res["c_a"].status, res["c_a"].units_reserved) == (R.RESERVED, 1)
    assert (res["c_b"].status, res["c_b"].units_reserved) == (R.RESERVED, 1)
    assert state.main.pledges == {}  # zero donor invites

    # D was asked only after A's shortfall, and released when B confirmed
    assert res["c_d"].status == R.RELEASED
    assert res["c_d"].asked_at > res["c_a"].asked_at
    sent_to_d = [m.kind for m in simulated.inbox("c_d") if m.direction == "out"]
    assert sent_to_d == ["staff_hold", "staff_release"]

    secured = next(d for d in state.main.decisions if d.status == RequestStatus.SECURED)
    assert secured.at - request.created_at < timedelta(minutes=20)


def test_s1_replan_twice_adds_nothing():
    state, rid = start("s1_surgery_tonight")
    reservations, messages = dict(state.main.reservations), sum(len(v) for v in state.inbox.values())
    assert planner.plan(state.main, rid, state.clock.now).actions == []
    assert loop.replan(rid, "again").actions == []
    assert state.main.reservations == reservations
    assert sum(len(v) for v in state.inbox.values()) == messages

    run_all(state)
    decisions = len(state.main.decisions)
    assert loop.replan(rid, "again").actions == []
    assert loop.replan(rid, "and again").actions == []
    assert len(state.main.decisions) == decisions


def test_decisions_carry_plain_summaries():
    state, rid = start("s1_surgery_tonight")
    run_all(state)
    summaries = [d.summary for d in state.main.decisions]
    assert summaries[0] == "Asked Centre B for 2 and Centre A for 2 (P 0% → 95%)."
    assert any("Status OPEN → SECURED" in s for s in summaries)


# --- Stock replies ---

def test_reservations_kept_in_arrival_order():
    store.set_state(load_scenario("s1_surgery_tonight"))
    state = store.state
    (rid,) = state.main.requests
    state.draws[rid].staff_delay_min["c_b"] = 5  # B answers "Reserve 2" first
    loop.start(rid)
    run_all(state)
    res = by_centre(state, rid)
    assert (res["c_b"].status, res["c_b"].units_reserved) == (R.RESERVED, 2)
    assert res["c_a"].status == R.RELEASED
    assert "c_d" not in res
    assert state.main.requests[rid].status == RequestStatus.SECURED


def test_reserve_more_than_needed_keeps_only_whats_needed():
    state, rid = start("s1_surgery_tonight")
    a, b = by_centre(state, rid)["c_a"], by_centre(state, rid)["c_b"]
    tap(state, "c_a", f"R:{a.id}:N1")
    tap(state, "c_b", f"R:{b.id}:ALL")  # offers 2, only 1 still needed
    assert b.units_reserved == 1 and b.status == R.RESERVED


def test_none_reply_moves_to_next_centre():
    state, rid = start("s1_surgery_tonight")
    b = by_centre(state, rid)["c_b"]
    tap(state, "c_b", f"R:{b.id}:NONE")
    assert b.status == R.NONE
    assert "c_d" in by_centre(state, rid)  # stock alone fell below 90%, so the next centre is asked


def test_some_then_count():
    state, rid = start("s1_surgery_tonight")
    a = by_centre(state, rid)["c_a"]
    tap(state, "c_a", f"R:{a.id}:SOME")
    assert a.status == R.PENDING
    picker = simulated.inbox("c_a")[-1]
    assert picker.kind == "staff_hold_count" and [b.id for b in picker.buttons] == [f"R:{a.id}:N1"]
    tap(state, "c_a", f"R:{a.id}:N1")
    assert (a.status, a.units_reserved) == (R.RESERVED, 1)


def test_stock_timeout_expires_and_replans():
    store.set_state(load_scenario("s1_surgery_tonight"))
    state = store.state
    (rid,) = state.main.requests
    state.draws[rid].staff_delay_min["c_b"] = 45  # B is slower than the 20-min timeout
    loop.start(rid)
    state.clock.advance(21, loop.on_timer)
    res = by_centre(state, rid)
    assert res["c_b"].status == R.EXPIRED
    assert any("didn't answer in time" in d.trigger for d in state.main.decisions)
    run_all(state)  # B's late answer is ignored
    assert res["c_b"].status == R.EXPIRED


def test_late_answer_after_release_is_ignored():
    state, rid = start("s1_surgery_tonight")
    run_all(state)
    d = by_centre(state, rid)["c_d"]
    tap(state, "c_d", f"R:{d.id}:ALL")
    assert d.status == R.RELEASED and d.units_reserved == 0


def test_tap_from_another_centre_is_ignored():
    state, rid = start("s1_surgery_tonight")
    a = by_centre(state, rid)["c_a"]
    tap(state, "c_b", f"R:{a.id}:ALL")
    assert a.status == R.PENDING


# --- Stock step rules ---

def test_o_neg_stock_not_asked_before_l2():
    store.set_state(load_scenario("s1_surgery_tonight"))
    s = store.state.main
    (request,) = s.requests.values()
    listed = store.state.clock.now - timedelta(minutes=30)
    s.stock.append(Stock(centre_id="c_c", product="PRBC", group=BloodGroup.O_NEG, listed_units=4,
                         listed_at=listed, true_units=4))
    assert "c_c" not in {x.centre_id for x in planner.stock_candidates(s, request)}
    request.escalation_level = 2
    assert "c_c" in {x.centre_id for x in planner.stock_candidates(s, request)}


def test_exact_group_first_then_fresher():
    store.set_state(load_scenario("s1_surgery_tonight"))
    s = store.state.main
    (request,) = s.requests.values()
    listed = store.state.clock.now - timedelta(minutes=10)
    s.stock.append(Stock(centre_id="c_c", product="PRBC", group=BloodGroup.O_POS, listed_units=2,
                         listed_at=listed, true_units=2))
    order = [x.centre_id for x in planner.stock_candidates(s, request)]
    assert order == ["c_b", "c_a", "c_d", "c_c"]  # B+ listings (fresh → old) before the fresher O+ one


def test_centres_outside_radius_not_asked():
    store.set_state(load_scenario("s1_surgery_tonight"))
    s = store.state.main
    (request,) = s.requests.values()
    s.stock.append(Stock(centre_id="c_g", product="PRBC", group=BloodGroup.B_POS, listed_units=5,
                         listed_at=store.state.clock.now, true_units=5))  # Whitefield, ~17 km
    assert "c_g" not in {x.centre_id for x in planner.stock_candidates(s, request)}
    request.radius_km = 20
    assert "c_g" in {x.centre_id for x in planner.stock_candidates(s, request)}


def test_covered_when_p_firm_reaches_target():
    store.set_state(load_scenario("s2_dengue_sdp"))
    state = store.state
    s, now = state.main, state.clock.now
    (request,) = s.requests.values()
    request.collection_centre_id = "c_b"
    donors = [d for d in s.donors if d.startswith("d_s2_")][:3]
    for i, (donor_id, status) in enumerate(zip(donors, [PledgeStatus.ACTIVE, PledgeStatus.STANDBY, PledgeStatus.STANDBY])):
        s.pledges[f"pl_{i}"] = Pledge(id=f"pl_{i}", request_id=request.id, donor_id=donor_id, status=status,
                                      wave=1, invited_at=now, replied_at=now)
    result = planner.plan(s, request.id, now)
    assert SetStatus(RequestStatus.COVERED) in result.actions
    assert result.p_firm == pytest.approx(0.931, abs=1e-3)


def test_a_yes_alone_is_never_secured():
    store.set_state(load_scenario("s2_dengue_sdp"))
    s, now = store.state.main, store.state.clock.now
    (request,) = s.requests.values()
    donor_id = next(d for d in s.donors if d.startswith("d_s2_"))
    s.pledges["pl_1"] = Pledge(id="pl_1", request_id=request.id, donor_id=donor_id, status=PledgeStatus.ACTIVE,
                               wave=1, invited_at=now, replied_at=now)
    assert planner.plan(s, request.id, now).status == RequestStatus.OPEN


def test_final_status_plans_nothing():
    state, rid = start("s1_surgery_tonight")
    state.main.requests[rid].status = RequestStatus.CANCELLED
    run_all(state)
    assert state.main.requests[rid].status == RequestStatus.CANCELLED


def test_s2_asks_centre_a_first():
    state, rid = start("s2_dengue_sdp")
    res = by_centre(state, rid)
    assert set(res) == {"c_a"} and res["c_a"].units_asked == 1
    run_all(state)
    assert res["c_a"].status == R.NONE  # A lists 1 but has 0
    assert state.main.requests[rid].status == RequestStatus.OPEN
