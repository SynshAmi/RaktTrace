import { useRef, useState } from "react";
import { api, type RequestSummary, type RequestView as View } from "../api";
import Baseline from "../components/Baseline";
import { Figures, UnitRows } from "../components/Confirmed";
import Gauge, { Chance } from "../components/Gauge";
import Ladder from "../components/Ladder";
import Notifications from "../components/Notifications";
import Supply from "../components/Supply";
import { baselineStatus, groupLabel, hhmm, pct, productLabel, requestStatus, timeLeft, toneText, when } from "../format";
import { usePoll } from "../usePoll";
import { trend as trendOf } from "../workflow";

/** A plain sentence for where the request stands, read only from the API's status, ladder and flags. */
function detail(v: View): string {
  const { confirmed } = v.units_ladder;
  switch (v.status) {
    case "OPEN":
      if (v.flags.waiting_for_stock) return "Waiting for blood centres to answer before contacting any donor.";
      if (!v.flags.donors_can_help) return "A donated unit couldn't be tested in time, so only stock can help.";
      return `Below the ${pct(v.target)} target. Still working on the gap.`;
    case "COVERED":
      return `Enough committed stock and donors to clear the ${pct(v.target)} target. Nothing counts until staff confirm.`;
    case "SECURED":
      return `Secured, not yet ready: every unit is reserved or collected in time. Waiting for blood-centre staff to confirm ${
        v.units - confirmed} more unit${v.units - confirmed === 1 ? "" : "s"} ready.`;
    case "FULFILLED":
      return `All ${v.units} required unit${v.units === 1 ? "" : "s"} confirmed ready by blood-centre staff.`;
    case "FAILED":
      return "The deadline passed without enough units confirmed ready.";
    case "CANCELLED":
      return "Cancelled by the coordinator.";
  }
}

const ESCALATION = ["", "Escalation level 1: the search radius was widened.", "Escalation level 2: the coordinator was alerted."];

function readBaselineOpen() {
  try {
    return localStorage.getItem("rakt.baseline") === "open";
  } catch {
    return false;
  }
}

type Props = {
  id: string; requests: RequestSummary[]; onPick: (id: string) => void; version: number; paused: boolean;
  run: number; activity: string;
};

