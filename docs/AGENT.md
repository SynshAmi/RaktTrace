# RaktTrace: The Agent

How RaktTrace decides. The code in `backend/rakt/agent/`, `llm/`, `baseline/` and `sim/` must match this file. Every number below lives in `config.py`, with the same name.

---

## 1. The loop

```
event (new request, staff tap, donor reply, silence timer, clock step)
   │
   ▼
1. UPDATE    apply the event to the request's state
2. READ      if it's free text: LLM reader → {intent, available_from, confidence}  (rules if LLM off/failing)
3. ESTIMATE  P = chance enough units are ready by the deadline (§3)
4. DECIDE    planner (§5): wait / ask stock / invite / promote / release / escalate / close
5. ACT       send messages, schedule timers, log a Decision with a plain sentence
```

- **The planner is the only decision-maker.** It's a pure function: `plan(state, now) -> list[Action]`.
- **Idempotent.** It only adds what's missing; running it twice on the same state adds nothing.
- **One request at a time.** Each event names a request.

## 2. Numbers (`config.py`)

| Name | Value | Basis |
|---|---|---|
| **Targets** | | |
| `TARGET_P` | 0.90 | Design |
| `ESCALATE_P` | 0.30 | Design: below this even the best plan is unlikely |
| `HALFTIME_ESCALATE_P` | 0.70 | Design: half the window gone and still below this |
| **Waves and rest** | | |
| `WAVE_CAP` | 10 | Design: max new donors per wave |
| `WAVE_INTERVAL_MIN` | 10 | Design |
| `REQUEST_DONOR_CAP` | 30 | Design: max donors messaged per request |
| `DONOR_REPLY_TIMEOUT_MIN` | 30 | Design |
| `STOCK_REPLY_TIMEOUT_MIN` | 20 | Design |
| `WAIT_SLACK_MIN` | 120 | Design: wait for stock replies only if donors would still have this much go window afterwards |
| `REST_H` | 72 | Design: not invited in the last 72 h (notification fatigue) |
| `MAX_ASKS_30D` | 4 | Design |
| `QUIET_HOURS` | 22:00–07:00, only for requests with > 24 h left | Design |
| `SEARCH_RADII_KM` | [5, 10, 20, 40] | Design |
| `STAFF_GRACE_MIN` | 30 | Design: reminder at expected time + 30; escalate at + 60. Expected times: arrival = booked_at + travel; screening result = arrived_at + VISIT; ready = collected_at + TEST (or reserved_at + ISSUE for stock); stock answer = asked_at + `STOCK_REPLY_TIMEOUT_MIN` (then `EXPIRED`, no reminder) |
| **Timing** | | |
| `TEST_MIN` | PRBC 720, SDP 360 | Whole-blood testing reported 12–24 h; SDP is an assumption |
| `VISIT_MIN` | PRBC 45, SDP 120 | Assumption: registration + screening + collection |
| `ISSUE_FROM_STOCK_MIN` | 45 | Reported crossmatch/issue times |
| `SAFETY_MARGIN_MIN` | 30 | Design |
| `CITY_SPEED_KMPH` | 18 | Assumption: Bengaluru city traffic |
| `ROAD_FACTOR` | 1.4 | Assumption: road ≈ 1.4 × straight line |
| **Stock chance** | | |
| `STOCK_P` | listing ≤ 6 h: 0.85 · 6–24 h: 0.65 · > 24 h: 0.50 | Assumption |
| **Donor chance** | | |
| `YES_RATE_PRIOR` | 0.25 | Assumption: share of invited donors who say yes |
| `PRIOR_STRENGTH` | 8 | Design: weight of the prior in "tonight's rate" |
| `IN_TIME_SHARE` | 0.70 if go window < 12 h, else 1.0 | Assumption: about 30% of yeses are for later |
| `NO_REPLY_FACTOR` | 0.25 | Design: a silent donor past the timeout keeps 25% |
| `P_SHOW` | 0.90 | Assumption |
| `P_PASS` | PRBC 0.88, SDP 0.75 | Deferral ~12% whole blood (reported range); SDP 25% (assumption) |
| `STANDBY_FACTOR` | 0.80 | Design: standby must be re-pinged |
| **Baseline** | | |
| `FAMILY_TRIP_MIN` | 45 | Assumption: the family travels to the listed centre |
| `BASELINE_WAVE`, `BASELINE_INTERVAL_MIN` | 10, 30 | Assumption: forwards to ~10 people every 30 min |
| **LLM** | | |
| `LLM_TIMEOUT_S` | 8 | Design |
| `LLM_MIN_CONFIDENCE` | 0.6 | Design: below this, treat as unclear |

