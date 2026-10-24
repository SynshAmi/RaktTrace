import type { RequestView } from "../api";
import { supply, units, type UnitState } from "../workflow";

const MARK: Record<UnitState, string> = {
  ready: "bg-success border-success",
  arranged: "border-caution bg-[linear-gradient(90deg,var(--caution)_50%,transparent_50%)]",
  at_centre: "border-text bg-[linear-gradient(90deg,var(--text)_50%,transparent_50%)]",
  committed: "border-text",
  missing: "border-faint",
};
const WORD: Record<UnitState, string> = { ready: "text-success", arranged: "text-caution", at_centre: "", committed: "", missing: "text-faint" };

function Figure({ label, value, note, tone = "" }: { label: string; value: number; note: string; tone?: string }) {
  return (
    <div>
      <dt className="text-sm font-bold uppercase tracking-wider text-muted">{label}</dt>
      <dd className={`text-4xl font-bold leading-tight ${tone}`}>{value}</dd>
      <dd className="text-sm text-faint">{note}</dd>
    </div>
  );
}

/** Required, arranged (reserved or collected), ready (staff confirmed) and the gap: the request's whole need. */
export function Figures({ v }: { v: RequestView }) {
  const s = supply(v);
  return (
    <dl className="grid grid-cols-4 gap-x-4" aria-label="Units">
      <Figure label="Required" value={s.required} note="asked for" />
      <Figure label="Arranged" value={s.arranged} note="reserved or collected" tone={s.arranged > s.ready ? "text-caution" : ""} />
      <Figure label="Ready" value={s.ready} note="staff confirmed" tone={s.ready > 0 ? "text-success" : ""} />
      <Figure label="Gap" value={s.gap} note="still to arrange" tone={s.gap > 0 ? "text-danger" : ""} />
    </dl>
  );
}

/** Where each required unit stands, from the request's own holds and pledges. Only staff confirmation is ready. */
export function UnitRows({ v }: { v: RequestView }) {
  return (
    <ol className="space-y-1" aria-label="Each required unit">
      {units(v).map((u, i) => (
        <li key={i} className="flex items-center gap-2.5">
          <span className={`inline-block h-3.5 w-3.5 shrink-0 rounded-full border-2 ${MARK[u.state]}`} aria-hidden />
          <span>
            <span className="text-muted">Unit {i + 1} of {v.units}:</span>{" "}
            <span className={`font-semibold ${WORD[u.state]}`}>{u.label}</span>
            {u.source && <span className="text-muted"> · {u.source}</span>}
          </span>
        </li>
      ))}
    </ol>
  );
}
