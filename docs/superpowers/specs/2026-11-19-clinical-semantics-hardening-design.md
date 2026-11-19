# Design: Clinical Semantics Hardening — Sex Contract & Reasoning Guard

> **Superseded in part, 2026-11-19.** The explicit `sex_convention` contract in this design was
> replaced by per-column auto-detection in
> [ADR-0002](../adr/0002-auto-detect-sex-encoding.md). The reasoning-validator work remains as
> designed. This document is kept for history; do not implement the sex selector or the
> fail-closed sex rejection.

**Date:** 2026-11-19
**Status:** Superseded in part by ADR-0002 (sex contract); reasoning guard accepted
**Scope:** §2.1 and §2.2 of `docs/DEFERRED_ML_AND_CLINICAL_REVIEW.md` only.
**Decision owner:** Project owner (approved 2026-11-19: explicit convention, fail closed); sex
policy superseded by the 2026-11-19 zero-friction directive

---

## 1. Problem

Two clinical-safety defects remain in the deterministic path. Neither is an ML issue; both are
data-contract and output-guard issues.

### 1.1 Sex is half-decoded when a file uses NHANES `1/2` coding

The documented contract is **`0 = male`, `1 = female`**
(`docs/PATIENT_DATA_CURATION.md:40`). The internal canonical field is the same
(`nabdh/data/nhanes.py:116`). The parser also understands `male/m/female/f`.

A file exported with NHANES coding (`1 = male`, `2 = female`) is therefore **half-decoded**:

```
_parse_sex([1, 2], "sex") -> [1.0, nan]   # 1 silently becomes female; 2 becomes missing
```

Reproduced against the live API:

| Input | Result |
|---|---|
| `id,age,sex,bmi` / `MALE40,40,1,26` | `Sex: Female lowers risk` + **Breast cancer mammography due** + **Cervical cancer screening due** |
| `FEMALE40,40,2,26` | `Insufficient data` (sex missing) |

The warning is generic: `"1 rows have unrecognised sex; scored with sex missing."` It does not
name `2`, does not explain the convention conflict, and is easy to miss while half the cohort is
silently inverted.

The documented `riagendr` escape hatch is **not reachable through the CSV API**:
`ALIASES["sex"]` is only `["sex", "gender"]`, so a `riagendr`-only upload returns
`422 Missing required column 'sex'`.

### 1.2 The reasoning validator accepts assertive diagnoses

`nabdh/reasoning/validate.py` blocks `diagnosis:`, `diagnosed with/of`, prescriptions, and
dosage. It is a keyword blocklist and does not block assertive natural-language diagnosis.
Reproduced with a real observation and `status = ok`:

| Claim text | Result |
|---|---|
| `Troponin 0.18 confirms the patient has diabetes` | **accepted** |
| `Troponin 0.18 is diagnostic of myocardial infarction` | **accepted** |
| `This is a case of undiagnosed diabetes` | **accepted** |
| `Elevated NT-proBNP indicates a need for echocardiography` | accepted (legitimate — must stay accepted) |
| `NT-proBNP 1450 warrants clinician review for diagnostic confirmation.` | accepted (legitimate — must stay accepted) |

A second bypass exists: when `status` is `refusal` or `insufficient_evidence`, the function
returns early and **never scans `rationale`**:

```
{"status":"refusal","rationale":"Troponin 0.18 confirms the patient has diabetes"}
-> status=refusal, rationale returned verbatim
```

The live scoring path uses `StubReasoner` (`nabdh/engine.py:797,1139`), so this is not currently
reachable from `/api/score`. It is an exported library safety gate (`nabdh/reasoning/__init__.py`)
and becomes live the moment `LocalReasoner` or `CloudReasoner` is wired in.

---

## 2. Goals

1. Make the sex encoding **explicit and auditable**; never infer it from observed values.
2. Preserve batch invariance: a patient's score must not depend on who else is in the file.
3. Fail closed on a clinical-field contract violation, with an actionable message.
4. Keep missing/blank sex as a **row-level** `Insufficient data` outcome, not a file error.
5. Make the documented `riagendr` path actually work end to end.
6. Block assertive diagnosis frames in reasoning claims without blocking legitimate
   "needs clinician review" language.
7. Prevent diagnosis text from leaking through a `refusal` rationale.
8. Change no ML model, threshold, stream-routing rule, or rule-pack semantic.
9. Leave the 60-row demo cohort's aggregate output identical.

## 3. Non-goals

