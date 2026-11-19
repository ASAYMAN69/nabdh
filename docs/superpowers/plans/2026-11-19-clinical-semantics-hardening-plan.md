# Implementation Plan: Clinical Semantics Hardening

> **Superseded in part, 2026-11-19.** The sex-contract steps in this plan were replaced by
> per-column auto-detection in
> [ADR-0002](../adr/0002-auto-detect-sex-encoding.md). The reasoning-validator steps remain as
> planned. This document is kept for history; do not reintroduce the sex selector or the
> fail-closed sex rejection.

**Spec:** [2026-11-19-clinical-semantics-hardening-design.md](../specs/2026-11-19-clinical-semantics-hardening-design.md)
**Date:** 2026-11-19
**Status:** Superseded in part by ADR-0002 (sex contract); reasoning guard executed
**Goal:** Make the sex encoding explicit and fail closed, and block assertive diagnosis frames in
reasoning output — without changing any ML model, threshold, stream-routing rule, or demo output.

---

## 0. Constraints and change control

- **No git repository exists.** Checkpoints are: SHA-256 of every changed file before and after,
  a change record, and the verification evidence below.
- **No ML changes.** Do not touch `models/`, `nabdh/model/`, feature sets, thresholds, or
  `nabdh/rules/`.
- **No stream-routing changes.** `insufficient_data`, `paediatric`, `prenatal`,
  `adult_preventive`, urgent override, and `requires_signoff` stay exactly as they are.
- **Demo output is a regression gate.** `data/sample/uae_demo_cohort.csv` must still produce
  `rows=60, urgent=1, high=10, elevated=16, missed_by_age_rules=4, observations_captured=4,
  unit_suspect=1`.
- **TDD.** Every behaviour change gets a failing test first.

### Pre-change hashes (captured 2026-11-19)

```
e51b3147c17d342908443bbdadcc41a18be0f045111560276fe31d958d08c0c6  nabdh/engine.py
a93e5826bb3ef77217ea321003e991edf99c5d2e24c0e27e41bd61f55d4a875b  app/api/routes.py
f34e327ade9804a4ef22b8fcdb5af7b7473254d7db9aa2f42a4fa1ad02956ccf  app/static/index.html
d3d3746514b3d41f7c7023e57b8844fbea5cf5323bf160fa287da790512156ab  app/static/app.js
375822cc61dfd92cff7733bded7353b546254060ef657a5ebe0b5a340e52b348  docs/PATIENT_DATA_CURATION.md
f6fda48c2a92d0950e32fde7b26fa9fbd16badd6565ca228195a256077017cc7  data/DATASETS.md
1e5a562ef13d9bd3a8ab026759c751ef45dc41c63572934fa8a884260422e301  docs/DEFERRED_ML_AND_CLINICAL_REVIEW.md
2d6f5bcbbdd24017c431688710978cc5b5b57f42d11cf57ffdf6d47541be4274  tests/test_app.py
b317eeb2c4a3e9da28859ad9fc705b7dbe9c159019dfffb36e3d63de7332a1d0  tests/test_audit_engine.py
```

---

## Task 1 — Write the failing tests (new file)

**File:** `tests/test_clinical_semantics.py`

Import:

```python
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from nabdh.engine import SexContractError, _parse_sex, score
from nabdh.observations.schema import Observation
from nabdh.reasoning.validate import validate_reasoning_output

client = TestClient(app)
```

Add a helper:

```python
def _obs(canonical="troponin_i", value=0.18):
    return Observation(
        patient_id="P", name_raw=canonical, canonical=canonical, code=None,
        value=value, unit=None, ref_low=None, ref_high=None, abnormal_flag=None,
        captured_at=None, source="csv", quality="ok",
    )
```

Tests (exact names and assertions):

1. `test_parse_sex_obeys_declared_convention`
   - `_parse_sex(pd.Series([0, 1]), "sex", "01")` → `[0.0, 1.0]`
   - `_parse_sex(pd.Series([1, 2]), "sex", "12")` → `[0.0, 1.0]`
   - `_parse_sex(pd.Series([1, 2]), "riagendr", "auto")` → `[0.0, 1.0]`
   - `_parse_sex(pd.Series(["M", "F", "male", "female"]), "sex", "auto")` →
     `[0.0, 1.0, 0.0, 1.0]`
   - `_parse_sex(pd.Series([3]), "sex", "01")` → `[NaN]` (pure parser does not raise)

