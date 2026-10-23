import type { BaselineView } from "../api";
import { hhmm } from "../format";
import Ladder from "./Ladder";
import Lane from "./Lane";

/** Today's workflow: the same request run the way it's done today (simulated), for comparison only. */
export default function Baseline({ view, units, onHide }: { view: BaselineView | null; units: number; onHide: () => void }) {
  if (!view) return <p className="text-muted">Loading today's workflow…</p>;
  const truth = view.truth_at_deadline;
  const says = view.status === "SAYS_FULFILLED";
  const fullyReady = truth !== null && truth.units_ready >= truth.units;
  return (
    <div>
      <button onClick={onHide} className="float-right text-sm text-muted underline-offset-2 hover:text-text hover:underline">
        Hide
      </button>
      <Lane
        title="Today's workflow"
        note="comparison"
        status={says ? "Says fulfilled" : "Searching"}
        tone="neu"
        detail={says && view.said_fulfilled_at ? `Claimed at ${hhmm(view.said_fulfilled_at)}, without checking timing or readiness` : undefined}
      >
        {truth ? (
          <div>
            <div className={`text-5xl font-semibold ${fullyReady ? "text-pos" : "text-neg"}`}>
              {truth.units_ready} of {truth.units}
            </div>
            <div className="mt-1 text-muted">units actually ready at the deadline</div>
          </div>
        ) : (
          <div>
            <div className="text-5xl font-semibold">{view.donors_messaged}</div>
            <div className="mt-1 text-muted">donors messaged · what was really ready shows at the deadline</div>
          </div>
        )}
        <Ladder
          steps={[
            { label: "Found", value: view.found_units, of: units },
            { label: "Said fulfilled", value: says ? 1 : null, of: 1, pending: "not yet", claim: true },
            { label: "Actually ready", value: truth ? truth.units_ready : null, of: units, pending: "at the deadline" },
          ]}
        />
        <ol className="space-y-2 text-muted">
          {view.timeline.map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ol>
      </Lane>
    </div>
  );
}
