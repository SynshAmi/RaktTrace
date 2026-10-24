import type { BaselineView } from "../api";
import { baselineStatus, hhmm, when } from "../format";

type Props = { view: BaselineView | null; units: number; deadline: string; now: string; onHide: () => void };

/** Today's workflow: the same request run the way it's done today (simulated). What it claims vs what was ready. */
export default function Baseline({ view, units, deadline, now, onHide }: Props) {
  if (!view) return <p className="text-muted">Loading today's workflow…</p>;
  const truth = view.truth_at_deadline;
  const says = view.status === "SAYS_FULFILLED";
  const short = truth !== null && truth.units_ready < truth.units;
  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wider text-muted">Today's workflow</h2>
          <p className="text-sm text-faint">The same request, handled the way it's done today (simulated)</p>
        </div>
        <button onClick={onHide} aria-expanded className="rounded-md border-2 border-line-strong px-2.5 py-1 text-sm font-semibold hover:border-text">
          Hide ✕
        </button>
      </div>

      <div className="mt-6">
        <div className="text-sm font-bold uppercase tracking-wider text-muted">What it claims</div>
        <div className="mt-1 text-4xl font-bold">{says ? "“Fulfilled”" : baselineStatus[view.status]}</div>
        <div className="text-muted">{says && view.said_fulfilled_at ? `since ${hhmm(view.said_fulfilled_at)}` : "no claim yet"}</div>
        {says && <p className="mt-2 text-sm text-faint">It counts a donor's yes as done, without checking timing or whether staff confirmed anything.</p>}
      </div>

      <div className="mt-5 border-t border-line pt-5">
        <div className="text-sm font-bold uppercase tracking-wider text-muted">Actually ready at the deadline</div>
        <div className={`mt-1 text-4xl font-bold ${short ? "text-danger" : truth ? "text-accent" : ""}`}>
          {truth ? `${truth.units_ready} of ${truth.units}` : "—"}
        </div>
        <div className={short ? "font-semibold text-danger" : "text-muted"}>
          {truth ? (short ? "short of what it claimed" : "every unit") : `known at ${when(deadline, now)}`}
        </div>
      </div>

      <p className="mt-5 border-t border-line pt-5 text-muted">
        Found in stock <span className="font-semibold text-text">{view.found_units} of {units}</span> · donors messaged{" "}
        <span className="font-semibold text-text">{view.donors_messaged}</span>
      </p>

      <ol className="mt-4 space-y-1.5 text-muted">
        {view.timeline.length === 0 ? <li>Nothing yet.</li> : view.timeline.map((line, i) => <li key={i}>{line}</li>)}
      </ol>
    </div>
  );
}
