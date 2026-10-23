import { useState } from "react";
import { api, type RequestSummary, type RequestView as View } from "../api";
import Baseline from "../components/Baseline";
import DecisionLog from "../components/DecisionLog";
import Gauge from "../components/Gauge";
import Ladder from "../components/Ladder";
import Lane from "../components/Lane";
import Supply from "../components/Supply";
import { groupLabel, pct, productLabel, requestStatus, timeLeft, when } from "../format";
import { usePoll } from "../usePoll";

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
      return `Every unit is reserved or collected in time. Waiting for blood-centre staff to confirm ${
        v.units - confirmed} more unit${v.units - confirmed === 1 ? "" : "s"} ready.`;
    case "FULFILLED":
      return "Blood-centre staff confirmed every unit ready for the patient.";
    case "FAILED":
      return "The deadline passed without enough units confirmed ready.";
    case "CANCELLED":
      return "Cancelled by the coordinator.";
  }
}

function readBaselineOpen() {
  try {
    return localStorage.getItem("rakt.baseline") === "open";
  } catch {
    return false;
  }
}

type Props = { id: string; requests: RequestSummary[]; onPick: (id: string) => void; version: number; paused: boolean };

export default function RequestView({ id, requests, onPick, version, paused }: Props) {
  const view = usePoll(() => api.request(id), id, version, undefined, paused);
  const decisions = usePoll(() => api.decisions(id), id, version, undefined, paused);
  const baseline = usePoll(() => api.baseline(id), id, version, undefined, paused);
  const [compare, setCompare] = useState(readBaselineOpen);

  const toggleCompare = (open: boolean) => {
    setCompare(open);
    try {
      localStorage.setItem("rakt.baseline", open ? "open" : "closed");
    } catch {
      /* per-viewer convenience only */
    }
  };

  const v = view.data;
  if (!v) return <p className="px-6 py-10 text-muted">{view.error ?? "Loading the request…"}</p>;

  const left = timeLeft(v.deadline_at, v.now);
  const status = requestStatus[v.status];
  const ladder = v.units_ladder;

  return (
    <main className="mx-auto max-w-[1600px] px-6 pb-16">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-line py-5 text-lg">
        {requests.length > 1 ? (
          <select value={id} onChange={(e) => onPick(e.target.value)} className="bg-bg font-semibold" aria-label="Request">
            {requests.map((r) => (
              <option key={r.id} value={r.id}>{r.id}</option>
            ))}
          </select>
        ) : (
          <span className="font-semibold">{v.id}</span>
        )}
        <span className="text-faint">·</span>
        <span>{groupLabel(v.group)} {productLabel(v.product)}</span>
        <span className="text-faint">·</span>
        <span>{v.units} unit{v.units === 1 ? "" : "s"}</span>
        <span className="text-faint">·</span>
        <span>{v.hospital.name}, {v.hospital.area}</span>
        {v.collection_centre && <span className="text-muted">· collecting at {v.collection_centre.name}</span>}
        <span className="ml-auto font-semibold">
          Deadline {when(v.deadline_at, v.now)}
          <span className={`ml-2 font-normal ${left ? "text-neu" : "text-text"}`}>{left ?? "· passed"}</span>
        </span>
      </div>
      {view.error && <p className="mt-3 text-sm text-neg">Couldn't refresh: {view.error}</p>}

      <div className={`mt-8 grid gap-10 ${compare ? "lg:grid-cols-[minmax(0,7fr)_minmax(0,3fr)]" : "lg:grid-cols-[minmax(0,1fr)_14rem]"}`}>
        <Lane title="RaktTrace" status={status.label} tone={status.tone} detail={detail(v)}>
          <div className="grid gap-8 md:grid-cols-[auto_1fr] md:items-end">
            <div className="pr-6 md:border-r md:border-line">
              <div className={`text-6xl font-semibold leading-none ${ladder.confirmed >= v.units ? "text-pos" : ""}`}>
                {ladder.confirmed} of {v.units}
              </div>
              <div className="mt-2 text-muted">confirmed ready by staff</div>
            </div>
            <Gauge p={v.p} pFirm={v.p_firm} target={v.target} units={v.units} />
          </div>

          <Ladder
            steps={[
              { label: "Found in stock", value: ladder.found, of: v.units },
              { label: "Donor said yes", value: ladder.said_yes, of: v.units },
              { label: "Can be ready in time", value: ladder.ready_in_time, of: v.units },
              { label: "Collected or reserved", value: ladder.collected_or_reserved, of: v.units },
              { label: "Confirmed by staff", value: ladder.confirmed, of: v.units },
            ]}
          />

          {decisions.data && <DecisionLog decisions={decisions.data} now={v.now} />}

          <Supply donors={v.donors} stock={v.stock} now={v.now} />
        </Lane>

        <aside className="lg:border-l lg:border-line lg:pl-8">
          {compare ? (
            <Baseline view={baseline.data} units={v.units} onHide={() => toggleCompare(false)} />
          ) : (
            <button
              onClick={() => toggleCompare(true)}
              className="w-full rounded border border-line p-4 text-left hover:border-neu"
            >
              <div className="text-lg">Today's workflow</div>
              <div className="mt-1 text-sm text-muted">
                See what today's process claims for this same request, and what was really ready.
              </div>
              <div className="mt-3 text-neu">Compare →</div>
            </button>
          )}
        </aside>
      </div>
    </main>
  );
}
