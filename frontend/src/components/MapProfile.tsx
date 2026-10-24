import type { ReactNode } from "react";
import type { CentreProfile, DonorProfile, HospitalProfile, Profile } from "../api";
import { groupLabel, productLabel, when } from "../format";
import { provenance } from "../mapview";

const dayFmt = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", year: "numeric" });
const day = (iso: string | null) => (iso ? dayFmt.format(new Date(iso)) : null);
const word = (s: string) => s.charAt(0) + s.slice(1).toLowerCase().replace(/_/g, " ");

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-t border-line pt-3">
      <h4 className="mb-1.5 text-sm font-bold uppercase tracking-wider text-muted">{title}</h4>
      {children}
    </section>
  );
}

function Rows({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted">{k}</dt>
          <dd className="font-semibold">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function Donor({ p, now, requestId }: { p: DonorProfile; now: string; requestId: string }) {
  const pl = p.pledge;
  return (
    <div className="space-y-3">
      <div>
        <div className="text-2xl font-bold">{p.name}</div>
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <span className="rounded-md bg-tab px-2 py-0.5 text-lg font-bold text-white">{groupLabel(p.group)}</span>
          {p.live && <span className="rounded border border-accent px-2 py-0.5 font-semibold text-accent">Live · Telegram</span>}
          <span className="text-muted">{p.area}</span>
        </div>
      </div>

      <Section title={`For ${requestId}`}>
        {pl ? (
          <Rows rows={[
            ["Status", word(pl.status)],
            ...(pl.booking_code ? [["Booking code", pl.booking_code] as [string, ReactNode]] : []),
            ["Invited", `${when(pl.invited_at, now)} · wave ${pl.wave}`],
            ...(pl.replied_at ? [["Replied", `${when(pl.replied_at, now)}${pl.reply_text ? ` · “${pl.reply_text}”` : ""}`] as [string, ReactNode]] : []),
            ...(pl.available_from ? [["Available from", when(pl.available_from, now)] as [string, ReactNode]] : []),
            ...(pl.on_way_at ? [["On my way", `tapped ${when(pl.on_way_at, now)} (not arrival)`] as [string, ReactNode]] : []),
            ...(pl.ready_at ? [["Unit ready by", when(pl.ready_at, now)] as [string, ReactNode]] : []),
            ...(pl.why ? [["Planner's reason", pl.why] as [string, ReactNode]] : []),
          ]} />
        ) : (
          <p className="text-muted">
            Not contacted.{p.candidate_why ? ` Passes the planner's filters now: ${p.candidate_why}.` : " Not on the planner's list right now."}
          </p>
        )}
      </Section>

      <Section title="Donor profile (synthetic)">
        <Rows rows={[
          ["Sex", p.sex === "M" ? "Male" : p.sex === "F" ? "Female" : "Not given (120-day rule applies)"],
          ["Age", `${p.age}`],
          ["Weight", `${p.weight_kg} kg`],
          ["Platelets (apheresis)", p.apheresis_ok ? "Can donate" : "No"],
          ["Last whole blood", day(p.last_whole_blood_at) ?? "Never"],
          ["Apheresis, last 12 months", p.apheresis_last_year ? `${p.apheresis_last_year} (last ${day(p.last_apheresis_at)})` : "None"],
          ...(p.deferred_until ? [["Deferred until", day(p.deferred_until)] as [string, ReactNode]] : []),
          ["Verified donor", p.donation_verified ? "Yes" : "No"],
          ["Asked in last 72 h", `${p.invites_last_72h}`],
          ...(p.opted_out ? [["Opted out", "Yes (STOP): never contacted"] as [string, ReactNode]] : []),
        ]} />
      </Section>

      {p.rule_check && (
        <Section title={`Donation rules for ${productLabel(p.rule_check.product)}`}>
          <p className={`font-semibold ${p.rule_check.passes ? "text-success" : "text-danger"}`}>
            {p.rule_check.passes ? "Passes the published interval, age and weight rules if they came now"
              : `Doesn't pass: ${p.rule_check.reasons.join("; ")}`}
          </p>
          <p className="mt-1 text-sm text-faint">The blood centre screens every donor; this is not a medical decision.</p>
        </Section>
      )}

      <Section title="Distance and position">
        <div className="space-y-1">
          {p.travel_min !== null && p.centre && (
            <p>About <b>{p.travel_min} min</b> to {p.centre} ({p.km} km straight line; the planner's estimate)</p>
          )}
          {p.stated_travel_min !== null && <p>They said: about {p.stated_travel_min} min away</p>}
          <p className="text-sm text-faint">{provenance({ ...p, lat: 0, lon: 0, candidate: false, pledge: null })}</p>
        </div>
      </Section>
    </div>
  );
}

function Centre({ p, onDonor }: { p: CentreProfile; onDonor: (id: string) => void }) {
  return (
    <div className="space-y-3">
      <div>
        <div className="text-2xl font-bold">{p.name}</div>
        <div className="text-muted">{p.address}</div>
      </div>
      <Rows rows={[
        ["Phone (synthetic)", p.phone],
        ["Staff", p.staff === "telegram" ? "Linked on Telegram" : "Simulated"],
        ["Platelets (apheresis)", p.apheresis ? "Yes" : "No"],
        ["Takes donors", p.accepts_donors ? "Yes" : "No"],
      ]} />
      <Section title={`Donors coming (${p.donors_coming.length})`}>
        {p.donors_coming.length === 0 ? <p className="text-muted">None booked here right now.</p> : (
          <ul className="space-y-1">
            {p.donors_coming.map((d) => (
              <li key={`${d.request_id}-${d.donor_id}`}>
                <button onClick={() => onDonor(d.donor_id)} className="text-left font-semibold underline-offset-2 hover:underline">
                  {d.name}
                </button>{" "}
                <span className="text-muted">{groupLabel(d.group)} · {word(d.status)}{d.booking_code ? ` · booking ${d.booking_code}` : ""} · {d.request_id}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Section title="Listed stock (what the listing says, not verified)">
        {p.listed_stock.length === 0 ? <p className="text-muted">Nothing listed.</p> : (
          <ul className="space-y-0.5">
            {p.listed_stock.map((x, i) => (
              <li key={i}>{groupLabel(x.group)} {productLabel(x.product)}: {x.listed_units} · listed {Math.round(x.listed_age_min / 60)} h ago</li>
            ))}
          </ul>
        )}
      </Section>
      {p.holds.length > 0 && (
        <Section title="Holds for this request">
          {p.holds.map((h, i) => <p key={i}>{word(h.status)} · asked {h.units_asked}, reserved {h.units_reserved}</p>)}
        </Section>
      )}
      <p className="text-sm text-faint">A synthetic centre in the demo city: not a real blood bank or live inventory.</p>
    </div>
  );
}

function Hospital({ p, now }: { p: HospitalProfile; now: string }) {
  return (
    <div className="space-y-3">
      <div>
        <div className="text-2xl font-bold">{p.name}</div>
        <div className="text-muted">{p.area}{p.own_centre ? ` · its blood centre: ${p.own_centre}` : ""}</div>
      </div>
      <Section title={`Requests (${p.requests.length})`}>
        {p.requests.length === 0 ? <p className="text-muted">None in this world.</p> : (
          <ul className="space-y-1">
            {p.requests.map((r) => (
              <li key={r.id}><b>{r.id}</b> · {groupLabel(r.group)} {productLabel(r.product)} × {r.units} · {word(r.status)} · by {when(r.deadline_at, now)}</li>
            ))}
          </ul>
        )}
      </Section>
      <p className="text-sm text-faint">Synthetic: not connected to any real hospital system.</p>
    </div>
  );
}

/** The selected marker's profile, from GET /map/profile. */
export default function MapProfile({ profile, error, now, requestId, onDonor }:
  { profile: Profile | null; error: string | null; now: string; requestId: string; onDonor: (id: string) => void }) {
  if (error) return <p className="text-danger">Couldn't load this profile: {error}</p>;
  if (!profile) return <p className="text-muted">Loading…</p>;
  if (profile.kind === "donor") return <Donor p={profile} now={now} requestId={requestId} />;
  if (profile.kind === "centre") return <Centre p={profile} onDonor={onDonor} />;
  return <Hospital p={profile} now={now} />;
}
