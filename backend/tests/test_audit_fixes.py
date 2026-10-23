"""Regression tests for the pre-Phase-6 audit fixes (C1 script scope, C2 stock re-asking, C3 failed units,
C4 secured but never confirmed ready)."""

from datetime import timedelta

from rakt import store
from rakt.agent import loop, planner
from rakt.agent.planner import AskStock
from rakt.agent.probability import estimate
from rakt.channels import simulated
from rakt.models import Channel, Inbound, PledgeStatus, RequestStatus, ReservationStatus
from rakt.sim import bots
from rakt.sim.scenarios import load_scenario

S, R, Q = PledgeStatus, ReservationStatus, RequestStatus


def start(scenario_id: str):
    store.set_state(load_scenario(scenario_id))
    state = store.state
    (rid,) = state.main.requests
    loop.start(rid)
    return state, rid


def tap(state, sender, button):
    loop.handle_inbound(Inbound(channel=Channel.SIM, sender_id=sender, button_id=button, at=state.clock.now))


def run_until(state, condition, limit=2000):
    for _ in range(limit):
        if condition() or state.clock.step(loop.on_timer) is None:
            return
    raise AssertionError("condition never met")


def run_all(state):
    while state.clock.step(loop.on_timer):
        pass


def reservations(state, rid, centre_id):
    return [r for r in state.main.reservations.values() if r.request_id == rid and r.centre_id == centre_id]


def silence_sim_people(state):
    for timer in state.clock.pending():
        if timer.kind == "sim_inbound":
            state.clock.cancel(timer)


# --- C1: the S2 donor script stays with the S2 request ---

def test_second_request_does_not_inherit_the_s2_script():
    state, rid = start("s2_dengue_sdp")
    request = state.main.requests[rid]
    other_id, merged = loop.create_request(request.group, request.product, 1, "h_lake",
                                           state.clock.now + timedelta(hours=20))
    assert not merged
    run_all(state)

    s2 = [p for p in state.main.pledges.values() if p.request_id == rid]
    other = [p for p in state.main.pledges.values() if p.request_id == other_id]
    assert other, "the second request should still invite donors"
    assert all(bots.latent_for(p.id) is None for p in other)  # no script, and no draws of its own yet (Phase 7)
    assert all(p.replied_at is None for p in other)
    assert request.status == Q.FULFILLED  # the S2 story itself is unchanged
    assert any(p.status == S.DEFERRED for p in s2) and any(p.status == S.TOO_LATE for p in s2)


def test_s2_script_still_drives_the_s2_request():
    state, rid = start("s2_dengue_sdp")
    run_until(state, lambda: bool(state.main.pledges))
    first = sorted(state.main.pledges.values(), key=lambda p: p.id)[0]
    scripted = state.scenario.donor_script[0].latent()
    assert bots.latent_for(first.id) == scripted


def test_live_linked_donor_never_gets_a_simulated_outcome():
    state, rid = start("s2_dengue_sdp")
    run_until(state, lambda: bool(state.main.pledges))
    pledge = next(iter(state.main.pledges.values()))
    state.main.donors[pledge.donor_id].telegram_demo = True  # the flag decides, not the message's channel
    assert bots.latent_for(pledge.id) is None


# --- C2 + C3: a reserved unit that fails testing, and re-asking centres ---

def s1_secured():
    state, rid = start("s1_surgery_tonight")
    run_until(state, lambda: state.main.requests[rid].status == Q.SECURED)
    silence_sim_people(state)  # the test answers for the centres from here on
    return state, rid


def fail_a(state, rid):
    a = next(r for r in reservations(state, rid, "c_a") if r.status == R.RESERVED)
    tap(state, "c_a", f"D:R:{a.id}:FAILED")
    return a


def test_failed_unit_is_no_longer_usable_supply():
    state, rid = s1_secured()
    request = state.main.requests[rid]
    a = fail_a(state, rid)
    assert a.status == R.NONE and a.id in state.main.failed_reservations
    assert planner.certain_units(state.main, request, state.clock.now) == 1  # only B's unit
    assert planner.ready_units(state.main, request) == 0
    assert estimate(state.main, request, state.clock.now).p_firm < 1
    assert request.status == Q.OPEN


