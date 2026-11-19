# Model Card — Nabdh Pre-Lab Triage Models

**Version:** 0.1.0
**Date:** 2026-11-19
**Artifacts:** `models/full__*.joblib`, `models/nofamily__*.joblib`, `models/metrics.json`, `models/coefficient_signs.json`
**Code:** `nabdh/data/nhanes.py`, `nabdh/model/train.py`, `nabdh/engine.py`
**Intended submission:** Future Health Digital Innovation Challenge — Population Health Challenge 04

---

## 1. What this model is

Nabdh contains five **pre-lab priority models**. They rank adults for cardiometabolic screening using questionnaire and anthropometric data that exist before laboratory results:

| Target | Question the score orders |
|---|---|
| `undiagnosed_dm` | Who is most likely to have undiagnosed diabetes and should be screened first? |
| `dysglycaemia` | Who is most likely to have any dysglycaemia (diabetes or prediabetes)? |
| `undiagnosed_htn` | Who is most likely to have undiagnosed hypertension? |
| `undiagnosed_dyslipidaemia` | Who is most likely to have undiagnosed dyslipidaemia? |
| `ckd_risk` | Who is most likely to have **self-reported kidney disease** (NHANES `KIQ022`: "Ever told you had weak/failing kidneys")? |

Each model is a survey-weighted logistic regression pipeline: mean imputation → standardisation → L2-regularised logistic regression (`C=1.0`, `max_iter=2000`). Outputs are **ranking scores**, not calibrated individual probabilities.

The models are only one layer. Deterministic, cited rules evaluate labs, blood pressure, pregnancy status, paediatric growth, genomic flags, and preventive-screening eligibility. A rule alert can override the model tier.

## 2. Intended use

**Intended users:** population-health teams, screening programme managers, and primary-care nurses working under clinician supervision.

**Intended use:**
- Rank a registered population for limited screening slots before lab results exist.
- Combine the ranking with guideline-due flags (age, sex, prior tests, vaccinations, Well-Child visits).
- Trigger deterministic clinician-review alerts when uploaded labs or vitals cross guideline thresholds.
- Produce an auditable queue and a simulated outreach preview.

**Out-of-scope:**
- Diagnosis, treatment, prescribing, or patient-facing risk disclosure.
- Triage of acute symptoms or emergency presentations.
- Replacing clinical judgement or a validated local risk calculator.
- Use on real patients without local validation, recalibration, regulatory review, and clinician sign-off.
- Automated messaging without consent, language verification, and an approved channel.

## 3. Training and evaluation data

| Item | Detail |
|---|---|
| Source | U.S. National Health and Nutrition Examination Survey (NHANES) |
| Training wave | NHANES 2017–2020 pre-pandemic |
| Temporal external wave | NHANES 2021–2023 |
| Unit of analysis | Adult participants with complete target definition and survey weights |
| Weighting | Survey MEC/exam weights normalised to mean 1 within the training set |
| External validation | `nofamily` variant only, because NHANES 2021–23 does not contain `MCQ300C` (family history of diabetes) |
| UAE data | **None.** No DoH, Malaffi, or Emirati cohort was used. |

The `full` variant uses all available features including family history. Its reported metrics are a **25% stratified internal holdout** from 2017–20 with the model refit on the remaining 75%. The deployed `full` artifact is refit on 100% of 2017–20. The `nofamily` variant drops family history and is evaluated temporally on 2021–23; it is the only externally validated path.

Because the 2021–23 wave lacks `MCQ300C`, the `full` variant **cannot** be externally validated on that wave. Any statement that all five models are externally validated is incorrect.

## 4. Features

### 4.1 Base feature set (13 columns)

`age`, `sex`, `whtr`, `bmi`, `diastolic_bp`, `family_hx_diabetes`, `diagnosed_htn`, `high_chol`, `cvd_history`, `current_smoker`, `sleep_hours`, `income_ratio`, `education`.

**`systolic_bp` is not a feature.** It was removed because r=0.65 with `diastolic_bp`. When both are in the model, systolic receives a small negative weight (over-correction artifact) while diastolic carries the positive signal. Diastolic BP is retained as the single BP measure.

