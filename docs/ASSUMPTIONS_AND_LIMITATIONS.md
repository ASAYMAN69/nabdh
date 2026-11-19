# Assumptions and Limitations

**Version:** 1.0 · 2026-11-19
**Scope:** the Nabdh demonstration prototype and the Challenge 04 submission.

This file is deliberately blunt. The prototype is demo-ready; it is not production-ready and not clinically validated. Every assumption below is either enforced in code, reported in the UI, or listed as a residual gap.

---

## 1. Input assumptions

### 1.1 Required columns

- `age` (years, 0–120) and `sex` are mandatory. Missing either produces a clear rejection message with the accepted encodings.
- Sex is encoded as `male`/`female`, `m`/`f`, `0`/`1` (0 = male, 1 = female), or `1`/`2` (1 = male, 2 = female). The convention is auto-detected per file. `riagendr` is always 1 = male, 2 = female.
- A file containing both `0` and `2` is treated as `0/1`; the `2` values are not silently recoded. This is a deliberate fail-safe, documented in ADR-0002.
- One row is one person. Duplicate IDs are not merged or de-duplicated.
- Empty cells, `NA`, `NaN`, `null`, `none`, `n/a`, and `.` are treated as missing.

### 1.2 Units

| Test | Canonical unit | Accepted explicit alternatives | Conversion |
|---|---|---|---|
| HbA1c | % (NGSP) | mmol/mol (IFCC) | NGSP = 0.09148 × IFCC + 2.152 |
| Fasting plasma glucose | mg/dL | mmol/L | × 18.018 |
| Total cholesterol / HDL / LDL | mg/dL | mmol/L | × 38.67 |
| Triglycerides | mg/dL | mmol/L | × 88.57 |
| Troponin I | ng/mL | ng/L, pg/mL | ÷ 1000 |
| D-dimer | ng/mL FEU | µg/mL, mg/L | × 1000 |
| hs-CRP | mg/L | mg/dL | × 10 |
| LVEF | % | fraction (0–1) | × 100 |

Conversion happens only when the unit is **explicit** in the column name or unit field. The original value and unit are preserved as `raw_value` / `raw_unit` and shown in the inspector. A bare implausible magnitude (for example `troponin_i = 180` with no unit) remains `unit_suspect`, is excluded from clinical rules, and is shown in a “Not Evaluated — Confirm Units” panel. The engine does not guess.

### 1.3 Bounds and missingness

- Physiologically impossible values are treated as missing for that field and produce a cohort warning.
- Missing model features are imputed by the model pipeline (mean imputation). The UI reports completeness; it does not fabricate a lab.
- BMI and waist-to-height ratio are derived when height/weight or waist/height are present. Derived values are not treated as measured.
- BP is a single uploaded reading. The rules do not confirm persistence, cuff size, technique, or white-coat effect.

### 1.4 Pregnancy and paediatric routing

- `pregnant=yes` routes a row to the prenatal stream. Adult non-pregnant ML models are withheld. A pregnant row with severe-range BP (≥160 systolic or ≥110 diastolic) is escalated to urgent obstetric review.
- Age <20 routes to the paediatric stream. Adult ML models are withheld. WHO 2006/2007 BMI-for-age tables drive the growth flag.
- A negative or implausible age is treated as missing; it does not silently enter the adult stream.

## 2. Clinical assumptions

- **The tool does not diagnose.** It prioritises and flags. Every actionable tier has `requires_signoff: true`.
- **Guideline thresholds are applied as written.** Key examples:
  - BP ≥180/120 → Urgent (ACC/AHA 2017 hypertensive crisis).
  - BP ≥160/100 → High (ACC/AHA 2017 stage 2).
  - BP ≥160/110 in pregnancy → Urgent obstetric review (ACOG Practice Bulletin 222).
  - HbA1c ≥6.5% or FPG ≥126 mg/dL → High, with “confirm with repeat testing” (ADA Standards of Care 2025).
  - Troponin I ≥0.04 ng/mL → Urgent (4th Universal Definition of MI; 2021 AHA/ACC chest-pain guideline).
  - NT-proBNP ≥900 pg/mL → Urgent (2022 AHA/ACC/HFSA heart-failure guideline).
  - LVEF <40% → Urgent (same guideline).
  - D-dimer above the age-adjusted / assay threshold → Urgent.
- **A single abnormal lab is not a diagnosis.** The action text says confirm, repeat, or evaluate. The rule pack cites the source and version.
- **The rules are not a complete clinical vocabulary.** They cover common cardiometabolic, cardiac, renal, paediatric, and preventive findings. An unlisted test is captured as an observation, not silently interpreted.
- **The model score and the rules are separate.** Labs and vitals change flags and tier, not the pre-lab priority percentage. This is stated in the UI.
- **Age-40 screening rules intentionally miss younger adults.** The queue surfaces those rows separately (`Missed by age-40 screening rule`) rather than pretending the guideline covers them. A clinician decides whether to include them.

