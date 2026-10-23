from datetime import datetime, timedelta

import pytest

from rakt import config
from rakt.domain.geo import haversine_km, travel_min
from rakt.domain.timing import (
    choose_collection_centre, donor_timing, donors_can_help, latest_arrival, stock_on_time, stock_ready_at,
)
from rakt.models import IST, Product
from rakt.sim.world import generate_world

NOW = datetime(2026, 10, 24, 22, 40, tzinfo=IST)
WORLD = generate_world(42, NOW)
H = WORLD.hospitals
C = WORLD.centres
CENTRES = list(C.values())


def hours(h: float) -> datetime:
    return NOW + timedelta(hours=h)


class Spot:
    def __init__(self, lat, lon):
        self.lat, self.lon = lat, lon


def test_travel_time_formula():
    a, b = C["c_a"], C["c_b"]
    km = haversine_km((a.lat, a.lon), (b.lat, b.lon))
    assert travel_min(a, b) == pytest.approx(km * 1.4 / 18 * 60)
    assert travel_min(a, a) == 0


def test_prbc_cannot_meet_4_hours():
    assert not donors_can_help(H["h_city"], CENTRES, Product.PRBC, NOW, hours(4))


def test_prbc_6_hours_is_stock_only():  # S3
    assert not donors_can_help(H["h_north"], CENTRES, Product.PRBC, NOW, hours(6))


def test_sdp_can_meet_16_hours():
    assert donors_can_help(H["h_city"], CENTRES, Product.SDP, NOW, hours(16))


def test_thresholds_about_14h_prbc_and_9h_sdp():
    city = H["h_city"]
    assert not donors_can_help(city, CENTRES, Product.PRBC, NOW, hours(13.5))
    assert donors_can_help(city, CENTRES, Product.PRBC, NOW, hours(14))
    assert not donors_can_help(city, CENTRES, Product.SDP, NOW, hours(8.75))
    assert donors_can_help(city, CENTRES, Product.SDP, NOW, hours(9))


def test_donors_can_help_needs_a_collecting_centre():
    no_apheresis = [c for c in CENTRES if not c.apheresis]
    assert not donors_can_help(H["h_city"], no_apheresis, Product.SDP, NOW, hours(30))


def test_donor_timing_fields():
    centre, hospital = C["c_b"], H["h_city"]
    donor = Spot(centre.lat, centre.lon)  # at the centre: no travel to it
    deadline = hours(15)
    t = donor_timing(donor, centre, hospital, Product.SDP, deadline, NOW)
    pipeline = config.VISIT_MIN["SDP"] + config.TEST_MIN["SDP"] + travel_min(centre, hospital)
    assert t.ready_at == NOW + timedelta(minutes=config.REPLY_LAG_MIN + pipeline)
    assert t.latest_arrival == deadline - timedelta(minutes=config.SAFETY_MARGIN_MIN + pipeline)
    assert t.go_window_min == pytest.approx((t.latest_arrival - NOW) / timedelta(minutes=1))
    assert t.on_time and t.invitable


def test_replied_donor_has_no_reply_lag():
    centre, hospital = C["c_b"], H["h_city"]
    donor = Spot(centre.lat, centre.lon)
    waiting = donor_timing(donor, centre, hospital, Product.SDP, hours(15), NOW)
    replied = donor_timing(donor, centre, hospital, Product.SDP, hours(15), NOW, replied=True)
    assert waiting.ready_at - replied.ready_at == timedelta(minutes=config.REPLY_LAG_MIN)


def test_available_from_null_safe_and_later_yes_too_late():  # S2 "kal 11:55"
    centre, hospital = C["c_b"], H["h_city"]
    donor = Spot(12.93, 77.585)
    deadline = datetime(2026, 10, 25, 14, 0, tzinfo=IST)
    now_yes = donor_timing(donor, centre, hospital, Product.SDP, deadline, NOW, available_from=None, replied=True)
    later = donor_timing(donor, centre, hospital, Product.SDP, deadline, NOW,
                         available_from=datetime(2026, 10, 25, 11, 55, tzinfo=IST), replied=True)
    assert now_yes.on_time
    assert not later.on_time and later.ready_at > deadline
    assert later.latest_arrival == now_yes.latest_arrival


