# Nabdh Raw Datasets Inventory & Schema Mapping

All datasets in `/mnt/ee/aprojects/nabdh/data/raw/` are real, openly downloadable public datasets retrieved without authentication, login, or access-gate bypass.

> **Important Note on Label Leakage:** Several datasets include both diagnostic biomarkers (e.g., `LBXGH` HbA1c, `LBXGLU` fasting glucose, `BPXOSY1–3` systolic BP) and questionnaire items (`DIQ010` diagnosed diabetes, `DIQ180` past-3-year glucose test). When training a **screening-prioritization model** whose label is derived from lab values (e.g., undiagnosed diabetes `HbA1c >= 6.5%` or prediabetes `HbA1c >= 5.7%` / `FPG >= 100 mg/dL`), **never include `LBXGH`, `LBXGLU`, `LBDGLUSI`, `DIQ050` (insulin), `DIQ070` (diabetes pills), or `DIQ160` (prediabetes told) as input features**.

---

## Summary Inventory

| # | Dataset | Directory | Format | Key Scope | Primary Role in Nabdh |
|---|---|---|---|---|---|
| 1 | **CDC NHANES 2017–March 2020 Pre-Pandemic (`P_*`)** | `data/raw/nhanes_2017_2020/` | 19 SAS `.xpt` files | `15,560` participants (ages `0–80+`, incl. `5,867` `<18y`, `2,025` `<5y`, `9,693` adults) | **Primary training cohort** — only recent NHANES cycle with biological family history (`MCQ300C`, `MCQ300A`), labs (HbA1c, FPG, lipids), oscillometric BP, screening history (`DIQ180`, `BPQ060`, `HUD062`), and pediatric growth/immunizations |
| 2 | **CDC NHANES 2021–2023 (`*_L`)** | `data/raw/nhanes_2021_2023/` | 19 SAS `.xpt` files | `11,933` participants (ages `0–80+`, incl. `3,780` `<18y`, `991` `<5y`, `8,153` adults) | **Temporal external validation / drift-check cohort** — post-pandemic clinical labs, BP, anthropometry, screening history (`DIQ180`), pediatrics (note: `MCQ300C`/`MCQ300A` removed; `HUQ055` is telehealth video visits only) |
| 3 | **UCI ID 891 — CDC Diabetes Health Indicators (BRFSS 2015)** | `data/raw/uci_datasets/` | CSV (`13.5 MB`) | `253,680` adults, `23` columns | **Large-scale adult lifestyle & care-access benchmark** (`HighBP`, `HighChol`, `CholCheck`, `BMI`, `AnyHealthcare`, `NoDocbcCost`, `GenHlth`, `Sex`, `Age` bins) |
| 4 | **UCI ID 529 — Early Stage Diabetes Risk Prediction** | `data/raw/uci_datasets/` | CSV (`34.7 KB`) | `520` patients, `17` columns | **Symptom-signal auxiliary set** (polyuria, polydipsia, sudden weight loss, visual blurring, obesity) |
| 5 | **UCI ID 45 — Heart Disease (Cleveland)** | `data/raw/uci_datasets/` | CSV (`11.3 KB`) | `303` patients, `14` columns | **CVD auxiliary benchmark** (chest pain, resting BP `trestbps`, cholesterol `chol`, `fbs > 120`, ECG, `thalach`, angiographic `num`) |
| 6 | **WHO Growth Reference 2007 (5–19 Years, `anthroplus`)** | `data/raw/who_growth_standards/` | 3 TSV `.txt` files | `340` rows BMI-for-age & height-for-age (`60–229` months), `124` rows weight-for-age (`60–121` months) | **Pediatric LMS z-score / percentile calculation** (ages `5–19y`) for Well-Child overweight/obesity & stunting flags |
| 7 | **WHO Global Health Observatory (GHO) — UAE Indicators** | `data/raw/who_gho_uae/` | 10 JSON files | UAE (`ARE`) national time-series (`26–405` records per indicator) | **Local UAE calibration priors & care-gap benchmarks** (diabetes prevalence `19.1%–24.3%`, treatment coverage `49.1%`, raised BP `27.2%–33.3%`, adult obesity `30.3%`, youth obesity `20.0%–21.9%`, DTP3 `98.0%`) |

---

## 1. CDC NHANES 2017–March 2020 Pre-Pandemic (`P_*`)

