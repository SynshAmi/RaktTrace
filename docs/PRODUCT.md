# RaktTrace: Product

What RaktTrace does, for whom, and the exact words it sends. Decisions are in `SPEC.md`; the logic is in `AGENT.md`.

---

## 1. How blood reaches a patient today

1. The doctor orders blood; a request and sample go to the hospital's blood centre.
2. If tested, compatible stock exists, it's issued. This covers most cases.
3. If stock is short (platelets in dengue season, rare groups, small hospitals, recurring patients), the family is told to "arrange blood".
4. The family checks e-RaktKosh, calls blood banks, and forwards a plea to WhatsApp groups.
5. Someone says "yes", and everyone treats the request as solved.

RaktTrace takes over at step 3 and changes what "solved" means.

## 2. Surfaces

| Surface | Who | What |
|---|---|---|
| **Dashboard** (web, laptop) | Coordinator, judges | New request, request view with two lanes, phones panel, controls, benchmark |
| **Telegram bot** | Donors, blood-centre staff, family, optionally the coordinator | Messages with buttons; free-text replies |
| **Simulated phones** (inside the dashboard) | Everyone not on Telegram | The same messages and buttons, shown in a phone-style panel |

### 2.1 Dashboard screens

1. **New request**
   - Paste the plea.
   - See the parsed draft: group, product, units, hospital, deadline, optional family contact.
   - Fix anything, then Confirm.
   - Shows a "Merged into RT-xxxx" notice if it's a duplicate.
2. **Request view** (the hero screen). Two lanes side by side: **RaktTrace** and **Today's workflow**. Each lane shows:
   - status badge;
   - unit ladder (per unit: found → said yes → ready in time → collected / reserved → confirmed);
   - timeline.

   The RaktTrace lane also shows:
   - the P gauge with the 90% line;
   - stock list and donor list;
   - decision log;
   - escalation banner with the LLM brief.
3. **Phones panel:** list of simulated phones (donors, centres, family) → a chat view with tappable buttons and a text box.
4. **Controls:**
   - scenario picker + Reset;
   - Step, +15 min, +1 h, Auto (play/pause);
   - sim clock;
   - LLM on/off.
5. **Benchmark:** run N requests and seed → a results table and a simple bar chart, today vs RaktTrace.

### 2.2 Telegram roles and onboarding (built in phase 6)

| Link | Role |
|---|---|
| `/start` (judges scan the QR on the slide) | Onboarding with two choices: **Join the live demo** or **Create my profile** |
| `?start=staff_<centre_id>` (private chat) | That centre's staff (Aditya, as Centre B) |
| `?start=family` | Family contact for the next demo request |
| `?start=coord` | Coordinator alerts (optional) |

**Join the live demo:** the account gets its own donor record cloned from a small pool of synthetic templates (about 5–10) designed for S2: O+, apheresis-capable, eligible, near Centre B, with a small location jitter. The pool size is not a cap: templates are reused, one donor record per account.

