# Submission — Nabdh

**Challenge:** Future Health Digital Innovation Challenge · Population Health Challenge 04 — Precision Prevention and Screening
**Submission date:** 20 November 2026
**Format:** working prototype repository + 3-minute pre-recorded demonstration
**Team size:** 1

---

## 1. What is submitted

| Item | Location |
|---|---|
| Working prototype | this repository; `make setup && make demo` |
| 3-minute demo video | linked from the submission portal (script: [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md)) |
| Technical documentation | [docs/TECHNICAL_OVERVIEW.md](docs/TECHNICAL_OVERVIEW.md) |
| Clinician guide | [docs/CLINICIAN_GUIDE.md](docs/CLINICIAN_GUIDE.md) |
| CSV preparation guide | [docs/CSV_GUIDE.md](docs/CSV_GUIDE.md) |
| Clinician CSV templates | [Full](data/sample/clinician_template.csv) · [Minimal](data/sample/clinician_template_minimal.csv) · [Lab units](data/sample/clinician_template_lab_units.csv) |
| Model card | [docs/MODEL_CARD.md](docs/MODEL_CARD.md) |
| Assumptions and limitations | [docs/ASSUMPTIONS_AND_LIMITATIONS.md](docs/ASSUMPTIONS_AND_LIMITATIONS.md) |
| Clinical semantics change record | [docs/CHANGE_RECORD_2026-11-19_CLINICAL_SEMANTICS.md](docs/CHANGE_RECORD_2026-11-19_CLINICAL_SEMANTICS.md) |
| Synthetic demo cohort | [data/sample/uae_demo_cohort.csv](data/sample/uae_demo_cohort.csv) |
| Clinician probe files | [data/sample/probes/](data/sample/probes/) |
| Pilot proposal | [docs/PILOT_ONE_PAGER.md](docs/PILOT_ONE_PAGER.md) |

No real patient data is included. All demo records are synthetic. Outreach messages are rendered in the UI and stored in a local SQLite table; none are sent.

## 2. The problem this addresses

Abu Dhabi's preventive pathways still rely heavily on broad age and sex rules. A 29-year-old with central obesity, family history, elevated blood pressure, and high polygenic risk can be invisible until disease is advanced, while a low-risk 40-year-old is invited. When a clinician does upload labs, a value in a non-canonical unit can be silently dropped, and a severe blood pressure can sit below the escalation threshold without anyone noticing.

Nabdh addresses three separable failures:

1. **Who to invite first** when labs do not exist yet.
2. **What the uploaded data actually means** when labs and vitals do arrive.
3. **When a rule must override the queue** because the finding is urgent.

## 3. What the prototype does

### 3.1 Pre-lab population triage

Five survey-weighted logistic-regression models rank adults for cardiometabolic screening using questionnaire and anthropometric data only: age, sex, waist-to-height ratio, BMI, blood pressure, family history, diagnosed hypertension, high cholesterol, cardiovascular history, smoking, sleep, and income ratio. Outputs are priority scores for queue ordering, not calibrated individual probabilities.

The engine selects the `full` variant when family history is present and the externally validated `nofamily` variant otherwise. Paediatric (<20 years), pregnant, and insufficient-data rows are routed away from adult inference.

### 3.2 Deterministic, versioned clinical rules

Thirty-two rules carry a rule ID, version, effective date, guideline, citation, severity, action, and `requires_signoff`. They cover:

- Hypertensive crisis (≥180/120) → urgent.
- Stage-2 hypertension (≥160/100) → high.
- Severe-range BP in pregnancy (≥160/110) → urgent obstetric review.
- Diagnostic glycaemic labs (HbA1c ≥6.5% or FPG ≥126 mg/dL) → high, with “confirm with repeat testing”.
- Cardiac markers: troponin I, NT-proBNP, LVEF, D-dimer.
- Renal, lipid, paediatric growth, Well-Child, immunisation, G6PD, thalassaemia, and polygenic-risk flags.
- Age/sex-appropriate preventive screening eligibility.

