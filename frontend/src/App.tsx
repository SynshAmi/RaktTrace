import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import Controls, { type Theme } from "./components/Controls";
import RequestView from "./pages/RequestView";
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
  const [picked, setPicked] = useState<string | null>(null);
  const inFlight = useRef(false);

  const scenarios = usePoll(api.scenarios, "scenarios", 0, 60_000);
  const clock = usePoll(api.clock, "clock", version, undefined, busy !== null);
  const health = usePoll(api.health, "health", version, 10_000);
  const requests = usePoll(api.requests, "requests", version, undefined, busy !== null);

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
        onLoad={load}
        onRestart={() => activeScenario && load(activeScenario.id)}
        onStep={() => control("Next event", api.step)}
        onAdvance={(m) => control(`+${m} min`, () => api.advance(m))}
        onAuto={(on) => control(on ? "Play" : "Pause", () => api.auto(on))}
        theme={theme}
        onTheme={(next) => {
          setTheme(next);
          store("rakt.theme", next);
        }}
      />
      {(controlError || offline) && (
        <p role="alert" className="bg-danger-fill px-4 py-2 text-on-danger sm:px-6">
          {controlError ?? `Can't reach the backend (${clock.error}). Showing the last state received; it may be out of date.`}
        </p>
      )}

      <div className="flex-1">
        {requestId ? (
          <RequestView id={requestId} requests={list} onPick={setPicked} version={version} paused={busy !== null} />
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