### 4.2 Per-target exclusions

| Target | Excluded features | Reason |
|---|---|---|
| `undiagnosed_htn` | `diastolic_bp`, `diagnosed_htn` | BP is the outcome definition; including it is leakage. The model predicts "who looks like they might have high BP" from non-BP signals. |
| `undiagnosed_dyslipidaemia` | `high_chol`, `age` | `high_chol` is the outcome definition (leakage). Age has no independent signal for *undiagnosed* dyslipidaemia after controlling for WHtR (partial r=0.002); its negative sign was a selection artifact from conditioning on `high_chol==0`. Removing age cost ~0.008 AUC on both internal and external sets — a trade-off, not a discovery. |
| `ckd_risk` | `bmi`, `current_smoker` | BMI shows the obesity paradox (reverse causation: low BMI is a consequence of CKD, not a cause). Current smoking is confounded by sick-quitter bias. Both are documented limitations, not model errors. Removing them means smokers are not prioritised for kidney checks by the ML; `PREV-TOBACCO-01` still raises a cessation flag, but it does not change the CKD tier or score. |
| Other targets | None (the `nofamily` variant additionally drops `family_hx_diabetes`) | |

### 4.3 Feature counts by target and variant

| Target | `full` features | `nofamily` features |
|---|---:|---:|
| `undiagnosed_dm` | 13 | 12 |
| `dysglycaemia` | 13 | 12 |
| `undiagnosed_htn` | 11 | 10 |
| `undiagnosed_dyslipidaemia` | 11 | 10 |
| `ckd_risk` | 11 | 10 |

### 4.4 Sign-constrained features (zeroed post-fit)

After fitting, any standardized coefficient whose direction contradicts clinical expectations (higher age, WHtR, diastolic BP, family history, CVD, smoking, high cholesterol must raise risk) is constrained to zero. The clamped features are recorded in `models/coefficient_signs.json`. **These features are present in the feature list but contribute exactly zero to the prediction.** They are not dead code — they were fitted, found to have a negative sign due to collinearity or confounding, and zeroed to prevent clinical inversion.

| Model | Zeroed (flat) features |
|---|---|
| `undiagnosed_dm` (both) | `high_chol` |
| `dysglycaemia` (both) | `cvd_history` |
| `undiagnosed_htn` (full) | `family_hx_diabetes`, `high_chol` |
| `undiagnosed_htn` (nofamily) | `high_chol` |
| `undiagnosed_dyslipidaemia` (both) | `cvd_history` |
| `ckd_risk` (both) | `diastolic_bp` |

**This means:** high cholesterol does not affect the diabetes score; CVD history does not affect the dysglycaemia or dyslipidaemia score; diastolic BP does not affect the CKD score. These are documented limitations of the sign-constraint approach, not hidden ablations. The alternative — allowing negative coefficients — would produce clinically inverted gradients (older adults scoring lower, CVD history appearing protective), which is worse for a prevention tool.

### 4.5 Why `education` is protective

`education` is coded 1–5 (less than high school to college graduate). Higher education is associated with lower cardiometabolic risk in NHANES (protective effect). It is therefore **not** in `POSITIVE_SIGN_FEATURES` and is allowed to carry a negative coefficient. This is correct, not a bug.

## 5. Evaluation

Unweighted metrics on the stated evaluation sets. `O:E` is observed prevalence divided by mean predicted probability; 1.0 is perfect calibration on average. AUC is discrimination.