def test_past_available_from_means_now():
    centre, hospital = C["c_b"], H["h_city"]
    donor = Spot(centre.lat, centre.lon)
    past = donor_timing(donor, centre, hospital, Product.SDP, hours(15), NOW,
                        available_from=NOW - timedelta(hours=1), replied=True)
    now = donor_timing(donor, centre, hospital, Product.SDP, hours(15), NOW, replied=True)
    assert past.ready_at == now.ready_at


def test_go_window_under_20_min_excluded():
    centre, hospital = C["c_b"], H["h_city"]
    arrival_gap = config.SAFETY_MARGIN_MIN + travel_min(centre, hospital) + config.TEST_MIN["SDP"] + config.VISIT_MIN["SDP"]
    donor = Spot(centre.lat, centre.lon)

    def timing(go_window: float):
        deadline = NOW + timedelta(minutes=arrival_gap + go_window)
        return donor_timing(donor, centre, hospital, Product.SDP, deadline, NOW, replied=True)

    assert timing(19.9).go_window_min == pytest.approx(19.9)
    assert timing(19.9).on_time and not timing(19.9).invitable
    assert timing(20).invitable


def test_late_donor_not_invitable_even_with_go_window():
    centre, hospital = C["c_b"], H["h_city"]
    far = Spot(13.10, 77.60)  # Yelahanka, ~19 km away
    deadline = NOW + timedelta(minutes=30 + 6 + 360 + 120 + 40)
    t = donor_timing(far, centre, hospital, Product.SDP, deadline, NOW, replied=True)
    assert t.go_window_min >= 20 and not t.on_time and not t.invitable


def test_latest_arrival_matches_formula():
    centre, hospital = C["c_a"], H["h_city"]
    deadline = hours(20)
    expected = deadline - timedelta(minutes=30 + travel_min(centre, hospital) + 720 + 45)
    assert latest_arrival(centre, hospital, Product.PRBC, deadline) == expected


def test_stock_ready_at():
    centre, hospital = C["c_a"], H["h_city"]
    travel = travel_min(centre, hospital)
    assert stock_ready_at(centre, hospital, NOW, reserved=True) == NOW + timedelta(minutes=45 + travel)
    assert stock_ready_at(centre, hospital, NOW, reserved=False) == NOW + timedelta(minutes=10 + 45 + travel)
    assert stock_on_time(centre, hospital, NOW, reserved=False, deadline=hours(4))  # S1: stock can make 4 h
    assert not stock_on_time(centre, hospital, NOW, reserved=False, deadline=hours(1))


def test_collection_centre_own_first():
    assert choose_collection_centre(H["h_city"], C, Product.SDP).id == "c_b"  # S2
    assert choose_collection_centre(H["h_city"], C, Product.PRBC, ["c_a"]).id == "c_b"


def test_collection_centre_falls_back_to_stock_holder_then_nearest():
    north = H["h_north"]  # no own centre
    assert choose_collection_centre(north, C, Product.PRBC, ["c_d", "c_a"]).id == "c_d"
    nearest = min((c for c in CENTRES if c.accepts_donors), key=lambda c: travel_min(c, north))
    assert choose_collection_centre(north, C, Product.PRBC).id == nearest.id


def test_collection_centre_sdp_needs_apheresis():
    east = H["h_east"]  # own centre c_g has no apheresis
    assert not C["c_g"].apheresis
    chosen = choose_collection_centre(east, C, Product.SDP, ["c_g", "c_c"])
    assert chosen.apheresis and chosen.accepts_donors
    assert choose_collection_centre(east, C, Product.SDP, ["c_g", "c_e"]).id == "c_e"


def test_collection_centre_skips_non_accepting():
    north = H["h_north"]
    assert not C["c_h"].accepts_donors
    assert choose_collection_centre(north, C, Product.PRBC, ["c_h"]).id != "c_h"