**Create my profile:** a short fixed-button Q&A: blood group, approximate area (from the city's area list), sex, age band, weight band, last donation (never / over 4 months ago / recently), apheresis yes/no. It creates the same kind of donor record. The bot only collects answers; it never decides matching or invitations.

**Live donors:**
- Both routes end in the same core registration. Live donors join the real donor pool; the planner alone decides compatibility, timing, ranking and invitations. They rank 2nd among candidates that pass every filter (AGENT §5.1); nobody is guaranteed an invitation, and custom profiles may never be contacted.
- A live donor never gets a simulated reply; simulated outcomes are switched off by the donor's live flag, not by the channel of a message.
- S2 is the live donor scenario. S1 and S3 keep their rules: donors can't help there, so live donors are not invited. The bot never asks which scenario to join.
- Joining while S2 runs adds the donor to the running pool without changing earlier decisions; they can be invited from the next wave the planner sends. The bot says: "You're in. You'll get a message only if a request needs someone like you." With no scenario running, they are registered but not told they joined a request.
- During the live window S2 runs in Step mode, so the presenter can wait for judges' replies before advancing sim time.

**Identity and reset:**
- One Telegram account = one donor identity for the life of the server process. `/start` is idempotent: an account that already has a donor profile gets "Your donor profile is already set up and linked. You're all set! Send /reset if you want to start over." (no onboarding choices, nothing replaced); a half-finished Q&A carries on from the question it reached; a staff, family or coordinator chat gets its role confirmed. `/start` never lifts STOP. "Prefer not to say" for sex means the stricter 120-day whole-blood interval applies.
- A chat has one role at a time. Linking a private chat as centre staff detaches it from the donor pool. Group chats are not supported for staff.
- **Centre staff (A, B and the other seeded centres):** `?start=staff_c_a` or `?start=staff_c_b` links the account to that existing centre (no centre is created). One staff account per centre: a second account is told the centre is taken until the first sends `/reset`; a staff account must `/reset` before linking to another centre (never a silent switch). The linked account gets that centre's cards on Telegram; the planner still decides everything.
- **Hybrid:** with no staff linked, a centre is run by the simulated staff, so the demo works without Telegram. Linking hands the centre's open cards to the real staff (pending simulated answers are dropped); staff `/reset` hands them back to the simulated staff. If a staff card can't be sent on Telegram, the simulated staff answer it; a second tap on an answered card does nothing. The dashboard's sim phone for a centre can always tap as that centre.
- A scenario reset keeps identities and profile answers, rebuilds the world with the currently linked live donors, and clears their scenario history (invites, pledges, deferrals, donations). STOP (a reply or `/stop`) is kept across resets until the person explicitly re-joins (Join the live demo or a finished profile).
- The registry is in memory: a server restart clears it (including STOP), and participants re-join.
- If the bot is off or Telegram can't be reached, messages for a live contact show on the dashboard's sim phone instead.
- **Commands:** `/start` (onboarding, a confirmation, or a deep link), `/stop` (opt out), `/reset` (clear my donor profile, or release my centre if this is a staff chat).
- **Arrival:** the invite already asks "Can you reach {centre} by {latest_arrival}?". A yes means "yes, by then"; a yes with a later time ("kal 11:55") is checked against the deadline, including travel, collection and testing, and becomes `TOO_LATE` if the unit couldn't be ready. A yes is never supply by itself: only an on-time `ACTIVE` donor counts towards P, and only staff confirmation makes a unit `READY`.
- **`/reset`** clears only the sender's donor profile and half-finished Q&A, never the scenario or anyone else. If they are on an open request, they leave it the way "can't make it" does: an active donor becomes `NO_SHOW` (so a standby is promoted), an invited or standby donor is released; units already arrived or collected stay with the centre staff. Their old donor record stays in the pool but is never invited again; the next join or finished profile gets a fresh donor record. STOP is not lifted by `/reset`, only by joining again. From a staff chat, `/reset` instead releases only that chat's centre link (the scenario, the centre, its stock and everyone else stay as they are); the simulated staff take the centre back. A family or coordinator chat is not changed by `/reset`.
- All profiles are synthetic; nothing collects a home address or real medical history, and the demo is not a verified donor registry. Screening stays with the blood centre.

## 3. Flows

### 3.1 Create a request
1. The coordinator pastes the plea.
2. The LLM extracts the fields; with the LLM off, the rule parser does.
3. The coordinator confirms.
4. If an open request already has the same group, product and hospital, the plea is merged into it, and the coordinator sees "Merged into RT-xxxx".
5. Otherwise request `RT-####` is created and the agent starts immediately.

### 3.2 Stock first
1. The agent asks compatible centres in range to reserve units:
   - order: exact group first, then fresher listing, then nearer;
   - it asks in parallel until stock alone looks ≥ 90% likely.
2. Staff answer `Reserve N`, `Some` (then pick a number) or `None`.
3. When reservations cover the need, the agent keeps what it needs and releases the rest ("not needed, thank you").
4. A centre isn't asked again while its hold is active, after it said None, or after it didn't answer. If a reserved unit fails testing, or more units are needed after a hold was released, a centre whose listing still has unused units can be asked again (AGENT §5 Step 2).

### 3.3 Donors for the gap
1. Only if stock can't cover the gap, **and** a donor's unit could still be ready before the deadline.
2. The agent invites a batch chosen by expected cost (the chance of success against disturbing more people), at most 10 per wave, from donors who pass every filter.
3. Replies:
   - **yes, in time** → ACTIVE (booking code, directions; staff get an incoming card) or STANDBY;
   - **yes, too late** ("kal 11:55") → thanked, not counted;
   - **no** → thanked;
   - **STOP** → opted out;
   - **unclear** → "Please tap a button" (shown to the coordinator).
4. **Next wave:** goes out only if P is still below 90%, at least 10 min have passed, and someone from the last wave has replied or gone silent past 30 min. A silent donor past 30 min counts for less.

### 3.4 Visit and confirmation (staff on Telegram)
1. Incoming card → `Arrived` / `Didn't show`.
2. After Arrived → `Collected` / `Deferred`.
   - Deferred: the reason is optional and never stored or shown. The agent promotes a standby or invites more.
3. When the unit's testing should be done → `Ready for patient` / `Failed testing`.
4. No tap within 30 min of the expected time → one reminder. Still nothing after 30 more min → escalation to the coordinator. The agent never assumes success.

### 3.5 Closing
- **SECURED:** every unit is reserved, or collected with its ready time before the deadline.
  - Remaining donors are stood down.
  - Standby donors are released.
  - Unneeded holds are released.
  - The family gets "blood arranged, please stop forwarding".
- **FULFILLED:** staff tap `Ready for patient` for every unit. The family gets the final message.

### 3.6 Escalation
- **L1:** no more candidates at the current radius and P < 90% → widen 5 → 10 → 20 → 40 km.
- **L2:** the coordinator gets the LLM brief and a call list on the dashboard (and on Telegram if linked). O− is unlocked for non-O− patients. Triggers:
  - even the best possible plan is below 30%;
  - half the time has gone and P < 70%;
  - the search has reached 40 km and P < 90%;
  - staff haven't tapped.
- **FAILED:** the deadline passed with units missing. The coordinator gets a final summary.

### 3.7 Cancel
The coordinator cancels: holds are released and donors stood down.

## 4. Statuses

### Request
| Status | Badge |
|---|---|
| `OPEN` | Finding blood |
| `COVERED` | On track |
| `SECURED` | Blood arranged |
| `FULFILLED` | Ready for patient |
| `FAILED` | Needs help |
| `CANCELLED` | Cancelled |

COVERED can drop back to OPEN, for example after a deferral. That's honest, and it's a good demo moment.

### Stock reservation
`PENDING → RESERVED → READY`, or `NONE` (declined, or a reserved unit that failed testing: no longer usable supply), `EXPIRED` (no answer), `RELEASED`.

### Donor pledge
```
INVITED ─yes in time─► ACTIVE ─arrived─► ARRIVED ─collected─► COLLECTED ─ready─► READY
   │        └─(enough active)─► STANDBY ─promoted─► ACTIVE           └─failed testing─► FAILED_TEST
   │                                                   ARRIVED ─deferred─► DEFERRED
   ├─yes too late─► TOO_LATE        ACTIVE ─didn't show / can't─► NO_SHOW
   ├─no─► DECLINED      ├─timeout─► NO_REPLY (late yes still accepted)
   ├─stop─► OPTED_OUT   └─request secured─► RELEASED
```

### Today's-workflow lane
`SEARCHING` → `SAYS_FULFILLED`. Its true outcome is shown only at the deadline: "units actually ready: x of n".

## 5. Message copy (English)

No patient names anywhere. Requests are identified by code only. Button titles ≤ 20 characters.

**Donor**

| ID | Text | Buttons |
|---|---|---|
| `donor_invite` | 🩸 RaktTrace · {code}<br>{group} {product_label} needed at {centre}, {area}, by {deadline}.<br>You're a match, about {km} km away. Can you reach {centre} by {latest_arrival}?<br>Only come if you're well (no recent illness, tattoo or antibiotics). Staff at the centre will check you. | Yes, I can go · Not this time · Stop requests |
| `donor_go` | Thank you! 🙏 Please go to {centre}, {address}.<br>Map: {maps_link}<br>Booking code: {booking_code}. Show it at the counter.<br>Please arrive by {latest_arrival}. | On my way · Can't make it |
| `donor_standby` | Thank you! Enough donors are heading there right now. Please stay on standby until {standby_until}. We'll message only if we need you. | OK · Not available |
| `donor_promote` | {code}: we need you now. Can you reach {centre} by {latest_arrival}? | Going now · Can't |
| `donor_too_late` | Thank you! This one is needed by {deadline}, so a donation at that time would be too late. We'll ask you next time. | — |
| `donor_thanks_no` | No problem, thank you for replying. | — |
| `donor_not_needed` | Thank you! Enough donors are already lined up for {code}, so you're not needed this time. Stay rested for the next one 💙 | — |
| `donor_stand_down` | Blood for {code} is arranged. You're not needed this time and stay rested for the next one. Thank you 💙 | — |
| `donor_thanks_collected` | Thank you for donating today ❤️ You can donate again from {next_date}. | — |
| `donor_closed` | {code} is closed, so you're not needed for it any more. Thank you for being ready 💙 (sent on cancel, or when the deadline passes) | — |
| `donor_unclear` | Sorry, I didn't get that. Please tap one of the buttons above 🙏 | — |

`{next_date}` follows DOMAIN_RULES §2: after whole blood, 90/120 days; after platelets, the earliest next donation of any kind (48 h for platelets).

**Staff**

| ID | Text | Buttons |
|---|---|---|
| `staff_hold` | RaktTrace · {code}: can you reserve {units} unit(s) of {group} {product_label} for a patient at {hospital}, needed by {deadline}? | Reserve {units} · Some · None |
| `staff_hold_count` | {code}: how many units can you reserve? | 1 · 2 · … (one button per count below the ask; ids `N{k}`) |
| `staff_incoming` | 🩸 Incoming donor · {code}<br>{donor_name} · {group} · Booking code {booking_code}<br>For: {product_label}, {hospital}, needed by {deadline}<br>Expected around {eta} | Arrived · Didn't show |
| `staff_visit` | {donor_name} · code {booking_code} · screening | Collected · Deferred |
| `staff_ready` | Unit from code {booking_code} (or reserved stock) for {code}: ready for the patient? | Ready for patient · Failed testing |
| `staff_reminder` | Reminder · {code}: any update on {subject}? | (same buttons as the open card) |
| `staff_release` | {code}: the reservation is no longer needed. Thank you! | — |

**Family**

| ID | Text |
|---|---|
| `family_secured` | ✅ Blood for {code} is arranged at {centre}, ready by {ready_by}. Please ask your groups to **stop forwarding** the message. |
| `family_fulfilled` | ✅ {units} unit(s) for {code} are ready for the patient at {centre}. The hospital team will take it from here. |

**Coordinator**

| ID | Text |
|---|---|
| `coord_alert` | ⚠️ {code} needs attention. Chance of {units} unit(s) by {deadline}: {p}%.<br>{brief}<br>Call list:<br>1) {c1}, {c1_phone}, {c1_note}<br>2) …<br>3) … |
| `coord_failed` | {code}: deadline passed. Ready: {ready} of {units}. {summary} |

## 6. Privacy

- Donors never see family numbers, and the family never sees donor numbers. RaktTrace relays everything.
- Staff see a donor's display name, group and booking code only.
- The LLM never receives phone numbers or names. It gets message text and ids only.
- Deferral reasons are never stored.
- STOP opts a donor out immediately.
