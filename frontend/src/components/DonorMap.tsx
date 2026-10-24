import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect, useRef, useState } from "react";
import { api, type MapCentre, type MapDonor, type MapHospital, type MapView } from "../api";
import { groupLabel } from "../format";
import { drawOrder, kind, KIND, pledgeLine, provenance, tally, type Kind } from "../mapview";
import { usePoll } from "../usePoll";

// OpenStreetMap's standard street tiles: keyless, attribution required, light interactive use only
// (https://operations.osmfoundation.org/policies/tiles/). Dark mode inverts them in CSS (index.css, .rakt-map).
const TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const BENGALURU: L.LatLngTuple = [12.9716, 77.5946];

type Selected = { type: "donor" | "centre" | "hospital"; id: string } | null;

const colour = (token: string) => getComputedStyle(document.documentElement).getPropertyValue(token).trim();

function useTheme() {
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme);
  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(document.documentElement.dataset.theme));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);
  return theme;
}

function DonorDetail({ d, centreName }: { d: MapDonor; centreName: string | null }) {
  return (
    <div className="space-y-1.5">
      <div className="text-lg font-bold">
        {d.name} <span className="font-normal text-muted">{groupLabel(d.group)}</span>
        {d.live && <span className="ml-2 rounded border border-accent px-1.5 text-xs font-semibold text-accent">Live · Telegram</span>}
      </div>
      <div className="font-semibold">{pledgeLine(d)}</div>
      {d.pledge?.why && <div className="text-sm text-muted">Planner's reason: {d.pledge.why}</div>}
      {d.travel_min !== null && centreName && (
        <div className="text-sm text-muted">
          Planner's travel estimate to {centreName}: about {d.travel_min} min ({d.km} km straight line × road factor at city speed)
        </div>
      )}
      {d.stated_travel_min !== null && <div className="text-sm text-muted">They said: about {d.stated_travel_min} min away</div>}
      <div className="text-sm text-faint">{provenance(d)}</div>
      {d.opted_out && <div className="text-sm text-muted">Opted out (STOP): never contacted.</div>}
    </div>
  );
}

function CentreDetail({ c, view }: { c: MapCentre; view: MapView }) {
  return (
    <div className="space-y-1.5">
      <div className="text-lg font-bold">{c.name} <span className="font-normal text-muted">{c.area}</span></div>
      {c.collection && <div className="font-semibold text-tab">Collection centre for {view.request?.id}</div>}
      <div className="text-sm text-muted">
        Staff: {c.staff === "telegram" ? "linked on Telegram" : "simulated"} · {c.apheresis ? "takes platelet (apheresis) donors" : "no apheresis"}
        {!c.accepts_donors && " · doesn't take donors"}
      </div>
      {c.holds.map((h, i) => (
        <div key={i} className="text-sm">Stock hold: {h.status.toLowerCase()} · asked {h.units_asked}, reserved {h.units_reserved}</div>
      ))}
      <div className="text-xs text-faint">A synthetic centre in the demo city: not a real blood bank or live inventory.</div>
    </div>
  );
}

function HospitalDetail({ h }: { h: MapHospital }) {
  return (
    <div className="space-y-1.5">
      <div className="text-lg font-bold">{h.name} <span className="font-normal text-muted">{h.area}</span></div>
      <div className="text-sm text-muted">{h.requesting ? "The hospital this request is for." : "A hospital in the demo city."}</div>
      <div className="text-xs text-faint">Synthetic: not connected to any real hospital system.</div>
    </div>
  );
}

function Swatch({ k }: { k: Kind }) {
  const { token, fill, size } = KIND[k];
  const d = Math.max(8, size + 4);
  return (
    <span aria-hidden className="inline-block shrink-0 rounded-full border-2"
      style={{ width: d, height: d, borderColor: `var(${token})`, background: fill ? `var(${token})` : "transparent" }} />
  );
}

/** The request on a map of the demo city: centres, the requesting hospital, every donor where the planner places them. */
export default function DonorMap({ requestId, version, paused }: { requestId: string; version: number; paused: boolean }) {
  const { data: view, error } = usePoll(() => api.map(requestId), requestId, version, undefined, paused);
  const theme = useTheme();
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layer = useRef<L.LayerGroup | null>(null);
  const fitted = useRef<string | null>(null);
  const [tiles, setTiles] = useState<"loading" | "ok" | "failed">("loading");
  const [selected, setSelected] = useState<Selected>(null);

  useEffect(() => {
    if (!box.current) return;
    const m = L.map(box.current, { preferCanvas: true, center: BENGALURU, zoom: 12, scrollWheelZoom: false });
    let loaded = false, failures = 0;
    L.tileLayer(TILES, { maxZoom: 19, attribution: ATTRIBUTION })
      .on("tileload", () => { loaded = true; setTiles("ok"); })
      .on("tileerror", () => { failures += 1; if (!loaded && failures >= 4) setTiles("failed"); })
      .addTo(m);
    m.on("click", () => setSelected(null));
    layer.current = L.layerGroup().addTo(m);
    map.current = m;
    return () => {
      m.remove();
      map.current = null;
    };
  }, []);

  useEffect(() => {
    const m = map.current, group = layer.current;
    if (!m || !group || !view) return;
    group.clearLayers();
    const pick = (type: "donor" | "centre" | "hospital", id: string) => (e: L.LeafletMouseEvent) => {
      L.DomEvent.stopPropagation(e);
      setSelected({ type, id });
    };

    const collection = view.centres.find((c) => c.collection);
    if (collection && view.request) {
      L.circle([collection.lat, collection.lon], {
        radius: view.request.radius_km * 1000, color: colour("--accent"), weight: 1.5, dashArray: "6 6",
        fill: true, fillOpacity: 0.04, interactive: false,
      }).addTo(group);
    }

    for (const d of drawOrder(view.donors)) {
      const k = kind(d), style = KIND[k], c = colour(style.token);
      const chosen = selected?.type === "donor" && selected.id === d.id;
      L.circleMarker([d.lat, d.lon], {
        radius: style.size + (d.live ? 2 : 0) + (chosen ? 3 : 0),
        color: d.live || chosen ? colour("--text") : c, weight: d.live || chosen ? 2.5 : style.fill ? 1 : 2,
        fillColor: c, fillOpacity: style.fill ? (k === "other" ? 0.75 : 0.95) : 0.12,
        dashArray: d.location === "approximate" ? "3 3" : undefined,
        bubblingMouseEvents: false,  // otherwise the map's own click clears the selection straight away
      }).on("click", pick("donor", d.id)).addTo(group);
    }

    for (const c of view.centres) {
      L.marker([c.lat, c.lon], {
        icon: L.divIcon({ className: "", html: `<span class="rk-centre${c.collection ? " is-collection" : ""}"></span>`,
          iconSize: c.collection ? [22, 22] : [16, 16] }),
        keyboard: true, title: c.name, zIndexOffset: c.collection ? 1000 : 500,
      }).bindTooltip(c.name, { permanent: true, direction: "right", offset: [10, 0], className: "rk-label" })
        .on("click", pick("centre", c.id)).addTo(group);
    }
    for (const h of view.hospitals) {
      L.marker([h.lat, h.lon], {
        icon: L.divIcon({ className: "", html: `<span class="rk-hospital${h.requesting ? " is-requesting" : ""}">+</span>`,
          iconSize: [20, 20] }),
        keyboard: true, title: h.name, zIndexOffset: h.requesting ? 900 : 400,
      }).bindTooltip(h.name, { permanent: h.requesting, direction: "left", offset: [-10, 0], className: "rk-label" })
        .on("click", pick("hospital", h.id)).addTo(group);
    }

    // Frame the request once (not on every poll, so a presenter's zoom stays put).
    if (fitted.current !== requestId) {
      const hospital = view.hospitals.find((h) => h.requesting);
      const points: L.LatLngTuple[] = [
        ...(collection ? [[collection.lat, collection.lon] as L.LatLngTuple] : []),
        ...(hospital ? [[hospital.lat, hospital.lon] as L.LatLngTuple] : []),
        ...view.donors.filter((d) => d.pledge).map((d) => [d.lat, d.lon] as L.LatLngTuple),
      ];
      if (points.length > 0) m.fitBounds(L.latLngBounds(points).pad(0.6), { maxZoom: 14 });
      fitted.current = requestId;
    }
  }, [view, theme, selected, requestId]);

  useEffect(() => setSelected(null), [requestId]);

  const counts = view ? tally(view) : null;
  const collectionName = view?.centres.find((c) => c.collection)?.name ?? null;
  const detail = !view || !selected ? null
    : selected.type === "donor" ? view.donors.find((d) => d.id === selected.id)
    : selected.type === "centre" ? view.centres.find((c) => c.id === selected.id)
    : view.hospitals.find((h) => h.id === selected.id);

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <div className="relative">
        <div ref={box} className="rakt-map h-[26rem] w-full overflow-hidden rounded-lg border border-line sm:h-[34rem]"
          role="region" aria-label="Map of the demo city: centres, the requesting hospital and donors" />
        {!view && (
          <div className="absolute inset-0 grid place-items-center rounded-lg bg-bg/70 text-muted">
            {error ? `Couldn't load the map data: ${error}` : "Loading the map…"}
          </div>
        )}
        {tiles === "failed" && (
          <p role="status" className="absolute top-3 left-3 right-3 z-[1000] rounded-md border border-danger bg-raise px-3 py-2 text-sm font-semibold text-danger">
            Street tiles couldn't load (no internet?). Positions and statuses on this map are still live.
          </p>
        )}
      </div>

      <div className="space-y-5 text-sm">
        <div className="min-h-24 rounded-lg border border-line bg-raise p-4" aria-live="polite">
          {detail
            ? selected?.type === "donor" ? <DonorDetail d={detail as MapDonor} centreName={collectionName} />
              : selected?.type === "centre" ? <CentreDetail c={detail as MapCentre} view={view!} />
              : <HospitalDetail h={detail as MapHospital} />
            : <p className="text-muted">Tap a donor, centre or hospital for details.</p>}
        </div>

        <div>
          <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-muted">Legend</h3>
          <ul className="space-y-1.5">
            <li className="flex items-center gap-2"><span className="rk-centre is-collection" aria-hidden /> Collection centre</li>
            <li className="flex items-center gap-2"><span className="rk-centre" aria-hidden /> Other blood centre</li>
            <li className="flex items-center gap-2"><span className="rk-hospital is-requesting" aria-hidden>+</span> Requesting hospital</li>
            {(Object.keys(KIND) as Kind[]).map((k) => (
              <li key={k} className={`flex items-center gap-2 ${counts && counts[k] === 0 ? "opacity-50" : ""}`}>
                <Swatch k={k} /> {KIND[k].label}{counts ? ` (${counts[k]})` : ""}
              </li>
            ))}
            {view?.request && (
              <li className="flex items-center gap-2">
                <span aria-hidden className="inline-block w-5 border-t-2 border-dashed border-accent" />
                Planner's search radius now: {view.request.radius_km} km, straight line
              </li>
            )}
          </ul>
          <p className="mt-3 text-xs text-faint">
            White ring = live Telegram donor · dashed ring = approximate (an area they picked). Every position is
            synthetic or approximate: no GPS, no real addresses. The planner decides who is invited; the map only shows it.
            {view && view.unplaced > 0 && ` ${view.unplaced} donor(s) have no usable position and aren't drawn.`}
          </p>
        </div>
      </div>
    </div>
  );
}