2. `test_nhanes_male_is_not_routed_to_female_screening`
   - `score(pd.DataFrame([{"id": "M40", "age": 40, "sex": 1, "bmi": 26}]), sex_convention="12")`
   - `"Sex: Male"` in reasons
   - no `"Breast cancer"` and no `"Cervical"` in flags

3. `test_out_of_contract_sex_rejects_the_file`
   - `sex=2`, `sex_convention="01"` → `pytest.raises(SexContractError)`
   - message contains `"1 value"`, `"0=male / 1=female"`, `"sex_convention=12"`

4. `test_nhanes_convention_rejects_zero`
   - `sex=0`, `sex_convention="12"` → `SexContractError`

5. `test_blank_sex_is_missing_not_a_contract_violation`
   - `sex=None` and `sex="  "` → both `tier == "Insufficient data"`, no raise
   - warnings contain `"missing sex"`

6. `test_riagendr_column_is_auto_detected`
   - DataFrame with `riagendr` 1 and 2, default `auto`
   - first `"Sex: Male"`, second `"Sex: Female"`

7. `test_riagendr_with_explicit_zero_one_convention_conflicts`
   - `riagendr` + `sex_convention="01"` → `ValueError` matching `"conflicts"`

8. `test_api_accepts_sex_convention`
   - `POST /api/score` with `data={"sex_convention": "12"}`, CSV `M,40,1` / `F,40,2`
   - 200; `M` has `"Sex: Male"` and no breast/cervical flags

9. `test_api_rejects_unknown_convention_before_reading_the_file`
   - empty file + `sex_convention="bogus"` → 422
   - detail contains `"sex_convention"` (proves validation happens before the empty-file error)

10. `test_api_maps_sex_contract_violation_to_422`
    - `sex=2`, default auto → 422
    - detail contains `"0=male / 1=female"`, response has no `"results"`

11. `test_csv_export_uses_declared_convention`
    - `POST /api/score.csv`, `sex=1`, `sex_convention="12"` → 200, `text/csv`

12. `test_batch_invariance_within_one_convention`
    - `X` alone vs `X` beside `Y sex=2`, both `sex_convention="12"`
    - identical `risk_pct`; both `"Sex: Male"`

13. `test_validator_blocks_assertive_diagnosis_frames` (parametrized)
    - `"Troponin 0.18 confirms the patient has diabetes"`
    - `"Troponin 0.18 is diagnostic of myocardial infarction"`
    - `"This is a case of undiagnosed diabetes"`
    - each → `pytest.raises(ValueError, match="forbidden")`

14. `test_validator_allows_legitimate_screening_language`
    - `"Elevated troponin indicates a need for cardiology review"`
    - `"Troponin 0.18 warrants clinician review for diagnostic confirmation."`
    - both → `status == "ok"`

15. `test_refusal_rationale_with_diagnosis_is_dropped`
    - `{"status": "refusal", "rationale": "Troponin 0.18 confirms the patient has diabetes"}`
    - `status == "refusal"`, `rationale is None`

**Run:** `.venv/bin/pytest tests/test_clinical_semantics.py`
**Expected:** collection succeeds, all tests fail (missing `SexContractError`, missing
`sex_convention` parameter, missing regex frames).

---

## Task 2 — Update the existing tests that encode the old behaviour

**File:** `tests/test_app.py`

- Replace `test_sex_float_with_blanks_and_zero_one_coding` with
  `test_sex_zero_one_coding_and_blanks`:
  - `A,45,0` → `"Sex: Male"`
  - `B,45,1` → `"Sex: Female"`
  - `C,45,` → `Insufficient data`
  - warning contains `"missing sex"`
- Replace `test_dirty_value_sex_zero_one_with_typo_two` with
  `test_out_of_contract_sex_two_is_rejected`:
  - `sex=2` alongside `0/1` → `pytest.raises(SexContractError)`
  - assert the message names the `0/1` contract and `sex_convention=12`
  - keep the `M0`/`F1` decoding assertions in a separate valid-cohort call

**File:** `tests/test_audit_engine.py`

- Split `test_missing_and_invalid_sex_routed_to_insufficient_data`:
  - `test_missing_sex_routed_to_insufficient_data` — `None` and `""` only.
  - `test_invalid_sex_is_a_contract_violation` — `"other"` and `2` → `SexContractError`.
- Update `test_parse_sex_is_batch_invariant_and_supports_riagendr`:
  - pass `sex_convention="12"` for the `1/2` cohort;
  - keep the identical-`risk_pct` assertion;
  - keep `_parse_sex(..., "riagendr") == [0.0, 1.0]`.

