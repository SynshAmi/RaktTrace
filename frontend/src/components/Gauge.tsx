import type { Decision, RequestView } from "../api";
import { pct, when } from "../format";
import { lastChange } from "../workflow";

/** P: an estimate of the chance every unit is ready by the deadline. Never coloured as success. */
export default function Gauge({ v, decisions, closed }: { v: RequestView; decisions: Decision[]; closed: boolean }) {
  const subject = v.units === 1 ? "the unit is" : `all ${v.units} units are`;
  const change = lastChange(decisions);
  const drifted = change && Math.round(v.p * 100) !== Math.round(change.p_after * 100);
  const awaitingStaff = v.units_ladder.confirmed < v.units;
  return (
    <div className="max-w-2xl">
      <div className="flex flex-wrap items-baseline gap-x-4">
        <span className="text-7xl font-bold leading-none tracking-tight">{pct(v.p)}</span>
        <span className="text-lg font-semibold">estimated chance {subject} ready by {when(v.deadline_at, v.now)}</span>
      </div>

      <div className="relative mt-5 h-3 rounded-full bg-line" aria-hidden>
        <div className="h-3 rounded-full bg-gauge transition-[width] duration-500" style={{ width: `${Math.round(v.p * 100)}%` }} />
        <div className="absolute -top-1.5 h-6 w-1 rounded bg-target" style={{ left: `calc(${v.target * 100}% - 2px)` }} />
      </div>
      <div className="relative mt-1.5 h-5 text-sm font-semibold">
        <span className="absolute translate-x-1/2 whitespace-nowrap" style={{ right: `${(1 - v.target) * 100}%` }}>
          {pct(v.target)} target
        </span>
      </div>

      <p className="mt-4 text-muted">
        <span className="font-semibold text-text">Firm chance {pct(v.p_firm)}</span>: counting only reserved stock and donors who said yes.
      </p>
      {change && (
        <p className="mt-1.5 text-muted">
          <span className="font-semibold text-text">Last change {pct(change.p_before)} → {pct(change.p_after)}</span> at{" "}
          {when(change.at, v.now)}, after: {change.trigger}.
          {drifted && !closed && ` Now ${pct(v.p)}: between decisions the estimate also moves as time passes.`}
        </p>
      )}
      {closed ? (
        <p className="mt-3 text-sm text-faint">The request is closed, so this is no longer a forecast.</p>
      ) : (
        v.p >= v.target && awaitingStaff && (
          <p className="mt-3 text-sm text-faint">
            A high estimate isn't blood: it is how likely the planned stock and donors are to come through.
          </p>
        )
      )}
    </div>
  );
}
