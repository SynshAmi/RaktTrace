# RaktTrace: Features After the Base

**Rule:** nothing here starts until phase 10 (rehearsal) has passed and the backup video is recorded. Build in this order. Each feature merges only if S1–S3 and the benchmark still work. Otherwise drop it. The benchmark's optional tiers come before these, and the stock-wait lookahead after them (`IMPLEMENTATION_PLAN.md`, "After phase 10").

Utilities (duplicate merge, stop-forwarding, stand-down, standby, reminders, booking codes, escalation brief, LLM toggle) are part of the base, not this file.

---

## Priority 1: build right after the rehearsal

### 1. Break-it button
- **What:** a dashboard button with a menu:
  - deferral of the active donor;
  - wrong listing (the next stock answer is "None");
  - silent donors (all pending invites go quiet);
  - deadline moved 2 h earlier.

  A judge picks one, and the agent replans live.
- **Why:** the clearest proof that it's an agent, not a script.
- **Hook:** injects the same events the world already produces (staff tap, stock answer, timeout, request edit) into `agent/loop.py`. No new logic. Each break re-runs the planner; the decision summary shows the new trade-off.
- **API:** `POST /api/demo/break {kind: "deferral"|"wrong_listing"|"silent"|"deadline"}`.
- **Demo moment:** "Pick any failure." The judge clicks; the P gauge drops; a backup or a new wave goes out; the decision log explains.
- **Done when:** each kind works on S2 and the request still ends correctly.
- **Size:** small.

### 2. Plea-still-active check
- **What:** anyone forwards a plea to the bot and gets back:
  - "✅ Fulfilled, please stop sharing";
  - "⏳ Still open, here's the status";
  - "Not found" (with a note to contact the helpline).
- **Why:** kills zombie pleas. It only works because we know when a request is truly closed.
- **Hook:** the LLM plea reader (or rules) → match against requests by group + product + hospital → reply. Read-only.
- **Demo moment:** a judge forwards the S1 plea after it's secured and gets "stop sharing".
- **Done when:** fulfilled, open and unknown pleas each get the right reply, with the LLM on and off.
- **Size:** small.

## Backlog (pitch as "what's next", don't build)

- "Why?" button: replaced by the decision summaries, which already state the trade-off.
- Recurring patients: medium size and not needed to prove the core; pitch as "what's next".
- Mission-control view: frontend-only polish with a map; not needed to prove the core.
- Shortage nudges: repeated shortages at a centre → suggest a donation drive to that centre, which approves it.
- Donor reliability memory: learn who replies and shows up.
- Voice-note replies.
- Hindi and regional templates.
- WhatsApp production channel.
- Real e-RaktKosh or hospital feed.

## Template for a new feature

```
### N. Name
- What:
- Why:
- Hook: (which existing event / module / endpoint it uses)
- API:
- Demo moment:
- Done when:
- Size: small | medium
```
