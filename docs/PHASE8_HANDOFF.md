# RaktTrace: Phase 8 Handoff (frontend on the live API)

For Aditya. The backend for phases 1–7 is merged on `main`. The frontend talks only to the HTTP API below: no backend imports, and it works whether or not Telegram is connected. Contracts live in `BUILD.md` §5.3; this page is the short version.

## 1. Run it

```bash
cd backend && uv sync && uv run uvicorn rakt.main:app --host 127.0.0.1 --port 8000   # no --reload
cd backend && uv run pytest -q                                                        # 295 tests, offline
cd backend && uv run python -m rakt.sim.benchmark                                     # seed 2026, N = 500, ~25 s
cd frontend && npm install && npm run dev                                             # dashboard on :5173, proxies /api
cd frontend && npm run build                                                          # type-check + production build
```
Startup loads `DEFAULT_SCENARIO` (S2) and starts the Telegram bot if `.env` has a token. `GET /api/health` → `{"ok", "now", "llm": "on"|"off", "telegram": "ok"|"off"}`. Vite should proxy `/api` to `:8000`.

## 2. What to poll (every 2 s)

| Screen part | Endpoint | Notes |
|---|---|---|
| Request list | `GET /api/requests` | id, status, p, deadline, hospital, escalation level |
| RaktTrace lane | `GET /api/requests/{id}` | RequestView: status, `p` / `p_firm` / `target`, `units_ladder`, `stock[]`, `donors[]` (each with `live` for Telegram donors), `counts`, `escalation {level, brief, call_list}`, `flags` |
| Today's-workflow lane | `GET /api/requests/{id}/baseline` | timeline up to the sim clock; `truth_at_deadline` is null until the deadline |
| Decision log | `GET /api/requests/{id}/decisions` | `summary` is the plain sentence to show |
| Phones panel | `GET /api/sim/phones`, `GET /api/sim/phones/{id}/messages` | roles: donor, staff, family, coordinator; reading messages marks them read. Linked Telegram chats appear too (their messages are copies; a failed Telegram send shows with `channel: "sim"`). |
| Clock | `GET /api/demo/clock` | `{now, auto}` |
| LLM | `GET /api/llm` | `{enabled, chain: [{name, healthy}]}` |

Statuses: `OPEN` "Finding blood", `COVERED` "On track", `SECURED` "Blood arranged", `FULFILLED` "Ready for patient", `FAILED` "Needs help", `CANCELLED`. `escalation.level == 2` → red banner with `brief` and `call_list`.

## 3. Controls (these change state)

| Action | Endpoint |
|---|---|
| Pick and reset a scenario | `GET /api/demo/scenarios`, `POST /api/demo/reset {scenario}` → `{now, request_id}` |
| Step / advance / auto | `POST /api/demo/step` → `{now, event}` · `POST /api/demo/advance {minutes}` (1–1440) · `POST /api/demo/auto {on}` (1 sim min per real s) |
| New request | `POST /api/requests/parse {text}` → draft + `missing` + `read_by`; then `POST /api/requests {group, product, units, hospital_id, deadline_at, family?}` → RequestView or `{merged_into}` |
| Cancel | `POST /api/requests/{id}/cancel` (409 if already closed) |
| Tap or type on a sim phone | `POST /api/sim/reply {phone_id, button_id?, text?}` (button ids are the ones in the message's `buttons`) |
| LLM toggle | `POST /api/llm {enabled}` |
| Benchmark | `GET /api/benchmark/cached` (the committed seed-2026 run, show first) · `POST /api/benchmark {n: 200, seed, reader}` (live re-run, ~10 s; essential tier only) |

Errors use `{"detail": ...}` with 404 / 409 / 422. All state changes, API or Telegram, go through one lock, so a poll always returns a consistent snapshot; send controls one at a time.

## 4. Telegram is optional

- No Telegram at all: everything works; simulated staff and donors answer.
- A judge taps **Join the live demo**: their donor appears in `donors[]` with `live: true`; they are invited only if the planner picks them. In S2, run the clock with **Step** during the live window and wait for their replies.
- A judge opens `t.me/RaktTraceDemoBot?start=staff_c_a` (or `staff_c_b`): that centre's cards go to their phone; `/reset` hands the centre back to the simulated staff. The centre's sim phone in the dashboard can always tap as that centre (a fallback).
- `/demo/reset` keeps linked people (donors, staff, family, coordinator) and gives them fresh history. A server restart forgets them.

## 5. Known limitations

- Benchmark numbers are from the synthetic world: show them as simulation results, never real-world evidence. False-done 0% is by construction.
- Only the essential benchmark tier exists (today vs rakttrace, nominal); broadcast, threshold, stress and calibration come after the rehearsal.
- Two demo-only phrases in the cache ("shaam ko 6 baje", "tonight after 9 PM") read as "now"; they are never drawn by the sim.
- Manual Telegram checks still pending (record in PROGRESS when done): S2 stepped with `/demo/step`; a live donor tap; a Hinglish reply with the LLM on and off; a linked vs an unlinked centre; donor and staff `/reset`; repeated `/start`.
