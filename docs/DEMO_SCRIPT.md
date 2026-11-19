# Three-Minute Demo Script

**Format:** screen recording, 1440×900 or 1440×1100, no live audience.
**Target length:** 2:55 including title and close.
**Demo file:** `data/sample/uae_demo_cohort.csv`
**Probe files:** `data/sample/probes/probe_glycaemic_units.csv`, `probe_bp_two_rows.csv`
**Rule:** never claim diagnosis, calibration, UAE validation, or production readiness.

Narration is written for captions or voiceover at roughly 140 words per minute. If a step runs long, cut the probe upload at 2:05, not the urgent or unit-suspect inspection.

---

## 0:00–0:12 — Title and problem

**On screen:** Home page, synthetic-demo banner visible. Slow scroll from header to the upload card.

**Narration:**

> Abu Dhabi screens by age and sex. A twenty-nine-year-old with central obesity, family history, and high polygenic risk is invisible. A low-risk forty-year-old is invited. Nabdh ranks the first person first — and never hides a dangerous lab behind a bad unit.

**Caption:** `Nabdh · Precision Prevention & Screening · Challenge 04`

---

## 0:12–0:30 — Upload and triage summary

**Actions:**

1. Click the dropzone, choose `data/sample/uae_demo_cohort.csv`.
2. Scoring starts automatically — do not click anything.
3. Wait for the summary. Do not scroll yet.

**On screen:** `60 rows uploaded`, then the KPI row: 1 Urgent review, 51 Screenable adults, 9 High priority (30d), 17 Elevated (90d), 4 Missed by age-40 rule, 1.0 Expected undiagnosed diabetes cases, 4 Observations captured.

**Narration:**

> Sixty synthetic Abu Dhabi residents. One urgent, nine high priority, seventeen elevated. Four are missed by the age-forty rule. These counts are pinned by tests — they cannot drift before the demo.

---

## 0:30–1:05 — The “wow”: the 29-year-old the age rule misses

**Actions:**

1. In **Search ID, flag, or district**, type `UAE-WOW-029`.
2. Click the row.
3. Pause on **Why Flagged** so the drivers are readable.
4. Scroll the inspector to **Culturally Tailored Outreach (AR)**.
5. Click **Confirm slot**, then **Mark screening completed**.
6. Scroll up slightly so the **Outcome & recall conversion** strip is visible.

**On screen:** Tier Elevated; DM priority 1.5%, dysglycaemia 49.1%; reasons include the cardiometabolic triad, family history, BMI, and diastolic BP; flags include `Missed by age-40 screening rule (<40)`, guideline-due glucose, cervical screening, and high polygenic risk. Arabic message rendered RTL.

**Narration:**

> She is twenty-nine, with a BMI of 33, a family history of diabetes, and an elevated diastolic pressure. The triad of central obesity, elevated BP, and family history lifts her above the age rule. Her Arabic preview is right-to-left, family-framed, and offers a real choice: confirm, reschedule, or opt out. Confirming and marking completion updates the cohort conversion strip. No message is sent — this is a simulated workflow.

**Caption:** `Age-40 rule: missed · Triad + family history + PRS: flagged`

---

## 1:05–1:35 — Urgent cardiac finding overrides the queue

**Actions:**

1. Clear search, type `UAE-URG-101`, click the row.
2. Pause on the red urgent banner and the three alerts.
3. Point at the **no outreach preview** area; scroll to the sign-off footer.

**On screen:** Urgent Clinical Review; troponin I 0.18 ng/mL, NT-proBNP elevated, LVEF 34%; rule IDs `CV-TROP-01`, `CV-NT-proBNP-01`, `CV-LVEF-01`; timing Immediate; no outreach preview.

**Narration:**

> A troponin of 0.18, a high NT-proBNP, and an LVEF of 34 percent. Three deterministic rules fire, each with its guideline citation and version. The tier becomes Urgent, timing is immediate, automated outreach is suppressed, and clinician sign-off is required. The model does not get to bury this.

---

## 1:35–2:00 — The silent failure: an ambiguous unit

**Actions:**

1. Clear search, type `UAE-UNIT-102`, click the row.
2. Pause on **Not Evaluated — Confirm Units**.
3. Scroll to the care-gap flags showing `Outreach withheld — confirm ambiguous lab unit before contact`.

**On screen:** Troponin value 4500 with no unit, quality `unit_suspect`, excluded from rules, no outreach preview.

**Narration:**

> Here is the failure mode that matters. A troponin of four thousand five hundred arrives with no unit. It could be ng/L. It could be a different assay. The engine refuses to guess. It records the value, marks it unit-suspect, excludes it from clinical rules, and withholds outreach until a clinician confirms the unit. “No brick can damage the wall” means an ambiguous value must never be silently cleared.

---

## 2:00–2:30 — The obvious cases still work

**Actions:**

1. Clear search. Upload `data/sample/probes/probe_glycaemic_units.csv` (replaces the cohort).
2. Show both rows High and the conversion warnings.
3. Upload `data/sample/probes/probe_bp_two_rows.csv`.
4. Show the adult 185/115 row urgent and the pregnant 165/110 row **Urgent obstetric review**.

**On screen:** Two High rows with `HbA1c 58 mmol/mol → 7.46%` and `FPG 7.0 mmol/L → 126.1 mg/dL`; then two urgent rows, one with `OB-BP-SEVERE-01`.

**Narration:**

> Non-canonical units are converted, not dropped. Fifty-eight mmol/mol becomes 7.46 percent and lifts to High. Seven mmol/L becomes 126 and lifts to High. A 185 over 115 is a hypertensive crisis. The same pressure in a pregnant woman routes to urgent obstetric review, not a generic alert.

---

## 2:30–2:50 — Safeguards and honest limits

**Actions:**

1. Re-upload `uae_demo_cohort.csv` and score.
2. Scroll to **Segment audit**. Highlight the suppressed `Liwa Oasis` and `AR` rows and the visible `UAE-SM-401` redaction.
3. Point to the model badge and the footer line: `Population triage recommendation — requires clinician sign-off`.

**On screen:** Segment table with `<10` and `suppressed (complementary)` badges; tier queue; model badge.

**Narration:**

> Small cells below ten are suppressed, and complementary suppression stops subtraction. Sex encoding is auto-detected, so a clinician can upload without learning our schema. The score is a priority ranker, not a calibrated probability. It is trained on US NHANES and has not been validated on UAE data. Every actionable row requires clinician sign-off.

---

## 2:50–2:58 — Close

**On screen:** Title card over the queue: “Catch the risk before the diagnosis. Confirm the unit before the action.”

**Narration:**

> Nabdh: pre-lab triage that surfaces the invisible, deterministic rules that catch the urgent, and guardrails that make uncertainty visible. Demo-ready. Not a diagnosis.

**Caption:** `Repository + technical documentation + model card + limitations`

---

## Production notes

- Record at 30 fps, 1440×900, browser zoom 100%.
- Hide the bookmarks bar and notifications. Use a clean Chromium profile.
- Pre-load the page once so fonts and static assets are cached, then reload before recording.
- Move the cursor deliberately; pause 0.8–1.2 s on each evidence panel.
- Add captions for every narration block. If no voiceover is available, burn captions and keep them on screen long enough to read.
- Do not show the terminal, file paths outside the repo, or any real data.
- If a click fails, stop and re-record the segment; do not improvise a claim.