- No retraining, recalibration, or renaming of model artefacts.
- No change to NT-proBNP thresholds, urgent routing, or `requires_signoff`.
- No privacy redesign (`harden_segment_suppression`, outreach language leak) — deferred.
- No new third-party dependency.
- No FHIR/HL7 ingestion work.
- No attempt to make the regex a complete semantic classifier.

---

## 4. Decision

**The sex encoding is declared, not guessed.**

- Canonical contract remains **`0 = male`, `1 = female`**.
- `sex_convention` accepts `auto`, `01`, or `12`.
  - `auto` (default): `12` when the source column is `riagendr`, otherwise `01`.
  - `01`: strict `0 = male`, `1 = female`.
  - `12`: strict `1 = male`, `2 = female`.
- String values `male/m/female/f` are always accepted (they are convention-independent).
- A **blank** sex cell is missing and is allowed. The row is routed to `Insufficient data`.
- A **non-blank** value that cannot be decoded under the declared convention is a
  **file-level contract violation**: nothing is scored, and the API returns `422` with counts,
  example values, and the exact remediation.
- `riagendr` becomes a real alias. If a `riagendr` column is paired with an explicit
  `sex_convention=01`, the declarations conflict and the request is rejected.

This keeps the documented contract, preserves batch invariance (decoding is per-column, not
per-row inference), and gives NHANES exports a first-class path.

### 4.1 Alternatives considered

| Alternative | Pros | Cons | Verdict |
|---|---|---|---|
| **Warn only, never reject** | Zero behaviour change; all tests pass | A `1/2` file still silently scores its `1`s as female — the core hazard remains | Rejected |
| **Reject only systematic `1/2` files** | Catches the real failure; tolerates isolated typos | Needs an arbitrary threshold; cannot catch an all-`1` file; changes the batch-invariance test anyway | Rejected |
| **Change the canonical contract to `1/2`** | Matches NHANES source | Breaks `PATIENT_DATA_CURATION.md`, the training pipeline, and every existing test; no migration value | Rejected |
| **Explicit convention, fail closed** | No guessing; auditable; batch-invariant; preserves the documented contract | One typo rejects the upload; small API/UI surface increase | **Chosen** |

### 4.2 Why not auto-detect from values

Auto-detection (`if 2 in column: use 1/2`) violates batch invariance: adding one row would
change how every other row is decoded. The existing test
`tests/test_audit_engine.py::test_parse_sex_is_batch_invariant_and_supports_riagendr`
exists specifically to prevent this. The chosen design keeps that property.

---

## 5. Detailed design

### 5.1 Engine (`nabdh/engine.py`)

```python
class SexContractError(ValueError):
    """Raised when a sex column violates the declared encoding contract."""

SEX_CONVENTIONS: dict[str, dict[float, float]] = {
    "01": {0.0: 0.0, 1.0: 1.0},   # 0=male, 1=female
    "12": {1.0: 0.0, 2.0: 1.0},   # 1=male, 2=female
}
SEX_CONVENTION_CHOICES = ("auto", "01", "12")
```

- `_parse_sex(raw, col_name="sex", convention="auto")` stays a **pure** parser:
  returns `float`/`NaN`, never raises. `riagendr` is forced to `12` by the caller's resolved
  convention, not by an internal special case.
- `resolve_sex_convention(convention, col_name)` validates the choice, resolves `auto`, and
  raises `ValueError` on an unsupported value or a `riagendr`/`01` conflict.
- `normalise(df, *, sex_convention="auto")`:
  - resolves the convention from `src_col["sex"]`;
  - parses;
  - calls `_assert_sex_contract(raw, parsed, convention, col_name)`;
  - emits `"N rows have missing sex; scored as 'Insufficient data'."` for **missing** values
    only (out-of-contract non-blank values raise instead).
- `score(df_raw, *, sex_convention="auto")` passes the convention to `normalise`.
- `ALIASES["sex"]` becomes `["sex", "gender", "riagendr"]` (order preserved: `sex` wins if both
  columns are present).

**Contract assertion**

```python
missing = raw.isna() | raw.astype(str).str.strip().eq("")
invalid = ~missing & parsed.isna()
if invalid.any():
    raise SexContractError(...)
```

Message shape (no patient IDs, no raw row dumps):

```
sex column contains 12 value(s) that are invalid under the declared
0=male / 1=female convention (examples: 2, other). Nothing was scored.
Fix: recode to 0/1, leave unknown cells blank, rename the column to
'riagendr', or resend with sex_convention=12 (1=male, 2=female).
```

