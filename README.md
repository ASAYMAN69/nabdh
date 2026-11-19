# Nabdh

**Precision prevention and screening engine — pre-lab population triage plus deterministic clinical rules.**

Nabdh ranks adults for cardiometabolic screening using questionnaire and anthropometric data available *before* labs, then applies versioned guideline rules to the results and vitals that arrive. It is a demonstration prototype for the Future Health Digital Innovation Challenge, Population Health Challenge 04. It is **not** a diagnostic device and is **not** clinically validated.

**Submission documents:** [SUBMISSION.md](SUBMISSION.md) · [Clinician guide](docs/CLINICIAN_GUIDE.md) · [CSV guide](docs/CSV_GUIDE.md) · [Model card](docs/MODEL_CARD.md) · [Assumptions & limitations](docs/ASSUMPTIONS_AND_LIMITATIONS.md) · [3-minute demo script](docs/DEMO_SCRIPT.md) · [Technical overview](docs/TECHNICAL_OVERVIEW.md)

## Quickstart

```bash
make setup          # create .venv and install dependencies
make demo           # serve on http://127.0.0.1:8000
make serve          # remote server: bind 0.0.0.0:8000
make test           # 126 passed, 2 skipped (125/3 in a fresh clone)
```

`make setup` uses `python3` by default. On a server with a different interpreter, override it:
`make setup BOOTSTRAP_PYTHON=python3.12`.

On the upload card, **Load 206-record demo** runs the full 206-row QA master with one click.

`make demo` does not require retraining: the deployed model artifacts and the WHO growth tables are committed. Raw NHANES source files are not committed; they are only needed to retrain (`python -m nabdh.model.train`).

Open `http://127.0.0.1:8000/`, then upload `data/sample/uae_demo_cohort.csv`. Clinician templates are `data/sample/clinician_template.csv` (full), `data/sample/clinician_template_minimal.csv` (4 columns), and `data/sample/clinician_template_lab_units.csv` (labs in non-standard units); all are downloadable from the upload screen. The one-row clinician probes are in `data/sample/probes/`.

## What the demo shows

| Probe | Input | Expected |
|---|---|---|
| Demo cohort | `data/sample/uae_demo_cohort.csv` (60 synthetic adults/children) | 1 urgent, 9 high, 17 elevated; 4 missed by age-40 rules; 1 unit-suspect lab surfaced |
| Age-40 miss | `UAE-WOW-029`, 29F, central obesity, family history, elevated BP | Flagged without a positive lab; Arabic outreach preview |
| Critical cardiac | `UAE-URG-101`, troponin 0.18 ng/mL | Urgent; outreach suppressed for clinician sign-off |
| Ambiguous unit | `UAE-UNIT-102`, troponin 4500 (no unit) | `unit_suspect`; explicitly not evaluated, never silently cleared |
| HbA1c in mmol/mol | `probe_hba1c_mmol.csv`, 58 mmol/mol | Converted to 7.46%; tier **High**; DM-LAB-01 |
| FPG in mmol/L | `probe_fpg_mmol.csv`, 7.0 mmol/L | Converted to 126.1 mg/dL; tier **High**; DM-LAB-01 |
| Troponin in ng/L | `probe_troponin_ngl.csv`, 180 ng/L | Converted to 0.18 ng/mL; **Urgent**; CV-TROP-01 |
| Hypertensive crisis | `probe_bp_crisis.csv`, 185/115 | **Urgent**; CV-BP-CRISIS-01 |
| Severe BP in pregnancy | `probe_pregnancy_bp.csv`, 165/110 at 28 weeks | **Urgent obstetric review**; OB-BP-SEVERE-01 |

## Architecture