- **Source URL:** `https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/` (`P_*.xpt`)
- **License:** Public Domain (U.S. CDC / NCHS; no login required)
- **Location:** `data/raw/nhanes_2017_2020/`

### Files & Observed Counts
| File | Size (bytes) | Rows | Cols | Module Description |
|---|---:|---:|---:|---|
| `P_DEMO.xpt` | 3,614,720 | 15,560 | 29 | Demographics, age (`RIDAGEYR`, `RIDAGEMN`), sex (`RIAGENDR`), interview language (`SIALANG`), income-poverty ratio (`INDFMPIR`), weights (`WTINTPRP`, `WTMECPRP`) |
| `P_BMX.xpt` | 2,520,640 | 14,300 | 22 | Body measures: weight (`BMXWT`), height (`BMXHT`), recumbent length (`BMXRECUM`), head circumference (`BMXHEAD`), BMI (`BMXBMI`), CDC pediatric BMI category (`BMDBMIC`, ages 2–19y), waist (`BMXWAIST`) |
| `P_BPXO.xpt` | 1,039,840 | 11,656 | 12 | Oscillometric BP (3 readings): `BPXOSY1–3` (systolic), `BPXODI1–3` (diastolic), `BPXOPLS1–3` (pulse) |
| `P_GHB.xpt` | 167,600 | 10,409 | 2 | Glycohemoglobin (`LBXGH` %) |
| `P_GLU.xpt` | 164,160 | 5,090 | 4 | Fasting plasma glucose (`LBXGLU` mg/dL, `LBDGLUSI` mmol/L, fasting subsample weight `WTSAFPRP`) |
| `P_HDL.xpt` | 294,000 | 12,198 | 3 | HDL cholesterol (`LBDHDD` mg/dL) |
| `P_TCHOL.xpt` | 294,000 | 12,198 | 3 | Total cholesterol (`LBXTC` mg/dL) |
| `P_TRIGLY.xpt` | 409,360 | 5,090 | 10 | Fasting triglycerides (`LBXTR`) & LDL (`LBDLDL`, `LBDLDLM`, `LBDLDLN`) |
| `P_DIQ.xpt` | 3,361,520 | 14,986 | 28 | Diabetes diagnosis (`DIQ010`), prediabetes (`DIQ160`), **blood sugar test in past 3 years (`DIQ180`)**, insulin (`DIQ050`), pills (`DIQ070`) |
| `P_MCQ.xpt` | 7,562,560 | 14,986 | 63 | Medical conditions & **biological family history**: close relative had diabetes (`MCQ300C`), close relative had heart attack/angina `<50y` (`MCQ300A`), asthma (`MCQ010`, `MCQ300B`), CHF (`MCQ160B`), CHD (`MCQ160C`), angina (`MCQ160D`), MI (`MCQ160E`), stroke (`MCQ160F`), liver (`MCQ160L`), cancer (`MCQ220`) |
| `P_BPQ.xpt` | 899,520 | 10,195 | 11 | Hypertension diagnosis (`BPQ020`), BP meds (`BPQ040A`/`BPQ050A`), high cholesterol (`BPQ080`), **cholesterol checked (`BPQ060`, `BPQ070`)** |
| `P_HUQ.xpt` | 873,120 | 15,560 | 7 | General health (`HUQ010`), routine care place (`HUQ030`), healthcare visits past year (`HUQ051`), **time since last healthcare visit (`HUD062`)** |
| `P_IMQ.xpt` | 1,371,600 | 15,560 | 11 | Immunizations: Hepatitis A (`IMQ011`), Hepatitis B (`IMQ020`), HPV (`IMQ060`, `IMQ070`) |
| `P_ECQ.xpt` | 431,360 | 5,365 | 10 | Early childhood (ages `0–15y`): maternal smoking in pregnancy (`ECQ020`), birth weight (`ECD070A` lbs / `ECD070B` oz), NICU/medical care (`ECQ080`/`ECQ090`), caregiver weight perception (`WHQ030E`) |
| `P_SLQ.xpt` | 777,200 | 10,195 | 11 | Sleep duration weekday/weekend (`SLD012`, `SLD013`), snoring/apnea (`SLQ030`, `SLQ040`), trouble sleeping (`SLQ050`) |
| `P_PAQ.xpt` | 1,321,440 | 9,693 | 17 | Physical activity & sedentary minutes (`PAD680`) |
| `P_SMQ.xpt` | 1,428,560 | 11,137 | 16 | Smoking history (`SMQ020`, `SMQ040`) |
| `P_HIQ.xpt` | 1,745,440 | 15,560 | 14 | Health insurance coverage (`HIQ011`, `HIQ210` coverage gap) |
| `P_KIQ_U.xpt` | 1,184,720 | 9,232 | 16 | Chronic kidney disease (`KIQ022` weak/failing kidneys) |

