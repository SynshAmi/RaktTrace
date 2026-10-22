# RaktTrace: Spec (source of truth)

**This file decides.** Every other doc explains *how*. If anything conflicts with this file, the other doc is wrong and gets fixed. Changing a decision here needs both teammates to agree, plus a dated line in §9.

Team Veritas (HX-BDXL): Suryansh Singh, Aditya Dev. AgentOps 2026 (MIT Bengaluru × CGI), 24 Oct 2026.

---

## 1. The idea

**A yes isn't blood.**

When a hospital is short of blood, the family is told to "arrange blood". Today, the request counts as done the moment someone says "yes". But:
- stock listings can be hours old;
- "kal subah aa jaunga" means tomorrow;
- donated blood needs hours of testing before it can be used;
- donors get deferred at screening;
- requests are never closed, so old pleas keep circulating.

**RaktTrace** is an agent that keeps working an urgent blood request until a **blood centre confirms the units**. It:
- checks stock first;
- messages only the donors truly needed, and only if their blood can be ready in time;
- keeps backups;
- warns a person early when the request is going to fail;
- closes the loop (stand-down to donors, "stop forwarding" to the family).

Secondary line: *e-RaktKosh tells you blood exists somewhere. RaktTrace gets it to your patient, on time.*

## 2. Users

| Who | What they do | Where |
|---|---|---|
| **Coordinator** (main user): helpline volunteer or hospital donor desk | Pastes the plea, confirms the request, watches it, gets escalations | Dashboard (+ optional Telegram alerts) |
| **Donors** (opted in) | Get asked, reply in their own words or by button | Telegram |
| **Blood-centre staff** | Reserve stock; mark Arrived, Collected, Deferred, Ready | Telegram buttons |
| **Family** | Receives updates and the "stop forwarding" message only | Telegram or sim phone |

One line: *family raises it, coordinator starts it, the agent runs it, donors respond, only blood-centre staff can close it.*

## 3. Locked decisions

| ID | Decision |
|---|---|
| L-01 | Done = units confirmed by a blood centre. We measure how often "fulfilled" was false. |
| L-02 | Request creation: coordinator pastes the plea → LLM extracts the fields → coordinator confirms. A manual form is the fallback. Family contact is optional. |
| L-03 | **The planner (fixed code) makes every decision.** The LLM does three jobs: (1) extract a request from a plea, (2) read donor replies, (3) write the escalation brief. A rule-based parser is the fallback. The dashboard has an LLM on/off toggle. |
| L-04 | **Stock first.** Donors are messaged only for the gap, and only if their unit can be ready before the deadline (testing included). If donors can't help in time, there are zero invites and the agent goes to stock and escalation. |
| L-05 | **Statuses:**<br>• `OPEN`<br>• `COVERED` (firm chance ≥ 90%)<br>• `SECURED`: every unit reserved, or collected with ready time before the deadline. Donors are stood down and the family is told to stop forwarding.<br>• `FULFILLED`: staff tap "Ready for patient".<br>• `FAILED`<br>• `CANCELLED` |
| L-06 | **Staff flow on Telegram:**<br>• Stock: `Reserve N / Some / None`.<br>• Donor visit: `Arrived / Didn't show` → `Collected / Deferred` → `Ready for patient / Failed testing`.<br>• No tap in time → one reminder → escalation. |
| L-07 | One live number, **P** = chance enough units are ready by the deadline. It drives:<br>• waiting for stock replies;<br>• the size of each donor wave (smallest that reaches 90%);<br>• backups;<br>• escalation. |
| L-08 | **Escalation:**<br>• L1: widen the search radius.<br>• L2: alert the coordinator with the LLM brief and a call list.<br>• FAILED at the deadline. |
| L-09 | **Today's-workflow lane:** the same world, run with today's behaviour, shown side by side. A **live benchmark** reports both. |
| L-10 | **Channel:** Telegram bot for real people in the demo; a simulated channel for everyone else. WhatsApp is the production path (pitch only). |
| L-11 | Synthetic data only. Same world model as the ideation simulation, ported to Python. Numbers live in config with a one-line basis. |
| L-12 | Two people, one Telegram bot, one laptop. No hosting, no database. |

