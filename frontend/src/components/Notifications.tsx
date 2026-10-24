import { useEffect, useRef, useState } from "react";
import type { Decision } from "../api";
import { advance, DURATION_MS, emptyQueue, enqueue, notesFor, type Queue, type Severity } from "../notify";

const LOOK: Record<Severity, { kicker: string; box: string; title: string }> = {
  routine: { kicker: "Update", box: "border-l-4 border-line-strong", title: "text-base" },
  escalation: { kicker: "Escalation", box: "border-2 border-danger", title: "text-lg text-danger" },
  fulfilled: {
    kicker: "Fulfilled", box: "border-2 border-success bg-[color-mix(in_srgb,var(--success)_14%,var(--raise))]",
    title: "text-xl text-success",
  },
  failed: {
    kicker: "Failed", box: "border-2 border-danger bg-[color-mix(in_srgb,var(--danger)_14%,var(--raise))]",
    title: "text-xl text-danger",
  },
};

type Props = { requestId: string; run: number; decisions: Decision[] | null; label: string };

/** Transient notes for new decisions, one on screen at a time. Display timers only: the simulation never waits. */
export default function Notifications({ requestId, run, decisions, label }: Props) {
  const [queue, setQueue] = useState<Queue>(emptyQueue);
  const seen = useRef<number | null>(null);
  const labelRef = useRef(label);
  labelRef.current = label;

  // A new run or request: start from its current log and drop anything still pending.
  useEffect(() => {
    seen.current = null;
    setQueue(emptyQueue);
  }, [requestId, run]);

  useEffect(() => {
    if (!decisions) return;
    if (seen.current === null || decisions.length < seen.current) {  // first look, or the world was reset elsewhere
      seen.current = decisions.length;
      return;
    }
    if (decisions.length > seen.current) {
      const notes = notesFor(decisions, seen.current, labelRef.current);
      seen.current = decisions.length;
      setQueue((q) => enqueue(q, notes));
    }
  }, [decisions]);

  // Fill the slot when it is free.
  useEffect(() => {
    if (!queue.active && queue.waiting.length) setQueue(advance);
  }, [queue.active, queue.waiting.length]);

  // Each note keeps its own display time; new arrivals don't extend or cut it.
  useEffect(() => {
    if (!queue.active) return;
    const timer = setTimeout(() => setQueue((q) => ({ ...q, active: null })), DURATION_MS[queue.active.severity]);
    return () => clearTimeout(timer);
  }, [queue.active]);

  const note = queue.active;
  const critical = queue.waiting.filter((n) => n.severity !== "routine").length;
  return (
    <div className="pointer-events-none fixed inset-x-4 bottom-4 z-40 sm:left-auto sm:w-[26rem]" aria-live="polite">
      {note && (
        <div role={note.severity === "failed" ? "alert" : "status"} data-severity={note.severity}
          className={`pointer-events-auto rounded-md bg-raise px-4 py-3 shadow-lg ${LOOK[note.severity].box}`}>
          <div className="flex items-baseline justify-between gap-3 text-xs font-bold uppercase tracking-wider text-muted">
            <span>{LOOK[note.severity].kicker}</span>
            <span>{note.at.slice(11, 16)}{critical > 0 && ` · ${critical} more alert${critical === 1 ? "" : "s"} waiting`}</span>
          </div>
          <div className={`mt-1 font-bold leading-snug ${LOOK[note.severity].title}`}>{note.title}</div>
          <p className="mt-1 text-sm text-muted">{note.body}</p>
        </div>
      )}
    </div>
  );
}
