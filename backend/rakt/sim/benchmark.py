"""Benchmark, essential tier (AGENT §10): today's workflow vs RaktTrace on N random requests.

Common random numbers: every request's outcomes (stock truth, staff delays, each donor's reply, show and pass) are
drawn once, before either policy runs, and both policies read the same draws. Simulated, synthetic world: these
numbers compare policies inside the model; they are not real-world evidence.

Run: `cd backend && uv run python -m rakt.sim.benchmark` (seed 2026, N = 500, cached LLM readings) → writes
`backend/bench/results_nominal_<seed>.json`. It never calls an LLM or Telegram.
"""

import argparse
import json
import math
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from rakt import config, llm, store
from rakt.agent import loop
from rakt.clock import Clock
from rakt.llm import client
from rakt.models import IST, BloodGroup, PledgeStatus, Product, Request, RequestStatus, ReservationStatus
from rakt.sim.world import draw_request, generate_world, rng_for
from rakt.store import AppState, Store, split_lanes

BENCH_DIR = Path(__file__).resolve().parents[2] / "bench"
REFERENCE_DAY = datetime(2026, 10, 24, 0, 0, tzinfo=IST)
DEADLINE_HOURS = {Product.PRBC: (2, 24), Product.SDP: (6, 30)}  # AGENT §10 mix
DONE = {RequestStatus.SECURED, RequestStatus.FULFILLED}
SAFE_NOTE = "Simulated synthetic world; compares policies inside the model, not real-world evidence."


@dataclass(frozen=True)
class Case:
    key: str
    product: Product
    group: BloodGroup
    units: int
    hospital_id: str
    created_at: datetime
    deadline_at: datetime


@dataclass(frozen=True)
class Outcome:
    on_time: bool
    done: bool  # marked fulfilled / secured at some point
    donors_messaged: int
    warning_h: float | None  # hours between the first human alert and the deadline


def make_cases(seed: int, n: int, hospitals: list[str]) -> list[Case]:
    rng = rng_for(seed, "cases")
    groups = [BloodGroup(g) for g in config.GROUP_MIX]
    weights = list(config.GROUP_MIX.values())
    cases = []
    for i in range(n):
        product = Product.PRBC if i % 2 == 0 else Product.SDP  # 50 / 50
        created = REFERENCE_DAY + timedelta(minutes=rng.uniform(0, 24 * 60))
        low, high = DEADLINE_HOURS[product]
        cases.append(Case(
            key=f"B{seed}-{i:04d}", product=product, group=rng.choices(groups, weights)[0],
            units=rng.randint(1, 3), hospital_id=rng.choice(hospitals), created_at=created,
            deadline_at=created + timedelta(hours=rng.uniform(low, high)),
        ))
    return cases


def truly_ready(s: Store, request: Request) -> int:
    """Units really ready for the patient by the deadline (AGENT §10 `on_time`; the safety margin is a planning
    buffer, not part of the truth). The sim has no post-collection failures."""
    limit = request.deadline_at
    stock = sum(r.units_reserved for r in s.reservations.values()
                if r.status in (ReservationStatus.RESERVED, ReservationStatus.READY) and r.ready_at and r.ready_at <= limit)
    donors = sum(1 for p in s.pledges.values()
                 if p.status in (PledgeStatus.COLLECTED, PledgeStatus.READY) and p.ready_at and p.ready_at <= limit)
    return stock + donors


def run_case(world, seed: int, case: Case) -> tuple[Outcome, Outcome]:
    """(today, rakttrace) for one request, both on the same pre-drawn outcomes."""
    draws = draw_request(world, list(world.donors), seed, case.key, case.product, case.created_at)
    base = Store(hospitals=dict(world.hospitals), centres=dict(world.centres), stock=list(draws.stock),
                 donors={k: d.model_copy(deep=True) for k, d in world.donors.items()})
    request = Request(id=case.key, group=case.group, product=case.product, units=case.units,
                      hospital_id=case.hospital_id, deadline_at=case.deadline_at, created_at=case.created_at,
                      radius_km=config.SEARCH_RADII_KM[0])
    base.requests[request.id] = request
    state = AppState(clock=Clock(case.created_at), lanes=split_lanes(base), draws={request.id: draws})
    store.set_state(state)
    loop.start(request.id)  # also works out today's workflow on its own lane copy
    while (timer := state.clock.peek()) is not None and timer.at <= case.deadline_at:
        state.clock.step(loop.on_timer)

    s = state.main
    final = s.requests[request.id]
    alerts = [d.at for d in s.decisions if "Alerted the coordinator (L2)" in d.summary]
    rak = Outcome(
        on_time=truly_ready(s, final) >= case.units,
        done=final.status in DONE or any(d.status in DONE for d in s.decisions),
        donors_messaged=len(s.pledges),
        warning_h=(case.deadline_at - alerts[0]).total_seconds() / 3600 if alerts else None,
    )
    run = state.baselines[request.id]
    today = Outcome(on_time=run.units_ready >= case.units, done=run.state.said_fulfilled_at is not None,
                    donors_messaged=run.state.donors_messaged, warning_h=None)
    return today, rak


