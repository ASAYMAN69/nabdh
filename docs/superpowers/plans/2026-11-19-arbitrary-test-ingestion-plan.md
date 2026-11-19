# Implementation Plan: Arbitrary / Niche Clinical Test Ingestion & Grounded Escalation

**Spec:** [2026-11-19-arbitrary-test-ingestion-design.md](../specs/2026-11-19-arbitrary-test-ingestion-design.md)
**Date:** 2026-11-19
**Goal:** Execute Phases A, B1, B2, and C incrementally while keeping all 22 existing tests passing, zero new third-party dependencies, and zero model/network calls during `score()`.

---

## Phase A — Observation Capture (`nabdh/observations/`)
1. **`nabdh/observations/schema.py`**
   - Define `Observation` frozen dataclass with all 13 spec fields (`patient_id`, `name_raw`, `canonical`, `code`, `value`, `unit`, `ref_low`, `ref_high`, `abnormal_flag`, `captured_at`, `source`, `quality`, `severity_hint`).
   - Define `VALID_QUALITIES` (`ok`, `unmapped`, `unit_suspect`, `non_numeric`, `out_of_plausible_range`, `no_reference_range`).
2. **`nabdh/observations/catalog.json` & `nabdh/observations/catalog.py`**
   - Versioned JSON catalog (zero YAML dependency) containing measurement metadata only (no clinical escalation thresholds — only `rules: [...]` pointers).
   - Seed v1 tests: `troponin_i` (ng/mL), `nt_probnp` (pg/mL, age-banded), `lvef_pct` (%), `coronary_calcium_score` (AU, aliases `cac_score`), `d_dimer` (ng/mL FEU, age-adjusted `age*10` for >50), `hs_crp` (mg/L), `lp_a` (nmol/L), plus passthrough free-text capture for `ecg_finding` and `clinical_notes`.
   - Unit-sanity checks:
     - Strip unit suffixes from headers (`nt_probnp_pg_ml` → `canonical="nt_probnp"`, `unit="pg/mL"`).
     - `troponin_i` declared `ng/mL` with magnitude `> 50` (likely `ng/L` / `pg/mL` 1000× mismatch) → `quality = "unit_suspect"`, refuse evaluation.
     - `lvef_pct` value `<= 1.0` (0–1 fraction vs 0–100%) → `quality = "unit_suspect"`, refuse evaluation.
     - Outside catalog `plausible` range → `quality = "out_of_plausible_range"`.
     - Missing age/sex when required by ref range → `quality = "no_reference_range"`.
3. **`nabdh/observations/ingest.py` & `nabdh/observations/__init__.py`**
   - `capture_wide_dataframe(df_raw, claimed_cols)` → captures every column not in `ALIASES` (plus unmapped passthrough columns) into per-row `list[Observation]`.
   - `ingest_long_observations(rows)` → normalises `test_name, value, unit, ref_low, ref_high, abnormal_flag, captured_at` grouped by `patient_id`.
4. **`nabdh/features/__init__.py`**
   - Re-export `Observation`, `capture_wide_dataframe`, `ingest_long_observations`, `resolve_test`.

---

## Phase B1 — Deterministic Rules Pack Refactor (`nabdh/rules/`)
1. **`nabdh/rules/rules_pack.json` & `nabdh/rules/pack.py`**
   - Every rule entry carries: `rule_id`, `version`, `effective_date`, `guideline`, `citation`, `severity`, `action`, `audience`, `requires_signoff`, `condition`.
   - Migrate all existing `_preventive_screenings()` ADA/USPSTF thresholds (`HbA1c`, `FPG`, `lipids`, `eGFR`, `colorectal`, `mammography`, `cervical`, `LDCT`, `osteoporosis`, `tobacco`, `sleep`, `chol_test_5y`) verbatim into the pack with zero behavioural change.
2. **`nabdh/rules/__init__.py`**
   - Export `evaluate_preventive_rules`, `evaluate_observation_rules`, `get_rule`, `RULES_PACK`.
