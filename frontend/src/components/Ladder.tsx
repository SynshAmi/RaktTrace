export type Step = { label: string; value: number | null; of: number; pending?: string; claim?: boolean };

const covered = (s: Step) => s.value !== null && s.value >= s.of;

/** Unit ladder: one dot per step, filled when the step covers every unit; "now" marks the step after the furthest one reached. */
export default function Ladder({ steps }: { steps: Step[] }) {
  const furthest = steps.map(covered).lastIndexOf(true);
  const current = furthest + 1 < steps.length ? furthest + 1 : -1;
  return (
    <ol className="flex flex-wrap gap-x-8 gap-y-4">
      {steps.map((s, i) => {
        const done = s.value !== null && s.value >= s.of;
        const partial = s.value !== null && s.value > 0 && !done;
        const dot = done && !s.claim ? "bg-pos border-pos" : done ? "bg-neu border-neu" : partial ? "bg-neu border-neu" : "border-faint";
        return (
          <li key={s.label} className="min-w-24">
            <div className="flex items-center gap-2">
              <span className={`inline-block h-3.5 w-3.5 rounded-full border-2 ${dot}`} aria-hidden />
              {i === current && <span className="text-xs text-neu">now</span>}
            </div>
            <div className={`mt-2 ${done || partial ? "text-text" : "text-muted"}`}>{s.label}</div>
            <div className="text-sm text-muted">
              {s.value === null ? s.pending ?? "not yet" : `${s.value} of ${s.of}`}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