- **Same-origin Python monorepo**: FastAPI backend plus a vanilla HTML/JS/CSS frontend (`app/`).
- **Stream router** (`nabdh/engine.py`): `insufficient_data`, `paediatric` (<20y), `prenatal` (`pregnant=yes`), and `adult_preventive` (20+, non-pregnant) are separated before inference. Paediatric and prenatal rows never receive adult ML scores.
- **Pre-lab ML** (`nabdh/data/nhanes.py`, `nabdh/model/train.py`): survey-weighted logistic regression for five targets (`undiagnosed_dm`, `dysglycaemia`, `undiagnosed_htn`, `undiagnosed_dyslipidaemia`, `ckd_risk`). The deployed `nofamily` variant is the temporal external-validation path (NHANES 2021–23); `full` is a 25% internal holdout used when family history is supplied. The percentages are **priority ranking scores, not calibrated individual probabilities**.
- **Observation capture** (`nabdh/observations/`): arbitrary wide/long CSVs and niche lab columns are alias-resolved against a versioned catalog. Explicit alternate units are converted with provenance (`raw_value`, `raw_unit`); ambiguous magnitudes remain `unit_suspect` and are excluded from rules.
- **Versioned rules** (`nabdh/rules/`): 32 deterministic ADA, ACC/AHA, ACOG, AHA/ACC/HFSA, ESC, KDIGO, USPSTF, Well-Child, and genomic rules, each with version, effective date, citation, severity, and `requires_signoff`.
- **Outcome tracker** (`nabdh/outcomes.py`): SQLite-backed `GET/POST /api/outcomes` for simulated outreach responses and completed screenings.

## Model evidence (short form)

| Target | `full` holdout AUC / O:E | `nofamily` external AUC / O:E |
|---|---|---|
| Undiagnosed diabetes | 0.767 / 1.255 | 0.782 / 0.926 |
| Dysglycaemia | 0.744 / 1.006 | 0.733 / 0.846 |
| Undiagnosed hypertension | 0.700 / 1.079 | 0.672 / 0.972 |
| Undiagnosed dyslipidaemia | 0.657 / 0.956 | 0.686 / 0.959 |
| CKD risk | 0.759 / 1.046 | 0.777 / 1.078 |

The DM holdout O:E 95% CI is approximately 0.95–1.95 on 33 events, so it is not statistically distinguishable from 1.0. A candidate Platt calibration (O:E 1.001, Brier 0.04449 → 0.04373) is documented but **not deployed**, because deploying it would change triage thresholds. Full details: [docs/MODEL_CARD.md](docs/MODEL_CARD.md).

## Endpoints

- `GET /` — static frontend
- `GET /health` — service health
- `POST /api/score` — score a CSV and return ranked triage JSON, segment audit, warnings
- `POST /api/score.csv` — export ranked results as formula-sanitized CSV
- `GET /api/outcomes`, `POST /api/outcomes` — read/record simulated outreach outcomes

## Documentation

- [SUBMISSION.md](SUBMISSION.md) — what is submitted and why
- [docs/CLINICIAN_GUIDE.md](docs/CLINICIAN_GUIDE.md) — how a clinician reads and acts on the results
- [docs/CSV_GUIDE.md](docs/CSV_GUIDE.md) — exact columns, units, and common mistakes
- `data/sample/clinician_template.csv` / `clinician_template_minimal.csv` / `clinician_template_lab_units.csv` — ready-to-fill templates
- [docs/TECHNICAL_OVERVIEW.md](docs/TECHNICAL_OVERVIEW.md) — data flow, rules, ingestion, safeguards
- [docs/MODEL_CARD.md](docs/MODEL_CARD.md) — intended use, metrics, calibration, limitations
- [docs/ASSUMPTIONS_AND_LIMITATIONS.md](docs/ASSUMPTIONS_AND_LIMITATIONS.md) — explicit assumptions and residual gaps
- [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) — timestamped 3-minute script
- [docs/DEMO_AND_LIMITATIONS.md](docs/DEMO_AND_LIMITATIONS.md) — original demo notes (model wording corrected)
- [docs/PATIENT_DATA_CURATION.md](docs/PATIENT_DATA_CURATION.md) — cohort and stream rules
- [data/DATASETS.md](data/DATASETS.md) — NHANES sources and leakage controls

## Testing

```bash
.venv/bin/pytest
.venv/bin/ruff check app nabdh tests scripts
node --check app/static/app.js
```

The suite covers unit conversion and provenance, BP/pregnancy escalation, known-diabetic BP crisis, sex auto-detection, reasoning guardrails, CSV export, API failures, and pinned demo aggregates.

## Clinical notice

Demo records are synthetic. No real patient data is included, and outreach messages are simulated in the UI/outcomes table rather than sent. Clinical deployment in the UAE requires local recalibration and validation on DoH/Malaffi data, prospective evaluation, regulatory review, and clinician sign-off. See [LICENSE](LICENSE).