A rule can raise a tier, never lower it. Any urgent alert overrides the model tier and suppresses automated outreach.

### 3.3 Input fidelity

Arbitrary wide or long CSVs are accepted. Aliases such as `gender`, `sbp`, `a1c`, and `family_history_diabetes` are resolved. Explicit alternate units are converted with provenance retained:

| Test | Accepted explicit unit | Conversion |
|---|---|---|
| HbA1c | mmol/mol | NGSP % |
| FPG, lipids | mmol/L | mg/dL |
| Troponin | ng/L, pg/mL | ng/mL |
| D-dimer | µg/mL, mg/L | ng/mL FEU |
| hs-CRP | mg/dL | mg/L |
| LVEF | fraction | % |

Sex encoding is auto-detected per file (`male/female`, `m/f`, `0/1`, `1/2`, `riagendr`) with no user selector. A bare implausible lab magnitude with no unit is **not guessed**: it is marked `unit_suspect`, excluded from clinical rules, shown in a “Not Evaluated — Confirm Units” panel, and outreach is withheld.

### 3.4 Culturally tailored, consent-aware engagement

The inspector shows a language-matched outreach preview (Arabic with RTL rendering for Arabic-preference records), with simulated **Confirm slot / Reschedule / Opt out** and **Mark screening completed** controls. Choices persist to `GET/POST /api/outcomes` and update the cohort conversion strip. Urgent rows never receive an outreach preview.

### 3.5 Population safeguards

- Segment audit by age band, district, and language.
- Primary small-cell suppression below 10, plus complementary suppression so the small cell cannot be derived by subtraction.
- Row-level redaction only for primary small cells; the clinician's own uploaded row is not hidden behind an aggregate rule.
- Synthetic-data banner, formula-sanitised CSV export, upload caps, and zero network/LLM calls during scoring.

## 4. Challenge requirement mapping

| Requirement | How the prototype answers it | Evidence |
|---|---|---|
| 1. Transparent risk and care-gap identification | Model priority plus deterministic rules; “Why Flagged” lists signed drivers; every alert has a citation and sign-off flag | `UAE-WOW-029` shows the age-40 miss and its drivers; inspector |
| 2. Personalized preventive pathways | Stream-specific pathway, timing window, and recall action; population triage explicitly separated from diagnosis | `UAE-URG-101` urgent cardiac pathway; `UAE-WCV-201` Well-Child pathway |
| 3. Culturally appropriate engagement | Arabic/English/Tagalog preview, RTL rendering, consent choices, simulated completion tracking | `UAE-WOW-029` Arabic preview; outcome conversion strip |
| 4. Local population safeguards | Segment audit, small-cell and complementary suppression, unit-suspect exclusion, false-negative probes, pinned aggregates | Summary segments; `UAE-SM-401`; `UAE-UNIT-102` |
| 5. Outcome-based evaluation | Outcome tracker records response and completion; model card documents AUC, O:E, Brier, uncertainty, and the calibration candidate | `GET/POST /api/outcomes`; `docs/MODEL_CARD.md` |

## 5. Evidence

### 5.1 Demonstration cohort (60 synthetic records)

`rows=60, adults=51, children/adolescents=8, urgent=1, high=9, elevated=17, missed_by_age_rules=4, observations_captured=4, unit_suspect=1, expected_undiagnosed_diabetes_cases=1.0`.

These numbers are pinned by `tests/test_demo_probes.py` so a late change cannot silently move the public demo.

### 5.2 Model performance (unweighted, stated evaluation sets)

| Target | `full` internal holdout AUC / O:E | `nofamily` external 2021–23 AUC / O:E |
|---|---|---|
| Undiagnosed diabetes | 0.767 / 1.255 | 0.782 / 0.926 |
| Dysglycaemia | 0.744 / 1.006 | 0.733 / 0.846 |
| Undiagnosed hypertension | 0.700 / 1.079 | 0.672 / 0.972 |
| Undiagnosed dyslipidaemia | 0.657 / 0.956 | 0.686 / 0.959 |
| CKD risk | 0.759 / 1.046 | 0.777 / 1.078 |

