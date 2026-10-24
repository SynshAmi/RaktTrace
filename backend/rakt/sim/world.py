"""Seeded synthetic Bengaluru (AGENT §9). Fictional names, real-ish coordinates.

Common random numbers: every random draw for a request is made before any policy runs, and each one
uses its own RNG keyed by (seed, request key, what is drawn). A donor's outcome depends only on its id,
never on the order in which donors are looked at.
"""

import json
import math
import random
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from rakt import config
from rakt.agent.probability import stock_p
from rakt.domain.geo import EARTH_RADIUS_KM, haversine_km
from rakt.models import BloodGroup, Centre, Channel, Contact, Donor, Hospital, Product, Stock

PHRASES_FILE = Path(__file__).with_name("phrases.json")
CITY_CENTRE = (12.9716, 77.5946)

AREAS = {
    "Jayanagar": (12.9250, 77.5938), "Basavanagudi": (12.9420, 77.5750), "BTM Layout": (12.9166, 77.6101),
    "Koramangala": (12.9352, 77.6245), "Indiranagar": (12.9784, 77.6408), "Malleshwaram": (13.0035, 77.5709),
    "Whitefield": (12.9698, 77.7500), "Yelahanka": (13.1007, 77.5963), "Hebbal": (13.0358, 77.5970),
    "Rajajinagar": (12.9915, 77.5550), "HSR Layout": (12.9116, 77.6474), "Banashankari": (12.9255, 77.5468),
}

# id, area, lat, lon, accepts_donors, apheresis
CENTRES = [
    ("c_a", "Basavanagudi", 12.9420, 77.5750, True, True),
    ("c_b", "Jayanagar", 12.9290, 77.5830, True, True),
    ("c_c", "Koramangala", 12.9352, 77.6245, True, False),
    ("c_d", "BTM Layout", 12.9166, 77.6101, True, False),
    ("c_e", "Indiranagar", 12.9790, 77.6400, True, True),
    ("c_f", "Malleshwaram", 13.0035, 77.5709, True, False),
    ("c_g", "Whitefield", 12.9698, 77.7500, True, False),
    ("c_h", "Yelahanka", 13.1007, 77.5963, False, False),
]

# id, name, area, lat, lon, own centre
HOSPITALS = [
    ("h_city", "City General Hospital", "Jayanagar", 12.9250, 77.5938, "c_b"),
    ("h_lake", "Lakeview Hospital", "Indiranagar", 12.9719, 77.6412, "c_e"),
    ("h_north", "Northside Medical Centre", "Hebbal", 13.0358, 77.5970, None),
    ("h_east", "Eastgate Hospital", "Whitefield", 12.9690, 77.7450, "c_g"),
]

FIRST_NAMES = [
    "Rahul", "Priya", "Arjun", "Sneha", "Vikram", "Ananya", "Karthik", "Divya", "Rohan", "Meera",
    "Aditya", "Kavya", "Siddharth", "Pooja", "Nikhil", "Shreya", "Manoj", "Lakshmi", "Varun", "Neha",
    "Imran", "Fatima", "Joseph", "Anita", "Suresh", "Deepa", "Harsh", "Ritu", "Ganesh", "Asha",
]
LAST_INITIALS = "ABCDGHIJKMNPRSTV"


@dataclass(frozen=True)
class World:
    seed: int
    hospitals: dict[str, Hospital]
    centres: dict[str, Centre]
    donors: dict[str, Donor]


@dataclass(frozen=True)
class DonorLatent:
    says_yes: bool
    is_later: bool
    available_from: datetime | None  # absolute; set only for later yeses
    reply_delay_min: float | None  # relative to the invite; None = never replies
    phrase_id: str | None
    will_show: bool
    will_pass: bool


@dataclass(frozen=True)
class RequestDraws:
    request_key: str
    tonight_factor: float
    stock: list[Stock]  # listings with their true units
    staff_delay_min: dict[str, float]  # by centre id
    donors: dict[str, DonorLatent]  # by donor id


def rng_for(seed: int, *key: object) -> random.Random:
    return random.Random(":".join(str(k) for k in (seed, *key)))


def nearest_area(lat: float, lon: float) -> str:
    return min(AREAS, key=lambda name: haversine_km((lat, lon), AREAS[name]))


def point_near(rng: random.Random, centre: tuple[float, float], radius_km: float) -> tuple[float, float]:
    r = 0.999 * radius_km * math.sqrt(rng.random())  # 0.999 keeps rounding inside the radius
    angle = rng.uniform(0, 2 * math.pi)
    deg_per_km = math.degrees(1 / EARTH_RADIUS_KM)
    dlat = r * math.cos(angle) * deg_per_km
    dlon = r * math.sin(angle) * deg_per_km / math.cos(math.radians(centre[0]))
    return round(centre[0] + dlat, 5), round(centre[1] + dlon, 5)