### Observed Cohort Counts (`SEQN` Left Join)
- Total participants: `15,560` (`<5y`: `2,025`; `<18y`: `5,867`; `>=18y`: `9,693`)
- Adults (`>=18y`) with HbA1c (`LBXGH`): `8,464`
- Adults with `MCQ300C` (family history of diabetes) valid (`1=Yes`, `2=No`): `9,099` (`4,367` Yes)
- Adults with `MCQ300A` (family history of early MI/angina) valid (`1=Yes`, `2=No`): `9,015` (`1,186` Yes)
- Adults `DIQ010 == 1` (diagnosed diabetes): `1,423`
- Adults **undiagnosed diabetes** (`DIQ010 != 1` and (`LBXGH >= 6.5` or `LBXGLU >= 126`)): `404`
- Adults **lab prediabetes** (`DIQ010 != 1`, not DM, and (`LBXGH >= 5.7` or `LBXGLU >= 100`)): `3,081`
- Adults diagnosed hypertension (`BPQ020 == 1`): `3,580`; measured elevated BP (`mean SBP >= 130` or `mean DBP >= 80`): `3,408`
- Pediatrics (`<18y`) with CDC BMI category `BMDBMIC`: `4,347` (`139` underweight, `2,601` normal, `703` overweight, `904` obese); with `IMQ011`: `4,887`; with `ECQ`: `5,363`

---

## 2. CDC NHANES 2021–2023 (`*_L`)

- **Source URL:** `https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2021/DataFiles/` (`*_L.xpt`)
- **License:** Public Domain (U.S. CDC / NCHS; no login required)
- **Location:** `data/raw/nhanes_2021_2023/`

### Files & Observed Counts
| File | Size (bytes) | Rows | Cols | Key Differences vs. 2017–2020 |
|---|---:|---:|---:|---|
| `DEMO_L.xpt` | 2,582,160 | 11,933 | 27 | Uses `WTINT2YR`, `WTMEC2YR`; adds `DMDHHSIZ` (household size) |
| `BMX_L.xpt` | 1,563,200 | 8,860 | 22 | Same core anthropometry + `BMDBMIC` |
| `BPXO_L.xpt` | 696,720 | 7,801 | 12 | Same 3 oscillometric readings (`BPXOSY1–3`, `BPXODI1–3`) |
| `GHB_L.xpt` | 174,000 | 7,199 | 3 | Includes phlebotomy weight `WTPH2YR` + `LBXGH` |
| `GLU_L.xpt` | 129,200 | 3,996 | 4 | Includes `WTSAF2YR` + `LBXGLU`, `LBDGLUSI` |
| `HDL_L.xpt` | 259,520 | 8,068 | 4 | `LBDHDD`, `LBDHDDSI`, `WTPH2YR` |
| `TCHOL_L.xpt` | 259,520 | 8,068 | 4 | `LBXTC`, `LBDTCSI`, `WTPH2YR` |
| `TRIGLY_L.xpt` | 321,840 | 3,996 | 10 | `LBXTLG` (note column name `LBXTLG` vs `LBXTR` in `P_TRIGLY`), `LBDLDL` |
| `DIQ_L.xpt` | 847,600 | 11,744 | 9 | Retains `DIQ010`, `DIQ160`, `DIQ180`, `DIQ050`, `DIQ070` (trimmed care-process cols) |
| `MCQ_L.xpt` | 3,294,000 | 11,744 | 35 | **Drops `MCQ300C` / `MCQ300A` / `MCQ300B` family history**; retains personal chronic conditions |
| `BPQ_L.xpt` | 409,680 | 8,501 | 6 | `BPQ020`, `BPQ030`, `BPQ150` (BP meds), `BPQ080`, `BPQ101D` (`BPQ060`/`BPQ070` dropped) |
| `HUQ_L.xpt` | 276,080 | 11,933 | 6 | Uses `HUQ055` (**telehealth/video visit in past 12m**, not equivalent to `HUQ051`; excluded from model features) |
| `IMQ_L.xpt` | 556,720 | 11,565 | 6 | `IMQ011` (HepA), `IMQ060` (HPV) |
| `ECQ_L.xpt` | 194,000 | 3,432 | 7 | `ECD070A`/`B`, `ECQ080`, `ECQ090`, `WHQ030E`, `MCQ080E` |
| `SLQ_L.xpt` | 375,840 | 8,501 | 7 | `SLD012`, `SLD013` sleep duration |
| `PAQ_L.xpt` | 409,520 | 8,153 | 8 | `PAD790Q`/`U`, `PAD800`, `PAD810Q`/`U`, `PAD820`, `PAD680` |
| `SMQ_L.xpt` | 651,120 | 9,015 | 9 | `SMQ020`, `SMQ040`, etc. |
| `HIQ_L.xpt` | 455,840 | 11,933 | 11 | `HIQ011`, `HIQ210` |
| `KIQ_U_L.xpt` | 564,320 | 7,809 | 9 | `KIQ022` kidney disease |

