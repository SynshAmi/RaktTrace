import { useState } from "react";
import type { DonorRow, StockRow } from "../api";
import { groupLabel, pct, statusWord, toneText, when, type Tone } from "../format";

const DONOR_TONE: Record<string, Tone> = {
  ACTIVE: "pos", ARRIVED: "pos", COLLECTED: "pos", READY: "pos",
  INVITED: "neu", STANDBY: "neu",
  TOO_LATE: "neg", DEFERRED: "neg", NO_SHOW: "neg", FAILED_TEST: "neg",
};
const STOCK_TONE: Record<string, Tone> = { RESERVED: "pos", READY: "pos", PENDING: "neu", NONE: "neg", EXPIRED: "neg" };
const STOCK_WORD: Record<string, string> = { NONE: "None available", EXPIRED: "No answer" };

const tone = (map: Record<string, Tone>, s: string) => toneText[map[s] ?? "muted"];

function age(min: number) {
  return min < 90 ? `${min} min old` : `${Math.round(min / 60)} h old`;
}

function Donors({ donors, now }: { donors: DonorRow[]; now: string }) {
  if (donors.length === 0) return <p className="text-muted">No donors messaged.</p>;
  return (
    <table className="w-full max-w-4xl text-left">
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
            <td className="py-3 pr-4">
              {d.name} <span className="text-muted">{groupLabel(d.group)}</span>
              {d.live && <span className="ml-2 rounded border border-neu px-1.5 text-xs text-neu">Live · Telegram</span>}
              {d.reply_text && (
                <div className="text-sm text-muted">
                  “{d.reply_text}”{d.read_by && ` · read by ${d.read_by}`}
                </div>
              )}
            </td>
            <td className={`py-3 pr-4 ${tone(DONOR_TONE, d.status)}`}>{statusWord(d.status)}</td>
            <td className="py-3 pr-4">{d.km} km</td>
            <td className="py-3 pr-4">{pct(d.p)}</td>
            <td className="py-3">
              {d.booking_code ?? <span className="text-faint">—</span>}
              {d.ready_at && <div className="text-sm text-muted">ready {when(d.ready_at, now)}</div>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Stock({ stock }: { stock: StockRow[] }) {
  if (stock.length === 0) return <p className="text-muted">No blood centres asked.</p>;
  return (
    <table className="w-full max-w-4xl text-left">
      <thead className="text-sm text-muted">
        <tr>
          <th className="py-2 font-normal">Centre</th>
          <th className="font-normal">Asked</th>
          <th className="font-normal">Reserved</th>
          <th className="font-normal">Status</th>
          <th className="font-normal">Listing when asked</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-line">
        {stock.map((s) => (
          <tr key={s.reservation_id}>
            <td className="py-3 pr-4">{s.centre}</td>
            <td className="py-3 pr-4">{s.units_asked}</td>
            <td className="py-3 pr-4">{s.units_reserved}</td>
            <td className={`py-3 pr-4 ${tone(STOCK_TONE, s.status)}`}>{STOCK_WORD[s.status] ?? statusWord(s.status)}</td>
            <td className="py-3">{age(s.listed_age_min)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Donors and stock behind two tabs, closed by default so the main story stays short. */
export default function Supply({ donors, stock, now }: { donors: DonorRow[]; stock: StockRow[]; now: string }) {
  const [open, setOpen] = useState<"donors" | "stock" | null>(null);
  const tab = (id: "donors" | "stock", label: string) => (
    <button
      onClick={() => setOpen(open === id ? null : id)}
      aria-expanded={open === id}
      className={`border-b-2 pb-1 text-lg ${open === id ? "border-text text-text" : "border-transparent text-muted hover:text-text"}`}
    >
      {label}
    </button>
  );
  return (
    <div>
      <div className="flex gap-8">
        {tab("donors", `Donors (${donors.length})`)}
        {tab("stock", `Stock (${stock.length})`)}
      </div>
      {open === "donors" && <div className="mt-4"><Donors donors={donors} now={now} /></div>}
      {open === "stock" && <div className="mt-4"><Stock stock={stock} /></div>}
    </div>
  );
}
