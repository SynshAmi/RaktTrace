# RaktTrace

**A yes isn't blood.** RaktTrace is an agent that keeps working an urgent blood request until a blood centre confirms the units are ready.

When a hospital is short of blood, families are told to "arrange blood", and a request counts as done the moment someone says yes. But listings are often stale, "kal aaunga" means tomorrow, donated blood needs hours of testing, and donors get deferred at screening. RaktTrace:

1. **Checks stock first**, and asks centres to reserve units.
2. **Messages only the donors truly needed**, and only if their blood can be ready in time.
3. **Checks every reply against the deadline**, testing included.
4. **Keeps backups** and promotes them when someone is deferred.
5. **Closes only on the blood centre's confirmation**, then stands donors down and tells the family to stop forwarding.
6. **Escalates early** with a plain-English handover when it won't make it.

The planner makes every decision. An LLM reads messy messages (English/Hindi/Hinglish) and writes escalation briefs, with a rule-based fallback.

Team Veritas (HX-BDXL): Suryansh Singh, Aditya Dev · AgentOps 2026.

## Live demo

| | |
|---|---|
| Dashboard | https://rakttrace-frontend.onrender.com/ |
| Backend API | https://rakttrace-backend.onrender.com |
| Backend health | https://rakttrace-backend.onrender.com/api/health |
| Health through the frontend (checks the `/api` rewrite) | https://rakttrace-frontend.onrender.com/api/health |
| Telegram bot | https://t.me/RaktTraceDemoBot (Centre B staff: `https://t.me/RaktTraceDemoBot?start=staff_c_b`) |

Health returns `{"ok", "now", "llm": "on"|"off", "telegram": "ok"|"off"}`. Everything runs in a **synthetic Bengaluru simulation**: no real patients, hospitals, donors or stock feeds.

## What's in the demo

- **Scenarios** S1 (surgery tonight, stock only), S2 (dengue platelets, donors, deferral and standby; the live Telegram scenario) and S3 (no way in time, early escalation), driven by a sim clock: Next event, +15 min, +1 h, Play/Pause.
- **Dashboard:** request status, required / arranged / ready / gap, the estimated chance of readiness by the deadline, unit-by-unit progress, decisions, donors, stock, a donor map, the level 2 escalation banner with the brief and call list, notifications, an LLM on/off toggle, and a "today's workflow" comparison of the same request.
- **Phones:** what each simulated donor, centre staff member, family or coordinator sees, with the real messages and buttons.
- **Telegram:** real people can join as synthetic donors ("Join the live demo" or "Create my profile") or link as Centre B staff; centres with no linked staff are run by simulated staff.
- **Benchmark:** a synthetic benchmark (seed 2026, N = 500, paired 95% CI) via the CLI and `/api/benchmark` (cached result: `/api/benchmark/cached`). Today's workflow vs RaktTrace: blood ready on time 50.0% vs 59.8% (+9.8 pts, CI [5.95, 13.65]); donors messaged per request 8.84 vs 5.11. Simulated results, not real-world evidence. There is no benchmark page in the dashboard yet.
- Not built yet: the paste-a-plea "new request" screen (the API exists: `POST /api/requests/parse`, `POST /api/requests`) and the benchmark page.

**Stack:** Python 3.12 · FastAPI · Uvicorn · python-telegram-bot (long polling) · OpenAI-compatible LLMs (Groq, Gemini) · React + Vite + TypeScript + Tailwind · Leaflet.

## Deployment (Render)

| | Backend | Frontend |
|---|---|---|
| Render service | Web Service | Static Site |
| Root directory | `backend` | `frontend` |
| Build | `pip install uv && uv sync --frozen --no-dev` | `npm ci && npm run build` |
| Start / publish | `uv run --no-sync uvicorn rakt.main:app --host 0.0.0.0 --port $PORT` | publish `dist` |
| Runtime (optional, recommended env var) | `PYTHON_VERSION=3.12` | `NODE_VERSION=22` |
| Health check | `/api/health` | — |

- The frontend calls relative `/api/...` paths. On Render a **rewrite rule** on the static site sends `/api/*` to `https://rakttrace-backend.onrender.com/api/*`, so the browser stays on one origin and no CORS setup is needed.
- Backend environment variables (see [`.env.example`](.env.example); set them in Render, never commit them): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`, `LLM_ENABLED`, `LLM_CHAIN`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY` (LLM keys are optional; without them a rule parser reads replies), `DEFAULT_SCENARIO`, `RANDOM_SEED`.
- Run **one backend instance with one Uvicorn worker**.

### Limitations

- **In-memory state, no database.** Any backend restart or redeploy resets everything: the active scenario and sim clock, decisions, and all Telegram links. Donors and staff must `/start` (and staff reopen their link) again.
- **One Telegram poller per bot token.** The bot uses long polling. Don't run another instance (a second replica, extra workers, or a local backend) with the same token while the deployed one is polling: they conflict (Telegram 409) and split updates. Updates sent while the backend is down are dropped.
- **Free Render services sleep after inactivity.** The first request after a sleep is a cold start; while the backend sleeps, the bot isn't polling, and waking it resets the state as above.
- **No authentication.** Anyone with the URL can reset or step the scenario and toggle the LLM.

## Run locally

```bash
cd backend && uv sync && uv run uvicorn rakt.main:app --host 127.0.0.1 --port 8000   # no --reload: a reload restarts the bot
cd frontend && npm install && npm run dev                                             # dashboard on :5173, proxies /api to :8000
cd backend && uv run pytest -q                                                        # backend tests, offline
cd frontend && npm test && npm run build                                              # frontend tests; type-check + build
cd backend && uv run python -m rakt.sim.benchmark                                     # benchmark, seed 2026, N = 500; overwrites backend/bench/results_nominal_2026.json
```

Copy `.env.example` to `.env` at the repository root for local settings. Without a Telegram token the simulated phones carry every message. `RAKT_API=http://127.0.0.1:<port> npm run dev` points the dashboard at a backend on another port.

## Docs

Start with [`CLAUDE.md`](CLAUDE.md) and [`docs/SPEC.md`](docs/SPEC.md). Product and screens: [`docs/PRODUCT.md`](docs/PRODUCT.md) · agent, planner and benchmark: [`docs/AGENT.md`](docs/AGENT.md) · build and API: [`docs/BUILD.md`](docs/BUILD.md) · status: [`docs/PROGRESS.md`](docs/PROGRESS.md).