## 3. Model assumptions

- The five models are **pre-lab rankers**, not calibrated risk calculators. AUC ≈ 0.67–0.77 is moderate discrimination for questionnaire/anthropometry data.
- The `nofamily` variant is the only externally validated path (NHANES 2021–23). `full` is a 25% internal holdout; it cannot be externally validated because NHANES 2021–23 lacks the family-history variable.
- The diabetes holdout O:E is 1.255 with a 95% CI of 0.934–1.899 on 33 events. It is not statistically distinguishable from 1.0. (The pre-sign-constraint artifact had O:E 1.377; the shipped artifact is 1.255.)
- A Platt calibration candidate reaches O:E 1.001 and improves Brier 0.04449 → 0.04373 without changing AUC. It is **not deployed**, because tier thresholds were not re-derived.
- The model is trained on U.S. NHANES. No UAE, Emirati, or Malaffi data was used. Local prevalence, ancestry, lab access, and care pathways will shift calibration.
- No subgroup (age, sex, ethnicity, district, language) performance audit has been completed.
- `income_ratio` is a model feature and may encode access to care. It is not a fairness-neutral variable.
- Feature experiments (glucose-test recency, age², BMI × family history, age × BMI) moved cross-validated AUC by less than ±0.001. LightGBM was worse on 8 of 10 target/variant pairs. The model was therefore frozen for the submission; retraining is not a demo-week activity.

## 4. Operational and security assumptions

- The demo is **single-tenant and local**: `uvicorn` on `127.0.0.1:8000`, no authentication, no TLS, no multi-user isolation.
- Uploads are capped at 64 MB, 200,000 rows, and 1,000 columns. Delimiters `, ; \t |` are detected.
- CSV export is formula-sanitised (leading `= + - @` are neutralised) and served with `nosniff` and `no-store`.
- Cohort scoring is deterministic and makes **zero network or LLM calls** by default. `StubReasoner` returns `unavailable` unless a local/approved reasoner is configured.
- Outreach previews are simulated. `data/outcomes.db` stores only the synthetic demo outcomes.
- Segment counts below 10 are suppressed, with complementary suppression to prevent subtraction.
- The demo cohort is synthetic; no PHI is present. The UI states this. A production pilot would still need a consent/authorised-use field, role-based access, audit logging, encryption at rest and in transit, retention rules, and a DPIA.
- Arabic outreach previews are generated for demonstration. They are not sent, and language/literacy validation with patients has not been performed.

## 5. Residual gaps (known, not hidden)

| Gap | Consequence | Mitigation in this submission |
|---|---|---|
| No UAE validation | Calibration and transportability unknown | Stated in UI, README, model card; local recalibration required |
| No calibration deployed | Percentages are not probabilities | UI says “priority score”; model card documents candidate calibration |
| `full` not externally validated | Internal holdout only | Model card and demo script say so explicitly |
| No subgroup audit | Fairness unknown | Listed as a pre-pilot requirement |
| Single BP reading | Crisis/stage-2 flags may over- or under-call | Action text says recheck / clinical evaluation |
| Finite rule coverage | Unlisted tests are captured but not interpreted | Observation panel + `unit_suspect` warning |
| No consent field | Outreach preview could be mistaken for authorised contact | Synthetic-data banner; messages simulated; production gap documented |
| No auth / TLS | Not internet-safe | Local demo only; deployment hardening listed |
| No prospective workflow study | Recall and completion impact unknown | Outcome tracker is a prototype; pilot metrics proposed |
| No regulatory review | Not a medical device | Clinical notice in LICENSE and README |

## 6. What would be required before a UAE pilot

1. **Local data access and governance:** DoH/Malaffi data-sharing agreement, ethics approval, DPIA, consent/authorised-use model.
2. **Recalibration and validation:** intercept/slope recalibration on a representative local cohort; prospective validation of AUC, O:E, and capture by subgroup.
3. **Threshold review:** re-derive tier cutoffs after calibration; clinician panel sign-off.
4. **Workflow evaluation:** nurse-led screening clinic, recall scripts in Arabic/English, completion and time-to-diagnosis metrics.
5. **Safety monitoring:** incident log for missed urgent findings, override audit, rule-pack change control.
6. **Security hardening:** authentication, role-based access, TLS, audit logs, encryption, retention, penetration test.
7. **Regulatory and clinical sign-off:** determine device classification, obtain approvals, and train users.

Until then, the correct description is: **a demo-ready pre-lab triage and guideline-rules prototype, not a clinical product.**
