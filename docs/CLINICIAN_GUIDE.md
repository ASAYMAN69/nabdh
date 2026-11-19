# A Clinician's Guide to Nabdh

**Who this is for:** clinicians, nurses, and screening programme staff who will upload a list of people and act on the results.
**Reading time:** about 10 minutes.
**What it is:** a demonstration tool that puts a screening list in priority order and highlights urgent findings.
**What it is not:** a diagnostic device, a substitute for clinical judgement, or a validated UAE screening calculator.

---

## 1. The short version

You upload a CSV with one row per person. Nabdh does three things:

1. **Puts the list in order.** People with the highest screening priority appear first.
2. **Explains the main reasons.** You can see what drove each person's position.
3. **Flags urgent findings.** If an uploaded lab or vital crosses a guideline threshold, the person is moved to **Urgent Clinical Review** and routine outreach is switched off.

A clinician still decides what the result means and what happens next. The tool never diagnoses, prescribes, or sends a message.

---

## 2. Before you upload

### The two required columns

| Column | What to put |
|---|---|
| `age` | Age in years, for example `45`. |
| `sex` | Safest: `male` or `female`. Also accepted: `m`/`f`, `0`/`1` (0 = male, 1 = female), `1`/`2` (1 = male, 2 = female). |

**Sex coding — read this once.** A file containing only `1`s is ambiguous: the tool reads it as `1 = female`. If all the people in your file are male and your system codes male as `1`, use the word `male`, or rename the column to `riagendr` and upload again. Mixing `0` and `2` in one file is also unsafe; use one convention.

### Strongly recommended

| Column | Why |
|---|---|
| `id` | A study or clinic ID. Without it, the tool uses the row number, and you cannot link a result back to a person after the file is closed. Do not use names or Emirates ID. |

### Complete for women who may be pregnant

`pregnant` (`yes`/`no`) is not just an optional extra. Pregnancy changes the pathway: a pregnant woman with severe-range blood pressure is sent to **urgent obstetric review**, not the adult pathway. If the person may be pregnant, record it. The minimal template includes a `pregnant` column; leave it blank for men.

### Helpful but optional

These make the priority order more complete:

- Height, weight, BMI, waist circumference
- Systolic and diastolic blood pressure
- Family history of diabetes
- Diagnosed high blood pressure, high cholesterol, heart disease, or kidney disease
- Diagnosed diabetes or prediabetes (`diagnosed_diabetes`, `borderline_diabetes`)
- Smoking, sleep hours
- Preferred language and district (for the outreach preview and privacy report)
- Lab results: HbA1c, fasting glucose, total cholesterol, HDL, LDL, triglycerides, eGFR, troponin, NT-proBNP, D-dimer, LVEF

If a field is missing, the tool still runs. It says the data is less complete; it does not invent a value.

### How to fill the cells

- **Do not type units inside a cell.** Write `126`, not `126 mg/dL`. If you need a non-standard unit, put the unit in the column name (see the CSV guide).
- **Do not use decimal commas or thousands separators.** Write `6.5`, not `6,5`; write `1200`, not `1,200`.
- **Dates are not read.** Do not put dates in numeric columns. For screening history, use the `yes`/`no` columns such as `glucose_test_3y`.
- **One row per person.** No merged cells, totals, or blank rows.

### File limits

- CSV, UTF-8.
- Comma is safest; semicolons, tabs, and `|` are also read.
- Maximum 200,000 rows, 1,000 columns, 64 MB.
- No names, Emirates ID, phone numbers, addresses, or free-text notes. Use a study or clinic ID.

### Templates

- Full template (all standard columns the tool reads): [`data/sample/clinician_template.csv`](../data/sample/clinician_template.csv) — also downloadable from the upload screen.
- Minimal starter (`id`, `age`, `sex`, `pregnant`): [`data/sample/clinician_template_minimal.csv`](../data/sample/clinician_template_minimal.csv).
- Labs in non-standard units: [`data/sample/clinician_template_lab_units.csv`](../data/sample/clinician_template_lab_units.csv).
- Full column guide: [CSV_GUIDE.md](CSV_GUIDE.md).

