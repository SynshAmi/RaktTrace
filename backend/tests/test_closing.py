from datetime import timedelta

from rakt import config, store
from rakt.agent import escalation, loop, planner
from rakt.agent.escalation import Alert, Fail, Widen
from rakt.channels import simulated
from rakt.domain.geo import km
from rakt.models import Channel, Inbound, PledgeStatus, RequestStatus, ReservationStatus
from rakt.sim.scenarios import load_scenario

S, R, Q = PledgeStatus, ReservationStatus, RequestStatus


def start(scenario_id: str):
    store.set_state(load_scenario(scenario_id))
    state = store.state
    (rid,) = state.main.requests
    loop.start(rid)
    return state, rid


def run_until(state, condition, limit=2000):
    for _ in range(limit):
        if condition() or state.clock.step(loop.on_timer) is None:
            return
    raise AssertionError("condition never met")


def run_all(state):
    while state.clock.step(loop.on_timer):
        pass


def kinds(phone, direction="out"):
    return [m.kind for m in simulated.inbox(phone) if m.direction == direction]


def tap(state, sender, button):
    loop.handle_inbound(Inbound(channel=Channel.SIM, sender_id=sender, button_id=button, at=state.clock.now))


def decision_with(state, text):
    return next(d for d in state.main.decisions if text in d.summary)


# --- S1–S3 end to end ---

def test_s1_end_to_end():
    state, rid = start("s1_surgery_tonight")
    request = state.main.requests[rid]
    run_until(state, lambda: request.status == Q.SECURED)
    assert request.status == Q.SECURED and state.clock.now - request.created_at < timedelta(minutes=20)
    assert kinds(f"family_{rid}") == ["family_secured"]

    run_all(state)
    assert request.status == Q.FULFILLED
    reserved = {r.centre_id: r for r in state.main.reservations.values()}
    assert (reserved["c_a"].status, reserved["c_a"].units_reserved) == (R.READY, 1)
    assert (reserved["c_b"].status, reserved["c_b"].units_reserved) == (R.READY, 1)
    assert reserved["c_d"].status == R.RELEASED
    assert state.main.pledges == {}  # 0 donors messaged
    assert kinds(f"family_{rid}") == ["family_secured", "family_fulfilled"]
    assert kinds("c_a").count("staff_ready") == 1 and kinds("c_b").count("staff_ready") == 1
    assert request.escalation_level == 0


def test_s2_end_to_end():
    state, rid = start("s2_dengue_sdp")
    request = state.main.requests[rid]
    run_until(state, lambda: any(p.status == S.DEFERRED for p in state.main.pledges.values()))
    assert request.status == Q.OPEN and state.main.promotions
    promoted = state.main.pledges[next(iter(state.main.promotions))]

    run_until(state, lambda: request.status == Q.SECURED)
    assert promoted.status == S.COLLECTED
    leftovers = [p for p in state.main.pledges.values() if p.status in planner.UNCOMMITTED]
    assert leftovers == []  # every unreplied or standby donor stood down
    stood_down = [p for p in state.main.pledges.values() if "donor_stand_down" in kinds(p.donor_id)]
    assert stood_down and all(p.status == S.RELEASED for p in stood_down)
    assert kinds(f"family_{rid}") == ["family_secured"]

    run_all(state)
    assert request.status == Q.FULFILLED and promoted.status == S.READY
    assert kinds(f"family_{rid}") == ["family_secured", "family_fulfilled"]
    assert request.escalation_level == 0 and request.radius_km == config.SEARCH_RADII_KM[0]  # no escalation
    assert all(kinds(p.donor_id).count("donor_stand_down") <= 1 for p in state.main.pledges.values())


def test_s3_end_to_end():
    state, rid = start("s3_no_way_in_time")
    request = state.main.requests[rid]
    alert = decision_with(state, "Alerted the coordinator (L2)")
    assert alert.at - request.created_at <= timedelta(minutes=5)
    assert request.escalation_level == 2 and request.radius_km == 40 and request.brief
    assert kinds("coordinator") == ["coord_alert"]
    body = simulated.inbox("coordinator")[0].body
    assert "Where it stands:" in body and "Next:" in body and "Call list:" in body

    run_all(state)
    assert request.status == Q.FAILED and state.main.pledges == {}  # 0 invites
    assert kinds("coordinator") == ["coord_alert", "coord_failed"]
    failed = decision_with(state, "Deadline passed")
    assert failed.at == request.deadline_at
    assert request.deadline_at - alert.at >= timedelta(hours=5, minutes=55)  # warned ~6 h early


# --- Staff reminders and overdue escalation ---

def s2_with_active_donor():
    """S2 after the first wave, with sim people quiet; one donor made ACTIVE by hand."""
    state, rid = start("s2_dengue_sdp")
    run_until(state, lambda: bool(state.main.pledges))
    for timer in state.clock.pending():
        if timer.kind == "sim_inbound":
            state.clock.cancel(timer)
    state.sim_latent.clear()
    a = next(iter(state.main.pledges.values()))
    tap(state, a.donor_id, f"P:{a.id}:YES")
    return state, rid, a


