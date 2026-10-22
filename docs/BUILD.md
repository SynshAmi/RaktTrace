# RaktTrace: Build Guide

Stack, folders, data shapes, coding rules, git, and the phases. What to build is in `SPEC.md`; how it decides is in `AGENT.md`.

---

## 1. Stack

| Part | Choice |
|---|---|
| Backend | Python 3.12 · **uv** · FastAPI + Uvicorn · Pydantic v2 · pytest |
| Telegram | `python-telegram-bot` (async, long polling, inline buttons; no public URL needed) |
| LLM | `openai` Python SDK pointed at any OpenAI-compatible provider, JSON output, fallback chain |
| Storage | In-memory, reset from seed. No database. |
| Frontend | React + Vite + TypeScript · Tailwind · Recharts · plain `fetch` with 2 s polling |
| Running | One laptop: backend on `:8000`, Vite dev server proxying `/api`. Phone hotspot as backup internet. |

Versions: latest stable on the day, pinned by `uv.lock` and `package-lock.json`.

## 2. Coding rules

1. **Clean, simple code over clever code.** If a simpler version works, use it.
2. **Minimal comments.** Only where the *why* isn't obvious. Names should explain the *what*.
3. **Clear organisation.** One responsibility per module, following the folder layout in §4. No dumping-ground files.
4. **Every number lives in `config.py`**, with a one-line basis comment.
5. **The planner decides; the LLM reads.** No decision logic inside LLM code, bot code or API routes.
6. **Pure logic, effects at the edges.** `domain/` and `agent/` are plain functions with no I/O. Only `channels/`, `llm/` and `api/` talk to the outside.
7. **Never crash the demo.** A Telegram or LLM failure is logged and falls back (rule parser, simulated channel).
8. **Test what matters:** domain rules, planner and scenarios S1–S3. No tests for glue code.
9. **Names match the docs:** statuses, fields and endpoints exactly as written here.
10. **No secrets or real personal data in git.** Keys in `.env`; synthetic donors only.
11. **Keep it runnable.** The app works after every step; no half-built pieces left lying around.
12. If code and docs disagree, fix whichever is wrong, in the same commit.

## 3. Git

- **`main`:** verified code only.
- **`phase`:** the working branch. Build the current phase on `phase`. When its *Done when* passes, merge into `main` and carry on with the next phase on `phase`.
- Commit messages: `phase 4: donor waves and promotion`.

## 4. Folder layout

```
rakttrace/
├── CLAUDE.md
├── README.md
├── .env.example
├── docs/
├── backend/
│   ├── pyproject.toml
│   ├── rakt/
│   │   ├── main.py            # app startup: load scenario, start bot, routes
│   │   ├── config.py          # settings from .env + every number from AGENT.md §2
│   │   ├── models.py          # data model (§5)
│   │   ├── store.py           # in-memory state + lane copies
│   │   ├── clock.py           # sim clock + timer queue
│   │   ├── domain/            # blood.py · eligibility.py · geo.py · timing.py
│   │   ├── agent/             # probability.py · ranking.py · planner.py · escalation.py · loop.py · messages.py
│   │   ├── baseline/          # policy.py (today's workflow)
│   │   ├── llm/               # client.py (chain) · reader.py (plea, reply, brief) · rules.py (fallback)
│   │   ├── channels/          # router.py · telegram_bot.py · simulated.py
│   │   ├── sim/               # world.py · scenarios.py · bots.py · benchmark.py · phrases.py · phrase_cache.json
│   │   └── api/               # requests.py · sim.py · demo.py · benchmark.py · llm.py
│   ├── scenarios/             # s1_surgery_tonight.json · s2_dengue_sdp.json · s3_no_way_in_time.json
│   └── tests/
└── frontend/
    └── src/                   # pages: NewRequest, RequestView, Benchmark; components: Lane, Gauge, Ladder, DecisionLog, Phones, Controls
```

