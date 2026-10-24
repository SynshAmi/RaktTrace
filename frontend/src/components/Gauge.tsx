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
      <div className="text-sm font-bold uppercase tracking-wider text-muted">Estimated chance</div>
      <div className="flex items-baseline gap-2">
        <span className={`text-4xl font-bold leading-tight ${BAND_TEXT[band(v.p)]}`}>{pct(v.p)}</span>
        <span className="text-base font-semibold text-muted" title="Direction of the last change in the estimate">
          <span aria-hidden>{ARROW[trend]}</span> {trend === "steady" ? "steady" : `${trend === "up" ? "up" : "down"} from ${pct(from ?? v.p)}`}
        </span>
      </div>
      <div className="text-sm text-faint">that {subject} ready by {when(v.deadline_at, v.now)} · an estimate, not a result</div>
    </div>
  );
}

/** The estimate's detail: the bar with the 90% line, the firm chance and what last moved it. */
export default function Gauge({ v, decisions, closed }: { v: RequestView; decisions: Decision[]; closed: boolean }) {
  const change = lastChange(decisions);
  const drifted = change && Math.round(v.p * 100) !== Math.round(change.p_after * 100);
  return (
    <div>
      <div className="relative h-4 rounded-full bg-line" aria-hidden>
        <div className={`h-4 rounded-full transition-[width] duration-500 ${BAND_FILL[band(v.p)]}`} style={{ width: `${Math.round(v.p * 100)}%` }} />
        <div className="absolute -top-1.5 h-7 w-1 rounded bg-target" style={{ left: `calc(${v.target * 100}% - 2px)` }} />
      </div>
      <div className="relative mt-1.5 h-6 text-base font-semibold">
        <span className="absolute translate-x-1/2 whitespace-nowrap" style={{ right: `${(1 - v.target) * 100}%` }}>
          {pct(v.target)} target
        </span>
      </div>
      <div className="mt-4 grid gap-4 @3xl:grid-cols-2">
        <div className="rounded-lg border border-line bg-raise p-4">
          <div className="text-sm font-bold uppercase tracking-wider text-muted">Firm chance</div>
          <div className="mt-1 text-3xl font-bold">{pct(v.p_firm)}</div>
          <p className="mt-1 text-base text-muted">Counting only reserved stock and donors who said yes in time.</p>
        </div>
        {change && (
          <div className="rounded-lg border border-line bg-raise p-4">
            <div className="text-sm font-bold uppercase tracking-wider text-muted">Last change</div>
            <div className="mt-1 text-3xl font-bold">{pct(change.p_before)} → {pct(change.p_after)}</div>
            <p className="mt-1 text-base text-muted">
              At {when(change.at, v.now)}, after: {change.trigger}.
              {drifted && !closed && " Between decisions the estimate also moves as time passes."}
            </p>
          </div>
        )}
      </div>
      <p className="mt-3 text-base text-faint">
        {closed ? "The request is closed, so this is no longer a forecast." : "A high estimate isn't blood: only staff confirmation makes a unit ready."}
      </p>
    </div>
  );
}
