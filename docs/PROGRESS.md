# RaktTrace: Progress

Read this first in every session. Update it after every phase: status + one log line.

Statuses: `TODO` · `DOING` · `DONE` · `CUT (reason)` · `BLOCKED (by what)`

## Now

| | |
|---|---|
| Current phase | 9 (frontend finish) |
| Current step | 9.1 |
| Branch state | `main` = phase 8 · `phase` = main |
| Publishing | Push normally to `origin`; freeze at 18:00 IST, 24 Oct 2026 (SPEC §8) |
| Build start / end | `__:__` / `__:__` |
| LLM chain (after phase 0 tests) | `groq:qwen/qwen3.8-27b,gemini:gemini-3.5-flash-lite` |

## Phases

| Phase | Title | Owner | Status | Note |
|---|---|---|---|---|
| 0 | Setup | both | DONE | Gate 0.V passed; bot, phrase bank, LLM verified |
| 1 | Foundation | Suryansh | DONE | Gate 1.V passed: 29 tests green; app starts, `/api/health` 200 |
| 2 | Domain rules | Suryansh | DONE | Gate 2.V passed: 96 tests green (67 new) |
| 3 | Stock first | Suryansh | DONE | Gate 3.V passed: 130 tests green (34 new) |
| 4 | Donors | Suryansh | DONE | Gate 4.V passed: 192 tests green (62 new); lookahead stretch not built |
| 5 | Closing + escalation | Suryansh | DONE | Gate 5.V passed: 214 tests green (20 new) |
| 6 | Telegram + LLM | Aditya (parallel); built by Suryansh (Claude) | DONE | 264 passed, 0 skipped; cached LLM 40/40 vs rules 27/40. Manual on real Telegram: onboarding, Centre B staff link, `/reset` passed. Still pending for integration/rehearsal (needs `/demo/step`): a live button tap and a Hinglish reply moving a request, LLM on and off |
| 7 | Baseline, benchmark, API | Suryansh | DONE | Gate 7.V passed: 295 tests green; benchmark seed 2026, N = 500 in 23.7 s; manual Telegram checks pending (below) |
| — | Frontend scaffold on mocks (alongside 1–7) | Antigravity, then Aditya | CUT (never built; phase 8 started directly on the live API) | |
| 8 | Frontend core | Aditya (built with Claude Code) | DONE | Gate 8.V passed: S1 run from the dashboard (Reset, Step, Auto, +15 min, +1 h), both lanes update, no console errors, `npm run build` ok; backend 295 passed |
| 9 | Frontend finish | both | TODO | |
| 10 | Rehearsal (gate) | both | TODO | |

## Features (after phase 10 only)

| # | Feature | Status |
|---|---|---|
| 1 | Break-it button | TODO |
| 2 | Plea-still-active check | TODO |

## Phase 0 results

| Check | Result |
|---|---|
| Bot username | `RaktTraceDemoBot` |
| `/start` from a non-team phone | PASS (verified: answered /start with welcome card) |
| Staff chat linked | PENDING (to link on bot startup in Phase 6 / demo) |
| LLM entry 1 (name, JSON ok?, latency) | `groq:qwen/qwen3.8-27b` · JSON ok · 0.31s |
| LLM entry 2 | `gemini:gemini-3.5-flash-lite` · JSON ok · 1.17s |
| LLM entry 3 | `openrouter` (not configured / key absent) |
| LLM entry 4 | — |

## Benchmark (fill in after phase 7 and on stage)

| Run | policy | regime | n | seed | on_time | donors_messaged | zero_donor | warned_early | false_done | CI (on_time diff) |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | today | nominal | 500 | 2026 | 50.0% | 8.84 | 48.8% | 0.0% | 47.4% | — |
| 1 | rakttrace (cached LLM) | nominal | 500 | 2026 | 59.8% | 5.11 | 35.2% | 100.0% (median 16.56 h) | 0.0% | +9.8 pts [5.9, 13.7] |
| 2 | rakttrace (rules only) | nominal | 500 | 2026 | 56.4% | 5.31 | 35.2% | 100% (median 16.53 h) | 0.0% | +6.4 pts [2.7, 10.1] |

## Log

`date time · phase · who · note`