def test_overdue_staff_tap_reminder_then_l2():
    state, rid, a = s2_with_active_donor()
    request = state.main.requests[rid]
    checks = sorted(t.at for t in state.clock.pending() if t.kind == "staff_check")
    remind_at, overdue_at = checks
    assert overdue_at - remind_at == timedelta(minutes=config.STAFF_GRACE_MIN)

    while "staff_reminder" not in kinds("c_b"):
        assert state.clock.step(loop.on_timer) is not None
    assert state.clock.now == remind_at
    reminder = [m for m in simulated.inbox("c_b") if m.kind == "staff_reminder"][0]
    assert [b.id for b in reminder.buttons] == [f"V:{a.id}:ARRIVED", f"V:{a.id}:NOSHOW"]
    assert request.escalation_level < 2

    while request.escalation_level < 2:
        assert state.clock.step(loop.on_timer) is not None
    assert state.clock.now == overdue_at
    assert "a staff tap is overdue" in state.main.decisions[-1].summary
    assert kinds("coordinator") == ["coord_alert"]


def test_tap_in_time_means_no_reminder():
    state, rid, a = s2_with_active_donor()
    tap(state, "c_b", f"V:{a.id}:ARRIVED")
    state.clock.advance(2 * config.STAFF_GRACE_MIN + 1, loop.on_timer)  # past both checks for the incoming card
    assert "staff_reminder" not in kinds("c_b")
    assert state.main.requests[rid].escalation_level < 2


# --- Ready for the patient ---

def test_secured_is_not_fulfilled_until_staff_tap_ready():
    state, rid, a = s2_with_active_donor()
    request = state.main.requests[rid]
    tap(state, "c_b", f"V:{a.id}:ARRIVED")
    tap(state, "c_b", f"V:{a.id}:COLLECTED")
    assert request.status == Q.SECURED
    tap(state, "c_b", f"D:P:{a.id}:READY")  # too early: no ready card yet, but staff may still confirm
    assert a.status == S.READY and request.status == Q.FULFILLED
    assert kinds(f"family_{rid}") == ["family_secured", "family_fulfilled"]


def test_failed_testing_reopens_without_a_second_family_message():
    state, rid, a = s2_with_active_donor()
    request = state.main.requests[rid]
    tap(state, "c_b", f"V:{a.id}:ARRIVED")
    tap(state, "c_b", f"V:{a.id}:COLLECTED")
    assert request.status == Q.SECURED
    tap(state, "c_b", f"D:P:{a.id}:FAILED")
    assert a.status == S.FAILED_TEST and request.status == Q.OPEN
    assert kinds(f"family_{rid}") == ["family_secured"]


def test_ready_taps_are_safe():
    state, rid, a = s2_with_active_donor()
    request = state.main.requests[rid]
    tap(state, "c_b", f"D:P:{a.id}:READY")  # not collected yet
    assert a.status == S.ACTIVE
    tap(state, "c_b", f"V:{a.id}:ARRIVED")
    tap(state, "c_b", f"V:{a.id}:COLLECTED")
    tap(state, "c_a", f"D:P:{a.id}:READY")  # wrong centre
    assert a.status == S.COLLECTED
    tap(state, "c_b", f"D:P:{a.id}:READY")
    tap(state, "c_b", f"D:P:{a.id}:READY")  # duplicate
    tap(state, "c_b", f"D:P:{a.id}:FAILED")  # out of order after ready
    assert a.status == S.READY and request.status == Q.FULFILLED
    assert kinds(f"family_{rid}") == ["family_secured", "family_fulfilled"]


def test_closing_is_idempotent():
    state, rid = start("s1_surgery_tonight")
    run_all(state)
    decisions, messages = len(state.main.decisions), sum(len(v) for v in state.inbox.values())
    assert loop.replan(rid, "again").actions == []
    assert len(state.main.decisions) == decisions and sum(len(v) for v in state.inbox.values()) == messages


def test_late_yes_after_stand_down_is_ignored():
    state, rid = start("s2_dengue_sdp")
    request = state.main.requests[rid]
    run_until(state, lambda: request.status == Q.SECURED)
    released = next(p for p in state.main.pledges.values() if "donor_stand_down" in kinds(p.donor_id))
    tap(state, released.donor_id, f"P:{released.id}:YES")
    assert released.status == S.RELEASED and kinds(released.donor_id).count("donor_go") == 0


# --- Duplicate merge and cancel ---

