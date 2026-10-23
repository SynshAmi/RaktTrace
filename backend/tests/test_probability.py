from datetime import datetime, timedelta

import pytest

from rakt import config
from rakt.agent.probability import (
    estimate, p_at_least, p_best, plugin_p, mixture_p, posterior, stock_p, unreplied_p,
)
from rakt.models import IST, Pledge, PledgeStatus, Reservation, ReservationStatus
from rakt.sim.scenarios import load_scenario

PRIOR = config.LATENT_PRIOR


def mean_rate(post) -> float:
    return sum(r * w for r, w in zip(config.LATENT_RATES, post))


# --- p_at_least ---

def test_p_at_least_sanity_values():
    assert p_at_least([], 0) == 1.0
    assert p_at_least([], 1) == 0.0
    assert p_at_least([(0.5, 1)], 1) == 0.5
    assert p_at_least([(0.5, 1), (0.5, 1)], 1) == pytest.approx(0.75)
    assert p_at_least([(0.5, 1), (0.5, 1)], 2) == pytest.approx(0.25)
    assert p_at_least([(0.85, 2), (0.65, 2)], 2) == pytest.approx(1 - 0.15 * 0.35)


def test_p_at_least_multi_unit_sources_cap_at_need():
    assert p_at_least([(0.9, 3)], 2) == pytest.approx(0.9)
    assert p_at_least([(1.0, 1), (0.85, 2)], 2) == pytest.approx(0.85)
    assert p_at_least([(1.0, 2)], 2) == 1.0
    assert p_at_least([(0.0, 5)], 1) == 0.0


def test_p_at_least_matches_brute_force():
    import itertools
    sources = [(0.3, 1), (0.6, 2), (0.45, 1), (0.8, 1)]
    for need in range(5):
        brute = 0.0
        for hits in itertools.product([0, 1], repeat=len(sources)):
            prob = 1.0
            for hit, (p, _) in zip(hits, sources):
                prob *= p if hit else 1 - p
            if sum(u for hit, (_, u) in zip(hits, sources) if hit) >= need:
                brute += prob
        assert p_at_least(sources, need) == pytest.approx(brute)


def test_stock_p_bands():
    assert stock_p(20) == 0.85 and stock_p(360) == 0.85
    assert stock_p(361) == 0.65 and stock_p(1440) == 0.65
    assert stock_p(1441) == 0.50


# --- posterior ---

def test_posterior_is_prior_at_zero_replies():
    assert posterior([]) == pytest.approx(PRIOR)


def test_silence_at_invite_time_changes_nothing():
    assert posterior([("silent", 0.0)] * 5) == pytest.approx(PRIOR)


def test_posterior_shifts_up_after_yeses():
    one, two = posterior([("yes", 10)]), posterior([("yes", 10), ("yes", 12)])
    assert mean_rate(posterior([])) < mean_rate(one) < mean_rate(two)
    assert two[2] > PRIOR[2] and two[0] < PRIOR[0]


def test_posterior_shifts_down_after_noes_and_stop():
    no, stop = posterior([("no", 10)]), posterior([("stop", 10)])
    assert mean_rate(no) < mean_rate(posterior([]))
    assert stop == pytest.approx(no)  # STOP counts as an explicit no


def test_silence_weaker_than_a_no():
    prior = mean_rate(posterior([]))
    for t in (10, 30, 120):
        silent, no = mean_rate(posterior([("silent", t)])), mean_rate(posterior([("no", t)]))
        assert no < silent < prior
    assert mean_rate(posterior([("silent", 120)])) < mean_rate(posterior([("silent", 10)]))


def test_unreplied_p_decays_with_silence():
    base = 0.5
    assert unreplied_p(0.25, base, 0) == pytest.approx(0.25 * base)
    assert unreplied_p(0.25, base, 60) < unreplied_p(0.25, base, 10) < unreplied_p(0.25, base, 0)


def test_mixture_differs_from_plugin_with_correlated_replies():
    unreplied = [(0.47, 0.0)] * 10
    mix, plug = mixture_p([], unreplied, PRIOR, 1), plugin_p([], unreplied, PRIOR, 1)
    assert mix == pytest.approx(0.686, abs=0.002)  # S2 first wave: 10 fresh invites
    assert mix < plug  # the mixture knows replies fail together on a bad night


# --- P, P_firm, P_best on a real request ---

def s2_with_pledges():
    state = load_scenario("s2_dengue_sdp")
    s = state.main
    (request,) = s.requests.values()
    request.collection_centre_id = "c_b"
    now = state.clock.now
    donors = [d for d in s.donors if d.startswith("d_s2_")]
    statuses = [PledgeStatus.ACTIVE, PledgeStatus.STANDBY, PledgeStatus.STANDBY,
                PledgeStatus.INVITED, PledgeStatus.INVITED, PledgeStatus.DECLINED]
    for i, (donor_id, status) in enumerate(zip(donors, statuses)):
        replied = None if status == PledgeStatus.INVITED else now
        s.pledges[f"pl_{i}"] = Pledge(id=f"pl_{i}", request_id=request.id, donor_id=donor_id, status=status,
                                      wave=1, invited_at=now - timedelta(minutes=20), replied_at=replied)
    return s, request, now


def test_p_firm_s2_one_active_two_standby():
    s, request, now = s2_with_pledges()
    est = estimate(s, request, now)
    assert est.p_firm == pytest.approx(1 - 0.325 * 0.46 ** 2, abs=1e-3)  # ≈ 0.931 → COVERED
    assert est.p > est.p_firm  # unreplied invites add to P, never to P_firm


def test_p_firm_identical_under_all_rates():
    s, request, now = s2_with_pledges()
    base = estimate(s, request, now).p_firm
    for evidence_change in (PledgeStatus.DECLINED, PledgeStatus.OPTED_OUT, PledgeStatus.NO_REPLY):
        s.pledges["pl_3"].status = evidence_change
        assert estimate(s, request, now).p_firm == pytest.approx(base)
    for estimator in ("mixture", "plugin"):
        assert estimate(s, request, now, estimator=estimator).p_firm == pytest.approx(base)


def test_p_firm_ignores_pending_stock_and_unreplied():
    state = load_scenario("s2_dengue_sdp")
    s = state.main
    (request,) = s.requests.values()
    now = state.clock.now
    s.reservations["res_1"] = Reservation(id="res_1", request_id=request.id, centre_id="c_a", group=request.group,
                                          units_asked=1, listed_at=now - timedelta(hours=15), asked_at=now)
    est = estimate(s, request, now)
    assert est.p == pytest.approx(0.65) and est.p_firm == 0.0
    s.reservations["res_1"].status = ReservationStatus.RESERVED
    s.reservations["res_1"].units_reserved = 1
    assert estimate(s, request, now).p_firm == 1.0


def test_p_best_adds_fresh_invites():
    s, request, now = s2_with_pledges()
    p = estimate(s, request, now).p
    assert p_best(s, request, now, [0.47] * 5) > p
    assert p_best(s, request, now, []) == pytest.approx(p)


def test_plugin_flag_changes_only_p():
    s, request, now = s2_with_pledges()
    mix, plug = estimate(s, request, now, estimator="mixture"), estimate(s, request, now, estimator="plugin")
    assert mix.p != plug.p and mix.p_firm == plug.p_firm
    assert config.ESTIMATOR == "mixture"
