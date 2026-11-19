# Patient Data Curation & Multi-Stream Routing Guide

To prevent ML models from hallucinating or extrapolating outside their training population, incoming patient records **must** be curated and divided into clinical streams **before** model inference. Nabdh enforces this automatically in `nabdh/engine.py`, and clinic data pipelines should prepare CSVs using the conventions below.

---

## 1. Pre-ML Clinical Streams

Before any ML model scores a row, the ingestion router assigns the patient to one primary clinical stream:

| Stream | Condition | Why Separated | What Runs Instead |
| :--- | :--- | :--- | :--- |
| **`insufficient_data`** | Missing/invalid `age` or `sex` | Models cannot stratify baseline risk without age and biological sex. | Returned for chart completion (`Insufficient data`). |
| **`paediatric`** | `age < 20` | Adult NHANES models were trained exclusively on ages `20–80+`. Applying them to children produces invalid probabilities. | WHO 2006 (`0–5y`) / WHO 2007 (`5–19y`) BMI-for-age LMS z-score rules + paediatric flags. |
| **`prenatal`** | `pregnant` is `yes`/`true`/`1` | Pregnancy alters anthropometrics (waist/WHtR), blood pressure, lipids, and glycaemic thresholds. | Prenatal screening reminders (BP monitoring, GDM screening window). |
| **`adult_preventive`** | `age >= 20` and not pregnant | Matches the NHANES adult training population. | Condition-gated ML models + USPSTF guideline screening rules + direct lab checks. |

---

## 2. Per-Target Eligibility Gates (Inside `adult_preventive`)

Even within `adult_preventive`, **a model only scores a condition if the patient is not already diagnosed with it**:

| ML Target | Excluded If Already True | Required/Core Signals |
| :--- | :--- | :--- |
| **`undiagnosed_dm`** | `diagnosed_diabetes == yes` | `age`, `sex`, `whtr`/`bmi`/`waist`, `systolic_bp`, `diagnosed_htn`, `family_hx_diabetes` (optional) |
| **`dysglycaemia`** | `diagnosed_diabetes == yes` OR `borderline_diabetes == yes` | Same as above |
| **`undiagnosed_htn`** | `diagnosed_htn == yes` | `age`, `sex`, `whtr`/`bmi`, `smoker`, `high_chol`, `cvd_history`, `income_ratio` (uses non-BP features so it can flag BP-check need when cuff BP is missing) |
| **`undiagnosed_dyslipidaemia`** | `high_chol == yes` | `age`, `sex`, `whtr`/`bmi`, `systolic_bp`, `diagnosed_htn`, `smoker`, `cvd_history`, `income_ratio` |
| **`ckd_risk`** | `ckd == yes` | `age`, `sex`, `whtr`/`bmi`, `systolic_bp`, `diagnosed_htn`, `high_chol`, `cvd_history`, `smoker`, `sleep_hours`, `income_ratio` |

> **Rule of thumb:** If a patient already has `diagnosed_diabetes = yes`, the engine skips `undiagnosed_dm` ML prediction for them (no false "undiagnosed" score) while still evaluating their **hypertension, dyslipidaemia, CKD, and cancer/osteoporosis screening gaps**.

---

## 3. How to Curate & Normalize Your CSV

### Required Columns
- `age`: numeric years (`0–120`).
- `sex`: strings `male`/`m`/`female`/`f`, or a numeric coding. **The numeric encoding is
  detected automatically from the column; you are never asked to choose it.**
  - The canonical internal encoding is `0 = male`, `1 = female`. A generic `sex`/`gender`
    column is read that way unless it contains a `2` and no `0`, in which case it is read as
    NHANES `1 = male`, `2 = female`. A column named `riagendr` is always read as
    `1 = male`, `2 = female`.
  - **Blank cells are allowed.** A blank sex routes that row to `Insufficient data`; it does not
    reject the file.
  - **Undecodable values do not reject the file.** They are reported in the response warnings,
    and that row is scored as `Insufficient data`. A file containing both `0` and `2` is treated
    as `0/1`; the `2`s degrade to missing rather than flipping the whole cohort.
  - **All-`1` ambiguity:** a generic column containing only `1`s is read as `1 = female` under
    the canonical `0/1` convention, and the response carries a warning. Rename an NHANES
    `1/2` column to `riagendr` to remove the ambiguity.
  - There is no sex-encoding field in the web UI or the API. See
    [ADR-0002](adr/0002-auto-detect-sex-encoding.md) and the
    [change record](CHANGE_RECORD_2026-11-19_CLINICAL_SEMANTICS.md).

### Recommended Anthropometrics & Vitals
Provide at least one adiposity measure so `whtr` (waist-to-height ratio) does not fall back to population mean:
- `height_cm` (cm), `weight_kg` (kg), `bmi` (kg/m²), `waist` (cm), `whtr` (`waist / height_cm`).
- `systolic_bp` (mmHg), `diastolic_bp` (mmHg).

### Clinical History & Lifestyle Columns (Boolean: `yes`/`no`, `true`/`false`, `1`/`0`)
- `family_hx_diabetes`, `diagnosed_htn`, `high_chol`, `cvd_history`, `ckd`, `pregnant`
- `diagnosed_diabetes`, `borderline_diabetes`
- `smoker` (or `current_smoker`), `pack_years` (numeric, for lung LDCT eligibility), `sleep_hours` (numeric hours/night)
- `glucose_test_3y`, `chol_test_5y`, `colorectal_screen_10y`, `mammogram_2y`, `cervical_screen_3y`
- `income_ratio` (household income / poverty threshold, numeric)

### Optional Lab Columns (When Available)
If your clinic export already includes recent labs, pass them directly—the engine flags abnormal results deterministically without guessing:
- `hba1c` (%), `fpg` (mg/dL), `total_chol` (mg/dL), `hdl` (mg/dL), `ldl` (mg/dL), `triglycerides` (mg/dL), `egfr` (mL/min/1.73m²)

### Outreach & Privacy Columns
- `id` (de-identified patient key), `district`, `language` (`EN`, `AR`, `UR`, `TL`, `HI`, `BN`, etc.).
- Note: Segment counts `< 10` are automatically redacted in cohort equity audits.

---

## 4. Curation Checklist Before Scoring
1. **De-identify rows:** Never upload names, national IDs, or phone numbers—use a pseudonymous `id`.
2. **Standardize units:** Heights in `cm`, weights in `kg`, waist in `cm`, BP in `mmHg`, glucose/lipids in `mg/dL`, HbA1c in `%`.
3. **Leave unknowns blank:** Use empty cells (`""` or `NA`), never `"0"` or `999` for missing measurements—the pipeline distinguishes true `0` from missing `NaN`.
4. **Separate known diagnoses:** Populate `diagnosed_diabetes`, `diagnosed_htn`, `high_chol`, `ckd`, and `pregnant` accurately so the pre-ML stream router suppresses irrelevant screening models.