## 5. Data model

Times are ISO-8601 with `+05:30`. Enums are UPPER_SNAKE. Fields are `snake_case`, used as-is by the frontend.

### 5.1 Enums
```
BloodGroup        O_POS | O_NEG | A_POS | A_NEG | B_POS | B_NEG | AB_POS | AB_NEG
Product           PRBC | SDP
RequestStatus     OPEN | COVERED | SECURED | FULFILLED | FAILED | CANCELLED
BaselineStatus    SEARCHING | SAYS_FULFILLED
ReservationStatus PENDING | RESERVED | READY | NONE | EXPIRED | RELEASED
PledgeStatus      INVITED | NO_REPLY | DECLINED | TOO_LATE | ACTIVE | STANDBY | ARRIVED | COLLECTED
                  | READY | DEFERRED | NO_SHOW | FAILED_TEST | RELEASED | OPTED_OUT
Intent            YES | NO | STOP | UNCLEAR
Channel           sim | telegram
```
Labels: `O_POS` → "O+", …; `PRBC` → "Red cells", `SDP` → "Platelets (SDP)".

### 5.2 Core objects (backend)
```python
Hospital:     id, name, area, lat, lon, centre_id | None
Centre:       id, name, area, address, lat, lon, phone, accepts_donors, apheresis, contact: Contact
Stock:        centre_id, product, group, listed_units, listed_at, true_units      # true_units hidden from API/agent
Contact:      name, channel, chat_id | phone
Donor:        id, display_name, group, sex, age, weight_kg, lat, lon, area, contact,
              consent, opted_out, apheresis_ok, last_whole_blood_at, apheresis_dates,
              donation_verified, deferred_until, invites: list[datetime], telegram_demo: bool
Request:      id, group, product, units, hospital_id, deadline_at, created_at, status,
              escalation_level, radius_km, collection_centre_id, family: Contact | None, brief: str | None
Reservation:  id, request_id, centre_id, group, units_asked, units_reserved, status, listed_at, asked_at, ready_at
Pledge:       id, request_id, donor_id, status, wave, invited_at, replied_at, reply_text,
              available_from, booking_code, ready_at, why
Decision:     id, request_id, at, trigger, p_before, p_after, status, actions: list[str], summary
Message:      id, at, direction (out|in), channel, to_name, request_id, kind, body, buttons, read_by (llm|rules|button)
BaselineState: request_id, status, said_fulfilled_at, found_units, donors_messaged, timeline: list[str]
```

### 5.3 API (all under `/api`)

**Reference**
```
GET  /health                 → {ok, now, llm: "on"|"off", telegram: "ok"|"off"}
GET  /hospitals              → [{id, name, area}]
GET  /centres                → [{id, name, area, apheresis, stock: [{product, group, listed_units, listed_age_min}]}]
```

**Requests**
```
POST /requests/parse   {text}
  → {draft: {group, product, units, hospital_id, deadline_at}, missing: [...], confidence, read_by: "llm"|"rules"}

POST /requests         {group, product, units, hospital_id, deadline_at, family?: "telegram"|"sim"}
  # family "telegram": the next chat that opens ?start=family is linked; "sim": a sim phone "Family" is created. No phone numbers are entered.
  → RequestView   or   {merged_into: "RT-4821"}

GET  /requests         → [{id, group, product, units, status, p, deadline_at, hospital_name, escalation_level}]
GET  /requests/{id}    → RequestView
GET  /requests/{id}/baseline → BaselineView
GET  /requests/{id}/decisions → [Decision]
POST /requests/{id}/cancel    → RequestView
```