## 4. Base requirements (the project is "done" when all of these work)

**Request handling**
1. Paste a plea → parsed draft → confirm → request created. Duplicate pleas merge into the open request.

**Stock first**

2. Ask centres to reserve until stock alone looks ≥ 90% likely, or there's nothing left to ask. Keep what's needed; release extra.
3. Timing check for every source (travel, collection, testing, issue).

**Donors**

4. Donor waves, smallest that reaches 90%, capped at 10.
5. Rest rules respected.
6. Replies read by the LLM, or by rules when the LLM is off. Too-late replies are not counted.
7. Yes → active (booking code + directions) or standby.
8. Deferral or no-show → standby promoted.

**Closing the loop**

9. Staff Telegram flow (L-06), including the reminder.
10. SECURED: stand-down to donors, "stop forwarding" to the family. FULFILLED on the Ready tap.
11. Escalation L1 / L2 with the LLM brief and a call list; FAILED at the deadline.
12. Every decision is logged with a plain sentence.

**Proof**

13. Today's-workflow lane, side by side.
14. Benchmark on N random requests, reporting:
    - on time %;
    - said done but wasn't %;
    - donors messaged per request;
    - solved with zero donors %;
    - failures warned early %.

**Demo controls**

15. Dashboard: request form, two lanes, P gauge, unit ladder, decision log, phones panel, clock controls (Reset / Step / +15m / +1h / Auto), LLM toggle, benchmark view.
16. Scenarios S1–S3 (§5) run end to end, including a real Telegram donor and real staff taps.

**Never cut:** stock first, the timing check, P and the planner, staff confirmation, SECURED/FULFILLED, the today's-workflow lane, the benchmark.

## 5. Demo scenarios (fixed, scripted, seeded)

| ID | Situation | RaktTrace must | Today's workflow shows |
|---|---|---|---|
| **S1 `surgery_tonight`** | B+ 2 units red cells, deadline 4 h. Centre A lists 3 (19 h old) but has 1; Centre B lists 2 (fresh); Centre D lists 1. | Message **0 donors** (testing can't finish in 4 h). Reserve A 1 + B 1, release the rest. SECURED in under 20 min. | Trusts A, finds 1 of 2 after 45 min, forwards to 30 donors who can't help in time, says "fulfilled" on a late yes. **1 of 2 at the deadline.** |
| **S2 `dengue_sdp`** (hero) | O+ 1 SDP platelets, deadline 14:00 next day. Centre A lists 1 (15 h old) but has 0. | Wait for A, then invite the smallest wave. First yes → active; next two → standby (COVERED); "kal 11:55" → too late, not counted. Active donor **deferred** → standby promoted → collected → SECURED → Ready tap → FULFILLED. A duplicate plea is merged. | Says "fulfilled" at the first yes. The deferral goes unnoticed. **0 of 1 at the deadline.** |
| **S3 `no_way_in_time`** | O− 2 units red cells, deadline 6 h, no O− stock within 40 km. | **0 donor invites.** Widen to 40 km, then L2 within minutes, with the brief and call list. FAILED at the deadline, but warned about 6 h early. | Forwards to donors who can't help in time, says "fulfilled" on a yes. No warning. |

## 6. Out of scope

- WhatsApp integration (pitch only).
- Real e-RaktKosh or hospital data.
- Hosting, database, logins.
- Hindi templates.
- An LLM making decisions.
- Medical eligibility decisions (always the blood centre's).
- Money or rewards of any kind.
- Products other than red cells (PRBC) and single-donor platelets (SDP).

## 7. After the base works

See `FEATURES.md`. Order:
1. Break-it button
2. Plea-still-active check
3. "Why?" button
4. Recurring patients
5. Mission-control view

## 8. Pending (defaults apply if no answer)

| Item | Default |
|---|---|
| Organiser: is any code allowed before the event? | No project code. Setup (Phase 0) only. |
| Exact build hours and judging format | About 6 hours; 5-minute pitch + demo |
| LLM chain order | Set after the Phase 0 key tests |

## 9. Change log

- 22 Oct 2026: spec created from the team's discussions and the submitted proposal.
