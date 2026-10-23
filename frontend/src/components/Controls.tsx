import type { ButtonHTMLAttributes } from "react";
import type { Clock, Health, Scenario } from "../api";
import { clockDay, hhmm } from "../format";

type Props = {
  scenarios: Scenario[];
  scenario: string;
  onScenario: (id: string) => void;
  clock: Clock | null;
  health: Health | null;
  busy: boolean;
  onReset: () => void;
  onStep: () => void;
  onAdvance: (minutes: number) => void;
  onAuto: (on: boolean) => void;
  theme: "dark" | "light";
  onTheme: () => void;
};

const shortTitle = (title: string) => title.split(":")[0];

function BarButton({ children, ...rest }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...rest}
      className="rounded px-3 py-1.5 text-on-bar/85 hover:bg-on-bar/10 hover:text-on-bar disabled:opacity-40 aria-pressed:bg-on-bar aria-pressed:text-bar"
    >
      {children}
    </button>
  );
}

export default function Controls(p: Props) {
  return (
    <header className="bg-bar text-on-bar">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-6 gap-y-3 px-6 py-3">
        <div className="mr-2">
          <div className="text-xl font-bold tracking-tight">RaktTrace</div>
          <div className="text-xs text-on-bar/60">A yes isn't blood.</div>
        </div>

        <div className="flex items-center gap-2">
          {/* The pick is what Reset loads; the API doesn't say which scenario is running. */}
          <label className="text-sm text-on-bar/60" htmlFor="scenario">Load</label>
          <select
            id="scenario"
            value={p.scenario}
            onChange={(e) => p.onScenario(e.target.value)}
            className="rounded border border-on-bar/25 bg-bar px-2 py-1.5 text-on-bar"
          >
            <option value="" disabled>Pick a scenario</option>
            {p.scenarios.map((s) => (
              <option key={s.id} value={s.id} title={s.title}>{shortTitle(s.title)}</option>
            ))}
          </select>
          <BarButton onClick={p.onReset} disabled={p.busy || !p.scenario}>Reset</BarButton>
        </div>

        <div className="flex items-center gap-1" role="group" aria-label="Sim clock">
          <BarButton onClick={p.onStep} disabled={p.busy}>Step</BarButton>
          <BarButton onClick={() => p.onAdvance(15)} disabled={p.busy}>+15 min</BarButton>
          <BarButton onClick={() => p.onAdvance(60)} disabled={p.busy}>+1 h</BarButton>
          <BarButton onClick={() => p.onAuto(!p.clock?.auto)} disabled={p.busy || !p.clock} aria-pressed={!!p.clock?.auto}>
            {p.clock?.auto ? "Pause" : "Auto"}
          </BarButton>
        </div>

        <div className="ml-auto flex items-center gap-6">
          <div className="text-right text-xs leading-tight text-on-bar/60">
            <div>LLM {p.health?.llm ?? "…"} · Telegram {p.health?.telegram ?? "…"}</div>
            <button onClick={p.onTheme} className="underline-offset-2 hover:text-on-bar hover:underline">
              {p.theme === "dark" ? "Light mode" : "Dark mode"}
            </button>
          </div>
          <div className="text-right">
            <div className="text-xs text-on-bar/60">{p.clock ? clockDay(p.clock.now) : "Sim clock"}</div>
            <div className="text-3xl font-semibold leading-none">{p.clock ? hhmm(p.clock.now) : "--:--"}</div>
          </div>
        </div>
      </div>
    </header>
  );
}