Delete the example rows and any columns you do not need. Blank cells are fine.

---

## 3. Reading the screen

### Cohort Summary

The cards at the top answer “what is in this list?”:

| Card | What it means |
|---|---|
| **Rows uploaded** | Number of people in the file. |
| **Urgent review** | People who need immediate clinician review. |
| **Adults with a score** | Adults who can receive an adult screening priority. |
| **High priority (30d)** | People to screen within about 30 days. |
| **Elevated (90d)** | People to screen within about 90 days. |
| **Missed by age-40 rule** | People under 40 who would not be invited by an age-only rule but have risk factors. |
| **Estimated undiagnosed diabetes cases** | A population-level estimate: the sum of the diabetes priority scores. It is **not** a count of people who have diabetes. |
| **Results checked** | Lab or vital results that were read and checked. |
| **Results not checked** | Results that could not be evaluated because the unit was unclear or implausible. They are **not** normal. |

### Screening Priority Queue

- The queue is sorted by priority. Use the search box to find a person by ID, flag, or district.
- Use the tier filter to show only urgent, high, or elevated people.
- Click a row to open the person's details.

### Patient details

When you click a person, you see:

- **Priority score** for diabetes and dysglycaemia. Higher means “screen sooner”.
- **Pathway and timing**: the recommended screening track and window.
- **Why flagged**: the main reasons, in plain language, with the direction of effect.
- **Urgent clinical alerts**: any rule that fired, with its guideline citation and version.
- **Other test results**: labs that were captured, including converted units.
- **Screening flags**: care gaps such as overdue tests or age-based eligibility.
- **Outreach preview**: a simulated message in the person's preferred language, with choices to confirm, reschedule, or opt out.

### Segment audit

The lower table shows how the list is distributed by age band, district, and language. Groups with fewer than 10 adults are hidden. A second “complementary” suppression stops someone from working out the small group by subtracting the other groups. This protects privacy; it does not change the person's own result.

---

## 4. What the priority score means

The score runs from **0 to 100**. A higher score means:

> “This person should be considered for screening sooner than someone with a lower score.”

It does **not** mean:

- “This person has a 49% chance of diabetes.”
- “This person will develop diabetes.”
- “This person should be excluded from care.”

The score was built to order a queue, not to estimate an individual's probability. The lab test and the clinician make the diagnosis. This distinction is deliberate: a screening programme can act on a ranking, but it cannot treat a ranking as a diagnosis.

---

## 5. What to do with each tier

| Tier | What it means | Usual action |
|---|---|---|
| **Urgent Clinical Review** | An uploaded result or vital crosses an urgent threshold, or the person is in an urgent clinical pathway. | Same-day clinician review. Do not rely on routine outreach; a clinician must act first. Follow your clinic's urgent/emergency route. |
| **High** | The person should be screened soon; a stage-2 BP or a lab in the diagnostic range may be present. | Accelerated screening, usually within about 30 days. As clinically indicated: HbA1c or fasting glucose, lipids, BP, kidney function. Confirm the result as local policy advises. |
| **Elevated** | Risk factors are present but no urgent threshold has been crossed. | Comprehensive screening within about 90 days. |
| **Routine - overdue** | The person is due for routine screening and is overdue. | Routine recall. |
| **Routine** | The person is due for routine screening. | Routine invitation. |
| **Low** | No significant flag in the supplied data. | Routine population screening. |
| **Insufficient data** | A required value is missing or invalid in that row, so the row cannot be scored. | Complete `age` or `sex` and upload again. Do not treat the row as “normal”. If the **column itself** is missing, the whole file is rejected with a message. |
| **Excluded** | The person already has diabetes, so the undiagnosed-diabetes score does not apply. They are routed to an existing-diabetes management pathway (or paediatric endocrine care for a child). | Continue routine diabetes care; do not treat the row as “no risk”. |