export default function RequestView({ id, requests, onPick, version, paused, run, activity }: Props) {
  const view = usePoll(() => api.request(id), id, version, undefined, paused);
  const decisions = usePoll(() => api.decisions(id), id, version, undefined, paused);
  const baseline = usePoll(() => api.baseline(id), id, version, undefined, paused);
  const [compare, setCompare] = useState(readBaselineOpen);
  // The last two distinct shown values of P in this run, for the trend arrow.
  const moves = useRef<{ key: string; last: number | null; previous: number | null }>({ key: "", last: null, previous: null });

  const toggleCompare = (open: boolean) => {
    setCompare(open);
    try {
      localStorage.setItem("rakt.baseline", open ? "open" : "closed");
    } catch {
      /* per-viewer convenience only */
    }
  };

  const v = view.data;
  if (!v) return <p className="px-4 py-10 text-muted sm:px-6">{view.error ?? "Loading the request…"}</p>;

  const left = timeLeft(v.deadline_at, v.now);
  const status = requestStatus[v.status];
  const closed = ["FULFILLED", "FAILED", "CANCELLED"].includes(v.status);
  const b = baseline.data;
  const key = `${v.id}:${run}`;  // the data's own id: a stale view from before a switch never seeds the trend
  if (moves.current.key !== key) moves.current = { key, last: v.p, previous: null };
  else if (Math.round(v.p * 100) !== Math.round((moves.current.last ?? v.p) * 100)) {
    moves.current = { key, last: v.p, previous: moves.current.last };
  }
  const direction = trendOf(moves.current.previous, moves.current.last ?? v.p);

  return (
    <main className="mx-auto max-w-420 px-4 pb-16 sm:px-6">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-line py-5 text-lg">
        {requests.length > 1 ? (
          <select value={id} onChange={(e) => onPick(e.target.value)} aria-label="Request"
            className="rounded-md border border-line-strong bg-bg px-2 py-1 font-bold">
            {requests.map((r) => (
              <option key={r.id} value={r.id}>{r.id} · {requestStatus[r.status].label}</option>
            ))}
          </select>
        ) : (
          <span className="font-bold">{v.id}</span>
        )}
        <span className="text-faint" aria-hidden>·</span>
        <span className="font-bold text-accent">{groupLabel(v.group)} {productLabel(v.product)}</span>
        <span className="text-faint" aria-hidden>·</span>
        <span>{v.units} unit{v.units === 1 ? "" : "s"}</span>
        <span className="text-faint" aria-hidden>·</span>
        <span>{v.hospital.name}, {v.hospital.area}</span>
        {v.collection_centre && (
          <span className="text-muted" title={v.collection_centre.staff === "simulated"
            ? "No staff phone is linked, so simulated staff answer this centre's cards (marked \"simulated staff\" in the log)"
            : "This centre's cards go to its linked Telegram staff"}>
            · collecting at {v.collection_centre.name} ({v.collection_centre.staff === "simulated" ? "simulated staff" : "staff on Telegram"})
          </span>
        )}
        <span className="ml-auto font-bold">
          Deadline {when(v.deadline_at, v.now)}
          <span className={`ml-2 ${left ? "text-accent" : "text-danger"}`}>{left ?? "passed"}</span>
        </span>
      </div>
      {view.error && <p className="mt-3 text-base text-danger">Couldn't refresh: {view.error}</p>}

      <div className={`mt-8 grid gap-10 ${compare ? "xl:grid-cols-[minmax(0,7fr)_minmax(20rem,3fr)]" : "xl:grid-cols-[minmax(0,1fr)_17rem]"}`}>
        <section aria-label="RaktTrace" className="@container">
          <div className="grid gap-x-8 gap-y-5 border-b border-line pb-6 @4xl:grid-cols-[minmax(17rem,1fr)_auto_auto]">
            <div>
              <h2 className="text-sm font-bold uppercase tracking-wider text-muted">
                RaktTrace · <span className={toneText[status.tone]}>{v.status}</span>
              </h2>
              <div className={`flex items-center gap-2 text-3xl font-bold tracking-tight ${toneText[status.tone]}`}>
                <span aria-hidden className="text-2xl">{status.icon}</span>
                {status.label}
              </div>
              <p className="mt-1.5 max-w-2xl text-muted">{detail(v)}</p>
            </div>
            <Figures v={v} />
            <Chance v={v} trend={direction} from={moves.current.previous} />
          </div>
          {v.escalation.level > 0 && (
            <p className="mt-4 inline-flex items-center gap-2 rounded border-2 border-danger px-3 py-1 font-semibold text-danger">
              <span aria-hidden>!</span>
              {ESCALATION[v.escalation.level] ?? `Escalation level ${v.escalation.level}.`}
            </p>
          )}

          <div className="space-y-8 border-b border-line py-6">
            <div>
              <h3 className="mb-2 text-sm font-bold uppercase tracking-wider text-muted">Units</h3>
              <UnitRows v={v} />
            </div>
            <div>
              <h3 className="mb-3 text-sm font-bold uppercase tracking-wider text-muted">Estimate</h3>
              <Gauge v={v} decisions={decisions.data ?? []} closed={closed} />
            </div>
          </div>

          <div className="pt-6">
            <Supply v={v} decisions={decisions.data ?? []} version={version} paused={paused} />
          </div>
          <div className="mt-8 border-t border-line pt-6">
            <Ladder v={v} />
          </div>
          <Notifications requestId={id} run={run} decisions={decisions.data} label={activity} />
        </section>

        <aside aria-label="Today's workflow comparison" className="border-t border-line pt-8 xl:border-t-0 xl:border-l-2 xl:pt-0 xl:pl-8">
          {compare ? (
            <Baseline view={b} units={v.units} deadline={v.deadline_at} now={v.now} onHide={() => toggleCompare(false)} />
          ) : (
            <div>
              <h2 className="text-base font-bold uppercase tracking-wider text-muted">Today's workflow</h2>
              {b && (
                <div className="mt-2 text-2xl font-bold">
                  {b.status === "SAYS_FULFILLED" && b.said_fulfilled_at
                    ? `Claims “fulfilled” since ${hhmm(b.said_fulfilled_at)}`
                    : baselineStatus[b.status]}
                </div>
              )}
              <p className="mt-2 text-muted">What today's process claims for this same request, and what was really ready.</p>
              <button
                onClick={() => toggleCompare(true)}
                aria-expanded={false}
                className="mt-4 rounded-md border-2 border-text px-3 py-1.5 font-semibold hover:bg-text hover:text-bg"
              >
                Show comparison →
              </button>
            </div>
          )}
        </aside>
      </div>
    </main>
  );
}
