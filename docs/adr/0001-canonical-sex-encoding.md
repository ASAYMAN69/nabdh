# ADR-0001: Canonical sex encoding and `sex_convention` contract

**Date**: 2026-11-19
**Status**: superseded by [ADR-0002](0002-auto-detect-sex-encoding.md) (2026-11-19)
**Deciders**: Project owner (approved 2026-11-19); implementation by agent under change control

> **Superseded 2026-11-19.** The project owner directed that the user-facing sex-encoding
> choice be removed and that the encoding come from the uploaded CSV with no user friction.
> ADR-0002 replaces the `sex_convention` contract with per-column auto-detection. This record
> is kept unchanged as the history of the explicit-convention decision.

## Context

Nabdh stratifies risk by biological sex. The documented and internal canonical encoding
is **`0 = male`, `1 = female`** (`docs/PATIENT_DATA_CURATION.md`, `nabdh/data/nhanes.py`).

`nabdh/engine.py::_parse_sex()` historically decoded a generic `sex`/`gender` column as `0/1`
only, while treating a column literally named `riagendr` as NHANES `1/2`. A file exported with
NHANES coding into a `sex` column was therefore **half-decoded**: `1` silently became female and
`2` became missing. Reproduced against the live API, a 40-year-old male was scored as female and
received breast-cancer and cervical-cancer screening flags, while a female with `sex=2` became
`Insufficient data`.

The existing test suite deliberately enforced **batch invariance** (a patient's score must not
depend on who else is in the file). Any value-sniffing fix (`if 2 in column: use 1/2`) violates
that property because adding one row changes the decoding of every other row.

The `riagendr` escape hatch was also not reachable through the CSV API: `ALIASES["sex"]` did not
include it, so a `riagendr`-only upload returned `422 Missing required column 'sex'`.

## Decision

**The encoding is declared, never guessed.**

- Canonical output remains **`0 = male`, `1 = female`**.
- `sex_convention` accepts `auto` (default), `01`, and `12`.
  - `auto` resolves to `12` when the source column is `riagendr`, otherwise `01`.
  - `01`: strict `0 = male`, `1 = female`.
  - `12`: strict `1 = male`, `2 = female`.
- `male`/`m`/`female`/`f` are always accepted and are convention-independent.
- A blank / whitespace / null-token cell is **missing**: allowed, and the row is scored as
  `Insufficient data`.
- A non-blank value that cannot be decoded under the declared convention is a **file-level
  contract violation**: nothing is scored, and the API returns HTTP `422` with the count,
  up to three example values, and the exact remediation.
- `riagendr` is a real alias. An explicit `sex_convention=01` paired with a `riagendr` column is
  a contradictory declaration and is rejected.
- Decoding is per-column, so batch invariance is preserved.

Scope is limited to the sex data contract and its API/UI surface. No ML model, threshold,
stream-routing rule, or rule-pack semantic changes.

## Alternatives considered

| Alternative | Pros | Cons | Verdict |
|---|---|---|---|
| Warn only, never reject | Zero behaviour change; all tests pass | A `1/2` file still silently scores its `1`s as female — the core hazard remains | Rejected |
| Reject only systematic `1/2` files | Catches the common real-world failure; tolerates isolated typos | Needs an arbitrary threshold; cannot catch an all-`1` file; still changes batch invariance | Rejected |
| Value-based auto-detection (`if 2 in column`) | No new API field | Violates batch invariance; silent mode switching; not auditable | Rejected |
| Change the canonical contract to `1/2` | Matches NHANES source | Breaks the documented contract, training pipeline, and existing tests; no migration value | Rejected |
| Explicit convention, fail closed | No guessing; auditable; batch-invariant; keeps the documented contract; gives NHANES a first-class path | One bad value rejects the whole upload | **Accepted** |

## Consequences

### Positive

- A NHANES-coded export can no longer be silently inverted; the operator must declare `12`.
- Errors are actionable and auditable: count, examples, and remediation.
- Batch invariance is preserved and covered by regression tests.
- The documented `riagendr` path works end to end.
- Blank sex remains a row-level data-quality outcome rather than a file failure.

### Negative

- A single mistyped non-blank sex value now rejects the entire upload (the accepted "fail closed"
  trade-off). A future quarantine mode would be a separate decision.
- Clients that previously relied on `sex=2 → Insufficient data` must now send `sex_convention=12`
  or leave the cell blank.
- The web UI adds one control (a `Sex encoding` selector).

### Neutral

- String values remain convention-independent.
- No model artefacts or thresholds are touched; the demo cohort output is unchanged because it
  uses `male`/`female`.

## References

- Code: `nabdh/engine.py` (`SEX_CONVENTIONS`, `validate_sex_convention`,
  `resolve_sex_convention`, `_parse_sex`, `_assert_sex_contract`, `normalise`, `score`);
  `app/api/routes.py`; `app/static/index.html`; `app/static/app.js`
- Docs: `docs/PATIENT_DATA_CURATION.md`, `data/DATASETS.md`,
  `docs/DEFERRED_ML_AND_CLINICAL_REVIEW.md` §2.1
- Design: `docs/superpowers/specs/2026-11-19-clinical-semantics-hardening-design.md`
- Change record: `docs/CHANGE_RECORD_2026-11-19_CLINICAL_SEMANTICS.md`