**RequestView**
```json
{
  "id": "RT-4821", "status": "OPEN", "group": "O_POS", "product": "SDP", "units": 1,
  "hospital": {"id": "h_city", "name": "City General Hospital", "area": "Jayanagar"},
  "collection_centre": {"id": "c_b", "name": "Centre B"},
  "created_at": "...", "deadline_at": "...", "now": "...",
  "p": 0.91, "p_firm": 0.85, "target": 0.9,
  "units_ladder": {"found": 1, "said_yes": 1, "ready_in_time": 1, "collected_or_reserved": 0, "confirmed": 0},
  "stock": [{"reservation_id": "res_1", "centre": "Centre A", "units_asked": 1, "units_reserved": 0,
             "status": "NONE", "listed_age_min": 900, "p": 0.0}],
  "donors": [{"pledge_id": "pl_3", "name": "Rahul S.", "group": "O_POS", "km": 3.2, "status": "ACTIVE",
              "p": 0.675, "booking_code": "4821", "ready_at": "...", "why": "O+ exact · 3.2 km · verified",
              "reply_text": "haan abhi aa sakta hoon", "read_by": "llm"}],
  "counts": {"messaged": 11, "yes": 2, "no": 3, "silent": 6, "active": 1, "standby": 1},
  "escalation": {"level": 2, "brief": "…", "call_list": [{"centre": "Centre F", "phone": "+91 99999 00006", "note": "lists 2 O− (8 h old)"}]},
  "flags": {"donors_can_help": true, "waiting_for_stock": false}
}
```

**BaselineView**
```json
{"request_id": "RT-4821", "status": "SAYS_FULFILLED", "said_fulfilled_at": "...",
 "donors_messaged": 10, "found_units": 0,
 "timeline": ["21:40 Listing shows 1 at Centre A: blood found", "22:25 Centre A has 0", "..."],
 "truth_at_deadline": {"units_ready": 0, "units": 1}}
```
`truth_at_deadline` is null until the deadline passes (or always shown in the benchmark).

**Simulated phones**
```
GET  /sim/phones               → [{id, name, role: "donor"|"staff"|"family", unread, last_at}]
GET  /sim/phones/{id}/messages → [Message]
POST /sim/reply                {phone_id, button_id?, text?} → {ok}
```

**Demo controls**
```
GET  /demo/scenarios     → [{id, title}]
POST /demo/reset         {scenario} → {now, request_id | null}
GET  /demo/clock         → {now, auto: bool}
POST /demo/step          → {now, event}          # jump to the next timer/script event and process it
POST /demo/advance       {minutes} → {now}       # processes every event in order
POST /demo/auto          {on: bool} → {auto}     # 1 sim minute per real second
```

**LLM and benchmark**
```
GET  /llm                → {enabled, chain: [{name, healthy}]}
POST /llm                {enabled: bool} → same

POST /benchmark          {n: 500, seed: 7, reader: "llm"|"rules"}
  → {n, by_product: {...}, today: Metrics, rakttrace: Metrics}
Metrics = {on_time_pct, false_done_pct, donors_messaged, zero_donor_pct, warned_early_pct, median_warning_h}
```

**Telegram button ids**
| Pattern | Who |
|---|---|
| `P:{pledge_id}:YES` · `NO` · `STOP` · `OMW` · `CANT` · `OK` | Donor |
| `R:{reservation_id}:ALL` · `SOME` · `NONE` · `N{k}` | Staff, stock |
| `V:{pledge_id}:ARRIVED` · `NOSHOW` · `COLLECTED` · `DEFERRED` | Staff, visit |
| `D:P:{pledge_id}:READY` · `FAILED`, `D:R:{reservation_id}:READY` · `FAILED` | Staff, ready |

Simulated phones use the same ids.

## 6. Phases

**Phase 0 (setup) is done before the event.** Phases 1–7 are backend. During phases 1–7, Aditya works on **frontend design only** (screens, layout, colours, references). Phases 8–9 build the frontend straight on the real API. Phase 10 is the gate.

