# Technical Overview

**System:** Nabdh 0.1.0
**Date:** 2026-11-19
**Scope:** demonstration prototype for Challenge 04 — population cardiometabolic screening and triage.

---

## 1. Design in one paragraph

Nabdh is a same-origin FastAPI + vanilla-JS application. A CSV upload passes through schema normalisation, sex auto-detection, physiological bounds, and unit interpretation. Adults are scored by five pre-lab logistic-regression models; children and pregnant participants are routed to rule-only streams. Deterministic, versioned guideline rules then evaluate observations, blood pressure, growth, pregnancy, genomic flags, and preventive-screening eligibility. The output is a ranked queue, an explainable inspector, a segment audit with small-cell suppression, and a CSV export. Every actionable tier is marked `requires_signoff`; urgent rows suppress automated outreach.

## 2. Components

| Path | Responsibility |
|---|---|
| `app/main.py` | FastAPI app, static files, security headers |
| `app/api/routes.py` | `/health`, `/api/score`, `/api/score.csv`, `/api/outcomes` |
| `nabdh/engine.py` | Normalisation, stream routing, ML scoring, tiering, explanations, summary, segment audit |
| `nabdh/data/nhanes.py` | NHANES loading, target construction, feature lists, leakage exclusions |
| `nabdh/model/train.py` | Survey-weighted logistic regression training and evaluation |
| `nabdh/observations/` | Test catalog, alias resolution, unit quality, observation capture |
| `nabdh/rules/` | Versioned JSON rules pack and evaluators |
| `nabdh/outcomes.py` | SQLite outcome tracker |
| `app/static/` | Accessible single-page UI |
| `tests/` | 126 regression tests, including pinned demo probes |

## 3. Request flow

```
CSV upload
  → size/row/column/delimiter checks
  → alias mapping and type coercion
  → sex encoding auto-detection (per file)
  → unit interpretation (explicit units only)
  → physiological bounds + derived BMI/WHtR
  → stream routing
       ├─ insufficient data
       ├─ paediatric (<20)
       ├─ prenatal (pregnant=yes)
       └─ adult preventive (20+, non-pregnant)
  → ML priority (adult stream only)
  → versioned preventive + observation + vital rules
  → tier escalation invariant
  → explanations, outreach preview, sign-off flags
  → summary + segment audit
  → JSON response / sanitised CSV export
```

## 4. Input normalisation

### 4.1 Aliases and required fields

`ALIASES` in `nabdh/engine.py` maps common EHR spellings to canonical columns (for example `gender` → `sex`, `family_history_diabetes` → `family_hx_diabetes`, `systolic` → `systolic_bp`). `age` and `sex` are mandatory; missing columns produce actionable `422` messages naming the accepted encodings.

### 4.2 Sex auto-detection

Canonical internal encoding is `0 = male`, `1 = female`. The parser accepts text (`male/female/m/f`) and numeric conventions:

- A file containing `2` (and no `0`) is decoded as `1 = male`, `2 = female`.
- A file containing only `0/1` is decoded as `0 = male`, `1 = female`.
- `riagendr` is always `1 = male`, `2 = female`.
- A file mixing `0` and `2` is treated as `0/1`; the `2` values become missing rather than being guessed.
- Blank cells become row-level `Insufficient data`; undecodable non-blank values produce a `422` with examples and remediation.

The convention is inferred from the column as a whole, so scoring is batch-invariant. See `docs/adr/0002-auto-detect-sex-encoding.md`.

### 4.3 Units and provenance

Explicit alternate units are converted before bounds validation:

- HbA1c mmol/mol → % (NGSP formula)
- FPG / total cholesterol / HDL / LDL / triglycerides mmol/L → mg/dL
- Troponin ng/L or pg/mL → ng/mL
- D-dimer µg/mL or mg/L → ng/mL FEU
- hs-CRP mg/dL → mg/L
- LVEF fraction → %

Conversions are warned about and the original value/unit is stored as `raw_value` / `raw_unit`. The inspector shows “converted from 58 mmol/mol”. A bare implausible magnitude with no unit is **not** converted: it remains `quality = unit_suspect`, is excluded from clinical rules, and appears in the “Not Evaluated — Confirm Units” panel.

### 4.4 Bounds and derivation

Physiologically impossible values are set to missing with a cohort warning. BMI and WHtR are derived only when the required measured fields exist. The demo cohort's aggregates are pinned by `tests/test_demo_probes.py` so ingestion changes cannot silently move the public numbers.

## 5. Model layer

- Five targets: `undiagnosed_dm`, `dysglycaemia`, `undiagnosed_htn`, `undiagnosed_dyslipidaemia`, `ckd_risk`.
- Pipeline: mean imputation → standardisation → L2 logistic regression.
- Survey weights normalised to mean 1.
- `full` variant includes family history; `nofamily` drops it. The engine selects `full` when family history is present and `nofamily` otherwise, so the externally validated path is used where the feature is unavailable.
- Paediatric, prenatal, and known-diabetes rows do not receive diabetes ML scores.
- Outputs are rounded to one decimal and labelled **priority**, not risk probability.

Details and metrics: [MODEL_CARD.md](MODEL_CARD.md).

## 6. Rules layer

