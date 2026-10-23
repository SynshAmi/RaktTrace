import random
from datetime import timedelta

import pytest

from rakt import config, store
from rakt.agent import loop, planner, ranking
from rakt.agent.planner import choose_k, p_curve, size_wave
from rakt.agent.probability import estimate, mixture_p
from rakt.channels import simulated
from rakt.models import BloodGroup, Channel, Inbound, PledgeStatus, RequestStatus
from rakt.sim.scenarios import load_scenario

S = PledgeStatus


def start(scenario_id: str, **request_changes):
    store.set_state(load_scenario(scenario_id))
    state = store.state
    (rid,) = state.main.requests
    for key, value in request_changes.items():
        setattr(state.main.requests[rid], key, value)
    loop.start(rid)
    return state, rid


def run_until(state, condition, limit=500):
    for _ in range(limit):
        if condition() or state.clock.step(loop.on_timer) is None:
            return
    raise AssertionError("condition never met")


def run_all(state):
    while state.clock.step(loop.on_timer):
        pass


def pledges(state, rid):
    return [p for p in state.main.pledges.values() if p.request_id == rid]


def first_wave_sent(state, rid):
    return lambda: bool(pledges(state, rid))


def tap(state, sender, button):
    loop.handle_inbound(Inbound(channel=Channel.SIM, sender_id=sender, button_id=button, at=state.clock.now))


def say(state, sender, text):
    loop.handle_inbound(Inbound(channel=Channel.SIM, sender_id=sender, text=text, at=state.clock.now))


def s2_after_first_wave():
    """S2 with the bots' replies cleared, so a test can drive donors by hand."""
    state, rid = start("s2_dengue_sdp")
    run_until(state, first_wave_sent(state, rid))
    for timer in state.clock.pending():
        if timer.kind == "sim_inbound":
            state.clock.cancel(timer)
    state.sim_latent.clear()  # sim donors and staff stay quiet; the test taps for them
    return state, rid


# --- Wave sizing (AGENT §5 Step 3) ---

@pytest.mark.parametrize("curve, tau, target, expected", [
    ([0, .40, .65, .80, .88, .91, .93], 0.015, 0.9, (5, True)),  # J: 1, .615, .38, .245, .18, .165 → 5
    ([0, .40, .65, .80, .88, .91, .93], 0.05, 0.9, (4, True)),  # J: 1, .65, .45, .35, .32, .34 → 4
    ([0, .40, .65, .80, .88, .91, .93], 0.30, 0.9, (1, True)),  # J: 1, .9, .95, 1.1, … → 1
    ([0, .20, .35, .45, .91], 0.30, 0.9, (0, True)),  # J: 1, 1.1, 1.25, 1.45, 1.29 → 0
    ([0, 0.5, 0.75], 0.25, 0.75, (1, True)),  # J: 1, .75, .75 → tie → the smaller k
    ([0, .30, .50, .62, .70], 0.015, 0.9, (4, False)),  # 90% unreachable → K
    ([0.95, 0.97], 0.015, 0.9, (0, True)),  # already there → invite no one
    ([0.2], 0.015, 0.9, (0, False)),  # no candidates
])
def test_argmin_matches_hand_computed_table(curve, tau, target, expected):
    assert choose_k(curve, tau, target) == expected


def test_argmin_on_the_s2_shaped_mixture_curve():
    # 30 fresh SDP invites with go window < 12 h: base = 0.70 × 0.90 × 0.75. Hand-computed: P first reaches
    # 90% at k = 23, and the marginal gain drops below τ = 0.015 after the 17th donor.
    base = 0.70 * 0.90 * 0.75
    curve = [mixture_p([], [(base, 0.0)] * k, config.LATENT_PRIOR, 1) for k in range(31)]
    assert curve[10] == pytest.approx(0.686, abs=0.001)
    assert next(k for k, p in enumerate(curve) if p >= 0.9) == 23
    assert choose_k(curve) == (17, True)