### Observed Cohort Counts (`SEQN` Left Join)
- Total participants: `11,933` (`<5y`: `991`; `<18y`: `3,780`; `>=18y`: `8,153`)
- Adults (`>=18y`) with HbA1c: `6,002`; with BMI: `6,235`; with SBP: `6,123`
- Adults `DIQ010 == 1` (diagnosed DM): `1,073`; **undiagnosed DM (lab only)**: `233`; **lab prediabetes**: `2,115`
- Adults diagnosed HTN (`BPQ020 == 1`): `2,956`; measured elevated BP (`>=130/80`): `2,465`
- Pediatrics (`<18y`) with `BMDBMIC`: `2,236` (`67` underweight, `1,334` normal, `336` overweight, `499` obese); `IMQ011`: `3,412`; `ECQ`: `3,432`

---

## 3. UCI ID 891 — CDC Diabetes Health Indicators (BRFSS 2015)

- **Source URL:** `https://archive.ics.uci.edu/static/public/891/data.csv` (Catalog: `https://archive.ics.uci.edu/dataset/891/cdc+diabetes+health+indicators`)
- **License:** CC BY 4.0 (UCI ML Repository; original survey CDC BRFSS 2015, public domain)
- **File:** `data/raw/uci_datasets/cdc_diabetes_health_indicators_uci891.csv` (`13,494,568` bytes, `253,680` rows, `23` columns, `0` missing values)
- **Key Columns:** `Diabetes_binary` (`0`: `218,334`, `1`: `35,346`), `HighBP` (`1`: `108,829`), `HighChol` (`1`: `107,591`), `CholCheck` (`1`: `244,210`, `0`: `9,470` — screening history!), `BMI` (`12–98`, mean `28.38`), `Smoker`, `Stroke`, `HeartDiseaseorAttack`, `PhysActivity`, `Fruits`, `Veggies`, `HvyAlcoholConsump`, `AnyHealthcare`, `NoDocbcCost`, `GenHlth` (`1–5`), `MentHlth` (`0–30`), `PhysHlth` (`0–30`), `DiffWalk`, `Sex` (`0`: `141,974`, `1`: `111,706`), `Age` (`1–13` BRFSS 5-year adult age brackets), `Education` (`1–6`), `Income` (`1–8`).
- **Limitations:** Self-reported telephone survey only (no lab HbA1c/glucose, no SBP numeric values, no family history, no pediatrics, age is binned `1–13`).

---

## 4. UCI ID 529 — Early Stage Diabetes Risk Prediction

- **Source URL:** `https://archive.ics.uci.edu/static/public/529/data.csv` (Catalog: `https://archive.ics.uci.edu/dataset/529/early+stage+diabetes+risk+prediction+dataset`)
- **License:** CC BY 4.0 (UCI ML Repository; Sylhet Diabetes Hospital Bangladesh, Islam et al. 2019)
- **File:** `data/raw/uci_datasets/early_stage_diabetes_uci529.csv` (`34,682` bytes, `520` rows, `17` columns, `0` missing values)
- **Key Columns:** `age` (`16–90`, mean `48.03`), `gender` (`Male`: `328`, `Female`: `192`), `polyuria`, `polydipsia`, `sudden_weight_loss`, `weakness`, `polyphagia`, `genital_thrush`, `visual_blurring`, `itching`, `irritability`, `delayed_healing`, `partial_paresis`, `muscle_stiffness`, `alopecia`, `obesity` (`Yes`/`No`), `class` (`Positive`: `320`, `Negative`: `200`).
- **Limitations:** Small clinical case-control sample (`61.5%` positive, high class imbalance vs. general population), symptom-heavy, lacks numeric BMI/BP/HbA1c/family history. Best used only for secondary symptom-signal validation, not population prevalence calibration.

