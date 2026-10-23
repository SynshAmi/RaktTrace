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

### 2.2 Telegram roles (deep links)

| Link | Role |
|---|---|
| `?start=donor` | Linked to a free demo donor slot (judges scan the QR on the slide) |
| `?start=staff_<centre_id>` | That centre's staff chat (Aditya, as Centre B) |
| `?start=family` | Family contact for the next demo request |
| `?start=coord` | Coordinator alerts (optional) |

Linked Telegram donors are real people in the demo. They rank first among equal candidates so they get invited.

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
`PENDING → RESERVED → READY`, or `NONE` (declined), `EXPIRED` (no answer), `RELEASED`.

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
