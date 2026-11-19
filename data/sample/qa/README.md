# QA CSV set — manual testing

Upload these through the demo UI (or `POST /api/score`). Every file uses recognised
column names from `docs/CSV_GUIDE.md`. Values are synthetic.

## Master file — start here

**`00_master_all_cases.csv`** — 206 rows, 62 columns, every stream and edge case in one upload.

Verified through the live API:

```
206 rows → 24 urgent / 52 high / 45 elevated / 69 routine / 6 low / 4 excluded / 3 insufficient
84 observations captured · 24 unit-suspect · 12 warnings
```

ID prefixes:

| Prefix | What's in it | Rows |
|---|---|---:|
| `M-HLTHY` | Healthy adults | 15 |
| `M-DMRISK` | High undiagnosed-diabetes risk | 20 |
| `M-HTN` | Undiagnosed hypertension: stage 1 / stage 2 / crisis | 20 |
| `M-PREG` | Pregnancy: normal / gestational / severe | 10 |
| `M-PED` | Paediatric ages 0.5–19, all BMI bands | 25 |
| `M-DMLAB` | HbA1c / FPG diagnostic + pre-diabetes, standard + mmol | 20 |
| `M-LIPID` | Dyslipidaemia patterns, standard + mmol | 15 |
| `M-CKD` | eGFR 15–60 | 10 |
| `M-CV` | Troponin / NT-proBNP / LVEF, standard + ng/L | 15 |
| `M-SUSPECT` | Ambiguous units — not escalated | 10 |
| `M-EDGE` | Missing / implausible / boundary / duplicate / unknown | 16 |
| `M-SES` | Education 1–5 / text / missing | 10 |
| `M-SCR` | Screening-history gaps | 10 |
| `M-COMPLEX` | Multi-morbidity, some urgent cardiac | 10 |

Upload this one file and you get every tier, every stream, and every warning.

## Individual scenario files

| File | What it tests | What to look for |
|---|---|---|
| `01_healthy_young.csv` | Healthy young adults | Low/Routine, no clinical flags |
| `02_high_dm_risk.csv` | High undiagnosed-diabetes risk | High/Elevated; DM priority high |
| `03_undiagnosed_htn.csv` | Undiagnosed hypertension | Elevated/High; raised BP without diagnosis |
| `04_hypertensive_crisis.csv` | 185/115 adult + 165/110 pregnant | Urgent Clinical Review; Urgent obstetric for pregnancy |
| `05_pediatric.csv` | Ages 2, 8, 12, 16 | Paediatric stream; obesity / Well-Child / immunisation flags |
| `06_dm_labs_standard.csv` | HbA1c 6.9, FPG 126, pre-diabetes | High for diagnostic labs; Elevated for pre-diabetes |
| `06b_known_diabetes.csv` | Known diabetes, borderline, high HbA1c | Known diabetes → Excluded from undiagnosed ML; borderline → Elevated |
| `07_labs_nonstandard_units.csv` | mmol/mol, mmol/L, ng/L, µg/mL, fraction | Conversions shown; troponin 180 ng/L → urgent |
| `08_unit_suspect.csv` | 180 with no unit; d-dimer 0.5; LVEF 0.45 | `unit_suspect`, NOT escalated; excluded from rules |
| `09_education_test.csv` | education 1, 5, "college" | 200 OK; warning for text; score changes 1 vs 5 |
| `10_ckd_dyslipidaemia.csv` | Low eGFR, abnormal lipids | Elevated/High; CKD and dyslipidaemia priorities |
| `11_missing_and_implausible.csv` | Missing age/sex; age 130; BMI -5 | Insufficient data / bounds warnings |
| `12_mixed_cohort.csv` | 22 rows, every stream | Full demo: urgent, high, elevated, peds, pregnancy, unit-suspect, missing |
| `13_edge_cases.csv` | Age 19/20 boundary, pregnant male, sex=1, duplicate ID | Peds vs adult routing; pregnancy warning; sex-code warning; duplicate kept |

## Quick API check

```bash
curl -s -X POST -F "file=@data/sample/qa/04_hypertensive_crisis.csv" \
  http://127.0.0.1:8000/api/score | python -m json.tool | head -40
```

Or open http://127.0.0.1:8000/ and drag a file onto the upload card.
