# How to Prepare Your CSV

**Who this is for:** anyone preparing a screening list for Nabdh.
**Time needed:** 5–10 minutes.
**Goal:** a clean CSV that the tool can read without warnings, with the right units and one row per person.

---

## 1. The short version

A CSV is just a table saved as text. You can make one in Excel or Google Sheets.

The tool **requires two columns**:

| Column | What to put |
|---|---|
| `age` | Age in years, for example `45`. |
| `sex` | `male` or `female` (also `m`/`f`, `0`/`1`, `1`/`2`). |

We **strongly recommend a third column**:

| Column | What to put |
|---|---|
| `id` | A study or clinic ID. Without it, the tool uses the row number, and you cannot link a result back to a person. Do not use names or Emirates ID. |

Everything else is optional. More detail gives a better priority order, but the tool still works with just `id`, `age`, and `sex`.

- Full template (all standard columns): [`data/sample/clinician_template.csv`](../data/sample/clinician_template.csv)
- Minimal starter (`id`, `age`, `sex`, `pregnant`): [`data/sample/clinician_template_minimal.csv`](../data/sample/clinician_template_minimal.csv)
- Labs in non-standard units: [`data/sample/clinician_template_lab_units.csv`](../data/sample/clinician_template_lab_units.csv)

---

## 2. Make the file in Excel or Google Sheets

1. Put the column names in the **first row**.
2. Put **one person per row** underneath.
3. Do not merge cells.
4. Do not add title rows, blank rows, totals, or notes below the table.
5. Keep the column names exactly as shown in this guide. Common alternatives are accepted, but the template is safest.
6. Save or download as **CSV UTF-8**. In Excel: **File → Save As → CSV UTF-8 (Comma delimited)**. In Google Sheets: **File → Download → Comma-separated values (.csv)**.
7. Check the first few rows after saving. If Excel changed a value (for example, removed a leading zero or turned a date into a serial number), fix it before uploading.

### Three things that commonly break a CSV

- **Units inside a cell.** Write `126`, not `126 mg/dL`. If you need a non-standard unit, put it in the column name (see §4).
- **Decimal commas or thousands separators.** Write `6.5`, not `6,5`; write `1200`, not `1,200`. Excel may interpret `6,5` as a date or split the column.
- **Dates inside numeric columns.** The tool does not read dates. Use the `yes`/`no` screening-history columns instead.

---

## 3. Column dictionary

### Required and recommended

| Column | Required? | Accepted values | Example | Notes |
|---|---|---|---|---|
| `id` | Recommended | Text or number | `EX-001` | Unique within the file. If missing, the tool uses the row number. Do not use names or Emirates ID. |
| `age` | **Required** | Whole years, 0–120 | `45` | Missing or impossible values are flagged, not guessed. |
| `sex` | **Required** | Safest: `male`, `female`. Also: `m`, `f`, `0`, `1`, `2` | `female` | `0/1` means 0 = male, 1 = female. `1/2` means 1 = male, 2 = female. Use one convention for the whole file. |

**Sex coding — read this once.** A file containing only `1`s is ambiguous: the tool reads it as `1 = female`. If all the people in your file are male and your system codes male as `1`, use the word `male`, or rename the column to `riagendr` and upload again. Mixing `0` and `2` in one file is also unsafe.

### Helpful: body and vitals

| Column | Unit | Example | Notes |
|---|---|---|---|
| `height_cm` | cm | `170` | Used to calculate BMI and waist-to-height ratio if BMI is missing. |
| `weight_kg` | kg | `82` | Used with height. |
| `bmi` | kg/m² | `31.0` | If missing, it is calculated from height and weight. |
| `waist_cm` | cm | `101` | Also accepted as `waist`. |
| `whtr` | ratio | `0.55` | Waist divided by height. Optional if waist and height are present. |
| `systolic_bp` | mmHg | `145` | Also accepted as `sbp` or `systolic`. |
| `diastolic_bp` | mmHg | `92` | Also accepted as `dbp` or `diastolic`. |

### Helpful: health history

Use `yes`/`no` (also `y`/`n`, `true`/`false`, `1`/`0`).

