# RaktTrace: Pitch, Demo and Q&A

Numbers on stage come from the **live benchmark**. Ideation numbers are quoted only as "our ideation simulation showed…".

---

## 1. Pitch (~2 min talk + ~3 min demo)

| Beat | Say (roughly) |
|---|---|
| **Hook** | "A dengue patient needs platelets by 2 PM tomorrow. At 10:40 PM a donor says 'haan, aa sakta hoon'. Everyone marks it done. At 11 PM he's deferred at screening. Nobody notices. At 2 PM there are no platelets." |
| **Problem** | "Today a request is 'done' the moment someone says yes. But a yes isn't blood. Listings are hours old, 'kal aaunga' means tomorrow, donated blood needs hours of testing, donors get deferred, and pleas are never closed." |
| **RaktTrace** | "RaktTrace is an agent for helpline coordinators. It checks stock first, contacts only the donors truly needed, checks every reply against the real deadline, keeps backups ready, warns a person early, and closes a request only when a blood centre confirms." |
| **Why it's an agent** | "It runs a loop: observe, read, estimate the chance of success, decide, act, and repeat until the blood centre confirms. One number drives every decision. The LLM is its eyes and ears: it reads Hinglish. Decisions stay in code we can test, because this is blood." |
| **Demo** | §2 |
| **Proof** | Live benchmark table: on time, said-done-but-wasn't, donors messaged, zero-donor, warned early. |
| **What's next** | WhatsApp channel, real stock feeds, recurring patients, regional languages. |
| **Close** | "A yes isn't blood. RaktTrace makes sure the blood actually arrives." |

## 2. Demo script

**Setup:** dashboard on the projector. Aditya's phone = Centre B staff on Telegram. Bot QR on the slide.

| # | Do | They see | Say |
|---|---|---|---|
| 1 | Reset **S1**, Step through | Left lane: today's workflow trusts Centre A's 19-hour-old listing. Right lane: RaktTrace asks B and A in parallel (enough for 90%); A really has 1; reserves A 1 + B 1; **0 donors**; SECURED | "Surgery tonight. Donated blood can't be tested in 4 hours, so RaktTrace doesn't bother a single donor. Today's workflow messages 30 and says 'fulfilled' with 1 of 2 units." |
| 2 | Reset **S2**; ask judges to scan the QR | Judges' phones become donors | "You're now O+ platelet donors near the hospital." |
| 3 | Step: Centre A answers None | P drops; the smallest wave goes out, including the judges' phones | "It waited for the stock reply first. Now it messages just enough people to reach 90%." |
| 4 | A judge replies in their own words | LLM reads it; ACTIVE; booking code and directions to the judge; incoming card on Aditya's phone | "Free text works. The staff already know who's coming." |
| 5 | Another reply: "kal 11:55 ke baad free hoon" | Marked too late, not counted | "That's a yes, but platelets need about 8 hours to be usable. Not counted." |
| 6 | Paste the same plea again | "Merged into RT-xxxx" | "Duplicate pleas don't start a second search." |
| 7 | Aditya taps **Arrived**, then **Deferred** | COVERED → OPEN; a standby is promoted within seconds | "Deferred at screening. Today nobody would know. Here the backup is already on the way." |
| 8 | Step to Collected | SECURED; donors stood down; family gets "stop forwarding" | "Closed only on the blood centre's confirmation." |
| 9 | Toggle the LLM **off**, send a messy reply | Rules misread it, or ask for a button | "This is what the LLM adds." |
| 10 | Run the **benchmark** (500) | Live table, today vs RaktTrace | "Not cherry-picked: 500 fresh requests, right now." |
| 11 | Reset **S3**, Step | 0 invites; L2 alert with the LLM brief and call list | "When it can't make it, it says so 6 hours early, with a handover." |

If time is short: steps 1, 3, 4, 7, 8, 10.

## 3. How we compare

| Existing | What it does | Where it stops |
|---|---|---|
| e-RaktKosh | Stock search, donor registry | Shows what was entered; no public API; doesn't run a request |
| Donor apps and groups (Simply Blood, Friends2Support, WhatsApp, Twitter handles) | Broadcast and match | No tracking of who actually comes; never closes |
| NGO helplines (Sankalp, Red Cross, Blood Warriors) | Humans calling around | Manual; lives in volunteers' heads |
| 2026 prototypes (RaktSetu, LIFE-LINK, RakthaLink AI, Blood Bridge AI) | Matching, alerts in waves, backups | All stop at the donor's "yes" |
| Research (donor notification, fatigue, LLM parsing) | Pieces of the problem | None measures "units ready by the deadline" |

**What's new in ours:**
1. Done = confirmed by the blood centre, and we measure false "fulfilled".
2. Stock before donors.
3. Timing checks including testing.
4. One probability driving waiting, waves, backups and escalation.
5. Early escalation with a handover.
6. Closing the loop.

## 4. Judge Q&A

| Question | Answer |
|---|---|
| Is this an agent or a script? | "It's a goal-driven loop that replans on every event. A wrong listing, silence, a 'tomorrow' reply or a deferral all change its path. A script does the same steps every time." |
| Why doesn't the LLM make the decisions? | "Because then nobody could test or explain who got messaged or why a request closed. The LLM does what code can't: read messy Hinglish and write a handover. Decisions stay auditable." |
| Why no LangChain or LangGraph? | "Our LLM jobs are three JSON calls with a fallback. A framework would add weight without adding capability." |
| Where do your numbers come from? | "Testing times and donor rules come from Indian regulations and reports. Donor behaviour is an assumption, so we tested a range of values. The benchmark runs live on a synthetic city." |
| What if staff forget to tap? | "One reminder, then the coordinator is alerted. It never assumes success." |
| Isn't this extra work for staff? | "Two or three taps per donor, and fewer calls from families asking whether their donor has come." |
| Does the AI decide medical eligibility? | "No. It checks published rules like donation intervals before inviting. Screening is always the blood centre's call." |
| Why Telegram, not WhatsApp? | "WhatsApp needs business verification and approved templates, which isn't a one-day job. The channel is a swappable adapter; WhatsApp is the production path." |
| Privacy? | "We relay messages, so no numbers are exchanged. No patient names. The LLM never sees phones or names. STOP works instantly." |
| Real data? | "e-RaktKosh has no public API we could find. Our stock data has the same shape, so a real feed plugs into one adapter." |
| What's real in the demo? | "The agent, the Telegram messages to your phones, the LLM reading, the staff taps. Simulated: the other donors and centres, and the stock." |

## 5. Lines to avoid

- Don't present simulated numbers as real-world results.
- Don't claim e-RaktKosh or WhatsApp integration.
- Don't say the AI decides eligibility.
- Don't name real blood centres or hospitals in demo data.
- Don't promise exact testing times; say "hours of testing (12–24 h for whole blood)".
