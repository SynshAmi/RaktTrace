import { useState } from "react";
import type { DonorRow, RequestView, StockRow } from "../api";
import { groupLabel, pct, statusWord, toneText, when, type Tone } from "../format";

// Only READY (staff confirmed) is positive; committed-but-unconfirmed states stay neutral.
const DONOR: Record<string, [string, Tone]> = {
  READY: ["Ready ✓", "pos"], ACTIVE: ["Going (active)", "neu"], ARRIVED: ["Arrived", "neu"],
  COLLECTED: ["Collected, awaiting staff", "neu"], STANDBY: ["Standby", "neu"],
  INVITED: ["Invited, no reply yet", "muted"], NO_REPLY: ["No reply", "muted"], DECLINED: ["Said no", "muted"],
  RELEASED: ["Stood down", "muted"], OPTED_OUT: ["Opted out", "muted"],
  TOO_LATE: ["Too late", "neg"], DEFERRED: ["Deferred", "neg"], NO_SHOW: ["No-show", "neg"], FAILED_TEST: ["Failed testing", "neg"],
};
const STOCK: Record<string, [string, Tone]> = {
  READY: ["Ready ✓", "pos"], RESERVED: ["Reserved, awaiting staff", "neu"], PENDING: ["Asked, waiting", "muted"],
  NONE: ["None available", "neg"], EXPIRED: ["No answer", "neg"], RELEASED: ["Released", "muted"],
};

function Status({ map, status }: { map: Record<string, [string, Tone]>; status: string }) {
  const [word, tone] = map[status] ?? [statusWord(status), "muted" as Tone];
  return <span className={toneText[tone]}>{word}</span>;
}

function age(min: number) {
  return min < 90 ? `${min} min old` : `${Math.round(min / 60)} h old`;
}

function Donors({ donors, now }: { donors: DonorRow[]; now: string }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-136 text-left">
        <thead className="text-sm text-muted">
          <tr>
            <th className="py-2 font-normal">Donor</th>
            <th className="font-normal">Status</th>
            <th className="font-normal">Distance</th>
            <th className="font-normal">Chance</th>
            <th className="font-normal">Booking</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {donors.map((d) => (
            <tr key={d.pledge_id} className="align-top">
              <td className="py-2.5 pr-4">
                {d.name} <span className="text-muted">{groupLabel(d.group)}</span>
                {d.live && <span className="ml-2 rounded border border-accent px-1.5 text-xs text-accent">Live · Telegram</span>}
                {d.reply_text && (
                  <div className="text-sm text-muted">“{d.reply_text}”{d.read_by && ` · read by ${d.read_by}`}</div>
                )}
              </td>
              <td className="py-2.5 pr-4"><Status map={DONOR} status={d.status} /></td>
              <td className="py-2.5 pr-4">{d.km} km</td>
              <td className="py-2.5 pr-4">{pct(d.p)}</td>
              <td className="py-2.5">
                {d.booking_code ?? <span className="text-faint">—</span>}
                {d.ready_at && <div className="text-sm text-muted">ready {when(d.ready_at, now)}</div>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Stock({ stock }: { stock: StockRow[] }) {
  if (stock.length === 0) return <p className="text-muted">No blood centre asked.</p>;
  return (
    <ul className="divide-y divide-line">
      {stock.map((s) => (
        <li key={s.reservation_id} className="flex flex-wrap items-baseline justify-between gap-x-4 py-2">
          <span>
            {s.centre} <span className="text-sm text-muted">· listing {age(s.listed_age_min)} when asked</span>
          </span>
          <span>
            <Status map={STOCK} status={s.status} />
            <span className="text-muted"> · {s.units_reserved} of {s.units_asked} asked</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

function why(v: RequestView): string {
  if (Math.max(0, v.units - v.units_ladder.found) === 0) return "Not needed: stock covers every unit.";
  if (!v.flags.donors_can_help) return "None: a donated unit couldn't be tested in time.";
  if (v.flags.waiting_for_stock) return "None yet: waiting for blood centres to answer first.";
  return "None messaged yet.";
}

/** Donors and stock behind two tabs, closed by default so the main story stays short. */
export default function Supply({ v }: { v: RequestView }) {
  const [open, setOpen] = useState<"donors" | "stock" | null>(null);
  const c = v.counts;
  const tab = (id: "donors" | "stock", label: string) => (
    <button
      onClick={() => setOpen(open === id ? null : id)}
      aria-expanded={open === id}
      className={`border-b-4 pb-1 text-lg font-semibold ${open === id ? "border-mark text-text" : "border-transparent text-muted hover:text-text"}`}
    >
      {label}
    </button>
  );
  return (
    <div>
      <div className="flex flex-wrap items-baseline gap-x-8 gap-y-2">
        {tab("donors", `Donors (${v.donors.length})`)}
        {tab("stock", `Stock (${v.stock.length})`)}
        <span className="text-muted">
          {c.messaged === 0
            ? why(v)
            : `${c.messaged} messaged · ${c.yes} said yes · ${c.active} going or in · ${c.standby} on standby · ${c.no} said no · ${c.silent} no reply yet`}
        </span>
      </div>
      {open === "donors" && (
        <div className="mt-4">{v.donors.length ? <Donors donors={v.donors} now={v.now} /> : <p className="text-muted">{why(v)}</p>}</div>
      )}
      {open === "stock" && <div className="mt-4 max-w-4xl"><Stock stock={v.stock} /></div>}
    </div>
  );
}