---

## 5. UCI ID 45 — Heart Disease (Cleveland)

- **Source URL:** `https://archive.ics.uci.edu/static/public/45/data.csv` (Catalog: `https://archive.ics.uci.edu/dataset/45/heart+disease`)
- **License:** CC BY 4.0 (UCI ML Repository; Detrano et al. 1989)
- **File:** `data/raw/uci_datasets/heart_disease_uci45.csv` (`11,334` bytes, `303` rows, `14` columns; `ca` has `4` nulls, `thal` has `2` nulls)
- **Key Columns:** `age` (`29–77`, mean `54.44`), `sex` (`1`: `206`, `0`: `97`), `cp` (chest pain `1–4`), `trestbps` (resting SBP `94–200`, mean `131.69`), `chol` (`126–564`, mean `246.69`), `fbs` (fasting blood sugar `>120 mg/dL`: `1` in `45` rows), `restecg`, `thalach`, `exang`, `oldpeak`, `slope`, `ca`, `thal`, `num` (`0`: `164`, `1–4`: `139`).
- **Limitations:** Small (`303` rows) cardiology referral cohort from 1988; angiographic outcome (`num > 0`) is diagnostic CAD, not primary-care screening incidence.

---

## 6. WHO Growth Reference 2007 (5–19 Years, `anthroplus`)

- **Source URL:** `https://github.com/WorldHealthOrganization/anthroplus/tree/main/data-raw/growthstandards`
- **License:** Open Source / WHO (`anthroplus` R package; public WHO 2007 growth reference tables)
- **Files (`data/raw/who_growth_standards/`):**
  - `who_5_19y_bfawho2007.txt` (`10,475` bytes, `340` rows, cols `['sex', 'age', 'l', 'm', 's']`, `age` `60–229` months — BMI-for-age LMS)
  - `who_5_19y_hfawho2007.txt` (`8,775` bytes, `340` rows, cols `['sex', 'age', 'l', 'm', 's']`, `age` `60–229` months — Height-for-age LMS)
  - `who_5_19y_wfawho2007.txt` (`3,779` bytes, `124` rows, cols `['sex', 'age', 'l', 'm', 's']`, `age` `60–121` months — Weight-for-age LMS)
  - `anthroplus_listing.json` (`4,480` bytes — GitHub directory metadata)
- **Usage:** Given `sex` (`1=Male, 2=Female`), `age_months`, and measurement $y$ (BMI, height cm, or weight kg), compute exact LMS z-score:
  $$z = \frac{(y / M)^L - 1}{L \cdot S} \quad (L \neq 0)$$
  Used for pediatric Well-Child screening rules (`z > +1` overweight, `z > +2` obesity, `z < -2` underweight/stunting).

---

## 7. WHO Global Health Observatory (GHO) — UAE (`ARE`) Benchmarks

- **Source URL:** `https://ghoapi.azureedge.net/api/` (`$filter=SpatialDim eq 'ARE'`)
- **License:** WHO Open Data / CC BY-NC-SA 3.0 IGO (WHO GHO public API, no auth)
- **Files (`data/raw/who_gho_uae/`):**
  - `indicators_catalog.json` (`31` indicator definitions)
  - `uae_NCD_DIABETES_PREVALENCE_CRUDE.json` (`198` records; latest `2022`: **`19.14%`** adults `18+`, **`24.28%`** adults `30+`)
  - `uae_NCD_DIABETES_PREVALENCE_AGESTD.json` (`198` records; latest `2022`: `26.09%` `18+`, `33.49%` `30+`)
  - `uae_NCD_DIABETES_TREATMENT_CRUDE.json` (`99` records; latest `2022`: **`49.15%`** overall, `47.44%` male, `52.91%` female — documents ~50.9% untreated/care-gap prevalence in UAE)
  - `uae_BP_03.json` (`90` records; latest `2019` crude raised BP `SBP>=140` or `DBP>=90`: **`27.15%`** overall, `30.30%` male, `18.29%` female)
  - `uae_BP_04.json` (`90` records; latest `2019` age-standardized raised BP: `33.26%`)
  - `uae_NCD_BMI_30C.json` (`135` records; latest `2024` crude adult obesity `BMI>=30`: **`30.28%`**, `28.02%` male, `34.87%` female)
  - `uae_NCD_BMI_PLUS2C.json` (`405` records; latest `2024` crude child/adolescent obesity `BMI > +2 SD`: **`20.02%`** ages `5–9y`, **`21.91%`** ages `10–19y`, **`21.23%`** ages `5–19y`)
  - `uae_WHS4_100.json` (`26` records; latest `2025` DTP3 immunization coverage among 1-year-olds: **`98.0%`**)
  - `uae_NCDMORT3070.json` (`72` records; latest `2023` premature NCD mortality age `30–70`: **`6.8%`**)