## 3. P: the chance of success

### 3.1 Sources
Each source can deliver units, with a probability `p`:

| Source state | p | units |
|---|---|---|
| Stock `PENDING` | `STOCK_P[listing age] × on_time` | units asked |
| Stock `RESERVED` | `1 × on_time` | units reserved |
| Stock `READY` | 1 | units |
| Donor `INVITED` | `r̂ × IN_TIME_SHARE × P_SHOW × P_PASS[product] × on_time` | 1 |
| Donor `NO_REPLY` | same × `NO_REPLY_FACTOR` | 1 |
| Donor `ACTIVE` | `P_SHOW × P_PASS × on_time` | 1 |
| Donor `STANDBY` | ACTIVE × `STANDBY_FACTOR` | 1 |
| Donor `ARRIVED` | `P_PASS` | 1 |
| Donor `COLLECTED` | 1 if ready time ≤ deadline − margin, else 0 | 1 |
| Donor `READY` | 1 | 1 |
| Anything else (`NONE`, `EXPIRED`, `TOO_LATE`, `DEFERRED`, `NO_SHOW`, `DECLINED`, …) | 0 | — |

**`r̂`, tonight's yes rate** (learns from this request):

```
r̂ = (PRIOR_STRENGTH × YES_RATE_PRIOR + yes_count) / (PRIOR_STRENGTH + resolved_count)
```

Here `resolved_count` = invites that replied, or passed their timeout.

### 3.2 Combining sources
P = probability that the delivered units total at least the units still needed. Sources are treated as independent, and the total is computed exactly with a small DP:

```python
def p_at_least(sources: list[tuple[float, int]], need: int) -> float:
    if need <= 0:
        return 1.0
    dist = [1.0] + [0.0] * need            # dist[k] = P(total = k), capped at need
    for p, units in sources:
        new = [0.0] * (need + 1)
        for k, mass in enumerate(dist):
            if mass:
                new[min(need, k + units)] += mass * p
                new[k] += mass * (1 - p)
        dist = new
    return dist[need]
```

### 3.3 Three views of P
| View | Uses | Drives |
|---|---|---|
| `P` | All sources | Inviting more donors |
| `P_firm` | Only committed sources: reserved/ready stock; ACTIVE / STANDBY / ARRIVED / COLLECTED / READY donors | `COVERED` when ≥ 0.9 |
| `P_best` | P if every remaining allowed candidate (up to the per-request cap, max radius) were invited now | L2 escalation when < 0.30 |

## 4. Timing checks

```
travel_min(a, b) = haversine_km(a, b) × ROAD_FACTOR / CITY_SPEED_KMPH × 60
```

**Donor** (donating at collection centre c, for hospital h):
```
start        = available_from if available_from else now + reply_lag   # reply_lag = 15 min if not yet replied, else 0
ready_at     = start + travel(donor, c) + VISIT[product] + TEST[product] + travel(c, h)
on_time      = ready_at ≤ deadline − SAFETY_MARGIN
latest_arrival = deadline − SAFETY_MARGIN − travel(c, h) − TEST − VISIT
go_window    = latest_arrival − now           # not invited if < 20 min
```

**Stock:**
```
ready_at = now + (0 if reserved else STOCK_REPLY_TIMEOUT/2) + ISSUE_FROM_STOCK + travel(c, h)
```

**Can donors still help at all?**
```
min pipeline = min over centres(VISIT + TEST + travel(c, h)) + 15
donors_can_help = now + min pipeline ≤ deadline − SAFETY_MARGIN
```

With the defaults, donors can only help **whole-blood requests with more than about 14 h left**, and **platelet requests with more than about 9 h left**. Shorter requests are stock-only. That's the S1 and S3 behaviour.