3. **Wire `nabdh/engine.py::_preventive_screenings()`** to call `evaluate_preventive_rules()` so every emitted flag has a citable `rule_id`.

---

## Phase B2 — Critical Thresholds, `Urgent Clinical Review`, API & UI
1. **Add critical cardiac/niche rules to `nabdh/rules/rules_pack.json`:**
   - `CV-TROP-01`: `troponin_i >= 0.04 ng/mL` → `urgent`
   - `CV-NT-proBNP-01`: `nt_probnp >= 900 pg/mL` → `urgent`
   - `CV-LVEF-01`: `lvef_pct < 40 %` → `urgent`
   - `CV-CAC-01`: `coronary_calcium_score >= 300 AU` → `urgent` (and `>= 100` → `elevated`)
   - `CV-DDIMER-01`: `d_dimer >= 500 ng/mL` (or age-adjusted `> age * 10` for `age > 50`) → `urgent`
2. **Update `nabdh/engine.py::score()`:**
   - Capture observations via Layer 1 (`nabdh/observations/`).
   - Evaluate Layer 2b observation rules (`evaluate_observation_rules()`).
   - Enforce escalation invariant: `Urgent Clinical Review` overrides `High`, `Elevated`, `Routine*`, `Low`, and even `Excluded` (when a known diabetic has a critical niche finding).
   - Set `requires_signoff: true`, `urgent_alerts: [...]`, `observations: [...]` (unmapped/abnormal/unit_suspect/critical), and **suppress `outreach_preview`** for `Urgent Clinical Review`.
   - Add summary counts: `observations_captured`, `observations_unmapped`, `observations_unit_suspect`, `urgent`.
3. **Update `app/api/routes.py` & `app/static/`:**
   - Add `"Urgent Clinical Review"` to `VALID_TIERS` and `"flagged"` CSV filter; flatten `urgent_alerts` in `/api/score.csv`.
   - Render `Urgent Clinical Review` badge, urgent alerts, and captured/unmapped observations in `app/static/index.html`, `app/static/app.js`, and `app/static/styles.css`.

---

## Phase C — Pluggable Reasoning Layer (`nabdh/reasoning/`)
1. **`nabdh/reasoning/base.py`**
   - `Reasoner` protocol, `ReasoningResult` dataclass, and `StubReasoner` (returns `status="unavailable"` with zero network/LLM calls).
2. **`nabdh/reasoning/validate.py`**
   - `validate_reasoning_output(raw, observations, pack)`:
     - Rejects diagnosis/treatment-shaped keys (`diagnosis`, `diagnosis_confirmed`, `assessment`, `treatment`, `prescription`).
     - Drops any claim lacking a `rule_id` in `RULES_PACK`.
     - Drops numeric claims whose cited value differs from input `Observation.value` beyond tolerance (`5%`).
     - Supports `refusal` / `insufficient_evidence`.
3. **`nabdh/reasoning/local.py` & `nabdh/reasoning/cloud.py`**
   - `LocalReasoner` (optional `llama-cpp-python`, returns `unavailable` if not installed).
   - `CloudReasoner` (requires explicit `allow_cloud_reasoning=True`, strips all non-essential fields to minimal pseudonymous `patient_id` + relevant observations + rule IDs).
4. **Wire `reasoning: {status, rationale, citations}` onto `score()` rows** (always `status: "unavailable"` during `score()` with zero model/network calls) and add `/api/explain` endpoint for on-demand per-patient reasoning.

---

## Verification Plan
- Separate test suites in `tests/test_observations.py`, `tests/test_rules_and_urgent.py`, and `tests/test_reasoning.py`, plus all 22 existing tests in `tests/test_app.py` untouched.
- Run `.venv/bin/pytest -q`, `.venv/bin/ruff check app nabdh tests scripts`, and `node --check app/static/app.js`.
