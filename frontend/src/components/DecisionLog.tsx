import type { Decision } from "../api";
import { groupsInText, pct, requestStatus, when } from "../format";
import { severity, type Severity } from "../notify";

const RULE: Record<Severity, string> = {
  routine: "border-line-strong", escalation: "border-danger", fulfilled: "border-success", failed: "border-danger",
};
const KICKER: Record<Severity, string> = {
  routine: "text-muted", escalation: "text-danger", fulfilled: "text-success", failed: "text-danger",
};

function Line({ d, now }: { d: Decision; now: string }) {
  return (
    <li className={`grid grid-cols-[4.5rem_1fr] gap-x-4 py-1.5 ${d.actions.length ? "" : "text-muted"}`}>
      <span className="text-muted">{when(d.at, now)}</span>
      <span>
        <span className="font-semibold">{groupsInText(d.trigger)}.</span> {groupsInText(d.summary)}
      </span>
    </li>
  );
}

/** The latest event in brief, then every decision so far. The planner's own sentences, unedited; the log is the
 *  record, the notifications only point at it. */
export default function DecisionLog({ decisions, now }: { decisions: Decision[]; now: string }) {
  if (decisions.length === 0) return <p className="text-muted">No decisions yet.</p>;
  const latest = decisions[decisions.length - 1];
  const previous = decisions[decisions.length - 2];
  const sev = severity(latest, previous);
  const changed = previous !== undefined && latest.status !== previous.status;
  const moved = Math.round(latest.p_before * 100) !== Math.round(latest.p_after * 100);

  return (
    <div className="max-w-4xl">
      <div className={`border-l-4 pl-4 ${RULE[sev]}`} aria-live="polite">
        <div className={`text-xs font-bold uppercase tracking-wider ${KICKER[sev]}`}>
          Latest decision · {when(latest.at, now)}
        </div>
        <div className="mt-0.5 text-lg font-bold leading-snug">{groupsInText(latest.trigger)}</div>
        <p className="leading-snug">{groupsInText(latest.summary)}</p>
        {(changed || moved) && (
          <div className="mt-1 text-sm text-muted">
            {moved && `Estimated chance ${pct(latest.p_before)} → ${pct(latest.p_after)}`}
            {moved && changed && " · "}
            {changed && `status now ${requestStatus[latest.status].label}`}
          </div>
        )}
      </div>

      <h4 className="mt-5 text-xs font-bold uppercase tracking-wider text-muted">
        All decisions ({decisions.length}), newest first
      </h4>
      <ol className="mt-1 max-h-80 divide-y divide-line overflow-y-auto pr-2">
        {[...decisions].reverse().map((d) => (
          <Line key={d.id} d={d} now={now} />
        ))}
      </ol>
    </div>
  );
}
