import type { Decision, RequestView } from "../api";
import { pct, when } from "../format";
import { band, lastChange, type Band, type Trend } from "../workflow";

// Display bands only (≥ 90 green, 70–89 amber, < 70 red); the planner never reads them.
const BAND_TEXT: Record<Band, string> = { good: "text-success", watch: "text-caution", risk: "text-danger" };
const BAND_FILL: Record<Band, string> = { good: "bg-success", watch: "bg-caution", risk: "bg-danger" };
const ARROW: Record<Trend, string> = { up: "▲", down: "▼", steady: "■" };

/** P in the summary strip: the estimate, its band colour and the direction of its last move. */
export function Chance({ v, trend, from }: { v: RequestView; trend: Trend; from: number | null }) {
  const subject = v.units === 1 ? "the unit is" : `all ${v.units} are`;
  return (
    <div>
      <div className="text-xs font-bold uppercase tracking-wider text-muted">Estimated chance</div>
      <div className="flex items-baseline gap-2">
        <span className={`text-4xl font-bold leading-tight ${BAND_TEXT[band(v.p)]}`}>{pct(v.p)}</span>
        <span className="text-sm font-semibold text-muted" title="Direction of the last change in the estimate">
          <span aria-hidden>{ARROW[trend]}</span> {trend === "steady" ? "steady" : `${trend === "up" ? "up" : "down"} from ${pct(from ?? v.p)}`}
        </span>
      </div>
      <div className="text-xs text-faint">that {subject} ready by {when(v.deadline_at, v.now)} · an estimate, not a result</div>
    </div>
  );
}

/** The estimate's detail: the bar with the 90% line, the firm chance and what last moved it. */
export default function Gauge({ v, decisions, closed }: { v: RequestView; decisions: Decision[]; closed: boolean }) {
  const change = lastChange(decisions);
  const drifted = change && Math.round(v.p * 100) !== Math.round(change.p_after * 100);
  return (
    <div>
      <div className="relative h-2.5 rounded-full bg-line" aria-hidden>
        <div className={`h-2.5 rounded-full transition-[width] duration-500 ${BAND_FILL[band(v.p)]}`} style={{ width: `${Math.round(v.p * 100)}%` }} />
        <div className="absolute -top-1.5 h-5.5 w-1 rounded bg-target" style={{ left: `calc(${v.target * 100}% - 2px)` }} />
      </div>
      <div className="relative mt-1 h-5 text-xs font-semibold">
        <span className="absolute translate-x-1/2 whitespace-nowrap" style={{ right: `${(1 - v.target) * 100}%` }}>
          {pct(v.target)} target
        </span>
      </div>
      <p className="mt-2 text-sm text-muted">
        <span className="font-semibold text-text">Firm chance {pct(v.p_firm)}</span>: counting only reserved stock and donors who said yes.
      </p>
      {change && (
        <p className="mt-1 text-sm text-muted">
          <span className="font-semibold text-text">Last change {pct(change.p_before)} → {pct(change.p_after)}</span> at{" "}
          {when(change.at, v.now)}, after: {change.trigger}.
          {drifted && !closed && " Between decisions the estimate also moves as time passes."}
        </p>
      )}
      <p className="mt-2 text-xs text-faint">
        {closed ? "The request is closed, so this is no longer a forecast." : "A high estimate isn't blood: only staff confirmation makes a unit ready."}
      </p>
    </div>
  );
}
