# CLAUDE.md: RaktTrace

RaktTrace is an agent that keeps working an urgent blood request until a blood centre confirms the units. It checks stock first, messages only the donors truly needed (and only if they can help in time), keeps backups, escalates early, and closes the loop. It's built by a team of two at AgentOps 2026.

**Core idea: a yes isn't blood. The planner decides; the LLM only reads messages and writes the escalation brief.**

## Start every session

1. Read `docs/PROGRESS.md`: the current phase and the latest log lines.
2. Read `docs/SPEC.md`, the source of truth. If anything conflicts with it, SPEC wins.
3. Read the current phase in `docs/BUILD.md` §6, and the docs it needs.
4. Work on the `phase` branch. When the phase's *Done when* passes, tell the user it's ready to merge into `main`.
5. Update `docs/PROGRESS.md` (status + one log line).

## Doc map

| Need | Read |
|---|---|
| What we're building, locked decisions, scenarios, must-haves | `docs/SPEC.md` |
| Users, screens, flows, statuses, message copy | `docs/PRODUCT.md` |
| Loop, P, timing, planner, escalation, LLM jobs, baseline, simulation, benchmark, all numbers | `docs/AGENT.md` |
| Medical and legal facts | `docs/DOMAIN_RULES.md` |
| Stack, folders, data model, API, coding rules, git, phases | `docs/BUILD.md` |
| Features after the base works | `docs/FEATURES.md` |
| Pitch, demo script, Q&A | `docs/PITCH.md` |

## Rules

- **Clean, simple code over clever code.** Minimal comments, only where the *why* isn't obvious. One responsibility per module, following the folder layout in BUILD.md §4.
- **The planner decides; the LLM reads.** Never put decision logic in LLM, bot or API code.
- **Every number lives in `backend/rakt/config.py`**, with a one-line basis comment, and matches AGENT.md §2.
- **Don't invent medical facts.** Use `docs/DOMAIN_RULES.md`.
- **Never crash the demo.** Telegram and LLM failures fall back (simulated channel, rule parser).
- **Test what matters:** domain rules, planner, scenarios S1–S3.
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
