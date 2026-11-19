# Design: Arbitrary / Niche Clinical Test Ingestion & Grounded Escalation

**Date:** 2026-11-19
**Status:** Approved for planning
**Scope:** Extend Nabdh from a fixed 13-feature tabular pipeline to a system that captures, interprets, and safely escalates arbitrary clinical tests (cardiac, oncology, autoimmune, metabolic) alongside the existing NHANES models.

---

## 1. Problem

`nabdh/engine.py::normalise()` maps only the columns listed in `ALIASES` (engine.py:22). Any niche cardiac test column — `troponin_i`, `nt_probnp`, `lvef_pct`, `coronary_calcium_score`, `d_dimer`, `hs_crp`, `lp_a` — or free-text `ecg_finding` / `clinical_notes` is **silently dropped** during normalisation and never reaches any downstream component.

The five survey-weighted models in `models/` accept fixed 9–13-column vectors defined by `FEATURES` (nabdh/data/nhanes.py:21). `cvd_history=yes` only nudges diabetes/CKD/dyslipidaemia probabilities. The models have no concept of a troponin spike, reduced LVEF, or a high calcium score.

**Result:** a cardiac patient with alarming niche test results is scored exactly like any other adult, ranked by metabolic risk, and assigned a routine recall interval. The system is blind to the most clinically urgent signal in the file.

---

## 2. Goals

1. Capture every unmapped column as a structured `Observation` instead of discarding it.
2. Interpret numeric tests deterministically against bundled reference ranges and critical thresholds.
3. Escalate critical findings to a new `Urgent Clinical Review` tier without any model call.
4. Ground every emitted flag in a citable guideline rule; never let a model invent a threshold.
5. Interpret free-text notes and resolve ambiguous test names via an optional, pluggable reasoning layer.
6. Preserve the existing public API, the 22 passing tests, and all current safety routing.

## 3. Non-goals

- **No FHIR/HL7 ingest in this design.** It is an adapter concern for later; `Observation` is designed so it maps cleanly.
- **No vector RAG over full guideline PDFs.** We need *thresholds*, which a curated rules pack expresses more reliably than prose retrieval.
- **No retraining of the NHANES models.** Layer 2 is unchanged.
- **No per-row batch LLM calls.** Cohort scoring never invokes a model (see §6).
- **No autonomous diagnosis or treatment recommendation**, at any tier, ever.

---

## 4. Decisions (final)

| # | Question | Decision |
|---|---|---|
| 1 | Runtime / hosting | Local-first, pluggable `Reasoner`. Cloud requires explicit opt-in with a minimised payload. |
| 2 | Input format | Wide CSV primary, long-format CSV/JSON secondary, both normalising to one canonical `Observation`. |
| 3 | Latency / batching | `/api/score` never calls a model. Reasoning is on-demand, triggered, and capped. |
| 4 | Grounding | LLM renders over a versioned rules pack; it is never a source of thresholds. |
| 5 | Liability | Strictly screening / follow-up prioritisation. `Urgent Clinical Review` tier requires clinician sign-off and suppresses patient outreach. |

### 4.1 The division of labour

| Layer | Owns | Mechanism |
|---|---|---|
| **1 — Capture** | Unmapped columns → structured `Observation` | Deterministic normalizer + test catalog |
| **2 — Baseline risk** | Population-level calibrated risk | Existing 10 NHANES models, unchanged |
| **2b — Deterministic rules** | All thresholds, all critical flags, all urgent alerts | Versioned rules pack, pure Python |
| **3 — Reasoning** | Free-text extraction, ambiguous-name resolution, rationale narration | LLM, validated against pack, optional |

**Governing principle: the LLM is an interpreter and a narrator, never the arbiter of a fact.** Thresholds come from the catalog and the rules pack. Reference ranges come from the catalog. If a claim cannot be traced to a rule ID that resolves to a pack entry, it is dropped rather than repaired.

**Consequence:** the safety-critical path is deterministic and available even when Layer 3 is down, unconfigured, or wrong. Clinical safety must not degrade with model availability.

---

## 5. Layer 1 — Observation capture

### 5.1 `Observation` record

New package `nabdh/observations/`. Frozen dataclass (or TypedDict) with:

| Field | Type | Notes |
|---|---|---|
| `patient_id` | `str` | From `id` column, or row ordinal |
| `name_raw` | `str` | Original column header / `test_name` |
| `canonical` | `str \| None` | Resolved via catalog; `None` if unmapped |
| `code` | `str \| None` | LOINC code when known |
| `value` | `float \| None` | Coerced numeric |
| `unit` | `str \| None` | Declared unit |
| `ref_low` | `float \| None` | From catalog, age/sex-adjusted when expressible |
| `ref_high` | `float \| None` | As above |
| `abnormal_flag` | `str \| None` | Source-provided `H`/`L`/`HH`/`LL`/`A` if present |
| `captured_at` | `str \| None` | ISO-8601 if the source provides it |
| `source` | `str` | `wide_csv` \| `long_csv` \| `fhir` |
| `quality` | `str` | See §5.4 |
| `severity_hint` | `str \| None` | Catalog's own classification: `critical` \| `abnormal` \| `normal` \| `unknown`. **Informational only** — escalation is governed exclusively by the rules pack `severity`. |

### 5.2 Test catalog (`nabdh/observations/catalog.py`)

Bundled, versioned data — not code. Each entry:

```yaml
- canonical: nt_probnp
  aliases: [nt_probnp, nt_probnp_pg_ml, nt-probnp, nterminalprobnp]
  code: "33762-6"
  unit: pg/mL
  plausible: [0, 300000]
  ref:
    age_bands:
      - {max_age: 49, high: 125}
      - {max_age: 59, high: 225}
      - {max_age: 74, high: 450}
      - {max_age: 120, high: 900}
  rules: [CV-NT-proBNP-01]
```

**v1 seed set** (the tests named in the request): `troponin_i`, `nt_probnp`, `lvef_pct`, `coronary_calcium_score` (aliases incl. `cac_score`), `d_dimer`, `hs_crp`, `lp_a`, plus passthrough capture for `ecg_finding` and `clinical_notes`.

Reference ranges are **age-banded and sex-specific where the guideline expresses them that way** (NT-proBNP, D-dimer are the obvious cases).

**Single source of truth:** the catalog holds *measurement metadata* (aliases, LOINC, unit, plausible range, reference range). The rules pack holds *clinical rules* (threshold, action, citation). The catalog's `rules` field is a **pointer only** — it never contains a threshold value. This prevents the two files drifting apart on the same number.

### 5.3 Unit sanity — the silent-failure trap

`nt_probnp` in pg/mL vs ng/L is numerically identical and harmless. **`troponin_i` in ng/mL vs ng/L is a 1000× error.** `lvef_pct` is sometimes `0–1` and sometimes `0–100`.

Rule: **a value is only evaluated if its magnitude is plausible for its declared unit.** If `unit` says `ng/mL` and the value is `4500`, that is almost certainly pg/mL → emit `quality = "unit_suspect"`, **refuse to evaluate**, and route to manual review. Never silently pick between units. Never rescale speculatively.

