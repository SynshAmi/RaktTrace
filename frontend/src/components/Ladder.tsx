import type { RequestView } from "../api";
import { steps, type State } from "../workflow";

function Dot({ state, ready }: { state: State; ready?: boolean }) {
  if (ready) return <span className="grid h-5 w-5 place-items-center rounded-full bg-mark text-xs font-bold text-on-mark">✓</span>;
  if (state === "blocked") return <span className="grid h-5 w-5 place-items-center rounded-full border-2 border-danger text-xs font-bold text-danger">!</span>;
  const look = {
    done: "bg-text border-text",
    partial: "border-text bg-[linear-gradient(90deg,var(--text)_50%,transparent_50%)]",
    todo: "border-faint",
    skip: "border-faint opacity-50",
  }[state];
  return <span className={`inline-block h-5 w-5 rounded-full border-2 ${look}`} />;
}

const STATE_WORD: Record<State, string> = { done: "done", partial: "partly", todo: "not yet", skip: "skipped", blocked: "blocked" };

/** The request's story in order: stock check → remaining gap → donor replies → timing → collected/reserved → staff. */
export default function Ladder({ v }: { v: RequestView }) {
  const all = steps(v);
  const current = all.findIndex((s) => s.state !== "done" && s.state !== "skip");
  return (
    <div>
      <h3 className="text-sm font-bold uppercase tracking-wider text-muted">How this request is moving · counts out of {v.units} required</h3>
      <ol className="mt-3 grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-3 @4xl:grid-cols-6">
        {all.map((s, i) => (
          <li key={s.label}>
            <div className="flex items-center gap-2">
              <Dot state={s.state} ready={s.ready} />
              <span className="sr-only">{STATE_WORD[s.state]}</span>
              {i === current && <span className="rounded bg-text px-1.5 text-xs font-bold text-bg">now</span>}
            </div>
            <div className={`mt-1.5 font-semibold ${s.state === "todo" || s.state === "skip" ? "text-faint" : ""}`}>
              {i + 1}. {s.label}
            </div>
            <div className={`${s.state === "blocked" ? "font-semibold text-danger" : "text-muted"}`}>{s.value}</div>
          </li>
        ))}
      </ol>
      <p className="mt-3 text-sm text-faint">Reserved or collected isn't ready. Only blood-centre staff confirming a unit makes it count.</p>
    </div>
  );
}
