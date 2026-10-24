// Notifications: transient feedback built from new entries in the decision log (the log stays the record).
// One slot on screen at a time; critical notes wait their turn and are never dropped; a newer routine summary
// replaces an older one that hasn't shown yet.
import type { Decision } from "./api";

export type Severity = "routine" | "escalation" | "fulfilled" | "failed";
export type Note = { id: string; severity: Severity; title: string; body: string; at: string };

export const DURATION_MS: Record<Severity, number> = { routine: 3500, escalation: 8000, fulfilled: 10000, failed: 10000 };

const pct = (p: number) => `${Math.round(p * 100)}%`;

export function severity(d: Decision, previous: Decision | undefined): Severity {
  const changed = d.status !== previous?.status;
  if (changed && d.status === "FULFILLED") return "fulfilled";
  if (changed && d.status === "FAILED") return "failed";
  if (d.actions.some((a) => a === "L2 alert" || a.startsWith("widen to"))) return "escalation";
  return "routine";
}

function single(d: Decision, sev: Severity): Note {
  const moved = Math.round(d.p_before * 100) !== Math.round(d.p_after * 100);
  return {
    id: d.id, severity: sev, at: d.at, title: d.trigger,
    body: d.summary + (moved ? ` Estimated chance ${pct(d.p_before)} → ${pct(d.p_after)}.` : ""),
  };
}

function summary(routine: Decision[], label: string): Note {
  const first = routine[0], last = routine[routine.length - 1];
  const statuses = routine.filter((d, i) => i > 0 && d.status !== routine[i - 1].status).map((d) => d.status);
  const shown = routine.slice(-3).map((d) => d.trigger);
  const parts = [
    shown.join(" · ") + (routine.length > 3 ? ` · and ${routine.length - 3} more` : ""),
    statuses.length ? `Status now ${statuses[statuses.length - 1]}.` : "",
    Math.round(first.p_before * 100) !== Math.round(last.p_after * 100)
      ? `Estimated chance ${pct(first.p_before)} → ${pct(last.p_after)}.` : "",
  ];
  return { id: `${first.id}..${last.id}`, severity: "routine", at: last.at, title: `${label}: ${routine.length} updates`,
           body: parts.filter(Boolean).join(" ") };
}

/** Notes for the decisions after `seen`, in log order: each critical one on its own, the routine ones together
 *  (a lone routine decision is shown as itself). `label` says what moved the clock, e.g. "+1 h" or "Auto". */
export function notesFor(all: Decision[], seen: number, label: string): Note[] {
  const fresh = all.slice(seen);
  const routine: Decision[] = [];
  const critical: Note[] = [];
  fresh.forEach((d, i) => {
    const sev = severity(d, all[seen + i - 1]);
    if (sev === "routine") routine.push(d);
    else critical.push(single(d, sev));
  });
  const routineNote = routine.length === 0 ? [] : routine.length === 1 ? [single(routine[0], "routine")] : [summary(routine, label)];
  return [...routineNote, ...critical];
}

export type Queue = { active: Note | null; waiting: Note[] };

export const emptyQueue: Queue = { active: null, waiting: [] };

export function enqueue(q: Queue, notes: Note[]): Queue {
  let waiting = [...q.waiting];
  for (const note of notes) {
    if (note.severity === "routine") waiting = waiting.filter((n) => n.severity !== "routine");
    waiting.push(note);
  }
  return { ...q, waiting };
}

/** Called when the slot is free: critical notes first, in arrival order, then the routine summary. */
export function advance(q: Queue): Queue {
  const i = q.waiting.findIndex((n) => n.severity !== "routine");
  const pick = i >= 0 ? i : q.waiting.length ? 0 : -1;
  if (pick < 0) return { active: null, waiting: [] };
  return { active: q.waiting[pick], waiting: q.waiting.filter((_, j) => j !== pick) };
}