Add `import pytest` and `SexContractError` to both files if missing.

**Run:** `.venv/bin/pytest tests/test_app.py tests/test_audit_engine.py`
**Expected:** failures only on the new/changed assertions.

---

## Task 3 — Engine (`nabdh/engine.py`)

1. Add after `SMALL_CELL`:

```python
class SexContractError(ValueError):
    """Raised when a sex column violates the declared encoding contract."""


SEX_CONVENTIONS: dict[str, dict[float, float]] = {
    "01": {0.0: 0.0, 1.0: 1.0},   # 0=male, 1=female
    "12": {1.0: 0.0, 2.0: 1.0},   # 1=male, 2=female
}
SEX_CONVENTION_CHOICES = ("auto", "01", "12")
_SEX_STRINGS = {"m": 0.0, "male": 0.0, "f": 1.0, "female": 1.0}
_SEX_NULL_TOKENS = {"", "nan", "none", "null", "na", "n/a", "<na>"}
```

2. Add `validate_sex_convention(convention)`:
   - accepts `auto`, `01`, `12`, plus aliases `0/1`, `m/f` → `01`; `1/2`, `nhanes` → `12`.
   - raises `ValueError` with the supported choices otherwise.

3. Add `resolve_sex_convention(convention, col_name)`:
   - calls `validate_sex_convention`;
   - `auto` → `12` when `col_name.strip().lower() == "riagendr"`, else `01`;
   - explicit `01` + `riagendr` → `ValueError` explaining the conflict.

4. Replace `_parse_sex`:

```python
def _parse_sex(raw: pd.Series, col_name: str = "sex", convention: str = "auto") -> pd.Series:
    """Parse sex per-row deterministically under a declared 0/1 or 1/2 convention."""
    resolved = resolve_sex_convention(convention, col_name)
    num = pd.to_numeric(raw, errors="coerce")
    parsed = num.map(SEX_CONVENTIONS[resolved])
    non_num = num.isna() & raw.notna()
    if non_num.any():
        str_vals = raw[non_num].astype(str).str.strip().str.lower().map(_SEX_STRINGS)
        parsed = parsed.copy()
        parsed.loc[non_num] = str_vals
    return parsed.astype(float)
```

5. Add `_assert_sex_contract(raw, parsed, convention, col_name)`:
   - `text = raw.astype(str).str.strip().str.lower()`
   - `missing = raw.isna() | text.isin(_SEX_NULL_TOKENS)`
   - `invalid = ~missing & parsed.isna()`
   - if none, return;
   - collect up to 3 unique raw examples, truncated to 24 chars;
   - raise `SexContractError` with count, declared convention, examples, remediation.

6. `normalise(df, *, sex_convention="auto")`:
   - keep `raw_sex = out["sex"].copy()`;
   - `sex_source = src_col.get("sex", "sex")`;
   - `resolved = resolve_sex_convention(sex_convention, sex_source)`;
   - `parsed = _parse_sex(raw_sex, sex_source, resolved)`;
   - `_assert_sex_contract(raw_sex, parsed, resolved, sex_source)`;
   - `out["sex"] = parsed`;
   - change the missing-sex warning to
     `"{n} rows have missing sex; scored as 'Insufficient data'."`

7. `score(df_raw, *, sex_convention="auto")`:
   - `df, warnings = normalise(df_raw, sex_convention=sex_convention)`.
   - No other changes.

8. `ALIASES["sex"] = ["sex", "gender", "riagendr"]`.

**Run:** `.venv/bin/pytest tests/test_clinical_semantics.py tests/test_app.py tests/test_audit_engine.py`
**Expected:** engine tests pass; API/UI tests still fail (fields not added yet).

---

## Task 4 — API (`app/api/routes.py`)

1. Import `SexContractError`, `score`, `validate_sex_convention`.
2. `POST /api/score` signature:
   `async def score_cohort(file: UploadFile = File(...), sex_convention: str = Form("auto"))`
   - validate the convention before `_read`;
   - pass the canonical value to `score`;
   - catch `SexContractError` → 422, then `ValueError` → 422, then `MemoryError` → 413.
3. `POST /api/score.csv` signature gains the same form field.
   - validate `min_tier` and `sex_convention` before `_read`;
   - pass the convention to `score`.
4. Do not change `DELETE /api/outcomes`, CSV headers, upload caps, or security middleware.

**Run:** `.venv/bin/pytest tests/test_clinical_semantics.py`
**Expected:** API tests pass.