The diabetes holdout O:E is 1.255 with a wide confidence interval on 33 events; it is not statistically distinguishable from 1.0. `full` cannot be externally validated because NHANES 2021–23 lacks the family-history variable. A Platt candidate reaches O:E 1.001 and Brier 0.04449 → 0.04373 but is **not deployed**, because calibration without re-deriving tier thresholds would change who is prioritised.

### 5.3 Adversarial clinician probes

A 25-case matrix covers the obvious uploads a clinician may attempt: HbA1c in mmol/mol, FPG in mmol/L, troponin in ng/L, NT-proBNP, low LVEF, low eGFR, high LDL, paediatric obesity, severe BP in pregnancy, missing age/sex, generic sex encodings, EHR aliases, duplicate IDs, implausible age/BMI, small-cell districts, and an unsupported language. All 25 pass.

The four previously silent false-negative paths — non-canonical units, hypertensive crisis, stage-2 hypertension, and severe BP in pregnancy — are now regression-tested and produce visible, actionable output.

### 5.4 Test suite

`126 passed, 2 skipped` (125/3 in a fresh clone; the raw-NHANES test skips when the raw files aren't committed), including unit conversion and provenance, BP/pregnancy escalation, known-diabetic BP crisis, sex auto-detection, reasoning guardrails, CSV export, API failure handling, suppression semantics, and pinned demo aggregates.

## 6. How to run

```bash
make setup     # Python 3.13 venv + dependencies
make demo      # http://127.0.0.1:8000
make test      # 126 tests (2 skipped)
```

Model artifacts (116 KB) and WHO growth tables are committed. Raw NHANES files are only needed to retrain and are documented in `data/DATASETS.md`.

Upload `data/sample/uae_demo_cohort.csv`. Templates are `data/sample/clinician_template.csv` (full), `clinician_template_minimal.csv` (4 columns), and `clinician_template_lab_units.csv` (non-standard lab units), all downloadable from the upload screen. The one-row probes are in `data/sample/probes/`.

## 7. What this is not

- **Not a diagnostic device.** Every actionable tier is `requires_signoff: true`; the model ranks for inclusion in screening, not exclusion from care.
- **Not calibrated for individuals.** The percentages are priority scores. The model card documents the calibration gap.
- **Not validated on UAE data.** No DoH, Malaffi, or Emirati cohort was used. Local recalibration and prospective evaluation are prerequisites for a pilot.
- **Not a production service.** No authentication, TLS, multi-tenancy, EHR integration, or messaging gateway. The demo runs locally on synthetic data.
- **Not complete rule coverage.** Unlisted tests are captured as observations with their units, not silently interpreted.

The full list is in [docs/ASSUMPTIONS_AND_LIMITATIONS.md](docs/ASSUMPTIONS_AND_LIMITATIONS.md).

## 8. What a pilot would measure

A 12-week nurse-led pilot in two districts would measure: screening completion by arm, time from upload to clinician action, urgent-alert acknowledgement, outreach response by language, missed urgent findings, and calibration by age/sex/district. The design and success thresholds are in [docs/PILOT_ONE_PAGER.md](docs/PILOT_ONE_PAGER.md).

## 9. Repository map

```
app/                 FastAPI app + static UI
nabdh/engine.py      normalisation, routing, scoring, tiering, summary
nabdh/observations/  test catalog, unit conversion, quality
nabdh/rules/         versioned rules pack + evaluators
nabdh/model/         training and evaluation
nabdh/outcomes.py    SQLite outcome tracker
models/              deployed joblib artifacts + metrics.json
data/sample/         synthetic UAE demo cohort + probes
docs/                model card, technical overview, limitations, ADR, change record
tests/               126 regression tests
```

## 10. Declaration

The prototype is my own work. It uses public NHANES data, public WHO growth standards, and synthetic demo records. It makes no diagnostic claim and is submitted as a demonstration of population triage, guideline-rule enforcement, and culturally aware engagement for evaluation purposes.
