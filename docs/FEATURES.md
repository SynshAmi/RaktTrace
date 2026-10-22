# RaktTrace: Features After the Base

**Rule:** nothing here starts until phase 10 (rehearsal) has passed and the backup video is recorded. Build in this order. Each feature merges only if S1–S3 and the benchmark still work. Otherwise drop it.

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
- **Hook:** injects the same events the world already produces (staff tap, stock answer, timeout, request edit) into `agent/loop.py`. No new logic.
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

## Priority 2: if time remains

### 3. "Why?" button
- **What:** on each decision in the log, "Why?" → the LLM answers in 2–3 lines using only that decision's facts (P before/after, candidates, rules applied).
- **Hook:** `llm/reader.py` gets one more prompt. Fallback: the decision's template summary.
- **API:** `POST /api/requests/{id}/decisions/{decision_id}/why` → `{answer}`.
- **Demo moment:** "Why only 4 donors?" → "4 more invites lift the chance from 81% to 91%; more would disturb people without much gain."
- **Size:** small.

### 4. Recurring patients
- **What:** register a patient on a fixed transfusion schedule (e.g. thalassemia, every 21 days). RaktTrace creates the request 3 days before each date and runs the normal loop. With days of lead time, it waits for stock, and donors are rarely needed.
- **Hook:** a scheduled timer creates a normal request (`source: "recurring"`). The core is unchanged. On FULFILLED, the next date rolls forward.
- **API:** `POST /api/patients {label, group, product, units, hospital_id, interval_days, next_at}`, `GET /api/patients`.
- **Demo moment:** register → +1 day jumps → the request appears, stock reserved, 0 donors, one message to the family.
- **Size:** medium.

## Priority 3: only if well ahead

### 5. Mission-control view
- **What:** a full-screen view with a map (centres, hospital, donors moving to the centre), a countdown, and the P gauge.
- **Hook:** frontend only, reading the existing RequestView (Leaflet + OpenStreetMap tiles).
- **Size:** medium.

## Backlog (pitch as "what's next", don't build)

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