**Collection centre** (fixed when the first wave is planned):
1. the hospital's own centre, if it accepts donors;
2. otherwise a centre already holding stock for this request;
3. otherwise the nearest accepting centre.

SDP needs a centre with apheresis.

## 5. The planner (`agent/planner.py`)

Runs after every event, in this order.

**Step 1: Estimate.** Compute P, P_firm and the units still needed. Status:
- `SECURED` if certain units cover the need (reserved stock + collected units on time);
- `COVERED` if P_firm ≥ 0.9;
- otherwise `OPEN`.

`FULFILLED`, `FAILED` and `CANCELLED` are final.

**Step 2: Stock.** If stock alone isn't ≥ 0.9 likely and there are un-asked compatible centres in radius:
- ask the next centre (exact group → fresher → nearer) for `min(listed, need − units_reserved)`. Pending asks are **not** subtracted, so several centres can be asked for the same units in parallel; extras are released on confirmation;
- repeat until stock alone looks ≥ 0.9 likely or no centres are left;
- O− stock for a non-O− patient only after L2.

Reservations are kept in the order they arrive. If a reservation brings more units than are still needed, keep only what's needed (e.g. "Reserve 2" when 1 is needed → 1 reserved). Once the need is covered, release every pending ask.

**Step 3: Wait or invite.**
- If stock replies are pending and, after `STOCK_REPLY_TIMEOUT`, the go window would still be ≥ `WAIT_SLACK_MIN`: **wait**. Pending stock counts as p = 1 for this decision, so no donors are bothered yet.
- Otherwise, if P < 0.9, donors can help, `REQUEST_DONOR_CAP` isn't reached, and (this is the first wave, **or** `WAVE_INTERVAL_MIN` has passed **and** at least one invite from the last wave has replied or timed out): add ranked candidates one by one until P ≥ 0.9, or `WAVE_CAP`, or no candidates left. If no candidates are left: `pool_exhausted`.

**Step 4: Roles for yes-replies.**
- Too late → `TOO_LATE`.
- ACTIVE donors < units needed from donors → `ACTIVE`: `donor_go` to the donor, `staff_incoming` to the collection centre.
- Otherwise, if P_firm < 0.9 and standby donors < 2 × units needed from donors → `STANDBY` (backups are added until P_firm ≥ 0.9; with 1 SDP unit that is 1 active + 2 standby ≈ 93%).
- Otherwise → `RELEASED` with thanks.

**Step 5: Promotion.** On `DEFERRED`, `NO_SHOW` or a "can't make it": send `donor_promote` to the best on-time standby. The pledge stays `STANDBY` until the donor taps **Going now** (`OMW`) → `ACTIVE` (then `donor_go` + `staff_incoming`). **Can't** (`CANT`) or no answer in 15 min → `RELEASED`, try the next standby. No standby left → step 3.

Standby buttons: **OK** = `OK` (no change), **Not available** = `CANT` → `RELEASED`.

**Step 6: Close.**
- On `SECURED`: stand down every non-committed donor; release standby donors and unneeded holds; send `family_secured`; stop wave timers.
- Schedule `staff_ready` at each unit's ready time.
- When every unit is `READY` → `FULFILLED`, send `family_fulfilled`.
- `FAILED_TEST` reopens the gap.

**Step 7: Escalate** (§6).

**Step 8: Log.** If anything happened, store a `Decision` with:
- trigger;
- P before and after;
- status;
- actions;
- a one-sentence summary from a template, e.g. "Centre A had 0. Invited 10 donors (P 0% → 72%)."

### 5.1 Ranking donors
**Hard filters** (all must pass):
1. opted in, not paused, not opted out;
2. compatible (`DOMAIN_RULES.md` §3), with O− protection;
3. eligible on the donation date (§2 of DOMAIN_RULES);
4. within the current radius of the collection centre;
5. rested: not invited in the last `REST_H`, fewer than `MAX_ASKS_30D` invites in 30 days;
6. not in quiet hours (when they apply);
7. on time, with go window ≥ 20 min;
8. not already on this request, and not ACTIVE/STANDBY on another open one;
9. SDP: apheresis-capable.