| Column | What it records | Example |
|---|---|---|
| `family_hx_diabetes` | Family history of diabetes | `yes` |
| `diagnosed_htn` | Already diagnosed with high blood pressure | `no` |
| `high_chol` | Already diagnosed with high cholesterol | `no` |
| `cvd_history` | History of heart disease or stroke | `no` |
| `family_hx_cvd` | Family history of heart disease or stroke | `no` |
| `ckd` | Already diagnosed with kidney disease | `no` |
| `pack_years` | Smoking pack-years | `0` |
| `current_smoker` | Currently smokes | `no` |
| `sleep_hours` | Average hours per night | `6.5` |
| `pregnant` | Currently pregnant | `no` |
| `diagnosed_diabetes` | Already diagnosed with diabetes | `no` |
| `borderline_diabetes` | Previously told they have prediabetes | `no` |

**Complete `pregnant` for every woman who may be pregnant.** It changes the pathway: severe-range BP in pregnancy is an urgent obstetric finding, not a routine adult result. The minimal template includes this column; leave it blank for men.

**`diagnosed_htn` records the diagnosis, not the treatment.** The tool does not know whether a raised BP is already treated or how many medicines the person takes.

### Helpful: screening history

Use `yes`/`no`. These replace dates: record whether the test was done, not when.

| Column | What it records | Example |
|---|---|---|
| `glucose_test_3y` | Glucose test in the last 3 years | `no` |
| `chol_test_5y` | Cholesterol test in the last 5 years | `yes` |
| `colorectal_screen_10y` | Colorectal screening in the last 10 years | `no` |
| `mammogram_2y` | Mammogram in the last 2 years | `no` |
| `cervical_screen_3y` | Cervical screening in the last 3 years | `yes` |
| `healthcare_visit_12m` | Any healthcare visit in the last 12 months | `yes` |

### Optional: lab results

Use the standard units in the table. If your lab uses a different unit, either convert it before upload or use the unit-suffixed column name in §4.

| Column | Standard unit | Example |
|---|---|---|
| `hba1c` | % | `6.9` |
| `fpg` | mg/dL | `126` |
| `total_chol` | mg/dL | `190` |
| `hdl` | mg/dL | `45` |
| `ldl` | mg/dL | `120` |
| `triglycerides` | mg/dL | `150` |
| `egfr` | mL/min/1.73m² | `78` |
| `troponin_i` | ng/mL | `0.18` |
| `nt_probnp` | pg/mL | `300` |
| `d_dimer` | ng/mL FEU | `500` |
| `lvef_pct` | % | `34` |
| `coronary_calcium_score` | AU | `120` |
| `hs_crp` | mg/L | `2.5` |
| `lp_a` | nmol/L | `30` |

**Do not type units in the cells.** A cell containing `126 mg/dL` is text and will be treated as missing. Use the column name for the unit.

### Optional: children and adolescents

For people under 20, the adult score is not used. These columns support the paediatric/Well-Child rules:

| Column | Accepted values | Example |
|---|---|---|
| `missed_well_child_visits` | Count | `1` |
| `developmental_delay_flag` | `yes`/`no` | `no` |
| `immunization_status` | `overdue`, `up_to_date`, `incomplete`, `complete` | `up_to_date` |
| `healthcare_visit_12m` | `yes`/`no` | `yes` |

### Optional: genomic flags

| Column | Accepted values | Example |
|---|---|---|
| `prs_cardiometabolic` | `low`, `medium`, `high` | `high` |
| `g6pd_status` | `normal`, `deficient` | `normal` |
| `thalassemia_carrier` | `yes`/`no` | `no` |

### Optional: context and outreach

| Column | Accepted values | Example | Notes |
|---|---|---|---|
| `district` | Text | `Al Ain` | Used in the privacy report. Small groups are hidden. |
| `language` | Text, for example `AR`, `EN`, `TL`, `UR` | `AR` | Used to choose the outreach preview language. |
| `income_ratio` | Number | `2.5` | Optional income measure. Leave blank if you do not have it. |

---

## 4. Units and unit-suffixed column names

If your lab uses a non-standard unit, the safest approach is to put the unit in the **column name**. These names are recognised:

| Lab | Column names that work | What the tool does |
|---|---|---|
| HbA1c | `hba1c`, `hba1c_mmol_mol`, `hba1c_ifcc`, `a1c` | Converts mmol/mol to %. |
| Fasting glucose | `fpg`, `fpg_mmol_l`, `glucose_mmol_l`, `fasting_glucose` | Converts mmol/L to mg/dL. |
| Total cholesterol | `total_chol`, `total_chol_mmol_l`, `cholesterol_mmol_l` | Converts mmol/L to mg/dL. |
| HDL | `hdl`, `hdl_mmol_l` | Converts mmol/L to mg/dL. |
| LDL | `ldl`, `ldl_mmol_l` | Converts mmol/L to mg/dL. |
| Triglycerides | `triglycerides`, `triglycerides_mmol_l`, `tg_mmol_l` | Converts mmol/L to mg/dL. |
| Troponin I | `troponin_i`, `troponin_i_ng_l`, `troponin_i_pg_ml` | Converts ng/L or pg/mL to ng/mL. |
| NT-proBNP | `nt_probnp`, `nt_probnp_pg_ml` | pg/mL. |
| D-dimer | `d_dimer`, `d_dimer_ug_ml`, `d_dimer_mg_l` | Converts µg/mL or mg/L to ng/mL FEU. **If you enter a µg/mL value such as 0.5 into `d_dimer`, it is marked unit-suspect and is not escalated.** Use `d_dimer_ug_ml` or convert. |
| LVEF | `lvef_pct`, `lvef_fraction` | Converts a fraction (0–1) to %. **A fraction such as 0.45 entered into `lvef_pct` is marked unit-suspect and is not escalated.** Use `lvef_fraction` or enter 45. |

The original value and unit are kept, and the screen shows a warning such as “interpreted and converted to mg/dL”. If you use a plain column such as `hba1c` and enter `58`, the tool detects that it cannot be a percentage and converts it from mmol/mol. If the value is plausible in the standard unit, it is left alone.

**If the value has no unit and looks implausible, the tool will not guess.** It marks the result as **unit-suspect**, excludes that result from clinical rules, and withholds outreach. Correct the unit and upload again.

**Assay names matter.** The tool reads **troponin I** and **NT-proBNP**. It does not distinguish troponin T from troponin I, or BNP from NT-proBNP. Do not put a different assay in these columns; leave it blank or use a column the tool recognises.

---

## 5. Common mistakes and how to fix them

| Mistake | What happens | Fix |
|---|---|---|
| Missing `age` or `sex` column | Upload is rejected with a message. | Add both columns. |
| A missing `age` or `sex` value in one row | That row is marked Insufficient data. | Fill the value or remove the row. |
| Mixing `0/1` and `1/2` sex codes in one file | The file is read as `0/1`; any `2` becomes missing. | Use one convention for the whole file. |
| Sex column contains only `1` | Read as `1 = female` with a warning. | If your file uses 1 = male and 2 = female, rename the column to `riagendr` and upload again. |
| A number field contains text such as `abc` | Treated as missing; row still scored if age/sex exist. | Correct the cell or leave it blank. |
| Age `130` or BMI `-5` | Treated as missing and warned about. | Correct the value. |
| HbA1c entered as `58` with no unit | The tool detects mmol/mol and converts it. If the value is ambiguous, it is marked unit-suspect. | Use `hba1c_mmol_mol` or convert to %. |
| D-dimer `0.5` entered into `d_dimer` | Marked unit-suspect; the urgent rule is not triggered. | Use `d_dimer_ug_ml` or convert to ng/mL FEU. |
| LVEF `0.45` entered into `lvef_pct` | Marked unit-suspect; no urgent alert is triggered. | Use `lvef_fraction` or enter 45. |
| A file of all `1`s for sex | Read as female. | Use `male`/`female`, or rename the column to `riagendr`. |
| A troponin T or BNP value in `troponin_i` / `nt_probnp` | Wrong assay; the threshold may be wrong. | Leave blank or use the correct column. |
| Units typed in a cell (`126 mg/dL`) | Treated as text and then as missing. | Put the unit in the column name or convert to the standard unit. |
| Decimal comma (`6,5`) or thousands separator (`1,200`) | The column may split or be read as text. | Use a dot and no separator. |
| Dates in numeric columns | Dates are not read. | Use the `yes`/`no` screening-history columns. |
| Merged cells or title rows | The header is not read correctly. | Keep one clean header row. |
| No `id` | The tool uses the row number. | Add an `id` if you need to link results back to a person. |
| Duplicate IDs | Both rows are kept; they are not merged. | Give each person a unique ID. |
| `pregnant` left blank for a woman who may be pregnant | The adult pathway is used instead of the obstetric pathway. | Complete `pregnant` for every woman who may be pregnant. |
| Extra unknown columns | Ignored unless the tool recognises them. | Remove columns you do not need. |
| Names, Emirates ID, phone numbers, notes | These are not needed and should not be uploaded. | Remove them; use a study ID. |
| CSV saved as `.xlsx` | The tool only reads CSV. | Save as CSV UTF-8. |

