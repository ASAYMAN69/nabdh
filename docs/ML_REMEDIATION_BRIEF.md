# ML Remediation Brief — Nabdh

**Date:** 19 Nov 2026 · **Submission:** 20 Nov 2026
**Repo:** `/mnt/ee/aprojects/nabdh` · **Timezone:** GST (UTC+4)
**Owner:** project owner · **Reviewer:** ML engineer (this brief)

---

## 0. READ FIRST — 19 Nov attack-matrix findings

The model is **not** the weak point. A clinician-style upload matrix found four hard
false-negative paths, all in input handling, none in the ML weights:

| Attack | Result |
|---|---|
| HbA1c 58 mmol/mol (7.5%) | value silently dropped as out-of-range; no diabetes alert |
| FPG 7.0 mmol/L (126 mg/dL) | value silently dropped as out-of-range; no diabetes alert |
| Troponin 180 ng/L (0.18 ng/mL) | marked `unit_suspect`, **not** evaluated; no urgent alert |
| BP 185/115 | only "Elevated BP — follow-up"; no urgent/high escalation |
| BP 160/100 | tier `Routine - overdue`, despite stage-2 hypertension |

**Feature experiment is negative — do not retrain.** 5-fold CV AUC deltas versus baseline:

| Addition | DM delta | Dysglycaemia delta |
|---|---|---|
| `glucose_test_3y` | −0.0004 | −0.0008 |
| `age²` | 0.0000 | +0.0005 |
| `bmi × family_hx` | −0.0007 | +0.0003 |
| `age × bmi` | −0.0005 | +0.0005 |
| glucose + age² | −0.0002 | −0.0006 |

LightGBM is also not better (CV delta −0.017 to +0.006). The 13-feature model is at its
ceiling. **Do not spend the remaining time retraining.** The accuracy work is input
normalization and rule coverage; the reporting work is calibration and uncertainty.

**Demo cohort impact of the proposed fixes: none.** Max BP in the demo is 155/94 (no row
crosses 160/100), and the demo has no HbA1c/FPG columns and uses troponin in ng/mL only.
The fixes harden arbitrary clinician uploads without changing the demo aggregates.

---

## 0b. Why this exists

The hackathon demo is tomorrow. The scoring engine is structurally sound but has three
credibility gaps that a clinical or ML judge can expose:

1. **No calibration estimator.** The UI shows percentages that read as probabilities.
   `full__undiagnosed_dm` reports O/E = 1.38 on its internal holdout.
2. **Only the `nofamily` variant is externally validated.** Most demo rows use `full`.
3. **Discrimination is modest** (AUC 0.67–0.77) because the model is deliberately
   pre-lab: 13 questionnaire/anthropometry features, no HbA1c, glucose, or lipids.

We are **not** trying to raise AUC substantially in one day. We are trying to make the
existing model honestly reportable, and to test the one cheap feature idea that might
move it.

**Already verified (do not redo):**

- `full__undiagnosed_dm` holdout O/E = 1.255 (post sign-constraint; the pre-constraint artifact was 1.377). The pre-constraint bootstrap 95% CI was **[0.934, 1.899]** (n = 695, 33 events); it is not statistically distinguishable from 1.0 and the CI has not been re-derived.
- Holdout AUC = 0.766 (post sign-constraint; the pre-constraint artifact was 0.747).
- A quick Platt fit on the pre-sign-constraint out-of-fold predictions gave holdout **O/E = 1.001**, Brier 0.04449 → 0.04373, AUC unchanged. This is illustrative of the method only; it has not been re-derived for the shipped artifacts and is not deployed.
- LightGBM does **not** beat logistic regression (CV delta −0.017 to +0.006). Do not
  switch models.
- NHANES 2021–23 has **no `MCQ300C`** (family-history variable), so the `full` variant
  **cannot** be externally validated on 2021–23. State this; do not attempt it.

---

## 1. Ground rules

- **Do not modify** `app/`, `nabdh/engine.py`, `nabdh/rules/`, thresholds, tiering,
  stream routing, or any deployed `models/*.joblib` / `models/metrics.json`.
- **All candidate artifacts** go in `models/candidates/`.
  **All reports** go in `docs/ml_review/`.
- Every number must state: evaluation set, n, number of events, weighted or unweighted.
- Negative and inconclusive results are acceptable. Silent promotion is not.
- **Hard stop: 14:30 GST.** Handoff complete by 15:00 GST. After 15:00 only docs/demo.

---

## 2. Task A — Calibration (2h)

**Goal:** quantify calibration and produce a candidate artifact, without deploying it.