**Order:**
1. exact group;
2. linked Telegram demo donor (demo only);
3. higher p;
4. centre-verified last donation;
5. nearer;
6. id.

Each candidate carries a `why` string, e.g. `"O+ exact · 3.2 km · verified"`.

### 5.2 Duplicates
A new plea with the same group, product and hospital as an **open** request is merged into it: logged as a decision, and shown to the coordinator. The open request's fields stay unchanged (the coordinator can cancel and recreate if details differ). No new search. The API returns `{merged_into: id}`.

## 6. Escalation (`agent/escalation.py`)

Levels only go up.

| Level | When | What |
|---|---|---|
| **L1 Widen** | `pool_exhausted` or no stock left to ask, and P < 0.9 | Jump to the smallest radius in `SEARCH_RADII_KM` that adds any candidate centre or donor (40 km if none); re-run the planner at once. |
| **L2 Alert** | Any of:<br>• `P_best < ESCALATE_P`<br>• ≥ 50% of the window gone and P < `HALFTIME_ESCALATE_P`<br>• at 40 km and P < 0.9<br>• a staff tap overdue by `2 × STAFF_GRACE_MIN` | LLM writes the brief (§7.3). `coord_alert` with the brief + call list (3 nearest centres listing any compatible units, including ones already asked). O− unlocked. Red banner. |
| **FAILED** | Deadline passed, ready units < need | `coord_failed` summary; standby donors released |

## 7. The LLM (three jobs, all optional)

All LLM calls go through `llm/client.py`:
- an OpenAI-compatible chain from `LLM_CHAIN` (e.g. `groq:<model>, groq:<model>, gemini:<model>, openrouter:<model>`);
- each entry tried in order;
- `LLM_TIMEOUT_S` per call;
- on timeout, 429, 5xx or bad JSON → next entry;
- all fail, or LLM toggled off → the rule fallback;
- JSON output only;
- the LLM never sees phone numbers or names.

### 7.1 Read a plea → draft request
Input: plea text, hospital list (id, name, area), now.

Output:
```json
{"group":"O_POS","product":"SDP","units":1,"hospital_id":"h_city","deadline_at":"2026-10-25T14:00:00+05:30",
 "confidence":0.86,"missing":[]}
```

Rules:
- "blood" means PRBC; "platelets" / "SDP" means SDP;
- unknown fields are null and listed in `missing`;
- relative times ("kal 2 baje") are converted using `now`.

**Fallback:** a regex for the group, units, product keywords and hospital-name match. The coordinator fills in the rest.

### 7.2 Read a donor reply
Input: reply text, request deadline, now.

Output:
```json
{"intent":"YES","available_from":"2026-10-25T11:55:00+05:30","confidence":0.9}
```
- `intent ∈ YES | NO | STOP | UNCLEAR`.
- `available_from` is null for "now".
- Confidence below `LLM_MIN_CONFIDENCE` → UNCLEAR.

**Fallback (rules):** word lists, case-insensitive.

| Intent | Words |
|---|---|
| STOP | stop, unsubscribe, band karo, बंद |
| NO | no, nahi, nahin, nai, not today, busy, नहीं |
| YES | yes, haan, han, ha, ok, okay, sure, coming, aa raha, aa rahi, aaunga, aaungi, हाँ, जी |

- "kal" / "tomorrow" + a time → `available_from`.
- Both YES and NO, or neither → UNCLEAR.

Button taps never need reading.

### 7.3 Write the escalation brief
Input: the request summary + the decision log (facts only).

Output: 4–6 short lines:
- where things stand;
- what was tried;
- who is coming;
- what's missing;
- next steps, chosen from a fixed list: call these centres · try a neighbouring district · rare-donor registry · ask the hospital's transfusion officer.

The prompt says: use only the facts given.

**Fallback:** a template that fills the same lines.

