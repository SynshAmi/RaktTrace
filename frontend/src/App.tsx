import { useEffect, useState } from "react";
import { api } from "./api";
import Controls from "./components/Controls";
import RequestView from "./pages/RequestView";
import { usePoll } from "./usePoll";

type Theme = "dark" | "light";

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
  const [busy, setBusy] = useState(false);
  const [controlError, setControlError] = useState<string | null>(null);
  const [scenario, setScenario] = useState(() => stored("rakt.scenario") ?? "");
  const [picked, setPicked] = useState<string | null>(null);

  const scenarios = usePoll(api.scenarios, "scenarios", 0, 60_000);
  const clock = usePoll(api.clock, "clock", version, undefined, busy);
  const health = usePoll(api.health, "health", version, 10_000);
  const requests = usePoll(api.requests, "requests", version, undefined, busy);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const list = requests.data ?? [];
  // After a reset the new request id arrives before the next list poll, so trust it over the (stale) list.
  const requestId = picked ?? list[0]?.id ?? null;

  // Controls go one at a time; every poll refreshes right after each one.
  async function control(run: () => Promise<unknown>) {
    setBusy(true);
    setControlError(null);
    try {
      await run();
    } catch (e) {
      setControlError((e as Error).message);
    } finally {
      setBusy(false);
      setVersion((n) => n + 1);
    }
  }

  const reset = () =>
    control(async () => {
      const r = await api.reset(scenario);
      setPicked(r.request_id);
    });

  return (
    <div className="flex min-h-screen flex-col">
      <Controls
        scenarios={scenarios.data ?? []}
        scenario={scenario}
        onScenario={(id) => {
          setScenario(id);
          store("rakt.scenario", id);
        }}
        clock={clock.data}
        health={health.data}
        busy={busy}
        onReset={reset}
        onStep={() => control(api.step)}
        onAdvance={(m) => control(() => api.advance(m))}
        onAuto={(on) => control(() => api.auto(on))}
        theme={theme}
        onTheme={() => {
          const next = theme === "dark" ? "light" : "dark";
          setTheme(next);
          store("rakt.theme", next);
        }}
      />
      {(controlError || clock.error) && (
        <p className="bg-neg-fill px-6 py-2 text-on-bar">
          {controlError ?? `Can't reach the backend: ${clock.error}`}
        </p>
      )}

      <div className="flex-1">
        {requestId ? (
          <RequestView id={requestId} requests={list} onPick={setPicked} version={version} paused={busy} />
        ) : (
          <p className="px-6 py-10 text-muted">
            {requests.data ? "No request yet. Pick a scenario and press Reset." : "Connecting to the backend…"}
          </p>
        )}
      </div>

      <footer className="px-6 py-4 text-sm text-faint">
        Synthetic Bengaluru simulation: no real patients, hospitals, donors or stock feeds.
      </footer>
    </div>
  );
}
