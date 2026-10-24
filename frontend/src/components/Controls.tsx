import { useEffect, useRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import type { Clock, Health, Scenario } from "../api";
import { clockDay, hhmm } from "../format";

export type Theme = "dark" | "light";

type Props = {
  scenarios: Scenario[];
  active: Scenario | null;
  clock: Clock | null;
  health: Health | null;
  offline: boolean;
  busy: string | null;
  notice: string | null;
  onLoad: (id: string) => void;
  onRestart: () => void;
  onStep: () => void;
  onAdvance: (minutes: number) => void;
  onAuto: (on: boolean) => void;
  theme: Theme;
  onTheme: (theme: Theme) => void;
};

const shortTitle = (title: string) => title.split(":")[0];

function BarButton({ children, working, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { working?: boolean }) {
  return (
    <button
      {...rest}
      aria-busy={working || undefined}
      className="inline-flex items-center gap-1.5 rounded-md border border-on-bar/30 px-2.5 py-1 text-sm text-on-bar sm:px-3 sm:py-1.5 sm:text-base hover:border-on-bar/50 hover:bg-on-bar/10 disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:bg-transparent"
    >
      {working && <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-on-bar border-t-transparent" aria-hidden />}
      {children}
    </button>
  );
}

function Group({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap items-center gap-2">
      <span className="hidden text-xs font-bold uppercase tracking-wider text-on-bar-muted lg:inline">{label}</span>
      {children}
    </div>
  );
}

/** A labelled dot: the label carries the meaning, the dot only reinforces it. */
function Signal({ state, label, short, title }: { state: "ok" | "off" | "down"; label: string; short: string; title: string }) {
  const dot = state === "ok" ? "bg-[#e8d99a]" : state === "down" ? "bg-[#f07178]" : "border border-on-bar-muted";
  return (
    <span title={title} className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <span className={`inline-block h-2.5 w-2.5 rounded-full ${dot}`} aria-hidden />
      <span className="lg:hidden" aria-hidden>{short}</span>
      <span className="sr-only lg:not-sr-only">{label}</span>
    </span>
  );
}

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
    </svg>
  );
}

function ThemeToggle({ theme, onTheme }: { theme: Theme; onTheme: (t: Theme) => void }) {
  const option = (value: Theme, label: string, icon: ReactNode) => (
    <button
      onClick={() => onTheme(value)}
      aria-pressed={theme === value}
      title={theme === value ? `${label} mode is on` : `Switch to ${label.toLowerCase()} mode`}
      aria-label={`${label} mode`}
      className="inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-on-bar-muted hover:text-on-bar aria-pressed:bg-on-bar aria-pressed:text-bar"
    >
      {icon}
      <span className="hidden lg:inline">{label}</span>
    </button>
  );
  return (
    <div role="group" aria-label="Colour theme" className="inline-flex rounded-md border border-on-bar/25 p-0.5 text-sm">
      {option("light", "Light", <SunIcon />)}
      {option("dark", "Dark", <MoonIcon />)}
    </div>
  );
}

export default function Controls(p: Props) {
  const disabled = p.busy !== null || p.offline || !p.clock;
  const playing = !!p.clock?.auto;
  const ref = useRef<HTMLElement>(null);

  // Publish the sticky header's height so scroll targets land below it at every width.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver(() =>
      document.documentElement.style.setProperty("--header-h", `${el.offsetHeight}px`));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <header ref={ref} className="sticky top-0 z-50 border-b border-white/10 bg-bar text-on-bar">
      <div className="mx-auto flex max-w-420 flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 sm:gap-x-6 sm:px-6">
        <div className="mr-auto flex items-baseline gap-3">
          <span className="text-xl font-bold tracking-tight">RaktTrace</span>
          <span className="hidden text-sm text-on-bar-muted lg:inline">A yes isn't blood.</span>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-on-bar-muted" aria-label="System status">
          <Signal
            state={p.offline ? "down" : p.health ? "ok" : "off"}
            label={p.offline ? "Backend unreachable" : p.health ? "Backend connected" : "Connecting…"}
            short={p.offline ? "API down" : "API"}
            title="The dashboard's link to the RaktTrace API"
          />
          <Signal
            state={p.health?.llm === "on" ? "ok" : "off"}
            label={p.health ? (p.health.llm === "on" ? "LLM configured" : "LLM off · rule parser") : "LLM …"}
            short="LLM"
            title={p.health?.llm === "on"
              ? "LLM reading is enabled and a provider key is set. Each call can still fail; then the rule parser reads the text."
              : "No LLM in use: replies and pleas are read by the rule parser"}
          />
          <Signal
            state={p.health?.telegram === "ok" ? "ok" : "off"}
            label={p.health ? (p.health.telegram === "ok" ? "Telegram bot polling" : "Telegram off · simulated phones") : "Telegram …"}
            short="Bot"
            title={p.health?.telegram === "ok"
              ? "The bot started and is listening. It doesn't mean a message was sent: only linked Telegram phones get messages, when the planner contacts them."
              : "No Telegram bot: simulated phones carry every message"}
          />
        </div>
        <ThemeToggle theme={p.theme} onTheme={p.onTheme} />
      </div>

      <div className="border-t border-on-bar/15">
        <div className="mx-auto flex max-w-420 flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2 sm:gap-x-8 sm:px-6">
          <Group label="Scenario">
            <select
              aria-label="Active scenario (changing it loads that scenario from its start)"
              title="Choosing a scenario loads it straight away and restarts the sim clock"
              value={p.active?.id ?? ""}
              onChange={(e) => p.onLoad(e.target.value)}
              disabled={p.busy !== null || p.offline}
              className="max-w-44 rounded-md border border-on-bar/30 bg-bar px-2 py-1 text-on-bar disabled:opacity-60 sm:max-w-none sm:min-w-56 sm:py-1.5"
            >
              {!p.active && <option value="" disabled>{p.offline ? "Unknown (backend unreachable)" : "No scenario running"}</option>}
              {p.scenarios.map((s) => (
                <option key={s.id} value={s.id} title={s.title}>{shortTitle(s.title)}</option>
              ))}
            </select>
            <BarButton onClick={p.onRestart} disabled={disabled || !p.active} working={p.busy?.startsWith("Loading")} title="Load this scenario again from its start" aria-label="Restart scenario">
              ↺<span className="hidden lg:inline">Restart</span>
            </BarButton>
          </Group>

          <Group label="Simulation">
            <BarButton onClick={p.onStep} disabled={disabled} working={p.busy === "Next event"}
              title="Run the sim clock to the next event that changes something, and process it">
              ⏭ Next<span className="hidden lg:inline"> event</span>
            </BarButton>
            <span className="hidden text-sm text-on-bar-muted lg:inline">Advance</span>
            <BarButton onClick={() => p.onAdvance(15)} disabled={disabled} working={p.busy === "+15 min"} title="Move the sim clock forward 15 minutes">+15 min</BarButton>
            <BarButton onClick={() => p.onAdvance(60)} disabled={disabled} working={p.busy === "+60 min"} title="Move the sim clock forward 1 hour">+1 h</BarButton>
            <BarButton
              onClick={() => p.onAuto(!playing)}
              disabled={disabled}
              working={p.busy === "Play" || p.busy === "Pause"}
              aria-pressed={playing}
              title={playing ? "Pause the sim clock" : "Run the sim clock at 1 sim minute per second"}
            >
              {playing ? "❚❚ Pause" : "▶ Play"}
            </BarButton>
            <span className="basis-full truncate text-sm text-on-bar-muted md:max-w-56 md:basis-auto" aria-live="polite">
              {p.busy ? `${p.busy}…` : p.notice ?? (playing ? "Playing · 1 sim min / s" : "Paused")}
            </span>
          </Group>

          <div className="ml-auto text-right" aria-label="Sim clock">
            <div className="hidden text-xs text-on-bar-muted lg:block">
              {p.clock ? `Sim clock · ${clockDay(p.clock.now)}` : "Sim clock"}
            </div>
            <div className="text-2xl font-bold leading-none sm:text-3xl">{p.clock ? hhmm(p.clock.now) : "--:--"}</div>
          </div>
        </div>
      </div>
    </header>
  );
}