`nabdh/rules/rules_pack.json` is versioned (`pack_version` 1.1.0) and contains 32 rules. Each rule carries:

```json
{
  "rule_id": "CV-BP-CRISIS-01",
  "version": "1.0",
  "effective_date": "2026-11-19",
  "guideline": "ACC/AHA",
  "citation": "2017 ACC/AHA ... Hypertensive Crisis",
  "condition": "systolic_bp >= 180 mmHg or diastolic_bp >= 120 mmHg",
  "severity": "urgent",
  "action": "Hypertensive crisis ...",
  "audience": "clinician",
  "requires_signoff": true
}
```

Evaluators:

- `evaluate_preventive_rules` — ADA/USPSTF/KDIGO screening eligibility, diagnostic glycaemic labs, lipids, CKD.
- `evaluate_observation_rules` — cardiac, renal, and niche lab thresholds with age/sex reference ranges.
- `evaluate_vital_rules` — BP crisis, stage-2 hypertension, severe-range BP in pregnancy.
- `evaluate_peds_genomic_and_wcv_rules` — WHO growth, Well-Child visits, immunisation, G6PD, thalassaemia, PRS.

### 6.1 Tier escalation

The final invariant is:

1. Any urgent alert → **Urgent Clinical Review**, immediate, outreach suppressed, sign-off required. A stream-specific urgent pathway (for example obstetric review) is preserved.
2. Diagnostic glycaemic lab or stage-2 BP → at least **High**, within 30 days.
3. Other abnormal observation → at least **Elevated**, within 90 days.
4. Otherwise the model/guideline tier stands (`High`, `Elevated`, `Routine - overdue`, `Routine`, `Low`, `Excluded`, `Insufficient data`).

The escalation is monotonic: a rule can raise a tier, never lower it.

## 7. Output and UI

- **Triage summary:** rows, adults, children, urgent/high/elevated counts, missed-by-age-40 count, expected undiagnosed diabetes cases (sum of priority scores / 100), observations captured, unit-suspect count.
- **Queue:** sortable/filterable by tier, population, ID, age, priority.
- **Inspector:** clinical inputs, model drivers, flags, urgent alerts with citations, observations and conversion provenance, outreach preview (suppressed for urgent), sign-off notice.
- **Segment audit:** age band, district, language; primary small cells (`<10`) and complementary suppression; row-level redaction only for primary small cells.
- **Export:** formula-sanitised CSV with `Content-Disposition`, `nosniff`, and `no-store`.

## 8. Safety and privacy controls

| Control | Implementation |
|---|---|
| No diagnosis language | Reasoning validator blocks assertive diagnosis/prescription frames |
| Clinician sign-off | `requires_signoff` on actionable tiers; visible in UI |
| Urgent outreach suppression | `outreach_preview` removed for `Urgent Clinical Review` |
| Unit ambiguity | `unit_suspect` excluded from rules; explicit warning panel |
| Small-cell suppression | Primary and complementary suppression in aggregate; row redaction for primary cells |
| Formula injection | Leading `= + - @` neutralised in CSV export |
| Upload limits | 64 MB, 200,000 rows, 1,000 columns |
| Network isolation | Scoring is local and deterministic; no LLM or external call by default |
| Synthetic demo | Banner in UI; no real patient data; messages simulated |

## 9. Testing and evidence

- `tests/test_demo_probes.py` — HbA1c mmol/mol, FPG mmol/L, troponin ng/L, D-dimer µg/mL, LVEF fraction, BP crisis/stage-2, pregnancy severe BP, known-diabetic BP crisis, rule boundaries, implicit-unit non-evaluation, pinned demo aggregates.
- `tests/test_app.py` — API contracts, sex encodings, suppression, CSV export, formula injection, outcomes.
- `tests/test_audit_engine.py` — stream routing, outreach, paediatric/prenatal gating, sign-off invariants.
- `tests/test_audit_obs_rules.py` — observation catalog, D-dimer units, DM-Lab rules.
- `tests/test_clinical_semantics.py` — sex contract and reasoning guard.

Run:

```bash
.venv/bin/pytest
.venv/bin/ruff check app nabdh tests scripts
node --check app/static/app.js
```

The current suite passes; the only warning is an upstream Starlette `TestClient`/`httpx` deprecation notice.

## 10. Deployment and non-goals

**Deployment for the submission:** local `uvicorn` on `127.0.0.1:8000`, one process, SQLite for outcomes. `make demo` starts it. Model artifacts and WHO tables are committed; raw NHANES files are not needed to run.

**Explicit non-goals:** authentication, multi-tenancy, TLS, EHR integration, messaging gateway, FHIR server, regulatory submission, and production observability. These are listed as pre-pilot work in [ASSUMPTIONS_AND_LIMITATIONS.md](ASSUMPTIONS_AND_LIMITATIONS.md).

## 11. Change control

- Rules are data, not code: a threshold change is a JSON edit with a new `version`, `effective_date`, and citation.
- Clinical semantic changes require a change record (see `docs/CHANGE_RECORD_2026-11-19_CLINICAL_SEMANTICS.md`) and owner sign-off.
- Model artifacts are versioned by variant and target; retraining is out of scope for the demo freeze.
- The demo aggregates are pinned in tests, so any change that moves the public numbers fails CI before it can be presented.