def test_failed_unit_lets_the_planner_ask_d_instead_of_escalating():
    state, rid = s1_secured()
    request = state.main.requests[rid]
    d_before = reservations(state, rid, "c_d")
    assert [r.status for r in d_before] == [R.RELEASED]  # D was asked once and released as not needed
    fail_a(state, rid)

    new_d = [r for r in reservations(state, rid, "c_d") if r.status == R.PENDING]
    assert len(new_d) == 1 and new_d[0].units_asked == 1  # D asked again for the missing unit
    assert request.escalation_level == 0  # no premature escalation while an answer is awaited
    assert not any("widened" in d.summary or "L2" in d.summary for d in state.main.decisions)

    tap(state, "c_d", f"R:{new_d[0].id}:ALL")
    assert request.status == Q.SECURED
    kept = {r.centre_id: r.units_reserved for r in state.main.reservations.values()
            if r.request_id == rid and r.status == R.RESERVED}
    assert kept == {"c_b": 1, "c_d": 1}


def test_failed_centre_may_be_asked_for_another_unit_only_if_its_listing_has_one():
    state, rid = s1_secured()
    fail_a(state, rid)
    again = [r for r in reservations(state, rid, "c_a") if r.status == R.PENDING]
    assert len(again) == 1 and again[0].units_asked == 1  # A lists 3, 1 used: it may still have another


def test_active_reservations_are_not_duplicated():
    state, rid = start("s1_surgery_tonight")
    assert {r.centre_id for r in state.main.reservations.values()} == {"c_a", "c_b"}
    for _ in range(3):
        assert not any(isinstance(a, AskStock) for a in planner.plan(state.main, rid, state.clock.now).actions)
    state.clock.now += timedelta(minutes=5)
    loop.replan(rid, "again")
    assert len(state.main.reservations) == 2


def test_explicit_none_is_not_asked_again():
    state, rid = start("s1_surgery_tonight")
    silence_sim_people(state)
    b = reservations(state, rid, "c_b")[0]
    tap(state, "c_b", f"R:{b.id}:NONE")  # B says none
    a = reservations(state, rid, "c_a")[0]
    tap(state, "c_a", f"R:{a.id}:N1")
    d = next(r for r in reservations(state, rid, "c_d") if r.status == R.PENDING)
    tap(state, "c_d", f"R:{d.id}:ALL")
    assert state.main.requests[rid].status == Q.SECURED
    tap(state, "c_a", f"D:R:{a.id}:FAILED")  # a new need appears
    assert len(reservations(state, rid, "c_b")) == 1  # B is not asked again


def test_no_answer_is_not_asked_again():
    state, rid = start("s1_surgery_tonight")
    silence_sim_people(state)
    state.clock.advance(21, loop.on_timer)  # A and B both time out
    assert all(r.status == R.EXPIRED for r in reservations(state, rid, "c_a") + reservations(state, rid, "c_b"))
    loop.replan(rid, "again")
    assert len(reservations(state, rid, "c_a")) == 1 and len(reservations(state, rid, "c_b")) == 1


def test_escalation_when_no_stock_option_remains():
    state, rid = s1_secured()
    request = state.main.requests[rid]
    fail_a(state, rid)
    for r in [r for r in state.main.reservations.values() if r.status == R.PENDING]:
        tap(state, r.centre_id, f"R:{r.id}:NONE")
    assert request.escalation_level == 2 and request.radius_km == 40
    assert simulated.inbox("coordinator")[-1].kind == "coord_alert"


def test_secured_request_asks_for_no_more_stock():
    state, rid = s1_secured()
    assert not any(isinstance(a, AskStock) for a in planner.plan(state.main, rid, state.clock.now).actions)


# --- C4: secured but never confirmed ready ---

def test_secured_but_never_confirmed_ready_fails_at_the_deadline(monkeypatch):
    state, rid = s1_secured()
    real_react = bots.react
    monkeypatch.setattr(bots, "react", lambda out: None if out.kind == "staff_ready" else real_react(out))
    request = state.main.requests[rid]  # from here nobody taps Ready
    run_all(state)
    assert request.status == Q.FAILED  # never FULFILLED without staff confirmation
    reminders = [m for c in ("c_a", "c_b") for m in simulated.inbox(c) if m.kind == "staff_reminder"]
    assert len(reminders) == 2  # one per unconfirmed unit
    assert any("staff tap is overdue" in d.summary for d in state.main.decisions)
    failed = simulated.inbox("coordinator")[-1]
    assert failed.kind == "coord_failed" and "Ready: 0 of 2" in failed.body
