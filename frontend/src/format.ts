import type { RequestStatus } from "./api";

// pos = fulfilled / confirmed, caution = secured but not ready, neg = urgent or failed, neu = working on it.
export type Tone = "pos" | "caution" | "neg" | "neu" | "muted";

export const toneText: Record<Tone, string> = {
  pos: "text-success",
  caution: "text-caution",
  neg: "text-danger",
  neu: "text-text",
  muted: "text-muted",
};

// PRODUCT §4 badges. Only staff-confirmed FULFILLED gets the positive tone: a yes isn't blood.
export const requestStatus: Record<RequestStatus, { label: string; tone: Tone; icon: string }> = {
  OPEN: { label: "Finding blood", tone: "neu", icon: "○" },
  COVERED: { label: "On track", tone: "neu", icon: "◔" },
  SECURED: { label: "Blood arranged", tone: "caution", icon: "◑" },
  FULFILLED: { label: "Ready for patient", tone: "pos", icon: "✓" },
  FAILED: { label: "Needs help", tone: "neg", icon: "!" },
  CANCELLED: { label: "Cancelled", tone: "muted", icon: "×" },
};

export const baselineStatus = { SEARCHING: "Searching", SAYS_FULFILLED: "Says fulfilled" } as const;

const GROUPS: Record<string, string> = {
  O_POS: "O+", O_NEG: "O−", A_POS: "A+", A_NEG: "A−", B_POS: "B+", B_NEG: "B−", AB_POS: "AB+", AB_NEG: "AB−",
};
const PRODUCTS: Record<string, string> = { PRBC: "Red cells", SDP: "Platelets (SDP)" };

export const groupLabel = (g: string) => GROUPS[g] ?? g;
export const productLabel = (p: string) => PRODUCTS[p] ?? p;
export const groupsInText = (text: string) => text.replace(/\b(AB|A|B|O)_(POS|NEG)\b/g, (g) => groupLabel(g));

export const statusWord = (s: string) => s.charAt(0) + s.slice(1).toLowerCase().replace(/_/g, " ");

export const pct = (p: number) => `${Math.round(p * 100)}%`;

// Sim times carry +05:30; always show them in IST, whatever the laptop's time zone.
const timeFmt = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit" });
const dayFmt = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", weekday: "short" });
const dateFmt = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", day: "numeric", month: "short" });

export const hhmm = (iso: string) => timeFmt.format(new Date(iso));

/** "22:40", or "Sat 01:30" when the day differs from `now`. */
export function when(iso: string, now?: string) {
  const d = new Date(iso);
  if (now && dateFmt.format(d) === dateFmt.format(new Date(now))) return timeFmt.format(d);
  return `${dayFmt.format(d)} ${timeFmt.format(d)}`;
}

export const clockDay = (iso: string) => `${dayFmt.format(new Date(iso))} ${dateFmt.format(new Date(iso))}`;

/** "3 h 05 m left", or null once the deadline has passed. */
export function timeLeft(deadline: string, now: string) {
  const min = Math.floor((new Date(deadline).getTime() - new Date(now).getTime()) / 60000);
  if (min <= 0) return null;
  const h = Math.floor(min / 60);
  const m = String(min % 60).padStart(2, "0");
  return h > 0 ? `${h} h ${m} m left` : `${min % 60} m left`;
}
