from datetime import timedelta

from rakt.models import BloodGroup, Product, RequestStatus
from rakt.sim.scenarios import list_scenarios, load_scenario
from rakt.sim.world import km_between


def listing(state, centre_id, product, group):
    matches = [s for s in state.main.stock if (s.centre_id, s.product, s.group) == (centre_id, product, group)]
    assert len(matches) == 1, (centre_id, product, group)
    return matches[0]


def age_min(state, stock):
    return (state.clock.now - stock.listed_at) / timedelta(minutes=1)


def only_request(state):
    (request,) = state.main.requests.values()
    return request


def test_scenarios_listed():
    assert [s["id"] for s in list_scenarios()] == ["s1_surgery_tonight", "s2_dengue_sdp", "s3_no_way_in_time"]


def test_s1_loads():
    state = load_scenario("s1_surgery_tonight")
    request = only_request(state)
    assert (request.group, request.product, request.units) == (BloodGroup.B_POS, Product.PRBC, 2)
    assert request.deadline_at - request.created_at == timedelta(hours=4)
    assert request.status == RequestStatus.OPEN

    a, b, d = (listing(state, c, Product.PRBC, BloodGroup.B_POS) for c in ("c_a", "c_b", "c_d"))
    assert (a.listed_units, a.true_units, age_min(state, a)) == (3, 1, 19 * 60)
    assert (b.listed_units, b.true_units) == (2, 2) and age_min(state, b) <= 6 * 60
    assert d.listed_units == 1
    assert age_min(state, d) > age_min(state, a)  # D older than A, so D isn't asked

    compatible = {BloodGroup.B_POS, BloodGroup.B_NEG, BloodGroup.O_POS, BloodGroup.O_NEG}
    holders = {s.centre_id for s in state.main.stock if s.product == Product.PRBC and s.group in compatible}
    assert holders == {"c_a", "c_b", "c_d"}

    delays = state.draws[request.id].staff_delay_min
    assert delays["c_a"] < delays["c_b"] < 20  # A answers before B, both inside 20 min


def test_s2_loads():
    state = load_scenario("s2_dengue_sdp")
    request = only_request(state)
    assert (request.group, request.product, request.units) == (BloodGroup.O_POS, Product.SDP, 1)
    assert request.deadline_at.isoformat() == "2026-10-25T14:00:00+05:30"

    a = listing(state, "c_a", Product.SDP, BloodGroup.O_POS)
    assert (a.listed_units, a.true_units, age_min(state, a)) == (1, 0, 15 * 60)
    o_pos_sdp = [s for s in state.main.stock if s.product == Product.SDP and s.group == BloodGroup.O_POS]
    assert o_pos_sdp == [a]

    hospital = state.main.hospitals[request.hospital_id]
    centre_b = state.main.centres[hospital.centre_id]
    assert centre_b.id == "c_b" and centre_b.apheresis and centre_b.accepts_donors

    added = [d for d in state.main.donors.values() if d.id.startswith("d_s2_")]
    assert len(added) == 14
    for donor in added:
        assert donor.group == BloodGroup.O_POS and donor.apheresis_ok and donor.consent and not donor.opted_out
        assert 18 <= donor.age <= 60 and donor.weight_kg >= 50 and donor.last_whole_blood_at is None
        assert km_between((centre_b.lat, centre_b.lon), (donor.lat, donor.lon)) <= 3.01
    assert all(d.id in state.draws[request.id].donors for d in added)

    script = state.scenario.donor_script
    assert [s.invite_order for s in script] == list(range(1, 11))
    assert script[3].latent().available_from.isoformat() == "2026-10-25T11:55:00+05:30"


def test_s3_loads():
    state = load_scenario("s3_no_way_in_time")
    request = only_request(state)
    assert (request.group, request.product, request.units) == (BloodGroup.O_NEG, Product.PRBC, 2)
    assert request.deadline_at - request.created_at == timedelta(hours=6)
    hospital = state.main.hospitals[request.hospital_id]
    for s in state.main.stock:
        if s.product == Product.PRBC and s.group == BloodGroup.O_NEG and s.listed_units > 0:
            centre = state.main.centres[s.centre_id]
            assert km_between((hospital.lat, hospital.lon), (centre.lat, centre.lon)) > 40


def test_lanes_are_independent_copies():
    state = load_scenario("s1_surgery_tonight")
    assert set(state.lanes) == {"rakttrace", "today"}
    request = only_request(state)
    state.lanes["today"].requests[request.id].status = RequestStatus.FAILED
    assert state.main.requests[request.id].status == RequestStatus.OPEN


def test_scenario_load_is_reproducible():
    a, b = load_scenario("s2_dengue_sdp"), load_scenario("s2_dengue_sdp")
    assert a.main == b.main and a.draws == b.draws
