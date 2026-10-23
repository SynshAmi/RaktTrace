import type { Decision } from "../api";
import { groupsInText, pct, requestStatus, when } from "../format";

const consequential = (d: Decision) => d.actions.length > 0;

function Line({ d, now }: { d: Decision; now: string }) {
  return (
    <li className={`grid grid-cols-[4.5rem_1fr] gap-x-4 py-2 ${consequential(d) ? "" : "text-faint"}`}>
      <span className="text-muted">{when(d.at, now)}</span>
      <span>
        <span className="text-muted">{groupsInText(d.trigger)}.</span> {groupsInText(d.summary)}
      </span>
    </li>
  );
}

/** The latest decision that did something, in full; earlier ones on demand. The planner's own sentences, unedited. */
export default function DecisionLog({ decisions, now }: { decisions: Decision[]; now: string }) {
  const latest = [...decisions].reverse().find(consequential);
  const newestFirst = [...decisions].reverse();
  const changed = latest && latest.status !== (decisions[decisions.indexOf(latest) - 1]?.status ?? latest.status);

  return (
    <div className="max-w-4xl">
      <h3 className="text-sm font-bold uppercase tracking-wider text-muted">Latest planner decision</h3>
      {!latest ? (
        <p className="mt-3 text-muted">No decisions yet.</p>
      ) : (
        <div className="mt-3 border-l-4 border-mark pl-4">
          <div className="text-muted">
            {when(latest.at, now)} · because: <span className="text-text">{groupsInText(latest.trigger)}</span>
          </div>
          <p className="mt-1 text-xl leading-snug">{groupsInText(latest.summary)}</p>
          <div className="mt-2 text-sm text-muted">
            Estimated chance {pct(latest.p_before)} → {pct(latest.p_after)}
            {changed && ` · status now ${requestStatus[latest.status].label}`}
          </div>
        </div>
      )}

      {decisions.length > 1 && (
        <details className="mt-5">
          <summary className="cursor-pointer text-muted hover:text-text">
            Every decision so far ({decisions.length}), newest first
          </summary>
          <ol className="mt-2 max-h-96 divide-y divide-line overflow-y-auto pr-2">
            {newestFirst.map((d) => (
              <Line key={d.id} d={d} now={now} />
            ))}
          </ol>
        </details>
      )}
    </div>
  );
}