---

## 6. Example

The full template contains two synthetic examples. This is the core of the first row:

```csv
id,age,sex,height_cm,weight_kg,bmi,waist_cm,systolic_bp,diastolic_bp,family_hx_diabetes,pregnant,district,language
EX-001,29,female,162,87,33.2,92,138,86,yes,no,Al Ain,AR
EX-002,52,male,175,95,31,101,145,92,yes,no,Khalifa City,EN
```

The full file also has blank columns for labs and screening history. Delete the example rows before you add your own people. Keep the header row. If you only need the essentials, use the minimal template:

```csv
id,age,sex,pregnant
EX-001,29,female,no
EX-002,52,male,
```

---

## 7. What happens after you upload

- The tool reads the file and shows a **Cohort Summary**.
- It lists warnings in plain language at the top of the results.
- A row with missing `age` or `sex` is marked **Insufficient data**. It is not treated as normal.
- If one lab has an ambiguous unit, **only that lab** is excluded. The person's other results are still used, and the detail panel says **Not Checked — Please Confirm the Unit**. Correct the unit and upload again.
- **A unit-suspect urgent-range lab will not make the person Urgent.** If a troponin, D-dimer, or NT-proBNP is in an urgent range but the unit is missing or ambiguous, the row may look routine. Treat the result as unreviewed and follow it up manually; the tier is not reassurance.
- Small groups are hidden in the privacy report.
- You can click any row to see why the person was flagged, what was captured, and what the recommended pathway is.

---

## 8. Tests the tool does not read

The tool applies clinical rules to a defined set of results. It does **not** apply rules to, for example:

- Creatinine, potassium, sodium
- INR
- Urine albumin/ACR
- ALT/AST, bilirubin
- TSH
- Haemoglobin
- ECG/QTc
- BNP (the tool reads NT-proBNP only)
- Troponin T (the tool reads troponin I only)

If one of these is in your file, it may appear under **Other test results**, but it does not change the tier. A blank column does not mean “normal”; it may mean “not read”.

---

## 9. Privacy checklist

Before you upload, remove:

- [ ] Names
- [ ] Emirates ID or national ID
- [ ] Phone numbers
- [ ] Addresses
- [ ] Email addresses
- [ ] Free-text notes
- [ ] Any column that could identify a person outside your clinic

Use a study or clinic ID that only your team can link back to the person. This demonstration is local and has no login; do not put real patient data in it.

---

## 10. Final checklist

- [ ] One row per person.
- [ ] `id`, `age`, and `sex` filled in for every row.
- [ ] One sex convention across the file.
- [ ] `pregnant` completed for women who may be pregnant.
- [ ] Standard units, or the unit is in the column name.
- [ ] No units, decimal commas, thousands separators, or dates inside numeric cells.
- [ ] No merged cells, totals, or blank rows.
- [ ] Saved as CSV UTF-8.
- [ ] No names or identifiers.
- [ ] First few rows checked after upload.
- [ ] Warnings read before acting on the list.
- [ ] If the file has no labs or BP, understood that urgent findings cannot be ruled out.

---

## 11. Need a hand?

- Main guide: [CLINICIAN_GUIDE.md](CLINICIAN_GUIDE.md)
- Full template: [`data/sample/clinician_template.csv`](../data/sample/clinician_template.csv)
- Minimal template: [`data/sample/clinician_template_minimal.csv`](../data/sample/clinician_template_minimal.csv)
- Synthetic example list: [`data/sample/uae_demo_cohort.csv`](../data/sample/uae_demo_cohort.csv)
- One-row test files: [`data/sample/probes/`](../data/sample/probes/)

If the tool rejects the file, read the message at the top of the screen. It names the missing or invalid column and what to do next.