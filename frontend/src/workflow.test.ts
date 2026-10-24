// node --experimental-strip-types --test (npm test). Fixtures are request states observed from the backend's S1–S3.
import assert from "node:assert/strict";
import { test } from "node:test";
import type { Decision, RequestView } from "./api.ts";
import { awaitingStaff, lastChange, steps, supply, units } from "./workflow.ts";

function view(over: Partial<RequestView> & Pick<RequestView, "units" | "units_ladder">): RequestView {
  return {
    id: "RT-1", status: "OPEN", group: "B_POS", product: "PRBC", hospital: { id: "h", name: "H", area: "A" },
    collection_centre: null, created_at: "", deadline_at: "", now: "", p: 0, p_firm: 0, target: 0.9, stock: [], donors: [],
    counts: { messaged: 0, yes: 0, no: 0, silent: 0, active: 0, standby: 0 },
    escalation: { level: 0, brief: null, call_list: [] }, flags: { donors_can_help: true, waiting_for_stock: false },
    ...over,
  };
}

const ladder = (found: number, said_yes: number, ready_in_time: number, collected_or_reserved: number, confirmed: number) =>
  ({ found, said_yes, ready_in_time, collected_or_reserved, confirmed });

const stock = (status: string, centre = "Centre", reserved = 1) =>
  ({ reservation_id: `${centre}-${status}`, centre, units_asked: reserved, units_reserved: reserved, status, listed_age_min: 1, p: 1 });

const donor = (name: string, status: string) => ({ pledge_id: name, name, group: "O_POS", km: 1, status, p: 0.5,
  booking_code: null, ready_at: null, why: "", reply_text: null, read_by: null, live: false });

test("S1 secured: stock covers both units, no donors needed, nothing counts until staff confirm", () => {
  const v = view({ units: 2, units_ladder: ladder(2, 0, 2, 2, 0), stock: [stock("RESERVED"), stock("RESERVED"), stock("RELEASED")],
    flags: { donors_can_help: false, waiting_for_stock: false } });
  assert.deepEqual(steps(v).map((s) => s.state), ["done", "done", "skip", "done", "done", "todo"]);
  assert.equal(steps(v)[2].value, "not needed");
  assert.equal(awaitingStaff(v), 2);
});

test("partial fulfilment: one of two confirmed, one still awaiting staff", () => {
  const v = view({ units: 2, units_ladder: ladder(2, 0, 2, 2, 1) });
  assert.equal(steps(v)[5].state, "partial");
  assert.equal(steps(v)[5].ready, false);
  assert.equal(awaitingStaff(v), 1);
});

test("S3: no stock, donors can't be tested in time, so the gap is blocked rather than worked", () => {
  const v = view({ units: 2, units_ladder: ladder(0, 0, 0, 0, 0), flags: { donors_can_help: false, waiting_for_stock: false } });
  const s = steps(v);
  assert.equal(s[0].value, "no listed stock asked");
  assert.equal(s[0].state, "done");
  assert.equal(s[1].state, "blocked");
  assert.equal(s[2].value, "no donors messaged");
});

test("S2 collected: a donor unit collected is still not ready", () => {
  const v = view({ units: 1, units_ladder: ladder(0, 6, 1, 1, 0),
    counts: { messaged: 15, yes: 6, no: 3, silent: 0, active: 1, standby: 0 } });
  assert.deepEqual(steps(v).map((s) => s.state), ["done", "partial", "done", "done", "done", "todo"]);
  assert.equal(steps(v)[2].value, "6 yes · 1 going · 0 standby");
  assert.equal(awaitingStaff(v), 1);
});

test("stock still being asked is shown as waiting, not as found", () => {
  const v = view({ units: 2, units_ladder: ladder(0, 0, 0, 0, 0), stock: [stock("PENDING"), stock("PENDING")] });
  assert.equal(steps(v)[0].value, "0 of 2 reserved · asking 2 centres");
  assert.equal(steps(v)[0].state, "partial");
});

test("fulfilled: every step reads as done and the last is marked ready", () => {
  const v = view({ units: 2, units_ladder: ladder(2, 0, 2, 2, 2) });
  assert.equal(steps(v)[5].ready, true);
  assert.equal(awaitingStaff(v), 0);
});

test("awaiting staff never goes negative or above the units needed", () => {
  assert.equal(awaitingStaff(view({ units: 1, units_ladder: ladder(0, 0, 0, 0, 1) })), 0);
  assert.equal(awaitingStaff(view({ units: 1, units_ladder: ladder(3, 0, 3, 3, 0) })), 1);
});

test("last change is the latest decision that moved P by a whole percent", () => {
  const d = (id: string, p_before: number, p_after: number) =>
    ({ id, request_id: "RT-1", at: "", trigger: id, p_before, p_after, status: "OPEN", actions: [], summary: "" }) as Decision;
  assert.equal(lastChange([d("a", 0, 0.95), d("b", 0.85, 0.93), d("c", 0.931, 0.934), d("d", 1, 1)])?.id, "b");
  assert.equal(lastChange([d("a", 1, 1)]), undefined);
});


test("supply: required, arranged, confirmed ready and the gap come from the ladder, never above what is required", () => {
  assert.deepEqual(supply(view({ units: 2, units_ladder: ladder(1, 0, 1, 1, 1) })), { required: 2, arranged: 1, ready: 1, gap: 1 });
  assert.deepEqual(supply(view({ units: 1, units_ladder: ladder(3, 0, 3, 3, 0) })), { required: 1, arranged: 1, ready: 0, gap: 0 });
});

test("units: one row per required unit, from real holds and pledges; standby and yes are never ready", () => {
  const v = view({ units: 2, units_ladder: ladder(1, 2, 2, 1, 0),
    stock: [stock("RESERVED", "Centre A"), stock("NONE", "Centre D")],
    donors: [donor("Fatima D. · 1", "STANDBY"), donor("Sneha V.", "ACTIVE")] });
  assert.deepEqual(units(v).map((u) => [u.state, u.source]), [["arranged", "Centre A stock"], ["committed", "Sneha V."]]);
});

test("units: confirmed first, the rest padded as not found", () => {
  const v = view({ units: 3, units_ladder: ladder(1, 0, 1, 1, 1), stock: [stock("READY", "Centre B")], donors: [donor("Asha H.", "ARRIVED")] });
  assert.deepEqual(units(v).map((u) => u.state), ["ready", "at_centre", "missing"]);
  assert.equal(units(v).filter((u) => u.state === "ready").length, supply(v).ready);
});

test("gap after stock waits for pending stock answers instead of flagging donors", () => {
  const v = view({ units: 2, units_ladder: ladder(0, 0, 0, 0, 0), stock: [stock("PENDING")], flags: { donors_can_help: false, waiting_for_stock: false } });
  assert.equal(steps(v)[1].state, "todo");
  assert.equal(steps(v)[1].value, "2 units until stock answers");
});
