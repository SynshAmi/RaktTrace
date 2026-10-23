# RaktTrace: Progress

Read this first in every session. Update it after every phase: status + one log line.

Statuses: `TODO` · `DOING` · `DONE` · `CUT (reason)` · `BLOCKED (by what)`

## Now

| | |
|---|---|
| Current phase | 6 (Telegram + LLM, Aditya) · core next: 7 (baseline, benchmark, API) |
| Current step | 6.1 / 7.1 |
| Branch state | `main` = phase 5 · `phase` = main |
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
| 6 | Telegram + LLM | Aditya (parallel) | TODO | |
| 7 | Baseline, benchmark, API | Suryansh | TODO | |
| — | Frontend scaffold on mocks (alongside 1–7) | Antigravity, then Aditya | TODO | |
| 8 | Frontend core | Aditya | TODO | |
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
| | | | | | | | | | | |

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
