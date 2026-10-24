// node --experimental-strip-types --test (npm test). Donor shapes follow GET /map.
import assert from "node:assert/strict";
import { test } from "node:test";
import type { MapDonor, MapView } from "./api.ts";
import { drawOrder, kind, pledgeLine, provenance, tally } from "./mapview.ts";

function donor(over: Partial<MapDonor> = {}): MapDonor {
  return {
    id: "d_001", name: "Asha H.", group: "O_POS", lat: 12.93, lon: 77.58, area: "Jayanagar",
    location: "synthetic", location_basis: "seeded", live: false, stated_travel_min: null, opted_out: false,
    km: 1.2, travel_min: 6, candidate: false, pledge: null, ...over,
  };
}
const pledge = (status: string, extra = {}) => ({ status, booking_code: null, on_way: false, why: "", ...extra });

test("only staff-confirmed READY is the ready kind; a yes or arrival never is", () => {
  assert.equal(kind(donor({ pledge: pledge("READY") })), "ready");
  assert.equal(kind(donor({ pledge: pledge("ACTIVE", { on_way: true }) })), "going");
  assert.equal(kind(donor({ pledge: pledge("ARRIVED") })), "atCentre");
  assert.equal(kind(donor({ pledge: pledge("COLLECTED") })), "atCentre");
});

test("standby, invited, can't-help and declined donors are told apart", () => {
  assert.equal(kind(donor({ pledge: pledge("STANDBY") })), "standby");
  assert.equal(kind(donor({ pledge: pledge("NO_REPLY") })), "invited");
  for (const s of ["TOO_LATE", "DEFERRED", "NO_SHOW", "FAILED_TEST"]) assert.equal(kind(donor({ pledge: pledge(s) })), "cantHelp");
  for (const s of ["DECLINED", "RELEASED", "OPTED_OUT"]) assert.equal(kind(donor({ pledge: pledge(s) })), "declined");
});

test("uncontacted donors follow the planner's candidate flag, not distance", () => {
  assert.equal(kind(donor({ candidate: true, km: 30 })), "candidate");
  assert.equal(kind(donor({ candidate: false, km: 0.1 })), "other");
});

test("provenance never claims a real location and tells approximate from simulated", () => {
  assert.match(provenance(donor({ location: "approximate", location_basis: "area", area: "Koramangala" })), /^Approximate.*Koramangala/);
  assert.match(provenance(donor({ location_basis: "simulated", stated_travel_min: 30 })), /^Simulated.*30 min/);
  assert.match(provenance(donor({ location_basis: "template" })), /^Synthetic/);
  assert.match(provenance(donor()), /^Synthetic/);
});

test("On my way is described as not arrival", () => {
  assert.match(pledgeLine(donor({ pledge: pledge("ACTIVE", { on_way: true, booking_code: "4821" }) })), /booking 4821.*not arrival/);
  assert.equal(pledgeLine(donor()), "Not contacted for this request");
});

test("draw order puts this request's donors above the background, live donors last within a kind", () => {
  const order = drawOrder([
    donor({ id: "r", pledge: pledge("READY") }), donor({ id: "o" }), donor({ id: "l", live: true }), donor({ id: "c", candidate: true }),
  ]).map((d) => d.id);
  assert.deepEqual(order, ["o", "l", "c", "r"]);
});

test("tally counts every donor once, and an empty world counts nothing", () => {
  const view: MapView = { now: "", request: null, centres: [], hospitals: [], unplaced: 0,
    donors: [donor({ pledge: pledge("ACTIVE") }), donor({ candidate: true }), donor()] };
  const t = tally(view);
  assert.equal(t.going + t.candidate + t.other, 3);
  assert.equal(Object.values(tally({ ...view, donors: [] })).reduce((a, b) => a + b, 0), 0);
});
