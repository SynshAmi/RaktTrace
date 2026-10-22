# RaktTrace: Implementation Plan

The step-by-step build, with a verification gate per phase. What to build is in `SPEC.md`; how it decides is in `AGENT.md`; stack, shapes and phases are in `BUILD.md`.

---

## How to use this plan

- Work one phase at a time, on the `phase` branch. Start each session: `PROGRESS.md` → this plan's current step → the BUILD/AGENT sections the step references.
- Each phase = 2–3 substeps (N.1–N.3) + a verification gate (N.V).
- **Gate rules:**
  - A phase is DONE only when its N.V passes. Never start the next phase with a failing gate.
  - If a test fails: fix and rerun. Never weaken or delete a test to make it pass. If a test contradicts the docs, stop and report.
  - If the same failure survives two fix cycles, stop and report (or apply the matching cut trigger in BUILD §6.3).
  - After a gate passes: update `PROGRESS.md` (status, current step, log line), commit on `phase`, merge into `main`.
- **References, not copies:** shapes = BUILD §5; interfaces = BUILD §5.4; constants and equations = AGENT §2–§5; scenarios = SPEC §5; copy = PRODUCT §5.

## Phase 0: Setup (before coding; mostly manual)

- **0.1** Telegram bot via BotFather (name, username, token, picture). A staff chat or group for "Centre B staff".
- **0.2** LLM keys for each chain entry. One JSON call per entry that reads "kal subah 8 baje aa jaunga". Record the results in PROGRESS. `.env` on both laptops (BUILD §7); Python 3.12, uv, Node, git, Claude Code installed.
- **0.3** Phrase bank `backend/rakt/sim/phrases.json` (Antigravity): 40 labelled replies (AGENT §9): 14 YES now, 8 YES later, 10 NO, 2 STOP, 6 UNCLEAR.

**0.V** Bot answers `/start` from a non-team phone; ≥ 2 LLM entries return valid JSON; `.env` complete; `phrases.json` valid with the exact counts.

## Phase 1: Foundation (BUILD §4–§5, AGENT §2, §9)

- **1.1** uv project, FastAPI app + `GET /api/health`. `config.py` with every AGENT §2 constant (same names and values, basis comments). `models.py` per BUILD §5.1–5.2, including `Button`, `Contact`, `Outgoing`, `Inbound`, `PleaDraft`, `ReplyRead`.
- **1.2** Store (per-lane and per-policy copies); sim clock + timer queue (step/advance in time order). §5.4 stubs: `router.deliver` → sim inbox; `loop.handle_inbound` / `loop.link_chat` no-ops; `llm.*` returning rule-fallback values.
- **1.3** World generator with common random numbers (AGENT §9: rescaled tonight factor; per-donor latent outcome keyed by donor id). Scenario loader + `s1`/`s2`/`s3` JSON (SPEC §5). Scenario data must make the SPEC outcomes reachable:
  - S1: Centre D's listing is older than A's, so the stock step asks B and A, not D; A answers "Some 1" before B answers "Reserve 2" (B is trimmed to 1).
  - S2: the scenario override adds enough eligible O+ apheresis-capable donors near Centre B that at least 12 pass every filter at t = 0 (realistic: centres keep apheresis donor lists).

**1.V** Tests:
- `test_config`: every §2 name and value; removed constants absent;
- `test_clock`: events fire in order; timers scheduled inside a jump fire; step = one event;
- `test_world_reproducible`;
- `test_latent_keyed_by_donor`;
- `test_factor_mean` (= 1.0);
- `test_group_mix` (± 3 points of DOMAIN_RULES §6);
- `test_scenarios_load`: S1 A listed 3 / true 1 (19 h), B 2 / 2 (fresh), D 1; S2 A 1 / 0 (15 h); S3 no O− PRBC within 40 km;
- `GET /api/health` returns 200.

Pass: all green.

## Phase 2: Domain rules (DOMAIN_RULES §2–§4, AGENT §4)

- **2.1** Compatibility + O− protection; eligibility E1–E11.
- **2.2** Travel time; donor and stock timing (`ready_at`, `on_time`, `latest_arrival`, `go_window`; `available_from` null-safe); `donors_can_help`; collection-centre choice.

**2.V** Tests: full red-cell table; SDP identical group only; O− hidden before L2; 89/90 and 119/120 days; unknown sex → 120; apheresis 48 h and 2 per week; PRBC can't meet a 4 h deadline; SDP can meet 16 h; go window < 20 min excluded. Pass: all green.

## Phase 3: P and stock first (AGENT §3, §5 Steps 1–2)

- **3.1** `agent/probability.py`: `p_at_least`; posterior over `LATENT_RATES` (yes → r; no or STOP → 1 − r; silent → (1 − r) + r·s(t)); source table; mixture P, P_firm, P_best; plug-in variant (`ESTIMATOR = "plugin"`).
- **3.2** Planner Steps 1–2: status; stock asks (parallel asks, keep in arrival order, trim, release); decision log; stock message templates (PRODUCT §5).
- **3.3** Loop handling for staff stock replies and timeouts; idempotent re-plan.

**3.V** Tests:
- `p_at_least` sanity values;
- posterior = prior at 0 replies; shifts up on yeses, down on noes and STOP; silence weaker than a no;
- P_firm identical under all rates;
- S1 to SECURED with 0 donor invites: B and A asked, D not; A 1 + B 1 kept;
- re-plan twice → no new actions.

Pass: all green.

## Phase 4: Donors (AGENT §5 Steps 3–5, §5.1)