def test_higher_tau_never_increases_k_star():
    rng = random.Random(7)
    for _ in range(300):
        steps = sorted(rng.random() for _ in range(rng.randint(1, 25)))
        curve = [0.0] + [rng.uniform(0.3, 1.0) * s for s in steps]
        curve = [max(curve[: i + 1]) for i in range(len(curve))]  # P(k) never falls as k grows
        target = rng.choice([0.5, 0.8, 0.9])
        ks = [choose_k(curve, tau, target)[0] for tau in (0.0, 0.005, 0.015, 0.03, 0.1, 0.5)]
        assert ks == sorted(ks, reverse=True)


def test_unreachable_target_invites_k_capped_per_wave():
    curve = [0.01 * k for k in range(26)]  # K = 25, never reaches 90%
    send, k_star, reachable = size_wave(curve)
    assert (k_star, reachable) == (25, False)
    assert send == config.WAVE_CAP


# --- S2 ---

def test_s2_zero_invites_at_t0_while_waiting_for_stock():
    state, rid = start("s2_dengue_sdp")
    assert pledges(state, rid) == []
    assert planner.plan(state.main, rid, state.clock.now).waiting_for_stock


def test_s2_first_wave_is_min_k_star_wave_cap_from_the_planner():
    state, rid = start("s2_dengue_sdp")
    (answer,) = [t for t in state.clock.pending() if t.kind == "sim_inbound"]  # Centre A's "None"
    # what the planner will see when A's answer arrives, computed on a copy, independently of the wave it sends
    s = state.main.copy()
    s.reservations["res_1"].status = "NONE"
    request, now = s.requests[rid], answer.at
    centre = planner.donor_centre(s, request)
    ranked = ranking.candidates(s, request, centre, now)[: config.REQUEST_DONOR_CAP]
    assert len(ranked) >= 12
    curve = p_curve(s, request, now, [], [c.base for c in ranked], estimate(s, request, now).posterior)
    k_star, _ = choose_k(curve)
    run_until(state, first_wave_sent(state, rid))
    wave = pledges(state, rid)
    assert len(wave) == min(k_star, config.WAVE_CAP) == 10
    assert [p.donor_id for p in wave] == [c.donor_id for c in ranked[:10]]
    decision = state.main.decisions[-1]
    assert decision.summary.startswith("Invited 10 donors (P 0% → ") and decision.p_after > 0


def test_s2_end_to_end():
    state, rid = start("s2_dengue_sdp")
    s = state.main
    request = s.requests[rid]

    run_until(state, lambda: request.status == RequestStatus.COVERED)
    replied = sorted((p for p in pledges(state, rid) if p.replied_at), key=lambda p: p.replied_at)
    # the active donor lives ~2 km away, so in the sim they have already arrived by the third yes
    assert [p.status for p in replied] == [S.ARRIVED, S.STANDBY, S.STANDBY]
    assert estimate(s, request, state.clock.now).p_firm >= config.TARGET_P

    run_until(state, lambda: any(p.status == S.TOO_LATE for p in pledges(state, rid)))
    too_late = next(p for p in pledges(state, rid) if p.status == S.TOO_LATE)
    assert too_late.reply_text == "kal 11:55 ke baad free hoon"
    assert too_late.available_from.isoformat() == "2026-10-25T11:55:00+05:30"

    run_until(state, lambda: any(p.status == S.DEFERRED for p in pledges(state, rid)))
    assert request.status == RequestStatus.OPEN  # COVERED → OPEN on deferral
    assert len(s.promotions) == 1
    promoted = s.pledges[next(iter(s.promotions))]
    assert promoted.status == S.STANDBY

    run_until(state, lambda: request.status == RequestStatus.SECURED)
    assert promoted.status == S.COLLECTED
    assert promoted.ready_at <= request.deadline_at - timedelta(minutes=config.SAFETY_MARGIN_MIN)
    kinds = [m.kind for m in simulated.inbox(promoted.donor_id) if m.direction == "out"]
    assert kinds == ["donor_invite", "donor_standby", "donor_promote", "donor_go", "donor_thanks_collected"]


