import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import Controls, { type Theme } from "./components/Controls";
import Phones from "./pages/Phones";
import RequestView from "./pages/RequestView";
import { hhmm } from "./format";
import { usePoll } from "./usePoll";

function stored(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function store(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* per-viewer convenience only */
  }
}

function initialTheme(): Theme {
  const saved = stored("rakt.theme");
  if (saved === "dark" || saved === "light") return saved;
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export default function App() {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const [controlError, setControlError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [page, setPage] = useState<"dashboard" | "phones">(() => (stored("rakt.page") === "phones" ? "phones" : "dashboard"));
  const [run, setRun] = useState(0);  // bumps on every scenario load: notifications and the trend start afresh
  const [activity, setActivity] = useState("Update");  // what last moved the clock, for notification summaries
  const [picked, setPicked] = useState<string | null>(null);
  const inFlight = useRef(false);

  const scenarios = usePoll(api.scenarios, "scenarios", 0, 60_000);
  const clock = usePoll(api.clock, "clock", version, undefined, busy !== null);
  const health = usePoll(api.health, "health", version, 10_000);
  const requests = usePoll(api.requests, "requests", version, undefined, busy !== null);
  const llm = usePoll(api.llm, "llm", version, 10_000);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const list = requests.data ?? [];
  // After a reset the new request id arrives before the next list poll, so trust it over the (stale) list.
  const requestId = picked ?? list[0]?.id ?? null;

  // The picked request can vanish (a reset from another tab); then fall back to the list.
  useEffect(() => {
    if (busy === null && picked && requests.data && !requests.data.some((r) => r.id === picked)) setPicked(null);
  }, [requests.data]);

  // Controls go one at a time; every poll refreshes right after each one. The ref blocks a second click that lands
  // before React re-renders with the buttons disabled.
  async function control(label: string, run: () => Promise<unknown>) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(label);
    setControlError(null);
    setNotice(null);
    setActivity(label === "+60 min" ? "+1 h" : label === "Play" ? "Auto" : label);
    try {
      await run();
    } catch (e) {
      setControlError((e as Error).message);
    } finally {
      inFlight.current = false;
      setBusy(null);
      setVersion((n) => n + 1);
    }
  }

  // Loading a scenario resets the world to its start: the backend's clock then reports it as the active one.
  const load = (scenarioId: string) =>
    control(`Loading ${scenarioId}`, async () => {
      const r = await api.reset(scenarioId);
      setPicked(r.request_id);
      setRun((n) => n + 1);
    });

  const offline = clock.error !== null;
  const activeScenario = offline ? null : clock.data?.scenario ?? null;

  return (
    <div className="flex min-h-screen flex-col">
      <Controls
        scenarios={scenarios.data ?? []}
        active={activeScenario}
        clock={offline ? null : clock.data}
        health={offline ? null : health.data}
        offline={offline}
        busy={busy}
        notice={notice}
        onLoad={load}
        onRestart={() => activeScenario && load(activeScenario.id)}
        onStep={() => control("Next event", async () => {
          const r = await api.step();
          setNotice(r.event ? `Event at ${hhmm(r.event.at)} done` : "No more events in this scenario");
        })}
        onAdvance={(m) => control(`+${m} min`, () => api.advance(m))}
        onAuto={(on) => control(on ? "Play" : "Pause", () => api.auto(on))}
        llm={llm.data?.enabled ?? null}
        onLlm={(on) => control(on ? "LLM on" : "LLM off", () => api.setLlm(on))}
        theme={theme}
        onTheme={(next) => {
          setTheme(next);
          store("rakt.theme", next);
        }}
      />
      {(controlError || offline) && (
        <p role="alert" className="border-b border-danger bg-raise px-4 py-2 font-semibold text-danger sm:px-6">
          {controlError ?? `Can't reach the backend (${clock.error}). Showing the last state received; it may be out of date.`}
        </p>
      )}

      <nav aria-label="Pages" className="mx-auto flex w-full max-w-420 gap-2 border-b border-line px-4 pt-3 sm:px-6">
        {(["dashboard", "phones"] as const).map((id) => (
          <button key={id} onClick={() => { setPage(id); store("rakt.page", id); }} aria-current={page === id}
            className={`-mb-px rounded-t-md border-b-4 px-4 py-1.5 font-semibold ${page === id
              ? "border-tab bg-tab/15 text-text" : "border-transparent text-muted hover:bg-text/5 hover:text-text"}`}>
            {id === "dashboard" ? "Dashboard" : "Phones"}
          </button>
        ))}
      </nav>

      <div className="flex-1">
        {page === "phones" ? (
          <Phones version={version} paused={busy !== null} run={run} onChanged={() => setVersion((n) => n + 1)} />
        ) : requestId ? (
          <RequestView id={requestId} requests={list} onPick={setPicked} version={version} paused={busy !== null}
            run={run} activity={clock.data?.auto ? "Auto" : activity} />
        ) : (
          <p className="px-4 py-10 text-muted sm:px-6">
            {requests.data ? "No request in this world yet. Load a scenario above." : "Connecting to the backend…"}
          </p>
        )}
      </div>

      <footer className="px-4 py-4 text-sm text-faint sm:px-6">
        Synthetic Bengaluru simulation: no real patients, hospitals, donors or stock feeds.
      </footer>
    </div>
  );
}