Example values are unique, truncated to 24 characters, and capped at three.

### 5.2 API (`app/api/routes.py`)

- `POST /api/score` gains `sex_convention: str = Form("auto")`.
- `POST /api/score.csv` gains the same field.
- Validate the choice **before** reading/scoring the file.
- Unsupported value → `422`:
  `Unsupported sex_convention: 'x'. Use 'auto', '01' (0=male, 1=female), or '12' (1=male, 2=female).`
- `SexContractError` → `422` with the message above. Existing `ValueError` handling stays.
- No change to `DELETE /api/outcomes`, CSV headers, upload caps, or security headers.

### 5.3 Frontend (`app/static/index.html`, `app/static/app.js`)

- Add a labelled `<select id="sex-convention">` next to the file picker:
  - `auto` — "Auto (0/1; 1/2 for riagendr)" (default)
  - `01` — "0 = male, 1 = female"
  - `12` — "1 = male, 2 = female (NHANES)"
- Append `sex_convention` to both the score and CSV-export `FormData`.
- No new inline script or style; the existing CSP (`script-src 'self'`) is unaffected.
- The selection persists for the session but resets on reload.

### 5.4 Reasoning validator (`nabdh/reasoning/validate.py`)

Extend `_FORBIDDEN_CLAIM_TEXT_RE` with these frames:

```python
r"|\b(?:confirms?|indicates?|proves?|establishes?)\b[^.;]{0,40}"
r"\b(?:has|have|suffers?\s+from|suffering\s+from)\b"
r"|\bdiagnostic\s+(?:of|for)\b"
r"|\b(?:is|are)\s+(?:a\s+)?case\s+of\b"
r"|\bconsistent\s+with\s+(?:a\s+)?diagnosis\b"
```

**Implementation note (precision deviation, recorded during execution):** the bare
`confirms… has…` combination from the paragraph above is too loose in both directions:
without a disease term it would block legitimate sentences such as *"indicates a need for
cardiology review"*, and the standalone `has|have` frame would block *"has a family history
of diabetes"*. The shipped regex therefore requires the assertive verb
(`confirms|indicates|proves|establishes`) followed by `has|have|suffers from`, then a
disease term within 30 characters (explicit `_DIAGNOSIS_TERMS` alternation), and skips
negated forms (`has not` / `has no`). The four structural frames remain exactly as
designed. The disease-term list is a documented precision/recall trade-off, not a semantic
classifier — bare assertions without one of these frames (for example
*"The patient has diabetes"* or *"confirms myocardial infarction"*) are a known residual
gap tracked in the deferred backlog.

- The existing `diagnosed with/of` pattern remains.
- Claim-text violations still raise `ValueError` (unchanged contract).
- For `refusal` / `insufficient_evidence` statuses, scan `rationale` **before** the early return.
  If it matches, return the same status with `rationale=None` and `citations=[]` instead of
  raising. Rationale is explanatory, not a scored claim; dropping it preserves availability while
  ensuring the diagnosis text never reaches the caller.
- No change to numeric grounding, forbidden keys, or rule resolution.

### 5.5 Documentation and change control

| Artefact | Change |
|---|---|
| `docs/PATIENT_DATA_CURATION.md` §3 | State the 0/1 contract, the `riagendr` alias, `sex_convention`, and the fail-closed rule |
| `data/DATASETS.md` (after the mapping table) | Clarify that `1=M/2=F` is a **source** encoding converted at ingestion |
| `docs/DEFERRED_ML_AND_CLINICAL_REVIEW.md` §2.1/§2.2 | Mark `RESOLVED 2026-11-19`, link to the ADR and change record |
| `docs/adr/0001-canonical-sex-encoding.md` | New ADR: context, decision, alternatives, consequences |
| `docs/adr/README.md` + `docs/adr/template.md` | New ADR index and template |
| `docs/CHANGE_RECORD_2026-11-19_CLINICAL_SEMANTICS.md` | Change ID, files, decisions, pre/post hashes, test evidence, rollback, sign-off |
| `docs/superpowers/plans/2026-11-19-clinical-semantics-hardening-plan.md` | TDD implementation plan |

There is no git repository in this workspace (`git status` → `fatal: not a git repository`), so
the change record plus SHA-256 hashes are the audit trail. `git init` is recommended but out of
scope.

---

## 6. Test design (TDD, failing tests first)

### 6.1 New `tests/test_clinical_semantics.py`

