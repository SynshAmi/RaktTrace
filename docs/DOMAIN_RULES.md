# RaktTrace: Domain Rules and Facts

The medical, legal and real-world facts the code and pitch rely on. **Don't invent a medical number.** Add it here first with a label.

Labels:
- **VERIFIED:** read in a primary source.
- **REPORTED:** a study or news report.
- **ASSUMPTION:** our estimate.
- **DESIGN:** our product policy.

---

## 1. Terms

| Term | Meaning |
|---|---|
| Blood centre | Licensed facility that collects, tests, stores and issues blood ("blood bank" was renamed in the 2020 amendment). VERIFIED |
| PRBC | Packed red blood cells. Most "I need blood" requests. One whole-blood donation = 1 unit. |
| SDP | Single-donor platelets, collected by apheresis from one donor. 1 procedure = 1 unit. |
| TTI tests | Mandatory infection tests on every unit before issue. |
| Deferral | A donor turned away at screening (temporarily or permanently). Decided by centre staff only. |

RaktTrace handles **PRBC and SDP only**. It takes the product and unit count as requested and never converts doses.

## 2. Donor eligibility (checked automatically before inviting)

Source: Drugs and Cosmetics Rules, 1945, donor criteria as substituted by G.S.R. 166(E), 11 Mar 2020 (CDSCO merged copy). VERIFIED.

| # | Rule | Value |
|---|---|---|
| E1 | Minimum age | 18 |
| E2 | Maximum age (whole blood) | 65; first-time donors not over 60 |
| E3 | Apheresis age | 18–60 |
| E4 | Weight, whole blood | ≥ 45 kg |
| E5 | Weight, apheresis | ≥ 50 kg |
| E6 | **Whole-blood interval** | **90 days men, 120 days women** (unknown sex → 120) |
| E7 | Apheresis interval | ≥ 48 h apart, ≤ 2 per week, ≤ 24 per year |
| E8 | Whole blood → apheresis | not within 28 days |
| E9 | Apheresis → whole blood | not within 28 days |
| E10 | Active deferral | not before `deferred_until` (default 30 days if staff give no date; DESIGN) |
| E11 | Consent | opted in, not opted out (legal, not medical) |

Intervals are checked against the **expected donation time**, not "now".

**Not checked by RaktTrace** (centre screening decides): haemoglobin (≥ 12.5 g/dL), blood pressure, pulse, temperature, recent illness (e.g. dengue 6 months after recovery), tattoo or piercing (12 months), antibiotics, vaccines, pregnancy. The invite says "only come if you're well", and staff decide.

## 3. Compatibility

Used to **shortlist** stock and donors. The blood centre's crossmatch decides. VERIFIED (standard ABO/RhD rules).

### 3.1 Red cells (PRBC): patient can receive from
| Patient | Donors, in preference order |
|---|---|
| O− | O− |
| O+ | O+, O− |
| A− | A−, O− |
| A+ | A+, A−, O+, O− |
| B− | B−, O− |
| B+ | B+, B−, O+, O− |
| AB− | AB−, A−, B−, O− |
| AB+ | AB+, AB−, A+, A−, B+, B−, O+, O− |

### 3.2 Platelets (SDP)
- Search the **ABO- and RhD-identical** group only in the base project.
- Non-identical platelets need clinician approval, so RaktTrace doesn't offer them.

### 3.3 Our group policy (DESIGN)
1. Exact group first.
2. **Protect O−:** O− stock and donors are used for non-O− patients only after escalation L2.

## 4. Time

| Fact | Value | Label |
|---|---|---|
| Every unit must pass TTI tests (HIV 1/2, HBsAg, HCV, syphilis, malaria) before issue | — | VERIFIED |
| Whole blood: donation → usable | 12–24 h (we use 12 h) | REPORTED |
| SDP: donation → usable | 6 h | ASSUMPTION |
| Visit: registration + screening + donation | whole blood 45 min, apheresis 120 min | ASSUMPTION |
| Issue from stock (crossmatch) | ~45 min | REPORTED (Kerala review ~45 min; Navi Mumbai audit: emergency mean 39 min) |
| Platelet shelf life | 5 days | VERIFIED |
| Red-cell shelf life | 35–42 days | VERIFIED |

**What follows:** a donor arriving now is not blood available now. Short-deadline requests can only be met from stock.

## 5. Law, policy, privacy

- **No paid donation.** *Common Cause v. Union of India* (1996) led to the ban on professional donation. VERIFIED (DGHS).
- Blood isn't for sale; centres may charge processing costs only (DCGI letter, Dec 2023). REPORTED.
- **RaktTrace policy (DESIGN):** no money or rewards for donating or recruiting.
- **Privacy (DESIGN, built to DPDP Act 2023 principles):** opt-in consent; data used only for matching; no patient names in messages; no number exchange between family and donors; no deferral reasons stored; STOP works immediately.
- **e-RaktKosh:** MoHFW's central blood bank system (C-DAC, 2016). Publishes stock by centre, but **no public API found** (22 Oct 2026). We use e-RaktKosh-shaped synthetic stock. REPORTED.

## 6. Blood-group mix (for synthetic donors)

Regional Indian donor studies: B and O most common (~30–37% each), A ~22%, AB ~8–11%, RhD-negative ~5–8%. REPORTED.

Seed mix (ASSUMPTION):

| O+ | B+ | A+ | AB+ | O− | B− | A− | AB− |
|---|---|---|---|---|---|---|---|
| 32 | 32 | 21 | 8 | 2.5 | 2.2 | 1.5 | 0.8 |

## 7. Context facts (pitch only)

| Fact | Label | Source |
|---|---|---|
| A Mumbai thalassaemia patient spent nearly 5 hours moving between blood banks despite adequate stock in the city | REPORTED | Free Press Journal, 1 Jul 2026 |
| India has an estimated 1–1.5 lakh children with thalassemia major; families search for blood monthly | REPORTED | ISignal (IndiaSpend), 25 Feb 2026 |
| Replacement donation is "an unofficial rule in most places"; families hunt for donors on social media | REPORTED | ISignal, 25 Feb 2026 |

## 8. Sources

- CDSCO, Guidelines for blood bank merged with GSR 166E (11.03.2020): https://cdsco.gov.in/opencms/resources/UploadCDSCOWeb/2018/UploadBloodBank/Guidelines_for_blood_bank-merged-with-GSR-166E-dated-11.03.2020.pdf
- DGHS blood transfusion services: https://dghs.mohfw.gov.in/bts.php
- Free Press Journal, 1 Jul 2026: https://www.freepressjournal.in/mumbai/mumbai-thalassemia-patients-face-delays-in-free-blood-transfusions-despite-adequate-blood-stocks
- ISignal, 25 Feb 2026: https://www.isignal.in/health/thalassemia-children-navigate-depleted-blood-supply-infection-risk-980732
- Vikaspedia, e-RaktKosh: https://en.vikaspedia.in/health/health-directory/e-blood-banks
- Crossmatch and turnaround times: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10125244/
- Blood-group distribution: https://pmc.ncbi.nlm.nih.gov/articles/PMC4140055
- **To add:** a citable source for the 12–24 h whole-blood testing time, the SDP turnaround, and whole-blood/SDP deferral rates.