def sim_contact(name: str, phone_id: str) -> Contact:
    return Contact(name=name, channel=Channel.SIM, phone=phone_id)


def group_counts(total: int) -> dict[BloodGroup, int]:
    """Exact counts from the seed mix (largest remainder), so the mix never drifts by chance."""
    shares = {BloodGroup(g): total * pct / 100 for g, pct in config.GROUP_MIX.items()}
    counts = {g: int(s) for g, s in shares.items()}
    by_remainder = sorted(shares, key=lambda g: shares[g] - counts[g], reverse=True)
    for g in by_remainder[: total - sum(counts.values())]:
        counts[g] += 1
    return counts


def make_donor(rng: random.Random, donor_id: str, group: BloodGroup, lat: float, lon: float, now: datetime) -> Donor:
    name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_INITIALS)}."
    past = rng.random() < config.SIM_PAST_DONATION_SHARE
    verified = past and rng.random() < config.SIM_VERIFIED_SHARE / config.SIM_PAST_DONATION_SHARE
    days_ago = rng.randint(*config.SIM_LAST_DONATION_DAYS)
    return Donor(
        id=donor_id,
        display_name=name,
        group=group,
        sex="F" if rng.random() < config.SIM_FEMALE_SHARE else "M",
        age=rng.randint(*config.SIM_AGE_RANGE),
        weight_kg=rng.randint(*config.SIM_WEIGHT_RANGE_KG),
        lat=lat,
        lon=lon,
        area=nearest_area(lat, lon),
        contact=sim_contact(name, donor_id),
        apheresis_ok=rng.random() < config.SIM_APHERESIS_SHARE,
        last_whole_blood_at=now - timedelta(days=days_ago) if past else None,
        donation_verified=verified,
    )


def generate_world(seed: int, now: datetime) -> World:
    hospitals = {
        hid: Hospital(id=hid, name=name, area=area, lat=lat, lon=lon, centre_id=centre_id)
        for hid, name, area, lat, lon, centre_id in HOSPITALS
    }
    centres = {}
    for i, (cid, area, lat, lon, accepts, apheresis) in enumerate(CENTRES, start=1):
        name = f"Centre {cid[-1].upper()}"
        centres[cid] = Centre(
            id=cid, name=name, area=area, address=f"{name} Blood Centre, {area}, Bengaluru",
            lat=lat, lon=lon, phone=f"+91 99999 {i:05d}", accepts_donors=accepts, apheresis=apheresis,
            contact=sim_contact(f"{name} staff", cid),
        )

    rng = rng_for(seed, "donors")
    groups = [g for g, n in group_counts(config.SIM_DONOR_COUNT).items() for _ in range(n)]
    rng.shuffle(groups)
    donors = {}
    for i, group in enumerate(groups, start=1):
        donor_id = f"d_{i:03d}"
        lat, lon = point_near(rng, CITY_CENTRE, config.SIM_DONOR_RADIUS_KM)
        donors[donor_id] = make_donor(rng, donor_id, group, lat, lon, now)
    return World(seed=seed, hospitals=hospitals, centres=centres, donors=donors)


def renamed(donor: Donor, name: str) -> Donor:
    return donor.model_copy(update={"display_name": name, "contact": donor.contact.model_copy(update={"name": name})})


def distinct_names(donors: dict[str, Donor]) -> dict[str, Donor]:
    """Synthetic names are drawn independently, so two donors can share one ("Fatima D."). Number each shared name
    in id order ("Fatima D. · 1", "Fatima D. · 2") so every screen and message tells them apart."""
    counts = Counter(d.display_name for d in donors.values())
    seen: Counter = Counter()
    result = {}
    for donor_id, donor in donors.items():
        if counts[donor.display_name] > 1:
            seen[donor.display_name] += 1
            donor = renamed(donor, f"{donor.display_name} · {seen[donor.display_name]}")
        result[donor_id] = donor
    return result


def load_phrases() -> list[dict]:
    return json.loads(PHRASES_FILE.read_text(encoding="utf-8"))


def phrase_time(phrase: dict) -> tuple[int, int]:
    """'tomorrow after 11:55 AM' → (11, 55)."""
    hour, minute, ampm = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM)", phrase["time"]).groups()
    return int(hour) % 12 + (12 if ampm == "PM" else 0), int(minute)