- 22 Oct · docs · both · Final doc set created (SPEC, PRODUCT, AGENT, DOMAIN_RULES, BUILD, FEATURES, PITCH, PROGRESS, CLAUDE.md, README).
- 23 Oct · docs · Suryansh · docs: final design D1–D5 applied.
- 23 Oct · docs · Suryansh · docs: IMPLEMENTATION_PLAN.md created; BUILD §6 slimmed.
- 23 Oct · docs · Suryansh · docs v1.0 locked.
- 23 Oct · phase 0 · Antigravity · phrase bank created & verified (40 items); Groq + Gemini verified; toolchain verified; bot username corrected.
- 23 Oct · phase 0 · both · Gate 0.V passed: bot answered /start from non-team phone; phrase bank (40) & LLM chain verified. Phase 0 DONE.
- 23 Oct · phase 1 · Suryansh (Claude) · Gate 1.V passed (`uv run pytest -q`: 29 passed). Built config (every AGENT §2 constant, checked against the doc), models (BUILD §5.1–5.2), store with lane copies, sim clock + timer queue, §5.4 stubs (router → sim inbox, loop no-ops, llm rule-fallback values), seeded world with common random numbers (rescaled tonight factor, latent outcome keyed by donor id), S1–S3 scenario JSON + loader, `GET /api/health`. Sim-only shape numbers (listing chance, units, female share, days since donation) are in config labelled "Assumption (sim only)". Later yeses use the next-morning phrases (7–12 h) so the true time matches the text; STOP/UNCLEAR phrases are not drawn as latent replies.
- 23 Oct · phase 2 · Suryansh (Claude) · Gate 2.V passed (`uv run pytest -q`: 96 passed). `domain/blood.py` (red-cell table, SDP identical only, O− hidden before L2), `domain/eligibility.py` (E1–E11 at the donation time; E7 counted over rolling 7-day and 365-day windows), `domain/geo.py` (haversine moved here from `sim/world.py`; travel time), `domain/timing.py` (donor/stock ready_at, on_time, latest_arrival, go window, invitable ≥ 20 min, donors_can_help, collection-centre choice). Eligibility numbers (DOMAIN_RULES §2) and AGENT §4's 15-min reply lag and 20-min go window added to config. Check on scenario data: S1/S3 donors can't help; S2 has 18 candidates within 5 km under the phase 2 filters.
- 23 Oct · phase 3 · Suryansh (Claude) · Gate 3.V passed (`uv run pytest -q`: 130 passed). `agent/probability.py` (p_at_least, posterior over LATENT_RATES with STOP = no, source table, mixture P, P_firm, P_best, plug-in flag), `agent/planner.py` Steps 1–2 (status, parallel stock asks exact → fresher → nearer, keep in arrival order, trim, release), `agent/messages.py` (staff_hold, count picker, staff_release), `agent/loop.py` (start, replan + decision log, stock replies ALL/SOME/N{k}/NONE, timeouts → EXPIRED), `sim/bots.py` (sim staff answer from the pre-drawn truth). Approved plan change: S1 under AGENT §5 Step 2 asks D after A's "Some 1" (stock alone 85% < 90%) and releases it when B confirms; plan 1.3 and gate 3.V reworded to match ("B and A in parallel at t = 0, D not"). Added `staff_hold_count` to PRODUCT §5.
- 23 Oct · phase 4 · Suryansh (Claude) · Gate 4.V passed (`uv run pytest -q`: 192 passed). `agent/ranking.py` (§5.1 filters + order + why; demo donors rank 2nd, no override), planner Step 3 (slack wait rule, wave guards, expected-cost sizing `choose_k`/`size_wave` with SIZING cost|target|all, pool_exhausted, collection centre fixed on the first wave), Step 4 roles (TOO_LATE / ACTIVE / STANDBY / RELEASED), Step 5 promotion (OMW, CANT, 15-min timeout); loop: invites, donor buttons and text, visit taps (Arrived / Didn't show → Collected / Deferred), NO_REPLY timeout; `llm/rules.py` rule reader (no LLM calls); sim bots for donors, promoted standbys and centre visit taps. S2 sim run: wait at 22:40 → A none at 22:55 → wave of 10 (P 0% → 69%) → 1 active + 2 standby COVERED by 23:07 → "kal 11:55" TOO_LATE → deferral 01:03 OPEN → promotion → SECURED 03:15. Agreed doc change: AGENT §7.2 "kal/tomorrow + a time" counts as YES (SPEC §9 line). S2 script phrases #3/#6 swapped for rule-readable ones of the same label. Added `donor_not_needed` copy to PRODUCT §5. Not built: WAIT_RULE = "lookahead" (stretch; raises if set), Step 6 close/stand-down, escalation (phase 5), LLM chain and Telegram (phase 6).
- 23 Oct · docs · Suryansh (Claude) · Publishing policy updated per the organiser's clarification: normal pushes allowed; hard freeze 18:00 IST, 24 Oct 2026 (SPEC §8, BUILD §3). Repo published to origin (main, phase).
- 23 Oct · phase 5 · Suryansh (Claude) · Gate 5.V passed (`uv run pytest -q`: 214 passed). `agent/escalation.py` (L1 widen, L2 alert with brief + call list, FAILED at the deadline, P_best), planner Step 6 (SECURED: stand down unreplied/standby donors, release holds, family_secured once; FULFILLED only when staff tap Ready for every unit, family_fulfilled once) and Step 7; loop: deadline/halftime timers, staff_ready cards, reminder at expected + 30 and overdue → L2 at + 60, Ready / Failed testing taps (FAILED_TEST reopens), cancel, duplicate merge (`create_request` → merged_into); brief template fallback in `llm/rules.py` (no LLM calls); sim staff confirm ready units; scenarios get a sim family phone. S1: SECURED 18:15 → FULFILLED 19:20, 0 donors. S2: no escalation, SECURED 03:15 → FULFILLED 09:32. S3: 40 km + L2 at 20:00, FAILED 02:00, 0 invites. Agreed doc change: AGENT §6 L1 trigger (SPEC §9 line). Added `donor_closed` copy to PRODUCT §5. A reserved unit tapped "Failed testing" becomes NONE (no stock-failure status exists). Requests made with `create_request` have no pre-drawn sim outcomes yet (phase 7 API wires that).
- 23 Oct · audit · Suryansh (Claude) · Pre-phase-6 corrections (maintenance step, not a phase; `uv run pytest -q`: 226 passed, 12 new in `tests/test_audit_fixes.py`). C1: the scenario donor script now applies only to the scenario's own request, and live-linked donors never get simulated outcomes (`sim/bots.latent_for`). C2: a released hold or a failed reserved unit no longer blocks re-asking a centre with unused listed units; a centre that said None or didn't answer isn't asked again; L1 waits while a stock answer is awaited (`planner.blocked_centres`, `units_left`, `store.failed_reservations`). C3/C4 documented and tested (failed stock unit → NONE, no longer supply; SECURED but unconfirmed → reminders, L2, FAILED at the deadline). C5: new-request outcomes assigned to phase 7.4. C6: live Telegram design locked in PRODUCT §2.2 / BUILD §5.4 / plan 6.2, 6.4, 6.V (not built). C7: empty CLAUDE.md heading removed. Phase 6 not started.
- 23 Oct · phase 6 · Suryansh (Claude) · Built, gate open. `llm/client.py` (chain from LLM_CHAIN, timeout, any failure → next entry, health), `llm/__init__.py` (cache → chain → rules for replies; LLM → rules plea parser; LLM → template brief; never raise), `llm/rules.py` plea parser, `sim/phrase_cache.py` (builder, not run: it calls the LLM), `agent/live.py` (registry outside AppState, 6 S2 templates reused, one identity per account, one role per chat, STOP kept across resets until re-join, `attach` after reset, rakttrace lane only), `channels/telegram_bot.py` (onboarding Join / Create my profile, staff/family/coord deep links in private chat, /stop, taps and text → `handle_inbound` in a worker thread under `store.lock`), router sends live contacts to Telegram and falls back to the sim phone, `loop.reset_scenario`. Tests: `uv run pytest -q` → 255 passed, 1 skipped. Rules reader on the phrase bank: 27 right, 0 wrong, 13 unclear of 40. Open for the gate: build `phrase_cache.json` (one LLM run) and the manual checks (a /start join, a button tap and a Hinglish reply from a real phone moving S2, LLM on and off; staff link for Centre B).
- 23 Oct · phase 6 · Suryansh (Claude) · Manual checks by the team: donor onboarding and Aditya's Centre B staff link work on real Telegram. Added `/reset` (donor profile only; withdraws from open requests through the normal lifecycle; STOP kept; 8 tests). Phrase cache built in one bounded run: 40 calls attempted, 40 succeeded (all Groq qwen3.8-27b), 0 failed, 0 rate-limited; quota at start 1000 requests/day (999 left), 8000 tokens/min. `phrase_cache.json` has 40 entries, all intents match the labels. Offline: cached LLM 40 right / 0 wrong / 0 unclear vs rules 27 / 0 / 13. `uv run pytest -q` → 264 passed. Gate still open on the manual 'tap + Hinglish reply moves a request' check.
- 23 Oct · phase 6 · team + Suryansh (Claude) · Manual gate: on a real Telegram phone, a donor with an existing synthetic profile sent `/reset` and got the expected confirmation with the two onboarding choices (Join the live demo / Create my profile). Backend restarted on `51e9c28` for this check (in-memory registry and S2 clock reset). `uv run pytest -q` → 264 passed, 0 skipped; `sim/phrase_cache.json` tracked (40 entries). Phase 6 closed by team decision with these caveats, not verified by the `/reset` check: (1) a live button tap and a Hinglish free-text reply moving a request, with the LLM on and off, wait for phase 7's `/demo/step` and the rehearsal; (2) the registry is in memory, so a server restart drops live links; (3) phase 7 must hold `store.lock` when it changes state. Agreed for phase 7 (not built): `/start` from an existing donor confirms the profile instead of showing the onboarding choices (`/reset` stays the way to start over); the sim keeps working without Telegram-linked staff while linked staff get live cards.
- 23 Oct · phase 7 · Suryansh (Claude) · Gate 7.V passed (`uv run pytest -q`: 295 passed, 0 skipped). `baseline/policy.py` (today's workflow on the today lane, same outcomes, truth at the deadline: S1 says fulfilled with 1 of 2 ready, S2 with 0 of 1), `sim/benchmark.py` (common random numbers, essential metrics, paired 95% CIs; seed 2026, N = 500 in 23.7 s → `backend/bench/results_nominal_2026.json`), every BUILD §5.3 endpoint plus `GET /benchmark/cached`, the auto clock, `store.lock` on every endpoint (LLM reads outside it), new requests with their own outcomes (7.4), hybrid staff routing (handover on link and `/reset`, simulated staff take failed Telegram cards, no double processing), `/start` refinements, staff `/reset`, stale-card guard. Fixed on the way: benchmark truth used deadline − margin (now: ready by the deadline, AGENT §10); the LLM had returned 'now' replies as clock times (22:40) and the cache stored them as times, so they were misapplied at other hours (now normalised locally, no new API calls; `READ_NOW_WINDOW_MIN`). Results are simulated, not real-world evidence. Manual checks still pending (need phones + the demo clock): S2 stepped with `/demo/step`; a live donor button tap; a Hinglish reply with the LLM on and off; linked vs unlinked centre routing; donor and staff `/reset` scope; repeated `/start`.
- 24 Oct · phase 8 · Aditya (Claude) · Gate 8.V passed. `frontend/` created (React 19 + Vite 8 + TypeScript 7 + Tailwind 4; no mock scaffold existed, so it went straight onto the live API). `api.ts` holds every call; 2 s polling, paused while a control runs (a reset would otherwise 404 the old request). Request view: status word from `status` with a one-line explanation read from the status, ladder and flags; "x of n confirmed ready by staff" shown apart from the P gauge (an estimate, never coloured as success) with the 90% line and P_firm; unit ladder; the latest consequential decision in full plus every decision on demand (the planner's own sentences); donors/stock tabs, closed by default; Today's workflow collapsed into a labelled Compare control that opens a ~30% side column (team agreement, PRODUCT §2.1). Aditya's palette with green = positive, red = negative, soft yellow/ochre = neutral; dark and light mode; Atkinson Hyperlegible Next font, self-hosted. Checked in the browser at 1440×900: S1 reset → SECURED 18:15 (0 of 2 confirmed, "waiting for staff") → FULFILLED 19:20 (2 of 2) while today's workflow says fulfilled with 1 of 2 actually ready at the deadline; S2 mid-run shows COVERED with 0 of 1 confirmed. Backend unchanged: `uv run pytest -q` → 295 passed. Not in phase 8 (phase 9.1/9.2): new request, phones panel, escalation banner, LLM toggle, benchmark page. Manual Telegram checks still pending as listed under phase 7.
