from datetime import datetime

from rakt import config
from rakt.models import IST, BloodGroup, Product
from rakt.sim.world import draw_request, generate_world, km_between, load_phrases, rng_for, tonight_factor

SEED = 42
NOW = datetime(2026, 10, 24, 22, 40, tzinfo=IST)


def test_world_reproducible():
    a, b = generate_world(SEED, NOW), generate_world(SEED, NOW)
    assert a == b
    assert generate_world(SEED + 1, NOW).donors != a.donors

    ids = list(a.donors)
    draws_a = draw_request(a, ids, SEED, "req-1", Product.SDP, NOW)
    draws_b = draw_request(b, ids, SEED, "req-1", Product.SDP, NOW)
    assert draws_a == draws_b
    assert draw_request(a, ids, SEED, "req-2", Product.SDP, NOW) != draws_a


def test_world_shape():
    world = generate_world(SEED, NOW)
    assert len(world.hospitals) == 4
    assert sorted(world.centres) == [f"c_{x}" for x in "abcdefgh"]
    assert sum(c.apheresis for c in world.centres.values()) == 3
    assert len(world.donors) == config.SIM_DONOR_COUNT
    centre = (12.9716, 77.5946)
    assert all(km_between(centre, (d.lat, d.lon)) <= config.SIM_DONOR_RADIUS_KM + 0.01 for d in world.donors.values())


def test_latent_keyed_by_donor():
    world = generate_world(SEED, NOW)
    ids = list(world.donors)
    full = draw_request(world, ids, SEED, "req-1", Product.PRBC, NOW).donors
    subset = draw_request(world, list(reversed(ids[:50])), SEED, "req-1", Product.PRBC, NOW).donors
    assert all(subset[d] == full[d] for d in subset)
    delays = [latent.reply_delay_min for latent in full.values() if latent.reply_delay_min is not None]
    assert len(set(delays)) > 0.8 * len(delays)  # each donor has its own draw


def test_latent_outcomes_are_consistent():
    world = generate_world(SEED, NOW)
    phrases = {p["id"]: p for p in load_phrases()}
    draws = draw_request(world, list(world.donors), SEED, "req-1", Product.SDP, NOW)
    for latent in draws.donors.values():
        if latent.reply_delay_min is None:
            assert not latent.says_yes and latent.phrase_id is None
            continue
        label = phrases[latent.phrase_id]["label"]
        if latent.is_later:
            assert label == "YES_LATER" and latent.available_from.date() == NOW.date().replace(day=25)
            assert 7 <= latent.available_from.hour <= 12
        else:
            assert latent.available_from is None
            assert label == ("YES_NOW" if latent.says_yes else "NO")


def test_factor_mean():
    exact = sum(f * w for f, w in zip(config.TONIGHT_FACTORS, config.TONIGHT_WEIGHTS))
    assert abs(exact - 1.0) < 1e-4
    draws = [tonight_factor(rng_for(SEED, "req", i, "tonight")) for i in range(20000)]
    assert abs(sum(draws) / len(draws) - 1.0) < 0.02
    assert abs(config.SIM_YES_RATE * exact - 0.25) < 1e-4


def test_group_mix():
    donors = generate_world(SEED, NOW).donors.values()
    for group in BloodGroup:
        share = 100 * sum(d.group == group for d in donors) / len(donors)
        assert abs(share - config.GROUP_MIX[group]) <= 3, group


def test_stock_truth_never_exceeds_listing():
    world = generate_world(SEED, NOW)
    draws = draw_request(world, [], SEED, "req-1", Product.PRBC, NOW)
    assert draws.stock
    assert all(0 <= s.true_units <= s.listed_units for s in draws.stock)
    assert all(world.centres[s.centre_id].apheresis for s in draws.stock if s.product == Product.SDP)
    assert all(10 <= d <= 30 for d in draws.staff_delay_min.values())