def test_s2_bookkeeping_after_the_run():
    state, rid = start("s2_dengue_sdp")
    run_all(state)
    waves = {}
    for p in pledges(state, rid):
        waves.setdefault(p.wave, []).append(p)
    assert all(len(w) <= config.WAVE_CAP for w in waves.values())
    assert len(pledges(state, rid)) <= config.REQUEST_DONOR_CAP
    assert state.main.requests[rid].status == RequestStatus.FULFILLED  # staff confirmed the unit ready


# --- Requests needing more than one unit ---

@pytest.mark.parametrize("units", [2, 3])
def test_multi_unit_requests_invite_donors(units):
    state, rid = start("s2_dengue_sdp", units=units)
    run_until(state, first_wave_sent(state, rid))
    wave = pledges(state, rid)
    assert 0 < len(wave) <= config.WAVE_CAP


# --- Caps and guards ---

def test_request_donor_cap_holds_across_waves(monkeypatch):
    monkeypatch.setattr(config, "REQUEST_DONOR_CAP", 12)
    state, rid = start("s2_dengue_sdp", units=3)
    run_all(state)
    assert len(pledges(state, rid)) <= 12
    assert all(sum(p.wave == w for p in pledges(state, rid)) <= config.WAVE_CAP
               for w in {p.wave for p in pledges(state, rid)})


def test_replan_is_idempotent_and_waits_between_waves():
    state, rid = s2_after_first_wave()
    count = len(state.main.pledges)
    assert planner.plan(state.main, rid, state.clock.now).actions == []
    assert loop.replan(rid, "again").actions == []
    state.clock.now += timedelta(minutes=config.WAVE_INTERVAL_MIN + 1)  # interval passed, nobody answered yet
    assert loop.replan(rid, "again").actions == []
    assert len(state.main.pledges) == count


def test_next_wave_after_interval_and_a_resolved_invite():
    state, rid = s2_after_first_wave()
    first = pledges(state, rid)
    state.clock.now += timedelta(minutes=config.WAVE_INTERVAL_MIN)
    say(state, first[0].donor_id, "nahi bhai busy")
    assert first[0].status == S.DECLINED
    assert max(p.wave for p in pledges(state, rid)) == 2


def test_no_invites_when_donors_cannot_help():
    state, rid = start("s1_surgery_tonight")
    run_all(state)
    assert pledges(state, rid) == []


# --- Ranking filters (AGENT §5.1) ---

def b_pos_prbc_long_deadline():
    store.set_state(load_scenario("s1_surgery_tonight"))
    s, now = store.state.main, store.state.clock.now
    (request,) = s.requests.values()
    request.deadline_at = now + timedelta(hours=20)
    return s, request, now, s.centres["c_b"]


def test_o_neg_donors_hidden_before_l2():
    s, request, now, centre = b_pos_prbc_long_deadline()
    request.radius_km = 40
    groups = {s.donors[c.donor_id].group for c in ranking.candidates(s, request, centre, now)}
    assert BloodGroup.O_NEG not in groups and groups <= {BloodGroup.B_POS, BloodGroup.B_NEG, BloodGroup.O_POS}
    request.escalation_level = 2
    groups = {s.donors[c.donor_id].group for c in ranking.candidates(s, request, centre, now)}
    assert BloodGroup.O_NEG in groups


def test_filters_rest_eligibility_radius_consent():
    s, request, now, centre = b_pos_prbc_long_deadline()
    found = ranking.candidates(s, request, centre, now)
    assert found
    ids = [c.donor_id for c in found]
    rested_out, eligible_out, consent_out = ids[0], ids[1], ids[2]
    s.donors[rested_out].invites = [now - timedelta(hours=10)]
    s.donors[eligible_out].last_whole_blood_at = now - timedelta(days=30)
    s.donors[consent_out].opted_out = True
    month = ids[3]
    s.donors[month].invites = [now - timedelta(days=d) for d in (5, 10, 15, 20)]
    left = {c.donor_id for c in ranking.candidates(s, request, centre, now)}
    assert not left & {rested_out, eligible_out, consent_out, month}
    assert all(c.km <= request.radius_km for c in found)


