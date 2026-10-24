// Pure readings of the API's fields for the request screen. Nothing here decides anything: it only arranges what
// the planner already reported (units ladder, counts, flags, decisions).
import type { Decision, RequestView } from "./api";

export type State = "done" | "partial" | "todo" | "skip" | "blocked";
export type Step = { label: string; value: string; state: State; ready?: boolean };

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** Units reserved or collected that staff haven't confirmed yet. */
export function awaitingStaff(v: RequestView): number {
  const confirmed = Math.min(v.units_ladder.confirmed, v.units);
  return Math.max(0, Math.min(v.units_ladder.collected_or_reserved, v.units) - confirmed);
}

/** The last decision that moved P (rounded to whole percent), so the change shown is one the planner recorded. */
export function lastChange(decisions: Decision[]): Decision | undefined {
  return [...decisions].reverse().find((d) => Math.round(d.p_before * 100) !== Math.round(d.p_after * 100));
}

/** Stock check → remaining gap → donor replies → timing → collected/reserved → staff confirmation. */
export function steps(v: RequestView): Step[] {
  const { found, ready_in_time, collected_or_reserved, confirmed } = v.units_ladder;
  const n = v.units;
  const gap = Math.max(0, n - found);
  const asking = v.stock.filter((s) => s.status === "PENDING").length;
  const c = v.counts;
  const of = (x: number) => `${Math.min(x, n)} of ${n}`;
  const level = (x: number): State => (x >= n ? "done" : x > 0 ? "partial" : "todo");
  return [
    {
      label: "Stock check",
      value: asking > 0 ? `${of(found)} reserved · asking ${plural(asking, "centre")}`
        : v.stock.length === 0 ? "no listed stock asked" : `${of(found)} reserved`,
      state: asking > 0 ? "partial" : "done", // the check is finished once no centre's answer is pending
    },
    {
      label: "Gap after stock",
      value: gap === 0 ? "none: stock covers it"
        : collected_or_reserved >= n ? `${plural(gap, "unit")}, covered by donors`
        : asking > 0 ? `${plural(gap, "unit")} until stock answers`
        : !v.flags.donors_can_help ? `${plural(gap, "unit")}; donors can't be tested in time` : `${plural(gap, "unit")} for donors`,
      state: gap === 0 || collected_or_reserved >= n ? "done"
        : asking > 0 ? "todo" : v.flags.donors_can_help ? "partial" : "blocked",
    },
    {
      label: "Donor replies",
      value: c.messaged === 0 ? (gap === 0 ? "not needed" : "no donors messaged")
        : `${c.yes} yes · ${c.active} going · ${c.standby} standby`,
      state: c.messaged === 0 ? (gap === 0 ? "skip" : "todo") : c.yes >= gap ? "done" : c.yes > 0 ? "partial" : "todo",
    },
    { label: "Ready in time", value: `${of(ready_in_time)} can make the deadline`, state: level(ready_in_time) },
    { label: "Collected or reserved", value: of(collected_or_reserved), state: level(collected_or_reserved) },
    { label: "Confirmed by staff", value: of(confirmed), state: level(confirmed), ready: confirmed >= n },
  ];
}

/** Required, arranged (reserved stock or collected donations), confirmed ready by staff, and the gap left. */
export function supply(v: RequestView) {
  const required = v.units;
  const arranged = Math.min(v.units_ladder.collected_or_reserved, required);
  const ready = Math.min(v.units_ladder.confirmed, required);
  return { required, arranged, ready, gap: Math.max(0, required - arranged) };
}

export type UnitState = "ready" | "arranged" | "at_centre" | "committed" | "missing";
export type Unit = { state: UnitState; label: string; source: string | null };

const RANK: Record<UnitState, number> = { ready: 0, arranged: 1, at_centre: 2, committed: 3, missing: 4 };

/** One row per required unit, from the request's own stock holds and donor pledges, furthest along first.
 *  Standby donors are backups, not units, so they never fill a row. */
export function units(v: RequestView): Unit[] {
  const found: Unit[] = [];
  for (const s of v.stock) {
    const source = `${s.centre} stock`;
    for (let i = 0; i < s.units_reserved; i++) {
      if (s.status === "READY") found.push({ state: "ready", label: "Confirmed ready by staff", source });
      else if (s.status === "RESERVED") found.push({ state: "arranged", label: "Reserved, awaiting staff", source });
    }
  }
  for (const d of v.donors) {
    if (d.status === "READY") found.push({ state: "ready", label: "Confirmed ready by staff", source: d.name });
    else if (d.status === "COLLECTED") found.push({ state: "arranged", label: "Collected, awaiting staff", source: d.name });
    else if (d.status === "ARRIVED") found.push({ state: "at_centre", label: "At the centre, being screened", source: d.name });
    else if (d.status === "ACTIVE") found.push({ state: "committed", label: "Donor said yes, can be ready in time", source: d.name });
  }
  found.sort((a, b) => RANK[a.state] - RANK[b.state]);
  const rows = found.slice(0, v.units);
  while (rows.length < v.units) rows.push({ state: "missing", label: "Not found yet", source: null });
  return rows;
}

export type Band = "good" | "watch" | "risk";

/** Display band for P, judged on the whole percent shown: green ≥ 90, amber 70–89, red below 70. Display only:
 *  the planner never reads it. */
export function band(p: number): Band {
  const shown = Math.round(p * 100);
  return shown >= 90 ? "good" : shown >= 70 ? "watch" : "risk";
}

export type Trend = "up" | "down" | "steady";

/** Direction of the last move in the shown percent; a rising 45% is still in the red band. */
export function trend(previous: number | null, now: number): Trend {
  if (previous === null) return "steady";
  const a = Math.round(previous * 100), b = Math.round(now * 100);
  return b > a ? "up" : b < a ? "down" : "steady";
}
