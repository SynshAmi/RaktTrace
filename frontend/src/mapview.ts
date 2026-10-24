// What each map marker means. Pure display rules over GET /map: the planner and staff decide everything; this only
// names and colours what they decided. Tested by npm test.
import type { MapDonor, MapView } from "./api";

export type Kind = "ready" | "atCentre" | "going" | "standby" | "invited" | "cantHelp" | "declined" | "candidate" | "other";

// Colours are theme tokens (index.css): green only for staff-confirmed ready, amber for at the centre but not ready,
// red only for a donor who can no longer help.
export const KIND: Record<Kind, { label: string; token: string; fill: boolean; size: number }> = {
  ready: { label: "Unit ready (staff confirmed)", token: "--success", fill: true, size: 12 },
  atCentre: { label: "At the centre or collected, not ready yet", token: "--caution", fill: true, size: 12 },
  going: { label: "Said yes in time, booked to donate", token: "--accent", fill: true, size: 12 },
  standby: { label: "Standby (said yes, kept in reserve)", token: "--accent", fill: false, size: 11 },
  invited: { label: "Invited, no answer yet", token: "--text", fill: false, size: 9 },
  cantHelp: { label: "Can't help now (too late, deferred, no-show, failed test)", token: "--danger", fill: false, size: 9 },
  declined: { label: "Said no, stopped, or released", token: "--faint", fill: false, size: 7 },
  candidate: { label: "Could be invited: passes the planner's filters now", token: "--text", fill: true, size: 7 },
  other: { label: "Other registered donor", token: "--faint", fill: true, size: 4 },
};

const BY_STATUS: Record<string, Kind> = {
  READY: "ready", COLLECTED: "atCentre", ARRIVED: "atCentre", ACTIVE: "going", STANDBY: "standby",
  INVITED: "invited", NO_REPLY: "invited", TOO_LATE: "cantHelp", DEFERRED: "cantHelp", NO_SHOW: "cantHelp",
  FAILED_TEST: "cantHelp", DECLINED: "declined", RELEASED: "declined", OPTED_OUT: "declined",
};

export function kind(d: MapDonor): Kind {
  if (d.pledge) return BY_STATUS[d.pledge.status] ?? "invited";
  return d.candidate ? "candidate" : "other";
}

/** Drawing order: background donors first, this request's donors on top, the most advanced last. */
const ORDER: Kind[] = ["other", "candidate", "declined", "invited", "cantHelp", "standby", "going", "atCentre", "ready"];
export const drawOrder = (donors: MapDonor[]) =>
  [...donors].sort((a, b) => ORDER.indexOf(kind(a)) - ORDER.indexOf(kind(b)) || (a.live ? 1 : 0) - (b.live ? 1 : 0));

/** How the position was set, in words. Never claims a real location. */
export function provenance(d: MapDonor): string {
  switch (d.location_basis) {
    case "area": return `Approximate: the centre of ${d.area}, the area they picked`;
    case "simulated": return `Simulated: placed about ${d.stated_travel_min ?? "?"} min from Centre B, as they said`;
    case "template": return "Synthetic: a live-demo profile near Centre B";
    default: return "Synthetic: generated with the demo city";
  }
}

export function pledgeLine(d: MapDonor): string {
  if (!d.pledge) return d.candidate ? "Not contacted · passes the planner's filters now" : "Not contacted for this request";
  const word = d.pledge.status.charAt(0) + d.pledge.status.slice(1).toLowerCase().replace(/_/g, " ");
  const parts = [word];
  if (d.pledge.booking_code) parts.push(`booking ${d.pledge.booking_code}`);
  if (d.pledge.on_way) parts.push("tapped On my way (not arrival)");
  return parts.join(" · ");
}

/** Counts per kind, for the legend. */
export function tally(view: MapView): Record<Kind, number> {
  const out = Object.fromEntries(Object.keys(KIND).map((k) => [k, 0])) as Record<Kind, number>;
  for (const d of view.donors) out[kind(d)] += 1;
  return out;
}