1. `_parse_sex` matrix for `01`, `12`, `riagendr`, strings, blanks.
2. `sex_convention="12"`: a 40-year-old `1` is male, gets **no** breast/cervical flags, and has
   `"Sex: Male"` in reasons.
3. `sex_convention="01"`: a `2` raises `SexContractError`; message contains the count and the
   remediation.
4. `sex_convention="12"`: a `0` raises `SexContractError`.
5. Blank / whitespace / `NaN` sex does **not** raise; the row is `Insufficient data`.
6. `riagendr`-only CSV works under `auto`; `1` is male, `2` is female.
7. `riagendr` + explicit `sex_convention="01"` raises.
8. `/api/score` accepts the form field and returns the correct sex.
9. `/api/score` rejects an unsupported convention with 422 **before** scoring.
10. `/api/score` maps a contract violation to 422 with no partial results.
11. `/api/score.csv` uses the same convention and still exports.
12. Batch invariance: the same row scored alone and in a mixed cohort has identical sex/risk
    **within one convention**.
13. Validator blocks all three reproduced diagnosis frames.
14. Validator still accepts the two legitimate screening-review sentences.
15. A `refusal` rationale containing diagnosis text is dropped, status stays `refusal`.

### 6.2 Existing tests to update (not weaken)

| Test | Change |
|---|---|
| `tests/test_app.py::test_sex_float_with_blanks_and_zero_one_coding` | Split: valid `0/1` behaviour; `1/2` now requires `sex_convention="12"` |
| `tests/test_app.py::test_missing_and_invalid_sex_routed_to_insufficient_data` | Missing/blank stays `Insufficient data`; `"other"` and `2` now raise `SexContractError` |
| `tests/test_app.py::test_dirty_value_sex_zero_one_with_typo_two` | Now expects `SexContractError` (the typo is a contract violation) |
| `tests/test_audit_engine.py::test_parse_sex_is_batch_invariant_and_supports_riagendr` | Preserve the invariance assertion; pass explicit conventions instead of relying on mixed `1/2` |

Every rewritten test keeps its original safety intent and adds a stricter assertion. No test is
deleted without a replacement in the new file.

### 6.3 Regression evidence to capture

- Demo cohort (`data/sample/uae_demo_cohort.csv`) aggregate is unchanged:
  `rows=60, urgent=1, high=10, elevated=16, missed_by_age_rules=4, observations_captured=4,
  unit_suspect=1`.
- Full suite: `pytest` (no `-q` so the summary is visible).
- `ruff check .`
- `node --check app/static/app.js`
- Real `uvicorn` smoke test for `/api/score` with `sex_convention=12` and `=01`.

---

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Existing clients sending `sex=2` now get 422 | Clear message with exact remediation; documented in the curation guide; demo uses `M/F` and is unaffected |
| A single typo rejects a large upload | Accepted trade-off of "fail closed"; message tells the operator how to fix it. A future "quarantine mode" can be a separate decision |
| Regex over-blocks legitimate language | Explicit positive tests for `"diagnostic confirmation"` and `"indicates a need for"` |
| Rationale sanitisation hides useful context | The status remains `refusal`; only the unsafe sentence is dropped |
| No git history | Change record + SHA-256 before/after; recommend `git init` separately |
| UI select drift from server choices | Single source of truth in `SEX_CONVENTION_CHOICES`; a test asserts the three values |

---

## 8. Acceptance criteria

1. `score(df)` with default `auto` and a `sex` column of `0/1` or `M/F` behaves exactly as today.
2. `score(df, sex_convention="12")` maps `1 → male`, `2 → female`; a 40-year-old `1` receives no
   breast or cervical screening flags.
3. A `sex` value outside the declared convention raises `SexContractError`; the API returns 422
   and scores nothing.
4. Blank sex values remain row-level `Insufficient data`, not a file error.
5. A `riagendr`-only CSV scores successfully under `auto`.
6. The three reproduced diagnosis claims raise `ValueError`; the two legitimate sentences still
   validate.
7. A diagnosis-bearing `refusal` rationale is dropped.
8. Demo cohort aggregates are byte-identical in shape and numerically identical.
9. `pytest`, `ruff`, and `node --check` are clean.

---

## 9. Approval

**Status: awaiting owner approval before implementation.**

On approval:
1. Write the implementation plan to
   `docs/superpowers/plans/2026-11-19-clinical-semantics-hardening-plan.md`.
2. Add the failing tests first.
3. Implement engine → API → UI → docs/ADR/change record.
4. Run the full verification matrix and report evidence.