def test_quiet_hours_only_for_requests_with_more_than_24h_left():
    s, request, now, centre = b_pos_prbc_long_deadline()
    late_night = now.replace(hour=23)
    request.deadline_at = late_night + timedelta(hours=30)
    assert ranking.candidates(s, request, centre, late_night) == []
    request.deadline_at = late_night + timedelta(hours=20)
    assert ranking.candidates(s, request, centre, late_night)


def test_timing_filter_excludes_late_donors():
    s, request, now, centre = b_pos_prbc_long_deadline()
    request.radius_km = 40
    request.deadline_at = now + timedelta(minutes=30 + 6 + 720 + 45 + 60)
    for c in ranking.candidates(s, request, centre, now):
        assert c.timing.on_time and c.timing.go_window_min >= config.MIN_GO_WINDOW_MIN


def test_order_exact_then_demo_then_nearer():
    s, request, now, centre = b_pos_prbc_long_deadline()
    found = ranking.candidates(s, request, centre, now)
    exact = [c for c in found if c.exact]
    other = [c for c in found if not c.exact]
    assert found[: len(exact)] == exact and other
    demo_exact, demo_other = exact[-1].donor_id, other[0].donor_id
    s.donors[demo_exact].telegram_demo = True
    s.donors[demo_other].telegram_demo = True
    order = [c.donor_id for c in ranking.candidates(s, request, centre, now)]
    assert order[0] == demo_exact  # demo ranks 2nd: after exact group, before everything else
    assert order.index(demo_other) == len(exact)  # an inexact demo donor still comes after every exact one
    assert "Telegram" in next(c.why for c in ranking.candidates(s, request, centre, now) if c.donor_id == demo_exact)


def test_why_strings():
    s, request, now, centre = b_pos_prbc_long_deadline()
    c = ranking.candidates(s, request, centre, now)[0]
    assert c.why.startswith("B+ exact · ") and " km" in c.why


def test_donor_active_elsewhere_is_skipped():
    state, rid = s2_after_first_wave()
    p = pledges(state, rid)[0]
    p.status = S.ACTIVE
    other = state.main.requests[rid].model_copy(update={"id": "RT-OTHER"})
    state.main.requests[other.id] = other
    ids = {c.donor_id for c in ranking.candidates(state.main, other, state.main.centres["c_b"], state.clock.now)}
    assert p.donor_id not in ids


# --- Replies ---

def test_yes_roles_and_secured_only_on_collection():
    state, rid = s2_after_first_wave()
    s, request = state.main, state.main.requests[rid]
    a, b, c, d = pledges(state, rid)[:4]
    tap(state, a.donor_id, f"P:{a.id}:YES")
    assert a.status == S.ACTIVE and a.booking_code and request.status == RequestStatus.OPEN
    assert [m.kind for m in simulated.inbox("c_b")][-1] == "staff_incoming"
    tap(state, b.donor_id, f"P:{b.id}:YES")
    tap(state, c.donor_id, f"P:{c.id}:YES")
    assert (b.status, c.status, request.status) == (S.STANDBY, S.STANDBY, RequestStatus.COVERED)
    tap(state, d.donor_id, f"P:{d.id}:YES")
    assert d.status == S.RELEASED  # P_firm ≥ 90%: not needed
    assert simulated.inbox(d.donor_id)[-1].kind == "donor_not_needed"

    tap(state, "c_b", f"V:{a.id}:ARRIVED")
    assert a.status == S.ARRIVED and request.status == RequestStatus.COVERED
    tap(state, "c_b", f"V:{a.id}:COLLECTED")
    assert a.status == S.COLLECTED and request.status == RequestStatus.SECURED
    assert s.donors[a.donor_id].apheresis_dates == [state.clock.now]