**Method**

1. Reuse the existing 5-fold out-of-fold machinery:
   `nabdh/model/train.py::_oof_probs`, `_fit_with_weights`, `_norm_weights`.
2. For each `variant × target`, fit Platt scaling on the 2017–20 OOF predictions:
   `logit(p_cal) = a * logit(p_raw) + b`.
3. Evaluate **before vs after** on the same evaluation split the repo already uses:
   - `full`: 25% stratified holdout, `random_state=42`
   - `nofamily`: NHANES 2021–23 temporal external
4. Report: O/E, calibration slope and intercept, Brier, Brier skill, AUC, and 95%
   bootstrap CIs (1000 resamples).

**Deliverables**

- `models/candidates/calibration__<variant>__<target>.json` with `{a, b, fit_set, n, events}`.
- `docs/ml_review/CALIBRATION.md` with the before/after table and a 10-line summary.

**Acceptance**

- For `nofamily`, external O/E moves toward 1.0 without degrading Brier skill.
- For `full`, the holdout result is reported but labelled **internal only**.
- AUC must be unchanged (Platt is monotone). If it changes, the implementation is wrong.

**Do not** wire the calibration into `nabdh/engine.py`. Tier thresholds use raw
`p_dm` / `p_dys`; recalibrating without re-deriving thresholds would silently change
triage. That is a clinical decision, not a demo-week change.

---

## 3. Task B — Uncertainty (1h)

Bootstrap 1000 resamples of the evaluation sets for AUC and O/E, per target/variant.
Deliver `docs/ml_review/UNCERTAINTY.md` with a compact table.

The headline we need: **the 1.38 O/E is a point estimate on 33 events; its CI includes
1.0, and the externally validated variant has O/E 0.90.** That is the honest defence.

---

## 4. Task C — Feature experiment (CLOSED — tested negative)

**Do not run this again.** It was tested on 19 Nov and is negative:

- `glucose_test_3y`: DM CV AUC 0.7328 → 0.7324; dysglycaemia 0.7451 → 0.7443.
- `age²`, `bmi × family_hx`, `age × bmi`, and glucose + age²: all within ±0.001.
- LightGBM: worse than logistic regression on 8 of 10 target/variant pairs.

The 13-feature model is at its ceiling. Retraining cannot move AUC materially without
new lab features or new data, neither of which can be validated by tomorrow. Preserve
the frozen artifacts.

---

## 5. Task D — Model card numbers (1h)

Produce one table per target/variant with:

- evaluation set, n, events, prevalence
- AUC (95% CI), O/E (95% CI), Brier skill
- capture@10% and capture@30%
- age-40 rule benchmark (AUC, screen rate, sensitivity) where already computed

Then add, in prose:

- **Intended use:** pre-lab population triage and pathway prioritisation; clinician
  sign-off required; not a diagnosis.
- **Out of scope:** individual diagnosis, treatment decisions, paediatric risk (separate
  WHO growth path), pregnant patients (separate stream), populations outside the
  training distribution.
- **Known failure modes:** uncalibrated absolute probabilities; NHANES ≠ UAE; no labs;
  family-history variant lacks external validation; small event counts.
- **Evaluation honesty:** the `full` holdout metrics come from a model refit on the
  75% training split, not from the deployed 100% fit. State this explicitly; do not
  imply the shipped artifact was evaluated on unseen data.
- **UAE applicability:** requires intercept/slope recalibration and prospective
  evaluation on a local cohort before clinical use.

Deliver `docs/ml_review/MODEL_CARD_NUMBERS.md`. I will merge it into `SUBMISSION.md`.

---

## 6. What not to do

- Do not retrain or overwrite the five deployed targets.
- Do not retune tier thresholds (0.09 / 0.045 / 0.04 / 0.80 / 0.88).
- Do not add labs or new data sources.
- Do not attempt external validation of `full` on 2021–23 — the variable does not exist.
- Do not touch `app/` or the demo cohort.

---

## 7. Handoff format

Each report starts with:

```
## Summary (10 lines max)
- What was tested
- What changed
- What we can claim
- What we cannot claim
- Recommendation: promote / hold / discard
```

Then the tables, then the commands used. File paths must be exact.

---

## 8. Decision gates

| Time (GST) | Gate |
|---|---|
| 12:00 | Task A report draft; calibration numbers visible |
| 14:30 | All reports complete; hard stop on model work |
| 15:00 | **Freeze.** No model artifacts or code changes after this |
| 15:00–20:00 | Docs, demo video, deck, rehearsal only |
