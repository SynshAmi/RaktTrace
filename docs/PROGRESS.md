# RaktTrace: Progress

Read this first in every session. Update it after every phase: status + one log line.

Statuses: `TODO` · `DOING` · `DONE` · `CUT (reason)` · `BLOCKED (by what)`

## Now

| | |
|---|---|
| Current phase | 1 (foundation) |
| Current step | 1.1 |
| Branch state | `main` = phase 0 · `phase` = main |
| Prebuild | Local coding allowed, no push before event |
| Build start / end | `__:__` / `__:__` |
| LLM chain (after phase 0 tests) | `groq:qwen/qwen3.8-27b,gemini:gemini-3.5-flash-lite` |

## Phases

| Phase | Title | Owner | Status | Note |
|---|---|---|---|---|
| 0 | Setup | both | DONE | Gate 0.V passed; bot, phrase bank, LLM verified |
| 1 | Foundation | Suryansh | TODO | |
| 2 | Domain rules | Suryansh | TODO | |
| 3 | Stock first | Suryansh | TODO | |
| 4 | Donors | Suryansh | TODO | |
| 5 | Closing + escalation | Suryansh | TODO | |
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