def metrics(outcomes: list[Outcome]) -> dict:
    n = len(outcomes)
    failed = [o for o in outcomes if not o.on_time]
    warned = [o.warning_h for o in failed if o.warning_h is not None and o.warning_h >= 1]
    return {
        "on_time_pct": round(100 * sum(o.on_time for o in outcomes) / n, 1),
        "false_done_pct": round(100 * sum(o.done and not o.on_time for o in outcomes) / n, 1),
        "donors_messaged": round(statistics.fmean(o.donors_messaged for o in outcomes), 2),
        "zero_donor_pct": round(100 * sum(o.on_time and o.donors_messaged == 0 for o in outcomes) / n, 1),
        "warned_early_pct": round(100 * len(warned) / len(failed), 1) if failed else 0.0,
        "median_warning_h": round(statistics.median(warned), 2) if warned else None,
    }


def paired_ci(diffs: list[float]) -> dict:
    """mean d ± 1.96 · sd(d) / √N (AGENT §10)."""
    mean = statistics.fmean(diffs)
    half = 1.96 * statistics.stdev(diffs) / math.sqrt(len(diffs)) if len(diffs) > 1 else 0.0
    return {"mean": round(mean, 4), "lo": round(mean - half, 4), "hi": round(mean + half, 4),
            "excludes_zero": (mean - half) > 0 or (mean + half) < 0}


def benchmark(n: int = 500, seed: int = 2026, reader: str = "llm") -> dict:
    started = time.perf_counter()
    llm.set_enabled(reader == "llm")  # cached phrase readings only: the network is never used here
    world = generate_world(seed, REFERENCE_DAY)
    cases = make_cases(seed, n, sorted(world.hospitals))
    pairs = [run_case(world, seed, case) for case in cases]
    today = [p[0] for p in pairs]
    rak = [p[1] for p in pairs]
    by_product = {
        product.value: {"n": sum(c.product == product for c in cases),
                        "today": metrics([t for t, c in zip(today, cases) if c.product == product]),
                        "rakttrace": metrics([r for r, c in zip(rak, cases) if c.product == product])}
        for product in Product
    }
    return {
        "n": n, "seed": seed, "regime": "nominal", "reader": reader, "policies": ["today", "rakttrace"],
        "by_product": by_product, "today": metrics(today), "rakttrace": metrics(rak),
        "ci": {"today": {
            "on_time_diff": paired_ci([int(r.on_time) - int(t.on_time) for t, r in pairs]),
            "donors_diff": paired_ci([r.donors_messaged - t.donors_messaged for t, r in pairs]),
        }},
        "runtime_s": round(time.perf_counter() - started, 1),
        "note": SAFE_NOTE,
    }


def results_path(seed: int, regime: str = "nominal") -> Path:
    return BENCH_DIR / f"results_{regime}_{seed}.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="RaktTrace essential benchmark (today vs rakttrace)")
    parser.add_argument("--n", type=int, default=500)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--reader", choices=["llm", "rules"], default="llm")
    parser.add_argument("--json", action="store_true", help="print the result JSON on stdout")
    args = parser.parse_args()
    client.complete_json = lambda system, user: None  # never call a provider from the benchmark
    result = benchmark(args.n, args.seed, args.reader)
    BENCH_DIR.mkdir(exist_ok=True)
    results_path(args.seed).write_text(json.dumps(result, indent=1), encoding="utf-8")
    if args.json:
        print(json.dumps(result))
    else:
        print(json.dumps({k: result[k] for k in ("n", "seed", "reader", "today", "rakttrace", "ci", "runtime_s")}, indent=1))


if __name__ == "__main__":
    main()