def test_duplicate_plea_merges_into_open_request():
    state, rid = start("s2_dengue_sdp")
    request = state.main.requests[rid]
    before = request.model_copy()
    merged_id, merged = loop.create_request(request.group, request.product, 2, request.hospital_id,
                                            request.deadline_at + timedelta(hours=3))
    assert (merged_id, merged) == (rid, True)
    assert state.main.requests[rid] == before and len(state.main.requests) == 1
    assert state.main.decisions[-1].trigger == "duplicate plea"


def test_different_plea_creates_a_new_request():
    state, rid = start("s2_dengue_sdp")
    request = state.main.requests[rid]
    new_id, merged = loop.create_request(request.group, request.product, 1, "h_lake",
                                         state.clock.now + timedelta(hours=20))
    assert not merged and new_id != rid and state.main.requests[new_id].status in (Q.OPEN, Q.COVERED)
    assert any(d.request_id == new_id and d.trigger == "new request" for d in state.main.decisions)


def test_cancel_releases_holds_and_donors():
    state, rid, a = s2_with_active_donor()
    request = state.main.requests[rid]
    others = [p for p in state.main.pledges.values() if p.id != a.id]
    loop.cancel(rid)
    assert request.status == Q.CANCELLED
    assert a.status == S.RELEASED and kinds(a.donor_id)[-1] == "donor_closed"
    assert all(p.status in (S.RELEASED, S.DECLINED, S.TOO_LATE, S.OPTED_OUT) for p in others)
    count = len(state.main.decisions)
    loop.cancel(rid)  # twice is harmless
    assert len(state.main.decisions) == count and loop.replan(rid, "after cancel").actions == []


def test_cancel_releases_stock_holds():
    state, rid = start("s1_surgery_tonight")
    loop.cancel(rid)
    assert all(r.status == R.RELEASED for r in state.main.reservations.values())
    assert kinds("c_b") == ["staff_hold", "staff_release"]
    run_all(state)  # late staff answers change nothing
    assert all(r.status == R.RELEASED for r in state.main.reservations.values())


# --- Escalation rules (AGENT §6) ---

def view(**overrides):
    fields = dict(p=0.5, stock_left=False, stock_at=lambda r: False, centre=None, donors_can_help=True,
                  pool_exhausted=False, ready=0, messaged=10, overdue=False)
    return escalation.View(**{**fields, **overrides})


def s2_request():
    store.set_state(load_scenario("s2_dengue_sdp"))
    s, now = store.state.main, store.state.clock.now
    (request,) = s.requests.values()
    return s, request, now


def test_no_l1_while_donors_are_still_being_worked():
    s, request, now = s2_request()
    assert escalation.plan_escalation(s, request, now, view(centre=s.centres["c_b"])) == []


def test_l1_when_nothing_left_at_this_radius():
    s, request, now = s2_request()
    centre = s.centres["c_b"]
    for d in s.donors.values():  # empty the 5 km pool
        if km(d, centre) <= 5:
            d.opted_out = True
    actions = escalation.plan_escalation(s, request, now, view(centre=centre, pool_exhausted=True))
    assert actions == [Widen(10)]


def test_l1_widens_to_40_when_no_radius_adds_anything():
    s, request, now = s2_request()
    actions = escalation.plan_escalation(s, request, now, view(donors_can_help=False))
    assert actions == [Widen(40)]


def test_l2_triggers():
    s, request, now = s2_request()
    request.radius_km = 40
    (alert,) = escalation.plan_escalation(s, request, now, view(p=0.85, centre=s.centres["c_b"]))
    assert isinstance(alert, Alert) and any("40 km" in r for r in alert.reasons)

    request.radius_km = 5
    half = request.created_at + (request.deadline_at - request.created_at) / 2
    (alert,) = escalation.plan_escalation(s, request, half, view(p=0.6, centre=s.centres["c_b"]))
    assert any("half the time" in r for r in alert.reasons)
    assert escalation.plan_escalation(s, request, half, view(p=0.75, centre=s.centres["c_b"])) == []

    (alert,) = escalation.plan_escalation(s, request, now, view(p=0.95, overdue=True, centre=s.centres["c_b"]))
    assert alert.reasons == ("a staff tap is overdue",)

    request.escalation_level = 2  # levels only go up: no second alert
    assert escalation.plan_escalation(s, request, now, view(p=0.1, overdue=True)) == []


def test_fail_at_deadline_only_when_short():
    s, request, now = s2_request()
    assert escalation.plan_escalation(s, request, request.deadline_at, view(ready=0)) == [Fail(0)]
    assert escalation.plan_escalation(s, request, request.deadline_at, view(p=1.0, ready=1)) == []


def test_call_list_three_nearest_compatible_centres():
    store.set_state(load_scenario("s1_surgery_tonight"))
    s = store.state.main
    (request,) = s.requests.values()
    entries = escalation.call_list(s, request)
    assert [e["centre"] for e in entries] == ["Centre B", "Centre D", "Centre A"]
    assert all(e["phone"].startswith("+91") and e["note"].startswith("lists ") for e in entries)