---

## Unified Mapping to Nabdh Schema

| Nabdh Schema Field | NHANES 2017–2020 (`P_*`) | NHANES 2021–2023 (`*_L`) | UCI 891 (BRFSS) | UCI 45 (Heart) |
|---|---|---|---|---|
| `age` | `RIDAGEYR` (or `RIDAGEMN/12` for `<2y`) | `RIDAGEYR` (or `RIDAGEMN/12`) | `Age` (5-yr bins `1–13`, adult `18+`) | `age` (years) |
| `sex` | `RIAGENDR` (`1=M, 2=F`) | `RIAGENDR` (`1=M, 2=F`) | `Sex` (`1=M, 0=F`) | `sex` (`1=M, 0=F`) |
| `bmi` | `BMXBMI` (`BMDBMIC` for `2–19y`) | `BMXBMI` (`BMDBMIC` for `2–19y`) | `BMI` | *N/A* |
| `hba1c` | `LBXGH` *(target-defining; do NOT use as feature for glycemic labels)* | `LBXGH` *(target-defining)* | *N/A* | *N/A* |
| `systolic_bp` | Mean of `BPXOSY1`, `BPXOSY2`, `BPXOSY3` | Mean of `BPXOSY1`, `BPXOSY2`, `BPXOSY3` | `HighBP` (binary self-report) | `trestbps` |
| `family_hx_diabetes` | `MCQ300C == 1` (`1=Yes, 2=No`) | *Unavailable (dropped in cycle)* | *N/A* | *N/A* |
| `family_hx_cvd` | `MCQ300A == 1` (`1=Yes, 2=No`) | *Unavailable* | *N/A* | *N/A* |
| `chronic_conditions` | `BPQ020` (HTN), `BPQ080` (chol), `MCQ160B–F` (CVD), `MCQ010` (asthma), `KIQ022` (CKD) | `BPQ020`, `BPQ080`, `MCQ160B–F`, `MCQ010`, `KIQ022` | `HighBP`, `HighChol`, `Stroke`, `HeartDiseaseorAttack`, `DiffWalk` | `cp`, `restecg` |
| `screening_history` | `DIQ180` (blood sugar check past 3y), `BPQ060`/`BPQ070` (chol check), `HUQ051`/`HUD062` (visit frequency/recency) | `DIQ180` (blood sugar check past 3y); `HUQ055` is telehealth/video visit only (not equivalent to `HUQ051`) | `CholCheck` (chol check past 5y), `AnyHealthcare`, `NoDocbcCost` | *N/A* |
| `pediatric_signals` | `ECQ` (birth weight `ECD070A/B`, maternal smoking `ECQ020`), `IMQ` (`IMQ011` HepA, `IMQ020` HepB, `IMQ060` HPV), `BMDBMIC` + WHO LMS z-scores | `ECQ_L`, `IMQ_L` (`IMQ011`, `IMQ060`), `BMDBMIC` + WHO LMS z-scores | *Adults only* | *Adults only* |
| `outcome_label` | **Glycemic Screening Yield** (among `DIQ010 != 1`): `LBXGH >= 5.7` or `LBXGLU >= 100` (prediabetes+); `LBXGH >= 6.5` or `LBXGLU >= 126` (undiagnosed DM). **Hypertension Yield** (among `BPQ020 != 1`): `SBP >= 130` or `DBP >= 80`. | Same lab/BP criteria for **external temporal validation** | `Diabetes_binary` (self-reported diagnosed DM) | `num > 0` (angiographic CAD) |

