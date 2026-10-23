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
      label: "Remaining gap",
      value: gap === 0 ? "none: stock covers it"
        : !v.flags.donors_can_help ? `${plural(gap, "unit")}; donors can't be tested in time` : `${plural(gap, "unit")} for donors`,
      state: gap === 0 ? "done" : v.flags.donors_can_help ? "partial" : "blocked",
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