| Phase | Build | Done when |
|---|---|---|
| **0. Setup** | Telegram bot via BotFather (name, username, token, picture). A second Telegram account or group for "Centre B staff". LLM keys for each chain entry, each tested with one JSON call that reads "kal subah 8 baje aa jaunga". `.env` on both laptops. Python 3.12, uv, Node, git, Claude Code installed. | Bot replies to `/start` from a non-team phone; at least 2 LLM entries return valid JSON; `.env` complete |
| **1. Foundation** | Project setup, `config.py`, `models.py`, store, sim clock + timer queue, seeded world generator (places, stock, donors), scenario loader | App starts; S1 loads; Step moves the clock |
| **2. Domain rules** | Compatibility, O− protection, eligibility E1–E11, travel time, timing checks, `donors_can_help` | Tests: compatibility table, 90/120-day rule, "PRBC can't make a 4 h deadline", "SDP can make 16 h" |
| **3. Stock first** | P (sources + DP + `r̂`), stock step, wait-or-invite rule, reservations with release of extras, decision log | Test: S1 → 0 donors, A 1 + B 1 reserved, SECURED |
| **4. Donors** | Ranking + filters, waves to 90%, rest rules, reply handling (button + rules reader), ACTIVE/STANDBY, TOO_LATE, promotion, booking codes, message templates | Test: S2 reaches SECURED via a promotion; "kal 11:55" counted as too late |
| **5. Closing + escalation** | SECURED/FULFILLED, stand-down, family messages, staff reminders, L1/L2/FAILED, call list, duplicate merge, cancel | Tests: S1–S3 end to end; S3 has 0 invites and L2 within 5 sim minutes |
| **6. Telegram + LLM** | Bot (deep-link roles, inline buttons, free text), router (Telegram or sim), LLM chain client, plea reader, reply reader, brief writer, toggle, fallbacks | A Telegram tap and a Hinglish reply move a request; the same works with the LLM off; killing the network doesn't crash anything |
| **7. Baseline, benchmark, API** | Today's-workflow policy, phrase bank + cache, benchmark, every endpoint in §5.3 | `POST /benchmark` returns both metric sets; every endpoint matches its shape |
| **8. Frontend core** | Request view (two lanes, gauge, ladder, decision log), controls (reset, step, advance, auto) | S1 runs from the dashboard with both lanes updating |
| **9. Frontend finish** | New request (paste → draft → confirm), phones panel, escalation banner + brief, LLM toggle, benchmark page, phone-width layout | S2 runs fully from the dashboard with a real Telegram donor and staff |
| **10. Rehearsal (gate)** | Full demo from `PITCH.md` §2 | One clean run with no code changes; recorded as the backup video |

After phase 10: `FEATURES.md`, in order. Each feature merges only if S1–S3 and the benchmark still work.

**If behind schedule, cut in this order:**
1. auto-play;
2. benchmark split by product;
3. phone-width layout;
4. brief by LLM (use the template instead);
5. plea parsing by LLM (use the form).

Never cut anything on the SPEC's never-cut list.

## 7. Running

```bash
cd backend && uv sync && uv run uvicorn rakt.main:app --reload     # API + bot on :8000
cd backend && uv run pytest -q                                     # tests
cd frontend && npm install && npm run dev                          # dashboard on :5173
```

### `.env.example`
```
TELEGRAM_BOT_TOKEN=
TELEGRAM_BOT_USERNAME=
LLM_ENABLED=true
LLM_CHAIN=groq:<model>,groq:<model>,gemini:<model>,openrouter:<model>
GROQ_API_KEY=
GEMINI_API_KEY=
OPENROUTER_API_KEY=
DEFAULT_SCENARIO=s2_dengue_sdp
RANDOM_SEED=42
```

## 8. Demo-day checklist

- Laptop charged; hotspot ready; `.env` present; `uv sync` and `npm install` done.
- Bot QR code on the pitch slide; tested from a phone that isn't on the team.
- Aditya's Telegram linked as Centre B staff; a family chat linked.
- Reset S2 just before going on stage.
- Backup video ready to play.