---

## Task 5 — Frontend (`app/static/index.html`, `app/static/app.js`)

1. In the `.action-bar` (or immediately above it), add:

```html
<div class="sex-convention-row">
  <label for="sex-convention">Sex encoding</label>
  <select id="sex-convention" name="sex_convention">
    <option value="auto" selected>Auto (0/1; 1/2 for riagendr)</option>
    <option value="01">0 = male, 1 = female</option>
    <option value="12">1 = male, 2 = female (NHANES)</option>
  </select>
</div>
```

2. In `app.js`:
   - `const sexConvention = () => $("sex-convention")?.value || "auto";`
   - `scoreFile`: `fd.append("sex_convention", sexConvention());`
   - `downloadFlaggedCsv`: same append.
3. Add minimal CSS only if the existing `.action-bar` cannot hold the select; prefer reusing
   existing form classes. No inline styles or scripts (CSP).
4. `node --check app/static/app.js`.

---

## Task 6 — Documentation, ADR, and change record

1. `docs/PATIENT_DATA_CURATION.md` §3 Required Columns:
   - state `0 = male`, `1 = female`;
   - state `riagendr` is accepted as an explicit `1 = male`, `2 = female` source column;
   - state `sex_convention=12` for generic `sex` columns;
   - state that a non-blank invalid value rejects the upload, while blanks become
     `Insufficient data`.
2. `data/DATASETS.md` after the mapping table:
   - clarify that `RIAGENDR (1=M, 2=F)` is a **source** encoding converted at ingestion;
   - canonical `sex` is `0 = male`, `1 = female`.
3. `docs/DEFERRED_ML_AND_CLINICAL_REVIEW.md`:
   - §2.1 and §2.2 status → `RESOLVED 2026-11-19`;
   - link the ADR and change record;
   - keep the residual limitation note that a regex is not a complete semantic classifier.
4. `docs/adr/README.md`, `docs/adr/template.md`,
   `docs/adr/0001-canonical-sex-encoding.md` (accepted).
5. `docs/CHANGE_RECORD_2026-11-19_CLINICAL_SEMANTICS.md`:
   - change ID, date, scope, decision, files, pre/post SHA-256, tests added/modified,
     verification evidence, rollback instructions, sign-off.

---

## Task 7 — Full verification

Run, in order, and paste the actual output into the change record:

```bash
.venv/bin/ruff check app/ nabdh/ tests/
node --check app/static/app.js
.venv/bin/pytest                     # no -q: the summary must be visible
```

Then a real `uvicorn` smoke test:

1. `GET /health` → 200.
2. `GET /` → 200, CSP present, `theme-init.js` referenced.
3. `POST /api/score` with `sex_convention=12` and a 40-year-old `sex=1`:
   - 200, `"Sex: Male"`, no breast/cervical flags.
4. `POST /api/score` with `sex_convention=01` and `sex=2`:
   - 422, detail contains the remediation.
5. `POST /api/score` with `riagendr` only:
   - 200, correct sex.
6. `POST /api/score` with the demo cohort:
   - `rows=60, urgent=1, high=10, elevated=16, observations_captured=4`.
7. `POST /api/score.csv` with the demo cohort:
   - 200, `text/csv`, `nosniff`.

---

## Task 8 — Close out

1. Record post-change hashes.
2. Update the change record with test counts and evidence.
3. Remove any stale references to the old "unrecognised sex" wording in docs.
4. Report to the owner: what changed, what did not, verification evidence, and the one residual
   limitation (regex cannot catch every diagnosis phrasing).

---

## Rollback

No git. To roll back:

1. Restore the files from the change record's pre-change hashes (the content is reproducible from
   the session diff).
2. Delete `tests/test_clinical_semantics.py` and the new docs.
3. Revert the four updated tests.
4. Re-run `.venv/bin/pytest`.

The demo cohort and all model artefacts are untouched, so rollback has no ML impact.

---

## Acceptance checklist

- [ ] `SexContractError` exists and is raised for non-blank undecodable values.
- [ ] `sex_convention` works in engine, both API endpoints, and the UI.
- [ ] `riagendr` works end to end.
- [ ] Blank sex remains row-level `Insufficient data`.
- [ ] Batch invariance preserved.
- [ ] Three diagnosis frames blocked; two legitimate sentences accepted.
- [ ] Refusal rationale sanitized.
- [ ] Demo cohort aggregates unchanged.
- [ ] `pytest` / `ruff` / `node --check` clean.
- [ ] ADR + change record written.