- **4.1** Ranking: filters, order, `why`. Wave sizing per AGENT §5 Step 3 (D1), as an internal helper in `agent/planner.py`: argmin of J over k ≤ k_cap; unreachable → K; send min(k*, `WAVE_CAP`). Wave guards; slack wait rule; flags `ESTIMATOR` / `SIZING` / `WAIT_RULE` (lookahead not implemented yet; default slack).
- **4.2** Replies: buttons + `llm.read_reply` (stub/rules for now); TOO_LATE; ACTIVE / STANDBY (P_firm-driven), RELEASED; booking code; staff visit taps (Arrived / Didn't show → Collected / Deferred); promotion (`OMW` → ACTIVE; `CANT` or 15 min → next standby); donor messages.
- **4.3** Edge cases: rest rules, `REQUEST_DONOR_CAP`, quiet hours (> 24 h left only), O− before L2, NO_REPLY status on timeout, demo-donor ranking.

**4.V** Tests:
- need-2 and need-3 requests invite > 0;
- argmin matches a hand-computed table;
- higher τ never increases k*;
- unreachable target invites K, capped per wave;
- `WAVE_CAP`, `REQUEST_DONOR_CAP` and O− protection hold;
- re-plan is idempotent;
- S2: 0 invites at t = 0; first wave = min(k*, `WAVE_CAP`) as computed by the planner, which is 10 in S2 (P after the wave is reported, not asserted to a fixed value); "kal 11:55" → TOO_LATE; 1 ACTIVE + 2 STANDBY → P_firm ≈ 0.931, COVERED; deferral → OPEN → promotion → SECURED.

Pass: all green (otherwise the cut trigger in BUILD §6.3).

## Phase 5: Closing and escalation (AGENT §5 Step 6, §6; PRODUCT §3.4–3.7)

- **5.1** SECURED / FULFILLED: stand-down, family messages, `staff_ready` timers, FAILED_TEST reopens; cancel.
- **5.2** Escalation: L1 (radius jump), L2 triggers + call list + `llm.write_brief` (template fallback), FAILED at the deadline; staff reminder and overdue escalation (`STAFF_GRACE_MIN`).
- **5.3** Duplicate merge (fields unchanged; `{merged_into}`).

**5.V** Tests: S1, S2, S3 end to end; S3 has 0 invites and L2 within 5 sim minutes, FAILED at the deadline; overdue staff tap → reminder, then L2; duplicate → `merged_into`; cancel releases holds and donors. Pass: all green.

## Phase 6: Telegram and LLM (Aditya; BUILD §5.4, AGENT §7; can run in parallel after phase 1)

- **6.1** LLM client chain (timeout; 429 / 5xx / bad JSON → next; all fail → rules); `set_enabled` / `status`; rules reader; `read_plea` / `read_reply` / `write_brief` returning `PleaDraft` / `ReplyRead` / str; never raise.
- **6.2** `router.deliver` (Telegram or sim; failed sends mirror to the sim inbox); `telegram_bot` (long polling; `/start` deep links → `loop.link_chat`; buttons and free text → `Inbound` → `loop.handle_inbound`).
- **6.3** `phrase_cache.json`: run the LLM once over `phrases.json`; offline tests use the cache.

**6.V**
- Tests: rules-reader accuracy on the phrase bank reported; LLM (cached) ≥ rules; network off → no exception, fallback used; LLM toggle off → `read_by = "rules"`.
- Manual: a `/start` donor link, a button tap and a Hinglish free-text reply reach `handle_inbound`; once phase 4 is merged, they move a request, with the LLM on and off.

Pass: all green + manual checks noted in PROGRESS.

## Phase 7: Baseline, benchmark, API (AGENT §8, §10; BUILD §5.3)

- **7.1** Today's-workflow policy on a lane copy; truth at the deadline.
- **7.2** Benchmark essential tier: common random numbers, today vs rakttrace, essential metrics, paired 95% CIs, cache to `backend/bench/`. The should/optional tiers come after phase 10 (BUILD §6.3).
- **7.3** Every BUILD §5.3 endpoint (requests, baseline, decisions, sim phones, demo controls, llm, benchmark).

**7.V** Tests:
- same seed → identical results;
- both policies read the same latent tuple per donor;
- rakttrace false_done = 0;
- paired CIs present; results file written to `backend/bench/`;
- S1 baseline SAYS_FULFILLED with 1 of 2 ready; S2 baseline SAYS_FULFILLED with 0 of 1;
- each endpoint matches its §5.3 shape;
- benchmark runtime recorded in PROGRESS.

Pass: all green.

## Phase 8: Frontend core (on the live API)

- **8.1** Switch the Antigravity scaffold from mocks to the live API. Request view: two lanes, P gauge, unit ladder, decision log.
- **8.2** Controls (reset, step, advance) and 2 s polling.

**8.V** S1 runs from the dashboard and both lanes update; no console errors; `npm run build` succeeds.

## Phase 9: Frontend finish

- **9.1** New request (paste → draft → confirm; merged notice), phones panel, escalation banner + brief, LLM toggle.
- **9.2** Benchmark page (optional sections only if present).

**9.V** S2 runs fully from the dashboard with a real Telegram donor and staff taps; S3 shows the banner and brief; toggling the LLM changes `read_by`. Pass: all checks noted in PROGRESS.

## Phase 10: Rehearsal gate

- **10.1** Full `PITCH.md` §2 run on the laptop.
- **10.2** Record the backup video.

**10.V** One clean run with no code changes in between; PROGRESS shows "REHEARSAL 1 PASSED".

## After phase 10 (optional, in this order)

1. Benchmark should/optional tiers (AGENT §10);
2. Break-it button (FEATURES.md, feature 1);
3. Plea-still-active check (FEATURES.md, feature 2);
4. Stock-wait lookahead (`WAIT_RULE = "lookahead"`, AGENT §5 Step 3).

**Mini gate for each:** its own tests pass, and S1–S3 end to end and the essential benchmark still pass.