Where the catalog cannot express a reference range for a given patient (e.g. a range the guideline defines only for a population we don't model), emit `quality = "no_reference_range"` and report **"unable to interpret"** — do not fabricate a threshold. Absence of a reference range produces no flag.

### 5.4 `quality` values

`ok` · `unmapped` · `unit_suspect` · `non_numeric` · `out_of_plausible_range` · `no_reference_range`

`unmapped` observations are still captured and surfaced to Layer 3 for terminology resolution — they are never dropped, which is the entire point of this layer.

### 5.5 Ingest

- **Wide CSV** (primary, today's input): every column not claimed by `ALIASES` becomes candidate observations, matched against catalog aliases.
- **Long CSV / JSON** (secondary): `test_name, value, unit, ref_low, ref_high` rows grouped by `patient_id`.
- Column names are matched case-insensitively after stripping units embedded in headers (`nt_probnp_pg_ml` → `nt_probnp`).

---

## 6. Layer 2b — Deterministic rules pack

### 6.1 Structure

New real content under `nabdh/rules/` (currently an empty re-export facade):

```yaml
rule_id: CV-NT-proBNP-01
guideline: AHA/ACC/HFSA
citation: "2022 AHA/ACC/HFSA Guideline for the Management of Heart Failure"
condition: "nt_probnp >= 900 pg/mL"
severity: urgent
action: "Urgent clinical review — evaluate for heart failure"
audience: clinician
requires_signoff: true
```

**Guideline precedence for a UAE population:** UAE MoHAP/DHA → AHA/ACC → ESC → ADA → KDIGO → USPSTF.

### 6.2 Migration of existing thresholds

`_preventive_screenings()` (engine.py:674) already hardcodes ADA/USPSTF thresholds as Python string literals: HbA1c ≥6.5, FPG ≥126, eGFR <60, TC ≥240, LDL ≥160, TG ≥200, colorectal age 45–75, mammography 40–74, cervical 21–65, LDCT 50–80.

**These migrate verbatim into the pack with no behavioural change.** This is a refactor of code already written, not a greenfield addition, and it is what makes every existing flag citable.

### 6.3 Tier ordering and the escalation invariant

```
Urgent Clinical Review > High > Elevated > Routine - overdue > Routine > Low
Excluded / Insufficient data  (orthogonal, computed first; critical Layer 2b findings still escalate Excluded-from-DM rows to Urgent Clinical Review)
```

**Invariant: tiers may only ever be escalated, never downgraded.** Tabular tier is computed first, rules are applied second, and the urgent override is applied **last** and unconditionally. The existing escalation at engine.py:1064 (`escalate_multi` → `Elevated`) must not be able to overwrite an urgent assignment.

### 6.4 `Urgent Clinical Review` semantics

- Computed **deterministically** from catalog critical thresholds and pack rules. No model call.
- Row gains `urgent_alerts: [...]` where each alert carries `rule_id`, `test`, `value`, `unit`, `threshold`, `guideline`, `citation`, `requires_signoff: true`.
- Row gains `requires_signoff: true`.
- **`outreach_preview` is suppressed for this tier.** Automated patient contact must never disclose a critical result. This is a safety invariant, not a preference.
- `_segments()` `flagged_pct` counts urgent rows as flagged (engine.py:665).

---

## 7. Layer 3 — Reasoning (optional)

### 7.1 Protocol

`nabdh/reasoning/base.py` defines a `Reasoner` protocol. Implementations: `LocalReasoner` (quantised 7–8B instruct via `llama-cpp-python`, CPU-capable), `CloudReasoner` (explicit opt-in).

**Both are optional.** With none configured, Layers 1 + 2 run fully and rows report `reasoning.status = "unavailable"`. The system never fails because a reasoner is absent.

### 7.2 Triggers

Reasoning runs only when:

1. an unmapped observation exists on the row, **or**
2. a critical threshold was crossed, **or**
3. an explicit per-patient `/api/score/{id}/explain` request arrives.

Capped at N patients per request (default 50), with `reasoning.status = "pending"` so the API returns immediately.

### 7.3 Payload minimisation

Cloud payloads contain **only** the observations needed to answer the question plus the relevant rule IDs. Never the full patient row, never identifiers beyond a pseudonymous `patient_id`. `allow_cloud_reasoning=true` is required; it defaults to `false`.

### 7.4 Validator (`nabdh/reasoning/validate.py`)

Schema-validates model output, then grounds it:

- Any claim lacking a `rule_id` that resolves to a pack entry is **dropped**.
- Any numeric value in the output must match the input observation within tolerance — otherwise the claim is dropped.
- Any field shaped like `diagnosis`, `diagnosis_confirmed`, `assessment`, or `treatment` is **rejected by schema** before validation.
- Output carries `refusal` / `insufficient_evidence` as first-class valid states.

---

## 8. Data contract changes

### 8.1 Response additions

`summary` gains: `observations_captured`, `observations_unmapped`, `observations_unit_suspect`, `urgent`.

`results[]` rows gain: `urgent_alerts[]`, `requires_signoff`, `observations[]` (unmapped/abnormal only, to bound payload size), `reasoning {status, rationale, citations}`.

### 8.2 API surface

- `app/api/routes.py:17` `VALID_TIERS` gains `"Urgent Clinical Review"`.
- CSV export (routes.py:110–131) flattens `urgent_alerts` the same way `reasons`/`flags` are flattened, honours the tier in the `min_tier` filter, and includes `"Urgent Clinical Review"` in `min_tier="flagged"`.
- `app/static/app.js` and `index.html` render the new tier and urgent alerts.
- **`nabdh.engine.score()` signature and return shape stay backward compatible** — existing keys are never removed or renamed.

### 8.3 Facades

`nabdh/features/__init__.py` re-exports from `nabdh.observations` alongside `ALIASES`/`BOUNDS`/`FEATURES`. `nabdh/rules/__init__.py` re-exports the pack evaluator. `nabdh/safeguards/__init__.py` unchanged.

---

## 9. Error handling & edge cases

| Case | Behaviour |
|---|---|
| Value unparseable as number | `quality = "non_numeric"`, captured, routed to Layer 3 |
| Value outside catalog `plausible` range | `quality = "out_of_plausible_range"`, not evaluated |
| Declared unit inconsistent with magnitude | `quality = "unit_suspect"`, not evaluated, manual review |
| No reference range expressible | `quality = "no_reference_range"`, no flag, reported as uninterpretable |
| Unknown test name entirely | `quality = "unmapped"`, captured, Layer 3 candidate |
| Free-text in a numeric field | `non_numeric`, never coerced to `0` |
| Cohort with zero observations | Identical to today's behaviour; no new failure mode |
| Reasoner unavailable/timeout | `reasoning.status = "unavailable"`; deterministic layers unaffected |
| `age` or `sex` missing | Existing `insufficient_data` stream runs first; observations still captured |

**Never:** coerce a missing value to `0`, invent a reference range, rescale units speculatively, or emit a flag without a resolvable `rule_id`.

---

## 10. Privacy & safety invariants

1. No patient data leaves the process unless `allow_cloud_reasoning=true` **and** the payload passes minimisation.
2. No automated patient outreach for `Urgent Clinical Review`.
3. No output field may assert a diagnosis.
4. Every flag carries a citable `rule_id`.
5. Critical escalation must succeed with Layer 3 entirely absent.
6. Existing small-cell suppression (`SMALL_CELL = 10`) and bilingual outreach previews are unaffected for non-urgent tiers.

---

## 11. Testing strategy

All 22 existing tests in `tests/test_app.py` must keep passing with their existing assertions unchanged. New coverage is added as separate tests, never by weakening an existing assertion.

New coverage:

- Catalog alias resolution, including unit-suffixed headers.
- Unit sanity: `ng/mL` vs `ng/L` magnitude mismatch produces `unit_suspect`, not a flag.
- Absence of a reference range produces no flag.
- Urgent tier assignment, `requires_signoff`, and outreach suppression.
- Escalation invariant: urgent cannot be downgraded by the existing `escalate_multi` path.
- Rules pack: every emitted flag has a resolvable `rule_id` and non-empty `citation`.
- Validator drops ungrounded and out-of-tolerance claims; rejects diagnosis-shaped fields.
- **No-model-call invariant:** `score()` on a cohort containing niche tests performs zero network and zero LLM calls (assert by monkeypatching the reasoner and any HTTP client).

---

## 12. Phasing

| Phase | Content | Depends on |
|---|---|---|
| **A** | `nabdh/observations/` — schema, catalog seed, wide+long ingest, unit sanity, `observations` in response | — |
| **B1** | Refactor `_preventive_screenings()` thresholds into the rules pack. **No behavioural change.** | — (parallel with A) |
| **B2** | Critical thresholds, `Urgent Clinical Review` tier, `urgent_alerts`, outreach suppression, `VALID_TIERS` | A, B1 |
| **C** | `nabdh/reasoning/` — protocol, stub, validator, then `LocalReasoner`, then `CloudReasoner` | A, B2 |

Phase A alone delivers the headline value: niche tests stop being invisible. Phase C ships stub-first so it never blocks A/B.

---

## 13. Risks & assumptions

1. **No GPU assumed.** Local reasoning targets CPU-capable quantised models. A GPU inference server would not change the architecture.
2. **No real clinic CSV with niche tests confirmed in hand.** The v1 catalog is seeded from the eight named tests. Validation against real exports is required before B2 is trusted clinically.
3. **`ecg_finding` and `clinical_notes` are genuinely free-text** and are the only inputs that require Layer 3. They are deferred to Phase C.
4. **Guideline versioning.** Every pack entry **must** carry `version` and `effective_date` alongside `guideline` and `citation`, so a 2022 HF guideline can be superseded without ambiguity about which edition a flag was derived from.
5. **Reference-range coverage will be incomplete at launch.** The honest behaviour (`no_reference_range`) is specified precisely so gaps surface as "unable to interpret" rather than as fabricated flags.

---

## 14. Acceptance criteria

- A CSV containing `troponin_i`, `nt_probnp`, `lvef_pct` produces structured observations for all three instead of silently dropping them.
- A critically elevated troponin yields `Urgent Clinical Review` with `requires_signoff: true`, a citable `rule_id`, and **no** `outreach_preview` — with no model configured.
- A unit-suffixed mismatch (`ng/mL` declared, `pg/mL` magnitude) yields `unit_suspect` and no clinical flag.
- Every flag in every row resolves to a pack entry with a non-empty citation.
- All 22 existing tests pass; `score()` performs zero model or network calls.
