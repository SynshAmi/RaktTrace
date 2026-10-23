# RaktTrace: Spec (source of truth)

Docs v1.0 — locked 23 Oct 2026. Any change needs both teammates' agreement and a dated line in §9.

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
| L-07 | One live number, **P**: a posterior mixture over tonight's reply rate (AGENT §3). Wave size is chosen by expected cost (failure risk vs donors disturbed, τ), stopping at 90% (AGENT §5). Stock waiting uses the slack rule. P_firm drives COVERED; P_best drives escalation. |
| L-08 | **Escalation:**<br>• L1: widen the search radius.<br>• L2: alert the coordinator with the LLM brief and a call list.<br>• FAILED at the deadline. |
| L-09 | **Today's-workflow lane:** the same world, run with today's behaviour, shown side by side. A **live benchmark** reports both. |
| L-10 | **Channel:** Telegram bot for real people in the demo (judges join via "Join the live demo" or "Create my profile"; staff via a private-chat deep link; PRODUCT §2.2); a simulated channel for everyone else. WhatsApp is the production path (pitch only). |
| L-11 | Synthetic data only. Same world model as the ideation simulation, ported to Python, with the tonight factor rescaled to mean 1.0 (AGENT §9). Numbers live in config with a one-line basis. |
| L-12 | Two people, one Telegram bot, one laptop. No hosting, no database. |

## 4. Base requirements (the project is "done" when all of these work)

**Request handling**
1. Paste a plea → parsed draft → confirm → request created. Duplicate pleas merge into the open request.

**Stock first**

2. Ask centres to reserve until stock alone looks ≥ 90% likely, or there's nothing left to ask. Keep what's needed; release extra.
3. Timing check for every source (travel, collection, testing, issue).

**Donors**

4. Donor waves sized by expected cost (AGENT §5), at most 10 per wave.
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
14. Benchmark on N random requests, with common random numbers; essential policies today vs rakttrace with paired 95% CIs; optional tiers in AGENT §10. Reporting:
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
| **S2 `dengue_sdp`** (hero) | O+ 1 SDP platelets, deadline 14:00 next day. Centre A lists 1 (15 h old) but has 0. | Wait for A, then invite the first wave: min(k*, 10) as computed by the planner (AGENT §5), which is 10 here. First yes → active; next two → standby (COVERED); "kal 11:55" → too late, not counted. Active donor **deferred** → standby promoted → collected → SECURED → Ready tap → FULFILLED. A duplicate plea is merged. | Says "fulfilled" at the first yes. The deferral goes unnoticed. **0 of 1 at the deadline.** |
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

The benchmark's optional tiers come before these, and the stock-wait lookahead after them (`IMPLEMENTATION_PLAN.md`, "After phase 10").

## 8. Pending (defaults apply if no answer)

| Item | Default |
|---|---|
| Exact event hours and judging format | About 8 hours of focused build (a target, not a commitment); 5-minute pitch + demo |
| LLM chain order | Set after the Phase 0 key tests |

Resolved (publishing, clarified by the organiser directly to the team; recorded 23 Oct 2026, the exact date of the clarification isn't recorded): we may develop, commit, push to GitHub and submit normally before the deadline. **Hard cutoff: 18:00 IST, 24 Oct 2026.** All development, commits, pushes and submission uploads must be done by then; after it, no commits, pushes or changes to the submitted project until judging is complete. This replaces the earlier no-push-before-the-event rule.

## 9. Change log

- 22 Oct 2026: spec created from the team's discussions and the submitted proposal.
- 23 Oct 2026: final design. Waves sized by expected cost, stopping at 90% (D1); P as a posterior mixture over tonight's reply rate (D2); slack stock-wait rule kept, lookahead as a stretch (D3); rescaled world factor, common random numbers and tiered benchmark with paired CIs (D4); shared types and internal interfaces in BUILD §5.2/§5.4 (D5). Statuses, scenarios and safety rules unchanged. Follow-ups: STOP likelihood, CI shape per policy, llm.status shape, L-11 and hours wording.
- 23 Oct 2026: implementation plan split into IMPLEMENTATION_PLAN.md; milestone-based cut triggers; no clock times.
- 23 Oct 2026: Docs v1.0 locked: S2 first-wave wording, phrases.json path, final consistency pass.
- 23 Oct 2026 (phase 4, agreed): AGENT §7.2 rule reader: "kal/tomorrow + a time" counts as a YES signal, so a later-yes like "kal 11:55" reads as YES with that time and the planner marks it TOO_LATE when it can't make the deadline.
- 23 Oct 2026 (pre-phase-5 audit, agreed): AGENT §2 now also lists STANDBY_PER_UNIT, PROMOTE_TIMEOUT_MIN, DEFAULT_DEFERRAL_DAYS, REPLY_LAG_MIN and MIN_GO_WINDOW_MIN (values unchanged, already in §4/§5 and DOMAIN_RULES E10).
- 23 Oct 2026: publishing policy updated per the organiser's clarification (§8): normal pushes allowed; freeze at 18:00 IST, 24 Oct 2026.
- 23 Oct 2026 (phase 5, agreed): AGENT §6 L1 widens only when nothing is left to try at the current radius (no stock left to ask, and donors can't help or the pool is exhausted). As first written ("pool_exhausted or no stock left"), S2 widened to 40 km and raised L2 while its donor wave was still working.
- 23 Oct 2026 (pre-phase-6 audit, agreed): stock centres whose hold was released, or whose reserved unit failed testing, can be asked again while units are needed (AGENT §5 Step 2); a centre that said None or didn't answer is not; L1 waits while a stock answer is awaited (AGENT §6). Failed stock units are NONE, and SECURED-but-unconfirmed requests fail honestly at the deadline (AGENT §5 Step 6, §6). Live Telegram demo design locked (PRODUCT §2.2): two onboarding choices, S2 templates, one identity per account, reset/STOP lifecycle, Step mode for the live window.