> **Sex encoding is a source-to-canonical transform, not a shared contract.** The values in
> the table above are **source** encodings. Nabdh infers the numeric encoding from the uploaded
> column and converts to its canonical internal encoding: **`0 = male`, `1 = female`** (the
> strings `male`/`m`/`female`/`f` are always accepted). A generic `sex`/`gender` column
> containing a `2` and no `0` is read as NHANES `1 = male`, `2 = female`; a column named
> `riagendr` is always read that way. A file containing both `0` and `2` is treated as `0/1`,
> and the `2`s become row-level `Insufficient data`. Undecodable values are reported in the
> response warnings and degrade to `Insufficient data`; they do not reject the upload. Blank
> cells also become row-level `Insufficient data`. See
> [ADR-0002](../docs/adr/0002-auto-detect-sex-encoding.md).

### Recommended Anti-Leakage Feature Split for Training
1. **Task A — Undiagnosed Dysglycemia Screening Prioritization (`HbA1c >= 5.7%` or `FPG >= 100 mg/dL` among `DIQ010 != 1` adults):**
   - **Train on:** NHANES 2017–2020 (`P_*`)
   - **Validate temporally on:** NHANES 2021–2023 (`*_L`) (handling missing `family_hx_diabetes` via explicit missingness/imputation indicator or ablation)
   - **Allowed Features:** `age`, `sex`, `bmi`/`whtr`, `systolic_bp`, `family_hx_diabetes` (`MCQ300C`), `diagnosed_htn` (`BPQ020`), `income_poverty_ratio` (`INDFMPIR`). Care-utilization items (`DIQ180`, `HUQ051`/`HUQ055`) are excluded from ML features to prevent utilization/telehealth confounding (`DIQ180` is used only in clinical overdue rules).
   - **Forbidden Features (Leakage):** `LBXGH`, `LBXGLU`, `LBDGLUSI`, `DIQ010`, `DIQ160`, `DIQ050`, `DIQ070`, `DID040`.
2. **Task B — Cardiometabolic Risk / Care-Gap Triage (excluding measured BP when predicting elevated BP):**
   - If predicting **undiagnosed elevated BP** (`SBP >= 130` or `DBP >= 80` among `BPQ020 != 1`), drop `BPXOSY*`, `BPXODI*`, `BPQ040A`, `BPQ050A`, `BPQ150`.

---

## Honest Limitations & Skipped Sources
1. **UAE / Abu Dhabi Open Microdata:** Direct unauthenticated portal downloads on `bayanat.ae` (returned HTTP 404 on CKAN API) and `data.abudhabi` (returned WAF/Request Error) were unavailable without interactive portal sessions; per policy, no access-gate bypass was attempted. Official UAE epidemiological baselines were instead captured via the open **WHO GHO API** (`data/raw/who_gho_uae/`).
2. **Genomic Sequencing / Polygenic Risk Scores (PRS):** Real individual-level genomic/PRS, G6PD, and thalassemia carrier datasets (e.g., Emirati Genome Program, UK Biobank, All of Us) require controlled-access DUA/registration and are not openly downloadable. NHANES 2017–2020 biological family history (`MCQ300C`, `MCQ300A`, `MCQ300B`) provides the real open-access familial/heritable proxy; synthetic Abu Dhabi demo profiles should layer PRS/G6PD/thalassemia fields transparently as simulated extensions anchored to published UAE priors.
3. **Pediatric Developmental Milestones & 0–5y LMS Tables:** Open NHANES/UCI tables do not include standardized developmental screening instruments (e.g., ASQ-3 speech/motor milestones). NHANES does provide real pediatric anthropometry (`0–17y`), CDC `BMDBMIC` categories (`2–19y`), early-childhood birthweight/perinatal risk (`ECQ`), and immunization uptake (`IMQ`). In addition, `cdc.gov/growthcharts` and `worldhealthorganization/anthro` (0–5y) raw downloads timed out on permission prompts and were skipped; WHO 2007 5–19y LMS tables (`anthroplus`) were downloaded cleanly.
4. **Geographic Generalizability:** NHANES and BRFSS represent U.S. populations (different ethnic/dietary/environmental baselines than Abu Dhabi residents), and NHANES 2017–2020 vs. 2021–2023 differ in survey weights and missing family-history variables (`MCQ300C` absent in 2021–2023). Calibration to UAE WHO GHO priors (`49.1%` diabetes treatment coverage, `19.1%–24.3%` crude diabetes prevalence, `30.3%` adult obesity) is essential before presenting UAE-calibrated outreach projections.
