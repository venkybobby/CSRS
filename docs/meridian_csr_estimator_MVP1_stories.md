# Meridian CSR Cost Estimator — MVP1 Stories
**Client:** Dana Whitfield, Director Member Services Ops, Meridian Health Plans
**Source:** Scoping call transcript + sample data (rate_sheet_2026.xlsx, members.json, plans.json) + plan ops confirmation (Marcus, in-person, 2026-08-08) + demo screenshots (csrsupport_demo_walkthrough.gif + Scenario-1 through Scenario-5, 2026-08-10)
**Scope confirmed:** CSR-internal web UI demo only. No CRM integration, no real systems, no prior-auth workflow, no member-facing anything.

---

## Agreed Scope — In / Out

### IN SCOPE (MVP1)
- Simple web page: CSR types plain-English question + member ID
- Member eligibility lookup from sample data (status, coverage dates, plan)
- Termed-member check — returns "not eligible as of [date]," never a dollar figure
- Plan lookup (deductible individual/family, coinsurance %, OOP max, preventive rules, prior-auth codes, exclusions)
- Rate lookup from rate sheet by CPT code or common name
- Deterministic cost calculation: embedded deductible logic → coinsurance → embedded OOP max cap
- Family vs. individual deductible/OOP logic for family-tier members (embedded model, confirmed)
- Prior-auth flag when plan requires it for the procedure
- Honest "rate not on file" response when procedure is absent from rate sheet
- Exclusion response ("not covered under this plan") when plan excludes the CPT code — distinct message from rate-not-found
- Explanation output: the breakdown (deductible met, amount applied, coinsurance %, OOP cap if triggered), not just the dollar total

### OUT OF SCOPE (MVP1) — agreed with Dana
- CRM integration (homegrown desktop system — future phase)
- Real eligibility, real rate, or real claims systems
- Prior-auth workflow (flag only, no submission)
- Member-facing interface
- Multi-procedure bundles in a single query
- Grievance or escalation tracking
- Finance rate-sheet update workflow

---

## Architecture Constraint (Enforceable Split)
Dana explicitly asked whether the deterministic/AI split is enforceable.

**Rule:** The LLM's only job is natural language → tool routing (which procedure, which member, which lookup). Every dollar figure originates from a deterministic calculator function. No number is ever generated inside the model. If a rate is absent, the tool returns "not on file" — the model surfaces that as-is, never substitutes an estimate.

This must be auditable: the response must show which tool calls produced which inputs to the calculator, so a supervisor can trace any quote back to its source data.

---

## Confirmed Plan Logic (Marcus, Plan Ops — 2026-08-08)

All three plans (MER-SLV-2026, MER-GLD-2026, MER-BRZ-2026) use **embedded** deductible and OOP max logic.

**Marcus's exact rule:** "A member exits the deductible phase when EITHER their individual deductible is met OR the family deductible is met — whichever happens first."

**OOP max follows the same embedded model:** a member's cost is capped at whichever is lower — their individual OOP remaining or the family OOP remaining.

**Deterministic implementation (three locked rules):**

```python
# Rule 1 — Are we past the deductible phase? (family tier only; individual uses clause A alone)
in_coinsurance = (ind_ded_met >= ind_ded) or (fam_ded_met >= fam_ded)

# Rule 2 — If still in deductible phase, how much deductible remains?
# Family aggregate can truncate an individual's remaining deductible.
remaining_ind_ded = ind_ded - ind_ded_met
remaining_fam_ded = fam_ded - fam_ded_met
deductible_remaining = min(remaining_ind_ded, remaining_fam_ded)  # binding constraint

# Rule 3 — Cap final member cost at the lower of individual or family OOP remaining
remaining_ind_oop = oop_max_individual - ind_oop_met
remaining_fam_oop = oop_max_family - fam_oop_met
oop_remaining = min(remaining_ind_oop, remaining_fam_oop)
member_cost = min(member_cost_before_cap, oop_remaining)
```

**Demo-scope assumption (stated, not asked):** Mid-year coverage start (e.g., M1008, coverage_start 2026-07-01) receives no deductible proration — full plan-year deductible applies. This matches standard plan design and must be documented in the implementation README as an explicit decision, not an oversight.

---

## Demo Grading (2026-08-10 — Screenshots)