### 7.4 Prompts (short on purpose)
- **Plea:** "Extract a blood request from this message (English/Hindi/Hinglish). Return JSON with group, product, units, hospital_id (choose from the list or null), deadline_at (ISO, now is {now}), confidence, missing. Never guess a field you can't find."
- **Reply:** "A blood donor replied to a request needed by {deadline}. Now is {now}. Return JSON: intent (YES/NO/STOP/UNCLEAR), available_from (ISO or null if now), confidence."
- **Brief:** "Write a 4–6 line handover for a blood-helpline coordinator using only these facts. Plain English, no speculation. End with up to 3 next steps from this list: …"

## 8. Today's-workflow lane (`baseline/policy.py`)

The same world, the same request, a copy of the state. Behaviour:
1. Trust the listing with the most units. Mark "blood found".
2. After `FAMILY_TRIP_MIN`, the family reaches that centre and gets what's actually there.
3. If short, forward to `BASELINE_WAVE` donors (nearest compatible, no timing check, no rest rules) every `BASELINE_INTERVAL_MIN`.
4. Mark **"fulfilled"** when stock found + yes-replies ≥ need. It counts any yes, including late ones, and stops searching.
5. No deferral tracking, no backups, no stand-down, no warning.

**At the deadline**, the true outcome is computed from the world: units actually ready in time.

## 9. Simulated world (`sim/`)

The same model as the ideation simulation, ported to Python. Seeded, so the same seed gives the same world.

**Places:** Bengaluru areas with real-ish coordinates and fictional names: 4 hospitals, centres A–H (3 with apheresis).

**Stock:**
- listings with an age (20 min – 30 h) and a listed count;
- the **true** count equals the listed count with probability `STOCK_P[age]`, otherwise it's lower;
- staff reply in 10–30 min.

**Donors:** about 300, with:
- the blood-group mix from DOMAIN_RULES §6;
- ages 18–60, weight 45–90 kg;
- 70% with a past donation, 30% centre-verified;
- 15% apheresis-capable;
- spread within 15 km.

**Hidden "tonight" factor** per request, drawn from `[0.3, 0.55, 0.8, 1.05, 1.3]` with weights `[.20, .25, .25, .20, .10]`. Each invited donor's latent outcome is drawn once:

| Outcome | Share |
|---|---|
| Yes | `0.25 × factor` |
| … of which later (next morning 07:00–12:00) | 30% |
| Explicit no | 35% of non-yes |
| Silent | the rest |

- Reply delay: exponential, mean 30 min.
- Show: `P_SHOW`. Pass screening: `P_PASS[product]`.
- **Reply text:** each reply is a phrase from a **phrase bank** of about 40 labelled English/Hindi/Hinglish messages ("haan abhi aa sakta hoon", "kal 11:55 ke baad free hoon", "nahi bhai busy", …). Each phrase has its true intent and time. Readers (LLM or rules) see only the text, so misreads matter.
- The LLM's reading of each phrase is cached once in `sim/phrase_cache.json`, so benchmarks never call the API.

**Both lanes see the same latent outcomes** for the same donor on the same request. That keeps the comparison fair.

**Scenario scripts** (S1–S3) override specific centres and donors, using the order in which donors were invited, so scripts stay valid if ranking details change.

## 10. Benchmark (`sim/benchmark.py`)

- N random requests (default 500), seeded.
- Mix: 50% PRBC (deadline 2–24 h), 50% SDP (deadline 6–30 h); 1–3 units.
- Each runs headless through **both** policies to the deadline.

| Metric | Definition |
|---|---|
| `on_time_pct` | Requests where all units were truly ready before the deadline |
| `false_done_pct` | Requests marked done (fulfilled / secured) that weren't truly ready in time |
| `donors_messaged` | Average donors messaged per request |
| `zero_donor_pct` | Requests solved without messaging any donor |
| `warned_early_pct` | Failed requests where a human was alerted ≥ 1 h before the deadline (+ median lead time) |

Results are also split by product. The RaktTrace policy runs with the LLM reader (cached phrase readings) or with rules only. The difference is the LLM's contribution.

Reference from the ideation simulation (2,000 requests):
- on time: today 66.6% vs RaktTrace 79.8%;
- false done: 30.9% vs 0%;
- donors messaged: 6.9 vs 3.4;
- zero-donor: 50.7% vs 64.0%;
- warned early: 0% vs 100%.

The live numbers will differ slightly. Report whatever the live run gives.
