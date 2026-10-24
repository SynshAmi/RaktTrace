// Every call to the backend (BUILD §5.3). Vite proxies /api to the backend on :8000.

export type RequestStatus = "OPEN" | "COVERED" | "SECURED" | "FULFILLED" | "FAILED" | "CANCELLED";

export type Health = { ok: boolean; now: string; llm: "on" | "off"; telegram: "ok" | "off" };
export type Scenario = { id: string; title: string };
export type Clock = { now: string; auto: boolean; scenario: Scenario | null };

export type RequestSummary = {
  id: string;
  group: string;
  product: string;
  units: number;
  status: RequestStatus;
  p: number;
  deadline_at: string;
  hospital_name: string;
  escalation_level: number;
};

export type UnitsLadder = {
  found: number;
  said_yes: number;
  ready_in_time: number;
  collected_or_reserved: number;
  confirmed: number;
};

export type StockRow = {
  reservation_id: string;
  centre: string;
  units_asked: number;
  units_reserved: number;
  status: string;
  listed_age_min: number;
  p: number;
};

export type DonorRow = {
  pledge_id: string;
  name: string;
  group: string;
  km: number;
  status: string;
  p: number;
  booking_code: string | null;
  ready_at: string | null;
  why: string;
  reply_text: string | null;
  read_by: string | null;
  live: boolean;
};

export type RequestView = {
  id: string;
  status: RequestStatus;
  group: string;
  product: string;
  units: number;
  hospital: { id: string; name: string; area: string };
  collection_centre: { id: string; name: string; staff: "telegram" | "simulated" } | null;
  created_at: string;
  deadline_at: string;
  now: string;
  p: number;
  p_firm: number;
  target: number;
  units_ladder: UnitsLadder;
  stock: StockRow[];
  donors: DonorRow[];
  counts: { messaged: number; yes: number; no: number; silent: number; active: number; standby: number };
  escalation: { level: number; brief: string | null; call_list: { centre: string; phone: string; note: string }[] };
  flags: { donors_can_help: boolean; waiting_for_stock: boolean };
};

export type BaselineView = {
  request_id: string;
  status: "SEARCHING" | "SAYS_FULFILLED";
  said_fulfilled_at: string | null;
  donors_messaged: number;
  found_units: number;
  timeline: string[];
  truth_at_deadline: { units_ready: number; units: number } | null;
};

export type Decision = {
  id: string;
  request_id: string;
  at: string;
  trigger: string;
  p_before: number;
  p_after: number;
  status: RequestStatus;
  actions: string[];
  summary: string;
};

export class ApiError extends Error {}

async function call<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().then((j) => j.detail, () => null);
    throw new ApiError(typeof detail === "string" ? detail : `${res.status} ${res.statusText}`);
  }
  return res.json();
}

export const api = {
  health: () => call<Health>("/health"),
  scenarios: () => call<Scenario[]>("/demo/scenarios"),
  clock: () => call<Clock>("/demo/clock"),
  reset: (scenario: string) => call<Clock & { request_id: string | null }>("/demo/reset", { scenario }),
  step: () => call<{ now: string; event: { kind: string; request_id: string | null; at: string } | null; quiet: number }>(
    "/demo/step", {}),
  advance: (minutes: number) => call<{ now: string }>("/demo/advance", { minutes }),
  auto: (on: boolean) => call<{ auto: boolean }>("/demo/auto", { on }),
  requests: () => call<RequestSummary[]>("/requests"),
  request: (id: string) => call<RequestView>(`/requests/${id}`),
  baseline: (id: string) => call<BaselineView>(`/requests/${id}/baseline`),
  decisions: (id: string) => call<Decision[]>(`/requests/${id}/decisions`),
};
