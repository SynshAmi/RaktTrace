# CLAUDE.md: RaktTrace

RaktTrace is an agent that keeps working an urgent blood request until a blood centre confirms the units. It checks stock first, messages only the donors truly needed (and only if they can help in time), keeps backups, escalates early, and closes the loop. It's built by a team of two at AgentOps 2026.

**Core idea: a yes isn't blood. The planner decides; the LLM only reads messages and writes the escalation brief.**

## Start every session

1. Read `docs/PROGRESS.md`: the current phase and step.
2. Read `docs/SPEC.md`, the source of truth. If anything conflicts with it, SPEC wins.
3. Read the current step in `docs/IMPLEMENTATION_PLAN.md`, and the sections it references.
4. Work on the `phase` branch. A phase is done only when its verification gate passes.
5. Update `docs/PROGRESS.md` (status + one log line).

## Doc map

| Need | Read |
|---|---|
| What we're building, locked decisions, scenarios, must-haves | `docs/SPEC.md` |
| Users, screens, flows, statuses, message copy | `docs/PRODUCT.md` |
| Loop, P, timing, planner, escalation, LLM jobs, baseline, simulation, benchmark, all numbers | `docs/AGENT.md` |
| Medical and legal facts | `docs/DOMAIN_RULES.md` |
| Stack, folders, data model, API, interfaces, coding rules, phases, cut order | `docs/BUILD.md` |
| Step-by-step plan and verification gates | `docs/IMPLEMENTATION_PLAN.md` |
| Frontend integration guide for the live API (phase 8) | `docs/PHASE8_HANDOFF.md` |
| Features after the base works | `docs/FEATURES.md` |
| Pitch, demo script, Q&A | `docs/PITCH.md` |

## Rules

- **Clean, simple code over clever code.** Minimal comments, only where the *why* isn't obvious. One responsibility per module, following the folder layout in BUILD.md §4.
- **The planner decides; the LLM reads.** Never put decision logic in LLM, bot or API code.
- **Every number lives in `backend/rakt/config.py`**, with a one-line basis comment, and matches AGENT.md §2.
- **Don't invent medical facts.** Use `docs/DOMAIN_RULES.md`.
- **Never crash the demo.** Telegram and LLM failures fall back (simulated channel, rule parser).
- **Test what matters:** domain rules, planner, scenarios S1–S3.
- **Tests are gates:** never proceed past a failing gate; never weaken a test to pass.
- **No secrets or real personal data in git.**
- **Features (`docs/FEATURES.md`) are locked** until phase 10 is DONE in PROGRESS.md.
- **Frontend design is Aditya's.** Follow his structure and choices; don't restyle unless asked.
- If code and docs disagree, fix the wrong one in the same commit. Changing anything in SPEC.md needs the user's explicit agreement.
- **Ask the user** before anything that costs money or messages a real number.

## Commands

```bash
cd backend && uv sync && uv run uvicorn rakt.main:app --reload
cd backend && uv run pytest -q
cd frontend && npm install && npm run dev
```

## Documentation maintenance — mandatory

Documentation updates are part of every phase's definition of done.

For every phase:
1. **`PROGRESS.md`** — Update the current phase and step, completed work, next phase, verification results, blockers or cuts, and a dated log entry. Never mark a phase complete until its verification gate passes.
2. **`IMPLEMENTATION_PLAN.md`** — Keep the plan consistent with the implementation. Do not rewrite or reorder planned phases just to reflect partial progress. Change it only when an approved plan change is necessary.
3. **`BUILD.md`** — Update implementation or setup instructions only when the actual workflow, commands, architecture, or interfaces have legitimately changed.
4. **`AGENT.md` and `SPEC.md`** — Treat these as authoritative specifications. Do not modify their requirements to make the implementation easier. Any change must follow the project's explicit approval and dated-changelog rules.
5. **Other relevant docs** — Update `README.md`, API documentation, configuration examples, or feature documentation when the completed work makes them inaccurate or incomplete.

Before committing, check documentation against the actual code and test results. Include all necessary documentation changes in the phase commit. Do not claim documentation is updated if it is not.

At the end of each phase, report which documents were changed and why. If a document did not need modification, say so rather than making a meaningless edit.