| Target | Variant / evaluation | n | Events | AUC | O:E | Brier |
|---|---|---:|---:|---:|---:|---:|
| Undiagnosed diabetes | `full` — 25% internal holdout | 695 | 33 | 0.767 | 1.255 | 0.0438 |
| Undiagnosed diabetes | `nofamily` — 2021–23 external | 2,218 | 77 | 0.782 | 0.926 | 0.0323 |
| Dysglycaemia | `full` — 25% internal holdout | 695 | 425 | 0.744 | 1.006 | 0.1971 |
| Dysglycaemia | `nofamily` — 2021–23 external | 2,218 | 1,193 | 0.733 | 0.846 | 0.2172 |
| Undiagnosed hypertension | `full` — 25% internal holdout | 1,151 | 386 | 0.700 | 1.079 | 0.2019 |
| Undiagnosed hypertension | `nofamily` — 2021–23 external | 3,592 | 1,138 | 0.672 | 0.972 | 0.2038 |
| Undiagnosed dyslipidaemia | `full` — 25% internal holdout | 1,238 | 412 | 0.657 | 0.956 | 0.2102 |
| Undiagnosed dyslipidaemia | `nofamily` — 2021–23 external | 3,161 | 977 | 0.686 | 0.959 | 0.1965 |
| CKD risk | `full` — 25% internal holdout | 2,283 | 96 | 0.759 | 1.046 | 0.0393 |
| CKD risk | `nofamily` — 2021–23 external | 7,753 | 321 | 0.777 | 1.078 | 0.0379 |

Source: `models/metrics.json`. Events are `round(n × prevalence)` and are shown for orientation.

### 5.1 Uncertainty

For the headline diabetes result:

- `full` holdout AUC **0.767** (improved from 0.747 before collinear systolic was removed).
- `full` holdout O:E **1.255** on 33 events. Wide confidence interval; includes 1.0.
- `nofamily` external AUC **0.782** (improved from 0.769), O:E **0.926** (closer to 1.0 than the pre-fix 0.901).

### 5.2 Known trade-offs

- **Dyslipidaemia AUC dropped ~0.008** on both internal and external sets after removing age. Age did carry discriminative signal; the negative sign was a selection artifact. This is a trade-off: we accepted lower AUC for clinically plausible gradients.
- **CKD model is thinner** after removing BMI, smoking, and zeroing diastolic BP. It still uses age, CVD history, diagnosed hypertension, high cholesterol, and WHtR. Smokers are not prioritised by the ML for kidney checks; the `PREV-TOBACCO-01` rule still fires.
- **Hypertension model uses zero BP inputs.** It predicts "who looks like they might have high BP" from age, BMI, family history, smoking, etc. This is conceptually the weakest model. A judge question about this is valid.
- **The demo mostly exercises the internally-validated path.** The demo cohort supplies family history for most adults, so ~95% of scored adults (43 of 45) are routed to `full`, which is validated only on a 25% internal holdout (33 events). The externally validated `nofamily` variant (the 0.782 headline) is used only when family history is absent — 2 of 45 rows. The external number therefore describes the path the demo exercises least.
- **Two targets add little over age alone.** Top-30% case capture vs an age-only ranking: undiagnosed_dm **+15pp**, dyslipidaemia **+15pp**, ckd_risk **+6pp** — but dysglycaemia **+3pp** and undiagnosed_htn **+2pp**. For those two, a simple "age ≥ 40" rule would lose little.
- **CKD label is self-report.** The `ckd_risk` target is NHANES `KIQ022` ("Ever told you had weak/failing kidneys"), a single self-report item — not eGFR, creatinine, or albumin/ACR. Construct validity is limited to diagnosed/self-reported kidney disease.

### 5.3 Calibration candidate (not deployed)

A Platt scaling fit on out-of-fold predictions was evaluated as a candidate (on the pre-sign-constraint model):

- Holdout O:E 1.255 → **1.001** (Platt candidate on the pre-sign-constraint model; illustrative only, not re-derived)
- Brier 0.04449 → **0.04373** (pre-sign-constraint reference)
- AUC unchanged (Platt is monotone)

It is **not shipped**. Tier thresholds use the raw model score; recalibrating without re-deriving thresholds would silently change who is prioritised. Deploying calibration requires clinician sign-off and a threshold review. See `docs/ML_REMEDIATION_BRIEF.md`.

## 6. How the score becomes a tier

The model output is combined with deterministic rules:

1. **Stream routing first.** Paediatric (<20y), prenatal (`pregnant=yes`), and insufficient-data rows are separated before inference. Paediatric and prenatal rows never receive adult ML scores.
2. **Model priority.** Adult non-pregnant rows receive diabetes and dysglycaemia priority scores; additional targets are shown in the inspector.
3. **Guideline-due flags.** Age/sex/prior-test rules add screening tracks and may lift a row.
4. **Lab/vital rules.** Urgent findings override the tier to **Urgent Clinical Review**; stage-2 BP and diagnostic glycaemic labs lift to **High**; other abnormal observations lift to **Elevated**.
5. **Sign-off.** Every actionable tier is marked `requires_signoff: true`. Urgent rows suppress automated outreach.