def test_collected_too_late_is_not_secured():
    state, rid = s2_after_first_wave()
    request = state.main.requests[rid]
    a = pledges(state, rid)[0]
    tap(state, a.donor_id, f"P:{a.id}:YES")
    tap(state, "c_b", f"V:{a.id}:ARRIVED")
    state.clock.now = request.deadline_at - timedelta(hours=2)  # collected far too late for testing to finish
    tap(state, "c_b", f"V:{a.id}:COLLECTED")
    assert a.status == S.COLLECTED and request.status != RequestStatus.SECURED


def test_duplicate_wrong_sender_and_out_of_order_taps_are_ignored():
    state, rid = s2_after_first_wave()
    a, b = pledges(state, rid)[:2]
    tap(state, b.donor_id, f"P:{a.id}:YES")  # someone else's button
    assert a.status == S.INVITED
    tap(state, a.donor_id, f"P:{a.id}:YES")
    messages = len(simulated.inbox(a.donor_id))
    tap(state, a.donor_id, f"P:{a.id}:YES")  # duplicate
    assert a.status == S.ACTIVE and len(simulated.inbox(a.donor_id)) == messages + 1  # only the inbound tap
    tap(state, "c_b", f"V:{a.id}:COLLECTED")  # can't collect before arrival
    assert a.status == S.ACTIVE
    tap(state, "c_a", f"V:{a.id}:ARRIVED")  # not the collection centre
    assert a.status == S.ACTIVE


def test_no_stop_and_unclear_replies():
    state, rid = s2_after_first_wave()
    s = state.main
    a, b, c = pledges(state, rid)[:3]
    say(state, a.donor_id, "nahi bhai busy")
    say(state, b.donor_id, "STOP")
    say(state, c.donor_id, "Kitna time lagega wahan?")
    assert a.status == S.DECLINED and simulated.inbox(a.donor_id)[-1].kind == "donor_thanks_no"
    assert b.status == S.OPTED_OUT and s.donors[b.donor_id].opted_out
    assert c.status == S.INVITED and simulated.inbox(c.donor_id)[-1].kind == "donor_unclear"


def test_timeout_sets_no_reply_and_a_late_yes_still_counts():
    state, rid = s2_after_first_wave()
    a = pledges(state, rid)[0]
    state.clock.advance(config.DONOR_REPLY_TIMEOUT_MIN, loop.on_timer)
    assert a.status == S.NO_REPLY
    say(state, a.donor_id, "haan abhi aa sakta hoon")
    assert a.status == S.ACTIVE


def test_too_late_yes_is_not_counted():
    state, rid = s2_after_first_wave()
    request = state.main.requests[rid]
    a = pledges(state, rid)[0]
    p_firm = estimate(state.main, request, state.clock.now).p_firm
    say(state, a.donor_id, "kal 11:55 ke baad free hoon")
    assert a.status == S.TOO_LATE and simulated.inbox(a.donor_id)[-1].kind == "donor_too_late"
    assert estimate(state.main, request, state.clock.now).p_firm == p_firm


# --- Promotion (Step 5) ---

def covered_with_one_active_two_standby():
    state, rid = s2_after_first_wave()
    a, b, c = pledges(state, rid)[:3]
    for p in (a, b, c):
        tap(state, p.donor_id, f"P:{p.id}:YES")
    return state, rid, a, b, c


def test_one_active_two_standby_is_covered_at_0_931():
    state, rid, a, b, c = covered_with_one_active_two_standby()
    request = state.main.requests[rid]
    assert (a.status, b.status, c.status) == (S.ACTIVE, S.STANDBY, S.STANDBY)
    assert estimate(state.main, request, state.clock.now).p_firm == pytest.approx(1 - 0.325 * 0.46 ** 2, abs=1e-4)
    assert request.status == RequestStatus.COVERED


