"""Scenario loader (SPEC §5). A scenario = a seeded world + one request + overrides on top of the draws."""

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, Field

from rakt import config
from rakt.clock import Clock
from rakt.models import BloodGroup, Channel, Contact, Product, Request, Stock
from rakt.sim.world import (
    DonorLatent, RequestDraws, World, distinct_names, draw_request, generate_world, make_donor, point_near,
    rng_for,
)
from rakt.store import AppState, Store, split_lanes

SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "scenarios"


class RequestSpec(BaseModel):
    group: BloodGroup
    product: Product
    units: int
    hospital_id: str
    deadline_at: datetime
    family: bool = False  # a sim phone "Family" gets the family messages


class ClearStock(BaseModel):
    product: Product
    groups: list[BloodGroup]


class StockSpec(BaseModel):
    centre_id: str
    product: Product
    group: BloodGroup
    listed_units: int
    age_min: int
    true_units: int


class AddDonors(BaseModel):
    """Extra donors near a centre. They get normal latent draws, keyed by their ids."""
    count: int
    group: BloodGroup
    near_centre: str
    within_km: float
    apheresis_ok: bool = False
    donation_verified: bool = False
    age_range: tuple[int, int] = (22, 45)
    weight_range_kg: tuple[int, int] = (58, 82)


class ScriptedDonor(BaseModel):
    """Outcome for the n-th simulated donor invited (1-based); linked Telegram donors don't count."""
    invite_order: int
    says_yes: bool
    is_later: bool = False
    reply_delay_min: float | None = None
    phrase_id: str | None = None
    available_from: datetime | None = None
    will_show: bool = True
    will_pass: bool = True

    def latent(self) -> DonorLatent:
        return DonorLatent(**self.model_dump(exclude={"invite_order"}))


class Scenario(BaseModel):
    id: str
    title: str
    seed: int
    now: datetime
    request: RequestSpec
    notes: list[str] = Field(default_factory=list)
    clear_stock: list[ClearStock] = Field(default_factory=list)
    stock: list[StockSpec] = Field(default_factory=list)
    staff_delay_min: dict[str, float] = Field(default_factory=dict)
    add_donors: list[AddDonors] = Field(default_factory=list)
    donor_script: list[ScriptedDonor] = Field(default_factory=list)


def list_scenarios() -> list[dict]:
    return [
        {"id": s.id, "title": s.title}
        for s in (read_scenario(p.stem) for p in sorted(SCENARIOS_DIR.glob("*.json")))
    ]


def read_scenario(scenario_id: str) -> Scenario:
    return Scenario.model_validate_json((SCENARIOS_DIR / f"{scenario_id}.json").read_text(encoding="utf-8"))


def added_donors(world: World, scenario: Scenario) -> dict:
    donors = {}
    for i, spec in enumerate(scenario.add_donors):
        centre = world.centres[spec.near_centre]
        rng = rng_for(scenario.seed, scenario.id, "add_donors", i)
        for n in range(1, spec.count + 1):
            donor_id = f"d_{scenario.id.split('_')[0]}_{i}{n:02d}"
            lat, lon = point_near(rng, (centre.lat, centre.lon), spec.within_km)
            donor = make_donor(rng, donor_id, spec.group, lat, lon, scenario.now)
            donors[donor_id] = donor.model_copy(update={
                "age": rng.randint(*spec.age_range),
                "weight_kg": rng.randint(*spec.weight_range_kg),
                "apheresis_ok": spec.apheresis_ok,
                "donation_verified": spec.donation_verified,
                "last_whole_blood_at": None,
            })
    return donors


def apply_stock_overrides(draws: RequestDraws, scenario: Scenario) -> RequestDraws:
    cleared = {(c.product, g) for c in scenario.clear_stock for g in c.groups}
    stock = [s for s in draws.stock if (s.product, s.group) not in cleared]
    overridden = {(s.centre_id, s.product, s.group) for s in scenario.stock}
    stock = [s for s in stock if (s.centre_id, s.product, s.group) not in overridden]
    stock += [
        Stock(centre_id=s.centre_id, product=s.product, group=s.group, listed_units=s.listed_units,
              listed_at=scenario.now - timedelta(minutes=s.age_min), true_units=s.true_units)
        for s in scenario.stock
    ]
    return replace(draws, stock=stock, staff_delay_min={**draws.staff_delay_min, **scenario.staff_delay_min})


def request_id(scenario: Scenario) -> str:
    return f"RT-{rng_for(scenario.seed, scenario.id, 'request_id').randint(1000, 9999)}"


def load_scenario(scenario_id: str) -> AppState:
    scenario = read_scenario(scenario_id)
    world = generate_world(scenario.seed, scenario.now)
    donors = distinct_names({**world.donors, **added_donors(world, scenario)})

    spec = scenario.request
    draws = draw_request(world, list(donors), scenario.seed, scenario.id, spec.product, scenario.now)
    draws = apply_stock_overrides(draws, scenario)

    rid = request_id(scenario)
    family = Contact(name="Family", channel=Channel.SIM, phone=f"family_{rid}") if spec.family else None
    request = Request(
        id=rid, group=spec.group, product=spec.product, units=spec.units,
        hospital_id=spec.hospital_id, deadline_at=spec.deadline_at, created_at=scenario.now,
        radius_km=config.SEARCH_RADII_KM[0], family=family,
    )
    store = Store(
        hospitals=dict(world.hospitals), centres=dict(world.centres), stock=list(draws.stock),
        donors=donors, requests={request.id: request},
    )
    return AppState(
        clock=Clock(scenario.now), lanes=split_lanes(store), draws={request.id: draws}, scenario=scenario,
        scenario_request_id=request.id,
    )
