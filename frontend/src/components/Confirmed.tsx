import type { RequestView } from "../api";
import { awaitingStaff } from "../workflow";

const MARK = {
  ready: "bg-mark border-mark",
  awaiting: "border-text bg-[linear-gradient(90deg,var(--text)_50%,transparent_50%)]",
  missing: "border-faint",
};
const WORD = { ready: "ready ✓", awaiting: "reserved or collected, awaiting staff", missing: "not yet" };

/** Units staff confirmed ready, apart from the estimate: only this count is blood. */
export default function Confirmed({ v }: { v: RequestView }) {
  const n = v.units;
  const confirmed = Math.min(v.units_ladder.confirmed, n);
  const awaiting = awaitingStaff(v);
  const done = confirmed >= n;
  return (
    <div>
      <div className={`text-7xl font-bold leading-none tracking-tight ${done ? "text-accent" : ""}`}>
        {confirmed} of {n}
      </div>
      <div className="mt-2 text-lg font-semibold">confirmed ready by blood-centre staff</div>
      <ul className="mt-4 space-y-1.5">
        {Array.from({ length: n }, (_, i) => {
          const state = i < confirmed ? "ready" : i < confirmed + awaiting ? "awaiting" : "missing";
          return (
            <li key={i} className="flex items-center gap-2.5">
              <span className={`inline-block h-3.5 w-3.5 rounded-full border-2 ${MARK[state]}`} aria-hidden />
              <span className={state === "missing" ? "text-faint" : ""}>Unit {i + 1}: {WORD[state]}</span>
            </li>
          );
        })}
      </ul>
      {!done && <p className="mt-3 max-w-sm text-muted">Nothing counts until blood-centre staff confirm a unit ready.</p>}
    </div>
  );
}