The timing windows are **planning targets**, not validated clinical deadlines. Local policy and clinical judgement come first.

---

## 6. Which results make a row urgent

A row becomes **Urgent Clinical Review** when any of these is present:

| Finding | Threshold used |
|---|---|
| Hypertensive crisis | BP ≥180/120 mmHg |
| Severe-range BP in pregnancy | BP ≥160/110 mmHg in a pregnant person |
| Elevated troponin I | ≥0.04 ng/mL (or your local assay's 99th-percentile upper reference limit) |
| Markedly elevated NT-proBNP | ≥900 pg/mL |
| Reduced LVEF | <40% |
| Severe coronary calcification | Coronary calcium score ≥300 AU |
| Elevated D-dimer | Above the age-adjusted upper reference limit (≥500 ng/mL FEU, or age × 10 if age >50) |

A low eGFR (<60) is **Elevated**, not urgent. A diagnostic HbA1c or fasting glucose is **High**, not urgent. This is deliberate: the tool escalates what needs immediate review, and routes the rest to a screening pathway.

If you believe a result is urgent but the tool did not flag it, act on your clinical judgement and record the reason. The tool does not replace review.

---

## 7. Common flags in plain language

| Flag | What it means |
|---|---|
| **Missed by age-40 screening rule (<40)** | The person is under 40, so an age-only invitation would skip them, but they have risk factors such as family history, central obesity, or elevated BP. |
| **Guideline-due with no glucose test in 3 years** | There is no recorded glucose test in the last 3 years. |
| **Cardiometabolic syndrome triad** | Central obesity (waist ≥102 cm in men, ≥88 cm in women) + elevated BP + family history or prediabetes. This combination raises priority even when age alone would not. |
| **Elevated BP without hypertension diagnosis** | BP is above the normal range but there is no recorded diagnosis. Follow up; do not assume the person is already treated. |
| **Stage 2 hypertension (BP ≥160/100)** | A single reading in the stage-2 range. Prompt clinical review and treatment assessment. |
| **Hypertensive crisis (BP ≥180/120)** | A single reading in the crisis range. Immediate BP recheck and emergency clinical evaluation. |
| **Diagnostic glycaemic lab (HbA1c ≥6.5% or FPG ≥126 mg/dL)** | A lab result in the diagnostic range. Confirm with repeat testing; a single lab is not a diagnosis. |
| **Severe-range BP in pregnancy (≥160/110)** | Urgent obstetric review, not a generic adult pathway. |
| **High cardiometabolic polygenic risk** | A genomic risk flag supplied in the file. It supports earlier preventive screening; it does not diagnose. |
| **Other test results** | A lab or vital was captured and checked. The detail panel shows the value, unit, and whether it was converted. |

---

## 8. When the tool deliberately holds back

These are safety features, not errors.

- **Missing `age` or `sex` column:** the file is rejected with a message telling you what to add.
- **A missing `age` or `sex` value in one row:** that row is marked **Insufficient data** and is not scored as normal.
- **A lab with no unit and an implausible value:** the value is marked **unit-suspect**. Only that lab is excluded from clinical rules; the person's other results are still used. Outreach is withheld in the demonstration. The detail panel says **Not Checked — Please Confirm the Unit**. Correct the unit and upload the file again. Do not treat the person as cleared.

**This matters most for urgent-range labs.** If a troponin, D-dimer, or NT-proBNP is in an urgent range but the unit is missing or ambiguous, it will **not** make the person Urgent. The row may look routine. Treat that result as unreviewed and follow it up manually; the tier is not reassurance.
- **A lab with an explicit non-standard unit:** it is converted (for example, HbA1c mmol/mol to %, or troponin ng/L to ng/mL). The original value and unit are kept.
- **Urgent finding:** routine outreach is switched off. A clinician must act.
- **Small group:** counts below 10 are hidden in the segment audit and in row-level district/language fields.
- **Pregnancy:** adult scores are withheld and the person follows the obstetric pathway.
- **Child (<20):** adult scores are withheld and the person follows the paediatric/Well-Child pathway.

### What the tool does not read

The tool applies clinical rules to a defined set of results. It does **not** apply rules to, for example: creatinine, potassium, sodium, INR, urine albumin/ACR, ALT/AST, bilirubin, TSH, haemoglobin, or ECG/QTc. If one of these is in your file, it may appear under **Other test results**, but it does not change the tier. A blank column does not mean “normal”; it may mean “not read”.

The tool also does not know:

- **When** a measurement was taken. Use the screening-history `yes`/`no` columns instead of dates.
- **Whether** a raised BP is already treated. `diagnosed_htn` records the diagnosis, not the treatment or the number of medicines.
- **Whether** a result has been repeated or confirmed.

---

## 9. Outreach previews

The outreach preview is **simulated**. No message is sent.

- Arabic previews render right-to-left.
- The preview offers **Confirm slot**, **Reschedule**, and **Opt out**.
- **Mark screening completed** records completion in the local tracker.
- The summary line above the queue shows how many people responded and completed screening.

In a real pilot, sending would require an approved channel, consent, language validation, and governance approval. None of that is active in this demonstration.

---

## 10. Safety and limits

Read this before using the tool outside the demonstration.

- **Not validated on UAE data.** The ranking was built from US national health survey data. It has not been tested on Emirati patients. Local prevalence, lab access, ancestry, and care pathways will change the results.
- **Not a diagnosis.** Every actionable tier requires clinician sign-off.
- **Single readings.** A single BP or lab value cannot confirm persistence, technique, or a chronic condition. Repeat as clinically appropriate.
- **Finite rule coverage.** The tool covers common cardiometabolic, cardiac, renal, paediatric, and preventive findings. It does not cover every test or condition.
- **No automated messaging.** The demo does not send anything.
- **No production security.** This is a local demonstration: no login, no multi-user isolation, no TLS. Do not put real patient data in it.
- **No fairness audit yet.** Performance by age, sex, ethnicity, district, and language has not been evaluated. A pilot must include that review.
- **No labs or BP in the file:** the tool can still order the list, but it has checked nothing that could be urgent. The absence of urgent rows means “not checked”, not “normal”.

---

## 11. Words you will see

| Word or abbreviation | Plain meaning |
|---|---|
| **HbA1c** | A blood test showing average glucose over about 3 months. |
| **FPG** | Fasting plasma glucose: a blood sugar test after fasting. |
| **LDL / HDL** | “Bad” / “good” cholesterol. |
| **eGFR** | A kidney filtration estimate. |
| **Troponin I** | A heart-muscle injury marker. |
| **NT-proBNP** | A heart-failure marker. |
| **D-dimer** | A clot-breakdown marker. Standard unit is ng/mL FEU; some labs report µg/mL FEU. If the unit is missing and the value looks implausible, the result is marked unit-suspect, not normal. |
| **LVEF** | Left ventricular ejection fraction: the percentage of blood the heart pumps out. A fraction such as 0.45 entered into `lvef_pct` is marked unit-suspect; use `lvef_fraction` or enter 45. |
| **Dysglycaemia** | Diabetes or prediabetes; blood sugar outside the normal range. |
| **Cardiometabolic** | Relating to the heart, blood vessels, and metabolism (blood sugar, cholesterol, blood pressure). |
| **Central obesity** | Fat around the waist. The tool uses waist ≥102 cm in men and ≥88 cm in women. |
| **Stage 2 hypertension** | BP in the ≥160/100 range. |
| **Well-Child pathway** | The child health visit and development/immunisation schedule. |
| **Obstetric pathway** | The pregnancy care pathway. |
| **Unit-suspect** | The number is present but the unit is unclear or implausible; the tool will not guess. An urgent-range result in this state is **not** escalated. |
| **BNP / NT-proBNP** | Two different heart-failure markers. The tool reads NT-proBNP only. |
| **Troponin I / troponin T** | Two different cardiac assays. The tool reads troponin I only. |
| **Small-cell suppression** | Hiding groups with fewer than 10 people to prevent identification. |
| **Outreach preview** | A simulated message. Nothing is sent. |

---

## 12. Questions clinicians often ask

**Can I upload my own column names?**
Common alternatives are accepted (for example `gender` for `sex`, `sbp` for `systolic_bp`, `a1c` for `hba1c`). The safest approach is to use the template.

**What if I do not have lab results?**
Upload what you have. The tool still orders the list, but the data completeness is lower and the priority is less certain.

**What if a value is missing?**
It is treated as missing, not as zero. The row may still be scored, with a completeness note. If the missing value is `age` or `sex`, the row is marked Insufficient data.

**What if I only have three columns?**
Use `id`, `age`, `sex`, and `pregnant`. The tool will order the list, but it checks no labs or BP. It cannot rule out an urgent finding. Use the full or lab-units template if you have results.

**Why is a child or pregnant woman not scored like an adult?**
Children use growth and Well-Child rules. Pregnant women use the obstetric pathway. Applying an adult cardiometabolic score to them would be misleading.

**What does “Estimated undiagnosed diabetes cases” mean?**
It is the sum of the diabetes priority scores across the list, expressed as a number. It is a population-level estimate to help size a screening list. It is not a count of confirmed cases.

**What does “unit-suspect” mean, and what should I do?**
The number was supplied but the unit is missing or implausible. The tool excludes that result from clinical rules and withholds outreach. Correct the unit in the source file and upload again. Do not treat the person as cleared.

**Why does the tool say “Insufficient data” for a row?**
A required value is missing or invalid, or the row cannot be interpreted. Complete `age` or `sex` and upload again.

**Can I send the outreach preview?**
No. It is a simulation. Sending requires a separate approved workflow.

**Can I use this for a real clinic list?**
Not without local validation, recalibration, governance approval, and clinician sign-off. The correct next step is a monitored pilot, not a go-live.

---

## 13. Before you upload: a 60-second checklist

- [ ] One row per person; no totals or merged cells.
- [ ] `age` and `sex` are filled in for every row.
- [ ] `id` is filled in and contains no names or Emirates ID.
- [ ] Sex uses one consistent convention across the file.
- [ ] `pregnant` is completed for women who may be pregnant.
- [ ] Units are standard, or the unit is in the column name.
- [ ] No units, decimal commas, thousands separators, or dates inside numeric cells.
- [ ] No names, Emirates ID, phone numbers, addresses, or notes.
- [ ] File is CSV, UTF-8, under 200,000 rows.
- [ ] You have checked the first few rows after upload and read the warnings.
- [ ] If the file has no labs or BP, you understand that urgent findings cannot be ruled out.

---

## 14. Where to learn more

- [CSV_GUIDE.md](CSV_GUIDE.md) — exact column names, accepted values, units, and common mistakes.
- [Full template](../data/sample/clinician_template.csv) — all standard columns the tool reads.
- [Minimal template](../data/sample/clinician_template_minimal.csv) — `id`, `age`, `sex`, `pregnant`.
- [Lab-units template](../data/sample/clinician_template_lab_units.csv) — non-standard units in the column names.
- [Synthetic example list](../data/sample/uae_demo_cohort.csv) — 60 example records.
- [MODEL_CARD.md](MODEL_CARD.md) — technical performance and limitations (for reviewers, not required for clinical use).
- [ASSUMPTIONS_AND_LIMITATIONS.md](ASSUMPTIONS_AND_LIMITATIONS.md) — full list of assumptions and gaps.

**Clinical notice:** this is a demonstration prototype. It is not a medical device and must not be used for diagnosis or treatment without local validation, regulatory review, and clinician sign-off.