| # | Case | Expected | Actual | Grade |
|---|---|---|---|---|
| 1 | M1002 knee MRI | $470, no prior auth flag (CPT 73721 not in Silver auth list), full breakdown | $470 ✓, correct breakdown ✓, audit ref shown ✓, no auth flag ✓ | ✅ Pass |
| 2 | M1004 knee surgery | $150 (OOP cap binding, $6,500 max − $6,350 met) | Negotiated rate $6,200 ✓, deductible $3,000/$3,000 met → $0 applied ✓, balance $6,200 ✓, coinsurance 30% = $1,860 ✓, amber "Out-of-pocket maximum reached — capped at $150.00" row ✓, **Member owes $150.00** ✓ | ✅ Pass (full-height screenshot 2026-08-10) |
| 3a | M1006 knee surgery | $1,860 via individual threshold | $1,860 ✓, "Deductible phase skipped via: individual threshold" ✓ | ✅ Pass |
| 3b | M1007 knee surgery | $1,860 via **family** threshold; explanation must say "family threshold" | **RETRACTED** — original grading error (M1006 and M1007 cards differ by one word; easy to misread). Retraction accepted on basis of: API JSON (`triggering_threshold: "FAMILY"`, audit `45611dd4`); source `family.py:37` showing `"INDIVIDUAL" if ind_deductible_met else "FAMILY"` (falsy for Hannah's $400/$3,000 → correctly returns "FAMILY"); single-commit git log confirming file unchanged since initial build. Note: source line and API JSON supplied as typed text, not uploaded artifacts — accepted with this qualification recorded. | ✅ Pass (bug retracted — grading error, not code defect) |
| 4 | M1005 (termed) | "Not eligible as of 2026-05-31. Do not quote a cost." | Red "Not Eligible" banner ✓, correct date ✓, correct CSR instruction ✓, no dollar shown ✓ | ✅ Pass |
| 5 | Cardiac CT M1003 | "No rate on file" — no estimate, CSR instruction | Grey "No Rate On File" banner ✓, correct message ✓, no number shown ✓ | ✅ Pass |

### UI Observations (from screenshots)
- **Audit ref** (e.g., `5ebc262b-bb18-4bbc-a998-8f4f06725686`) is present in Scenario-1 output — satisfies the auditability requirement from the enforceable split constraint. ✅
- **Color-coded banners** are implemented: red for Not Eligible (Scenario-4), grey/neutral for No Rate On File (Scenario-5) — satisfies Story 6's visual distinction requirement. ✅
- **Breakdown row labels** match the story spec exactly: Negotiated rate / Deductible / Applied to deductible / Balance after deductible / Coinsurance / Member owes. ✅
- **"Deductible phase skipped via"** label is present in family scenarios — confirmed correct for both M1006 ("individual threshold") and M1007 ("family threshold").
- **OOP max amber row** — "Out-of-pocket maximum reached / capped at $150.00" renders in amber/orange with distinct visual treatment when OOP cap binds (Scenario-2 full-height screenshot). ✅ Satisfies Story 3's OOP cap display requirement.

### Bug: M1007 Wrong Trigger Label — RETRACTED (grading error, not code defect)

**Originally claimed:** "Deductible phase skipped via: individual threshold" — should say "family threshold."

**Retraction basis (accepted with qualification):**
- API JSON supplied by build team: `{"triggering_threshold":"FAMILY","member_cost":"1860.00","deductible_met_ytd":"400.00","name":"Hannah Santos","audit_id":"45611dd4-3bcc-4b14-836a-29d08c3b7116"}`
- Source `agent/csr_agent/calculator/family.py:37`: `triggering_threshold = "INDIVIDUAL" if ind_deductible_met else "FAMILY"` — for Hannah Santos (`ind_ded_met = $400`, `ind_ded = $3,000`), `ind_deductible_met` evaluates falsy, so the ternary correctly returns `"FAMILY"`
- `git log --oneline -- family.py` → single commit `1b74bff feat: initial CSRSupport implementation` — file unchanged since before the original grading pass
- **Qualification:** source line, API JSON, and git log were supplied as typed text, not uploaded artifacts. Accepted given internal consistency and the ternary logic reading cleanly, but not independently verified from file.

**Root cause of grading error:** M1006 and M1007 output cards are visually near-identical (same dollar amount, same coinsurance rate). The original grading pass read M1006's "individual threshold" label onto M1007's card. Error was in observation, not in the build.

**Story 5 negative-test AC is retained as a standing regression guard** — the logic is correct now; the test ensures it stays correct if `family.py` is ever touched.

---

## User Stories

### Story 1 — Member Eligibility Check
**As a CSR,** I want to type a member ID in plain English so that I immediately know whether that member has active coverage before quoting a cost.

**Acceptance Criteria:**
- Given a member ID in any part of a plain-English question
- When the system looks up that member
- Then it returns: member name, plan name, coverage tier (individual/family), coverage start date, current status
- And if status = "termed," it returns: "Not eligible as of [coverage_end date]. Do not quote a cost." — no dollar figure is shown, calculator does not run
- And if status = "active" with a future coverage_end date (e.g., M1010 terms 2026-08-31), the system flags: "⚠️ Coverage ends [date] — confirm date of service falls within coverage period" alongside the cost estimate
- And the eligibility check is always the first step — the calculator never runs for a termed member under any input phrasing

**Edge cases from data:**
- M1005 (Priya Raman): status = "termed," coverage_end = 2026-05-31 → eligibility refusal, no quote
- M1010 (George Ellery): status = "active," coverage_end = 2026-08-31 → future-term warning + cost estimate shown

---

### Story 2 — Procedure Rate Lookup
**As a CSR,** I want to type a procedure in common English ("MRI on his knee," "that heart scan") so that the system maps it to the right CPT code and negotiated rate without me knowing the code.

**Acceptance Criteria:**
- Given a plain-English procedure description
- When the LLM routes to the rate-lookup tool
- Then the tool returns: CPT code, procedure common name, negotiated rate
- And the response shows the matched CPT code so the CSR can confirm the right procedure was identified
- And if the procedure description cannot be confidently matched to a code in the rate sheet, the system returns: "We don't have a rate on file for [procedure as typed]. Do not estimate — transfer to Member Services supervisor."
- And the system never interpolates, averages, or substitutes a nearby procedure's rate

**Known missing procedures (absent from rate sheet by design):**
- "Cardiac CT" / cardiac CT angiography → honest miss
- Any procedure outside the 15 on the sheet → honest miss

**Preventive vs. diagnostic distinction:**
- "Colonoscopy" without qualifier → system asks: "Is this a preventive (screening) or diagnostic colonoscopy?" before calculating
- Preventive (CPT 45380): $0 on all three plans (preventive_covered_100pct = true)
- Diagnostic (CPT 45378): subject to deductible and coinsurance

---

### Story 3 — Cost Calculation with Explanation (Individual Tier)
**As a CSR,** I want the system to calculate what an individual-tier member owes and show the full breakdown so that I can explain the number to the caller without doing the math myself.

**Acceptance Criteria:**
- Given an active individual-tier member, a matched CPT code, and a negotiated rate
- When the deterministic calculator runs
- Then the output includes ALL of the following — not just the total:
  - Negotiated rate used
  - Individual deductible: plan total / met YTD / remaining
  - Amount of this service applied to deductible (may be partial if rate < remaining deductible)
  - Balance after deductible applied
  - Coinsurance % and dollar amount on that balance
  - Whether OOP max was hit and what it caps the member's cost to
  - Member's estimated cost (the final number the CSR reads to the caller)
  - Prior-auth required flag if applicable (Story 4)

**Deterministic calculation (individual tier):**

```python
# Step 1 — Deductible
deductible_remaining = deductible_individual - deductible_met_ytd
applied_to_deductible = min(negotiated_rate, deductible_remaining)
balance_after_deductible = negotiated_rate - applied_to_deductible

# Step 2 — Coinsurance
coinsurance_amount = balance_after_deductible * coinsurance_pct
member_cost_before_cap = applied_to_deductible + coinsurance_amount

# Step 3 — OOP cap
oop_remaining = oop_max_individual - oop_met_ytd
member_cost = min(member_cost_before_cap, oop_remaining)
```

**Edge cases from data:**
- M1001 (Alice Trevino, Silver, deductible_met=$0): full $1,500 deductible applies before any coinsurance
- M1002 (Robert Chen, Silver, deductible_met=$1,200, oop_met=$1,200): $300 deductible remaining → partial deductible, then 20% coinsurance on balance; OOP headroom = $2,800
- M1004 (James Whitaker, Bronze, oop_met=$6,350): OOP max = $6,500 → only $150 remaining; calculator must cap output at $150 regardless of procedure cost — OOP max binding
- M1003 (Dorothy Okafor, Gold, deductible_met=$500, oop_met=$1,100): deductible fully met ($500/$500), OOP headroom = $1,400; coinsurance = 10%

---

### Story 4 — Prior Auth Flag
**As a CSR,** I want the system to flag when a procedure requires prior authorization so that I don't quote a cost without warning the member the claim could be denied.

**Acceptance Criteria:**
- Given a CPT code that appears in the member's plan's prior_auth_required_codes list
- When the cost response is displayed
- Then a visible warning appears: "⚠️ Prior authorization required for [procedure name] under [plan name]. Advise member to obtain auth before service. Cost estimate shown assumes auth is approved."
- And the cost estimate is still shown (it is the cost if auth is granted)
- And if the CPT code is NOT in prior_auth_required_codes for that plan, no prior-auth mention appears

**Data-grounded cases:**
| CPT | Procedure | Silver (MER-SLV) | Gold (MER-GLD) | Bronze (MER-BRZ) |
|---|---|---|---|---|
| 70551 | MRI Brain | ⚠️ Required | Not required | ⚠️ Required |
| 72148 | MRI Low Back | ⚠️ Required | Not required | ⚠️ Required |
| 73721 | MRI Knee | Not required | Not required | ⚠️ Required |

---

### Story 5 — Family Deductible Logic (Embedded Model)
**As a CSR,** I want the system to correctly apply embedded family deductible and OOP max rules so that family-tier members get an accurate quote — including when the family aggregate frees a member from their individual deductible phase even though they've personally paid little.

**Confirmed rule (Marcus, Plan Ops):** A member exits the deductible phase when EITHER their individual deductible is met OR the family deductible is met — whichever happens first. OOP max works identically: the member's cost is capped at whichever is lower between individual OOP remaining and family OOP remaining.

**Acceptance Criteria:**
- Given a member with coverage_tier = "family"
- When calculating cost
- Then the system evaluates the in_coinsurance flag using BOTH individual and family deductible accumulators
- And if in_coinsurance = true (either accumulator exhausted), no deductible amount is applied — coinsurance runs on the full negotiated rate
- And if in_coinsurance = false, deductible_remaining = min(remaining_ind_ded, remaining_fam_ded) — the family aggregate can truncate the individual's remaining deductible
- And the OOP cap = min(remaining_ind_oop, remaining_fam_oop) — embedded on both sides
- And the explanation output states explicitly which threshold triggered (individual or family) and why
- And the trigger label is derived from which clause fired — NOT assumed to always be "individual": if `ind_ded_met >= ind_ded` is the sole TRUE clause, label = "individual threshold"; if `fam_ded_met >= fam_ded` fires (regardless of individual clause), label = "family threshold"; if both fire simultaneously, label = "individual threshold" (individual took precedence)
- **Negative test (from demo bug):** M1007 — ind_ded_met = $400, ind_ded = $3,000 (individual NOT met); fam_ded_met = $6,000, fam_ded = $6,000 (family met). System MUST display "family threshold." Displaying "individual threshold" for M1007 is an AC failure regardless of whether the dollar amount is correct.

**Deterministic calculation (family tier):**

```python
# Step 1 — Determine deductible phase
in_coinsurance = (ind_ded_met >= ind_ded) or (fam_ded_met >= fam_ded)

# Step 2 — Deductible amount owed (only if not already in coinsurance)
if in_coinsurance:
    applied_to_deductible = 0
    balance_after_deductible = negotiated_rate
else:
    remaining_ind_ded = ind_ded - ind_ded_met
    remaining_fam_ded = fam_ded - fam_ded_met
    deductible_remaining = min(remaining_ind_ded, remaining_fam_ded)
    applied_to_deductible = min(negotiated_rate, deductible_remaining)
    balance_after_deductible = negotiated_rate - applied_to_deductible

# Step 3 — Coinsurance
coinsurance_amount = balance_after_deductible * coinsurance_pct
member_cost_before_cap = applied_to_deductible + coinsurance_amount

# Step 4 — OOP cap (embedded: lower of individual or family remaining)
remaining_ind_oop = oop_max_individual - ind_oop_met
remaining_fam_oop = oop_max_family - fam_oop_met
oop_remaining = min(remaining_ind_oop, remaining_fam_oop)
member_cost = min(member_cost_before_cap, oop_remaining)
```

**Worked examples from data (Bronze plan: ind_ded=$3,000 / fam_ded=$6,000 / coinsurance=30% / ind_oop_max=$6,500 / fam_oop_max=$13,000):**

**M1006 (Miguel Santos):**
- ind_ded_met = $3,000 → individual deductible fully met → in_coinsurance = TRUE
- Coinsurance runs on full negotiated rate immediately (no deductible step)
- ind_oop_met = $3,400 → ind_oop_remaining = $3,100
- fam_oop_met = $4,500 → fam_oop_remaining = $8,500
- OOP cap = min($3,100, $8,500) = $3,100

**M1007 (Hannah Santos — same family, same plan):**
- ind_ded_met = $400 → individual deductible NOT met ($2,600 remaining)
- fam_ded_met = $6,000 → family deductible FULLY met → in_coinsurance = TRUE (family threshold triggers)
- Hannah is freed from her individual deductible by the family aggregate — coinsurance runs on full negotiated rate immediately
- ind_oop_met = $400 → ind_oop_remaining = $6,100
- fam_oop_met = $6,200 → fam_oop_remaining = $6,800
- OOP cap = min($6,100, $6,800) = $6,100
- Explanation must state: "Family deductible met ($6,000/$6,000) — individual deductible phase skipped."
- "Deductible phase skipped via" label must read: **family threshold** (not "individual threshold" — confirmed bug in demo build)

**Acceptance test — M1006 vs. M1007 same procedure:**
Both members are in coinsurance territory (different triggers). Their cost calculations will use the same coinsurance rate but will differ because their OOP accumulators are different. The system must produce different outputs and explain the different OOP positions. If it returns identical numbers, the per-member accumulator lookup is wrong.

**Prior-incorrect logic (corrected):** The original draft stated M1007 "pays her individual share because family aggregate hasn't yet freed her." This was wrong — family_ded_met = $6,000 equals the family deductible, so Hannah IS freed. The correct output is: Hannah skips her individual deductible and goes straight to coinsurance.

---

### Story 6 — Plan Exclusion Response
**As a CSR,** I want the system to tell me when a procedure is excluded from a member's plan — with a distinct message from "rate not on file" — so I can tell the member the service is not covered rather than guessing.

**Acceptance Criteria:**
- Given a CPT code that appears in the member's plan's excluded_codes list
- When the system checks coverage before calculating cost
- Then it returns: "This procedure ([CPT code] — [common name]) is excluded from [plan name]. It is not a covered benefit. Do not quote a cost."
- And this message is visually distinct from the "rate not on file" message (different label, different color/icon in UI)
- And no cost calculation runs

**Data-grounded case:**
- CPT S8092: in excluded_codes for Bronze (MER-BRZ-2026); Silver and Gold have no exclusions
- A Bronze member asking about S8092 → "not a covered benefit"
- A Silver or Gold member asking about S8092 → "rate not on file" (it's not excluded, but also not on the sheet — different fact, different CSR script)

**Why the distinction matters (Dana's words):** These are different regulatory facts. "Not covered" triggers a specific member rights disclosure. "Rate not on file" is an operational gap. A CSR using the wrong script for either situation is a grievance risk.

---

### Story 7 — Preventive Service Zero-Cost
**As a CSR,** I want the system to correctly return $0 for preventive services so that I don't accidentally quote a member a cost for a covered-100% benefit.

**Acceptance Criteria:**
- Given a procedure confirmed as preventive (CPT 45380 — Colonoscopy Preventive)
- And the member's plan has preventive_covered_100pct = true (all three Meridian plans)
- When the system calculates cost
- Then it returns: "Member owes $0. [Procedure] is covered at 100% as a preventive benefit under [plan name]. No deductible or coinsurance applies."
- And deductible and OOP accumulators are NOT debited in the explanation (preventive does not count against deductible)
- And the system does not run the cost calculator for preventive — it short-circuits to $0 after the preventive check

---

### Story 8 — Rate Not On File (Honest Miss)
**As a CSR,** I want the system to say clearly when a procedure's rate isn't in our system so that I don't guess or tell the member a number we can't stand behind.

**Acceptance Criteria:**
- Given a procedure description that does not match any CPT code in the rate sheet
- When the LLM routes the lookup and the tool finds no match
- Then the system returns: "We don't have a negotiated rate on file for [procedure as typed]. Do not estimate. Please transfer to Member Services supervisor or advise the member we'll call back with a confirmed cost."
- And no dollar figure of any kind is shown
- And the response does not reference a similar procedure's rate as a proxy

**Data-grounded case:**
- "Cardiac CT" / cardiac CT angiography — not in the 15-procedure rate sheet → honest miss
- Any free-text procedure the LLM cannot confidently map to a sheet entry → honest miss

---

## Human-in-Loop Scenarios

| Trigger | System Behavior | Who Acts |
|---|---|---|
| Member is termed | Eligibility refusal, no cost shown, calculator does not run | CSR verifies coverage manually before any further action |
| Rate not on file | "Not on file" message, no estimate | CSR transfers to supervisor or initiates callback — no improvised quote |
| Prior auth required | Cost estimate shown + visible ⚠️ auth warning | CSR advises member to obtain auth before scheduling service |
| Plan exclusion | "Not a covered benefit" message, visually distinct from rate-miss | CSR escalates to Member Services — specific member rights disclosure applies |
| Preventive vs. diagnostic colonoscopy ambiguity | System asks clarifying question before calculating | CSR confirms procedure type with caller before proceeding |
| Future coverage end date (active but terminating) | Cost estimate shown + ⚠️ "coverage ends [date]" warning | CSR confirms date of service falls within coverage period |
| Query returns two plausible CPT matches | System asks clarifying question, does not guess | CSR gets more specifics from caller to disambiguate |
| OOP max exhausted or nearly exhausted | Clearly flags in output; caps cost correctly | CSR confirms with member they owe $0 or small residual — does not read a larger number |
| Family aggregate frees member with low individual accumulator | Calculator skips deductible phase; explanation states which threshold triggered | CSR reads explanation to member — this is the case CSRs most often get wrong on the phone |

---

## Open Questions (Updated)

| Question | Owner | Status |
|---|---|---|
| Family deductible model — embedded or aggregate? | Marcus / Plan Ops | ✅ **Resolved:** Embedded, all three plans. Individual and family thresholds both checked; first met wins. |
| Coinsurance when family deductible met but individual is not | Marcus / Plan Ops | ✅ **Resolved:** Coinsurance applies immediately from dollar one — deductible phase is skipped entirely. One coinsurance rate per plan, no variation. |
| Finance rate sheet update cadence | Finance / Dana | 🔴 Open — not blocking demo, blocking production |
| Date-of-service context — today's date or CSR-specified? | Dana | 🟡 Open — not blocking demo |
| Real CRM integration path | IT | ⚪ Out of scope MVP1 |

---

## Demo Script (5 Cases to Validate MVP1)

| # | Input | Expected Output | What It Tests |
|---|---|---|---|
| 1 | "M1002 wants an MRI on his knee, what does he owe?" | Deductible remaining = $300 → applied to deductible. Balance = $850 → coinsurance 20% = $170. **Member owes $470.** CPT 73721 not in Silver's prior_auth list → no auth flag. Full breakdown shown. | Partial deductible + coinsurance math |
| 2 | "What's James Whitaker M1004 looking at for knee surgery?" | CPT 29881, rate $6,200. OOP met = $6,350, OOP max = $6,500 → $150 headroom. **Member owes $150 (OOP max binding).** Explanation states OOP cap triggered. | OOP max cap |
| 3 | "Same question for M1007 and M1006 — knee surgery" | M1006: individual deductible met → "individual threshold" label → $1,860. M1007: family deductible met → "family threshold" label → $1,860. Dollar amounts may match; trigger labels MUST differ. | Embedded family logic; M1007 family-freed path — 🔴 trigger label bug open |
| 4 | "M1005 — anything, what do they owe?" | "Priya Raman is not eligible as of 2026-05-31. Do not quote a cost." | Termed member block |
| 5 | "Cardiac CT for M1003" | "We don't have a negotiated rate on file for cardiac CT. Do not estimate." | Honest miss |

---

## Change Log

| Version | Change | Source |
|---|---|---|
| v1 | Initial stories from scoping call | Dana Whitfield call |
| v1.1 | Added explanation output requirement and termed-member rule (Dana post-scope additions) | Dana Whitfield call |
| v1.2 | Locked embedded deductible/OOP logic; corrected M1007 calculation; closed two blocking open questions; added mid-year proration assumption | Marcus (Plan Ops) + coach confirmation 2026-08-08 |
| v1.3 | Added demo grading section (4/5 pass, 1 partial, 1 bug); strengthened Story 5 AC with negative test for trigger label; noted audit ref and color-coded banner as implemented; updated demo script case 3 to flag open bug | Demo screenshots 2026-08-10 |
| v1.4 | M1004 partial → Pass (full-height screenshot confirms OOP cap at $150, amber row visible); M1007 bug → Retracted (grading error — source ternary logic correct, API JSON confirms "FAMILY" trigger; qualification noted: code/API evidence supplied as text not artifacts) | Full-height screenshots + build team evidence 2026-08-10 |
