import { pct } from "../format";

type Props = { p: number; pFirm: number; target: number; units: number };

/** P: the estimated chance that enough units are ready by the deadline, with the target line. */
export default function Gauge({ p, pFirm, target, units }: Props) {
  // An estimate, not an outcome: it never gets the positive colour.
  return (
    <div>
      <div className="flex items-baseline gap-3">
        <span className="text-6xl font-semibold leading-none">{pct(p)}</span>
        <span className="text-muted">
          estimated chance {units === 1 ? "the unit is" : `all ${units} units are`} ready by the deadline
        </span>
      </div>
      <div className="relative mt-4 h-2 max-w-xl rounded-full bg-line" aria-hidden>
        <div
          className="h-2 rounded-full bg-neu transition-[width] duration-500"
          style={{ width: `${Math.round(p * 100)}%` }}
        />
        <div className="absolute -top-1.5 h-5 w-0.5 bg-text" style={{ left: `${target * 100}%` }} />
      </div>
      <div className="mt-2 flex max-w-xl justify-between text-sm text-muted">
        <span>Firm chance, counting only reserved stock and donors who said yes: {pct(pFirm)}</span>
        <span>{pct(target)} target</span>
      </div>
    </div>
  );
}