The numeric tier cutoffs are product heuristics for queue ordering, not validated clinical decision thresholds.

## 7. Known limitations

- **Transportability:** NHANES is a U.S. sample. No UAE validation exists. Prevalence, lab access, ancestry, and care pathways differ.
- **Calibration:** deployed scores are uncalibrated. The UI calls them priority scores, not probabilities.
- **Internal vs external:** `full` is internally validated only. The externally validated `nofamily` variant is used when family history is absent.
- **Small event counts:** diabetes holdout has 33 events; CIs are wide.
- **No labs in the model:** by design. The model cannot learn from HbA1c, FPG, or lipids; those are handled by rules.
- **Sign-constrained features:** six feature→target pairs are zeroed (see §4.4). High cholesterol does not affect diabetes; CVD history does not affect dysglycaemia; diastolic BP does not affect CKD.
- **CKD model is thinner:** BMI, smoking, and diastolic BP are excluded or zeroed. Smokers are not ML-prioritised for kidney checks.
- **Hypertension model has no BP input:** predicts from non-BP signals only.
- **Dyslipidaemia model has no age input:** age was removed due to selection artifact; AUC dropped ~0.008 as a result.
- **No subgroup audit:** performance by age, sex, ethnicity, or district has not been evaluated.
- **No prospective evaluation:** no workflow, recall, or clinical-outcome study has been run.

## 8. Ethical and privacy considerations

- The demo cohort is **100% synthetic**. No real patient data is included.
- The demo contains no names, Emirates IDs, phone numbers, or addresses. Patient IDs are synthetic.
- Segment counts below 10 are suppressed with complementary suppression.
- Outreach previews are rendered in the UI and recorded in a local SQLite table; **no message is sent**.
- A production deployment would need a consent/authorised-use field, role-based access, audit logging, encryption, retention rules, and a DPIA.
- The tool must not be used to deny care or to rank individuals for exclusion. It ranks for inclusion in screening.

## 9. Fairness

No fairness audit has been completed. The following are known risks:

- `income_ratio` and `education` may proxy access to care and could disadvantage lower-SES groups if the model is used as a gate rather than a queue.
- NHANES racial/ethnic categories do not map cleanly to the UAE population.
- Arabic-language outreach is only a preview; language and literacy were not validated with patients.
- Paediatric and prenatal streams are rule-only, which avoids adult-model bias but is not a fairness guarantee.
- The CKD model's removal of smoking means smokers are not ML-prioritised for kidney checks.

Before a pilot, evaluate calibration and capture by age band, sex, district, and language group on local data. Do not deploy a single global threshold without that review.

## 10. Maintenance

Retrain or recalibrate when:

- Local validation shows O:E outside 0.8–1.25 or AUC materially below the external benchmark.
- Screening guidelines or lab units change.
- A new population or care pathway is added.
- A rule-pack version changes a threshold or citation.

Every rule carries `version`, `effective_date`, `guideline`, `citation`, and `requires_signoff`. Model artifacts are versioned by variant and target. Changes to clinical semantics require a change record and clinician sign-off.

## 11. Evidence and provenance

- `models/metrics.json` — all AUC, O:E, Brier, and calibration-table values.
- `models/coefficient_signs.json` — audit trail of zeroed features per model.
- `docs/ML_REMEDIATION_BRIEF.md` — attack matrix, calibration candidate, feature experiment (negative), freeze gates.
- `docs/CHANGE_RECORD_2026-11-19_CLINICAL_SEMANTICS.md` — sex encoding and reasoning-guard change record.
- `docs/DEFERRED_ML_AND_CLINICAL_REVIEW.md` — unresolved ML/clinical/privacy items.
- `tests/test_model_signs.py` — regression tests for sign plausibility and non-ablation of age/whtr.