def test_deferral_reopens_and_promotes_first_standby():
    state, rid, a, b, c = covered_with_one_active_two_standby()
    request = state.main.requests[rid]
    tap(state, "c_b", f"V:{a.id}:ARRIVED")
    tap(state, "c_b", f"V:{a.id}:DEFERRED")
    assert a.status == S.DEFERRED and request.status == RequestStatus.OPEN
    assert state.main.donors[a.donor_id].deferred_until > state.clock.now
    assert list(state.main.promotions) == [b.id]
    assert simulated.inbox(b.donor_id)[-1].kind == "donor_promote"
    tap(state, b.donor_id, f"P:{b.id}:OMW")
    assert b.status == S.ACTIVE and not state.main.promotions


def test_cant_after_promotion_tries_next_standby():
    state, rid, a, b, c = covered_with_one_active_two_standby()
    tap(state, a.donor_id, f"P:{a.id}:CANT")  # the active donor can't make it
    assert a.status == S.NO_SHOW and list(state.main.promotions) == [b.id]
    tap(state, b.donor_id, f"P:{b.id}:CANT")
    assert b.status == S.RELEASED and list(state.main.promotions) == [c.id]


def test_promotion_times_out_after_15_minutes():
    state, rid, a, b, c = covered_with_one_active_two_standby()
    tap(state, "c_b", f"V:{a.id}:ARRIVED")
    tap(state, "c_b", f"V:{a.id}:NOSHOW")  # Didn't show only applies before arrival
    assert a.status == S.ARRIVED
    tap(state, a.donor_id, f"P:{a.id}:CANT")
    tap(state, "c_b", f"V:{a.id}:DEFERRED")
    assert list(state.main.promotions) == [b.id]
    state.clock.advance(config.PROMOTE_TIMEOUT_MIN, loop.on_timer)
    assert b.status == S.RELEASED and list(state.main.promotions) == [c.id]


def test_standby_ok_changes_nothing_and_not_available_releases():
    state, rid, a, b, c = covered_with_one_active_two_standby()
    tap(state, b.donor_id, f"P:{b.id}:OK")
    assert b.status == S.STANDBY
    tap(state, c.donor_id, f"P:{c.id}:CANT")
    assert c.status == S.RELEASED and not state.main.promotions


def test_omw_without_promotion_is_ignored():
    state, rid, a, b, c = covered_with_one_active_two_standby()
    tap(state, b.donor_id, f"P:{b.id}:OMW")
    assert b.status == S.STANDBY


# --- Decision summaries ---

def test_deferral_summary_follows_action_order_and_says_why():
    state, rid = start("s2_dengue_sdp")
    run_until(state, lambda: any(p.status == S.DEFERRED for p in pledges(state, rid)))
    decision = state.main.decisions[-1]
    assert decision.trigger.endswith("DEFERRED")
    assert decision.actions[0].startswith("promote ") and decision.actions[1].startswith("invite wave 2")
    assert decision.summary.startswith("Asked standby ")
    assert "Invited 5 donors (P 79% → 90%), enough to reach 90%." in decision.summary
    assert decision.summary.endswith("Status COVERED → OPEN.")


def test_invite_sentence_reasons():
    from rakt.agent.planner import Invite, invite_sentence
    capped = Invite(("d",) * 10, ("",) * 10, 1, 18, False)
    assert invite_sentence(capped, 0, 0.69) == ("Invited 10 donors (P 0% → 69%); the cost rule wanted more, capped at 10 "
                                                "per wave; 90% isn't reachable with the donors available.")
    interior = Invite(("d",) * 4, ("",) * 4, 1, 4, True, False, 0.012)
    assert invite_sentence(interior, 0.5, 0.8) == ("Invited 4 donors (P 50% → 80%); one more would add +1.2%, "
                                                   "below the 1.5% bar.")