def phrase_pools(phrases: list[dict]) -> dict[str, list[dict]]:
    """Latent replies use YES_NOW, NO and next-morning YES_LATER phrases (AGENT §9: later = next morning).
    STOP, UNCLEAR and other later phrases stay in the bank for the readers and the demo."""
    morning = [
        p for p in phrases
        if p["label"] == "YES_LATER" and p["time"].startswith("tomorrow") and 7 <= phrase_time(p)[0] <= 12
    ]
    return {
        "yes_now": [p for p in phrases if p["label"] == "YES_NOW"],
        "yes_later": morning,
        "no": [p for p in phrases if p["label"] == "NO"],
    }


def tonight_factor(rng: random.Random) -> float:
    return rng.choices(config.TONIGHT_FACTORS, weights=config.TONIGHT_WEIGHTS)[0]


def draw_listings(world: World, seed: int, key: str, created_at: datetime) -> list[Stock]:
    listings = []
    for centre in world.centres.values():
        for product in Product:
            if product == Product.SDP and not centre.apheresis:
                continue
            for group in BloodGroup:
                rng = rng_for(seed, key, "stock", centre.id, product, group)
                kind = "SDP" if product == Product.SDP else ("PRBC_NEG" if group.endswith("NEG") else "PRBC_POS")
                if rng.random() >= config.SIM_LISTING_CHANCE[kind]:
                    continue
                listed = rng.randint(*config.SIM_LISTED_UNITS[product])
                age = rng.uniform(*config.SIM_LISTING_AGE_MIN)
                true = listed if rng.random() < stock_p(age) else rng.randint(0, listed - 1)
                listings.append(Stock(
                    centre_id=centre.id, product=product, group=group, listed_units=listed,
                    listed_at=created_at - timedelta(minutes=round(age)), true_units=true,
                ))
    return listings


def draw_donor(seed: int, key: str, donor_id: str, factor: float, product: Product,
               created_at: datetime, pools: dict[str, list[dict]]) -> DonorLatent:
    rng = rng_for(seed, key, "donor", donor_id)
    u_yes, u_later, u_no = rng.random(), rng.random(), rng.random()
    delay = rng.expovariate(1 / config.SIM_REPLY_DELAY_MEAN_MIN)
    u_phrase, u_show, u_pass = rng.random(), rng.random(), rng.random()

    says_yes = u_yes < config.SIM_YES_RATE * factor
    is_later = says_yes and u_later < config.SIM_LATER_SHARE
    replies = says_yes or u_no < config.SIM_EXPLICIT_NO_SHARE
    pool = pools["yes_later" if is_later else "yes_now" if says_yes else "no"]
    phrase = pool[int(u_phrase * len(pool))] if replies else None

    available_from = None
    if is_later:
        hour, minute = phrase_time(phrase)
        next_day = created_at + timedelta(days=1)
        available_from = next_day.replace(hour=hour, minute=minute, second=0, microsecond=0)

    return DonorLatent(
        says_yes=says_yes,
        is_later=is_later,
        available_from=available_from,
        reply_delay_min=round(delay, 1) if replies else None,
        phrase_id=phrase["id"] if phrase else None,
        will_show=u_show < config.P_SHOW,
        will_pass=u_pass < config.P_PASS[product],
    )


def draw_request(world: World, donor_ids: list[str], seed: int, key: str, product: Product,
                 created_at: datetime) -> RequestDraws:
    """All randomness for one request, drawn before any policy runs."""
    factor = tonight_factor(rng_for(seed, key, "tonight"))
    pools = phrase_pools(load_phrases())
    return RequestDraws(
        request_key=key,
        tonight_factor=factor,
        stock=draw_listings(world, seed, key, created_at),
        staff_delay_min={
            cid: round(rng_for(seed, key, "staff", cid).uniform(*config.SIM_STAFF_REPLY_MIN), 1)
            for cid in world.centres
        },
        donors={d: draw_donor(seed, key, d, factor, product, created_at, pools) for d in donor_ids},
    )


def draw_new_request(seed: int, key: str, centre_ids: list[str], donor_ids: list[str], product: Product,
                     created_at: datetime) -> RequestDraws:
    """Outcomes for a request created after the world exists (dashboard or API): its own tonight factor, staff
    delays and donor outcomes, keyed by its request id. Stock stays the world's (no new listings)."""
    factor = tonight_factor(rng_for(seed, key, "tonight"))
    pools = phrase_pools(load_phrases())
    return RequestDraws(
        request_key=key,
        tonight_factor=factor,
        stock=[],
        staff_delay_min={cid: round(rng_for(seed, key, "staff", cid).uniform(*config.SIM_STAFF_REPLY_MIN), 1)
                         for cid in centre_ids},
        donors={d: draw_donor(seed, key, d, factor, product, created_at, pools) for d in donor_ids},
    )
