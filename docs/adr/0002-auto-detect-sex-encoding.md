# ADR-0002: Auto-detect sex encoding from the uploaded column

**Date**: 2026-11-19
**Status**: accepted
**Supersedes**: [ADR-0001](0001-canonical-sex-encoding.md)
**Deciders**: Project owner (directive 2026-11-19: remove the frontend sex-encoding control,
zero friction, encoding must come from the model or the uploaded CSV)

## Context

ADR-0001 fixed the half-decoding of NHANES-style numeric sex columns, but it did so by adding a
**Sex encoding** selector to the upload card and a `sex_convention` form field to both scoring
endpoints. The default `auto` only special-cased a column literally named `riagendr`; a generic
`sex`/`gender` column using `1/2` still required the user to understand and declare the encoding.
A non-blank value outside the declared convention rejected the whole file with HTTP `422`.

The project owner reviewed the UI and directed that the control be removed. Users should not
have to understand source encodings, and a file exported from a clinic system should work as
exported. The requirement is explicitly zero friction: the encoding comes from the ML model or
the uploaded CSV, never from a user choice.

The canonical internal encoding remains **`0 = male`, `1 = female`**, because the models,
rules, and downstream contract consume that representation.

## Decision

**Infer the numeric sex encoding from the uploaded column. Never ask the user.**

Precedence, applied per column:

1. A column named `riagendr` is NHANES coding: `1 = male`, `2 = female`.
2. Otherwise, if the column contains a numeric `2` and no numeric `0`, it is NHANES coding:
   `1 = male`, `2 = female`.
3. Otherwise it is the canonical coding: `0 = male`, `1 = female`.

Supporting rules:

- `male`/`m`/`female`/`f` are always accepted and are convention-independent.
- A file containing both `0` and `2` is treated as canonical `0/1`. The `2`s are invalid and
  become row-level `Insufficient data`; one stray value does not flip the whole file.
- A generic column containing only `1`s is read as `1 = female` under canonical `0/1`, and the
  response carries an ambiguity warning. Renaming an NHANES source column to `riagendr` removes
  the ambiguity.
- Blank / whitespace / null-token cells are missing: allowed, and the row is scored as
  `Insufficient data`.
- A non-blank value that cannot be decoded is **not** a file-level error. A response warning
  names the count and up to three examples, and the affected rows are `Insufficient data`.
- The `sex_convention` field is removed from the web UI and from both API endpoints. The engine
  keeps a private `sex_convention` keyword override for tests and advanced callers; it is not
  part of the web contract.
- The convention is derived from the column as a whole, not from row order, so batch invariance
  is preserved.

Scope is limited to the sex data contract and its UI/API surface. No ML model, threshold,
stream-routing rule, rule-pack semantic, or privacy surface is changed.

## Alternatives considered

| Alternative | Pros | Cons | Verdict |
|---|---|---|---|
| Keep the explicit selector (ADR-0001) | Unambiguous; no guessing | User friction; requires understanding NHANES coding; explicitly rejected by the owner | Rejected |
| Require `riagendr` naming for `1/2` | No guessing; one simple rule | Most real `1/2` exports name the column `sex`/`gender`; the original silent misdecode returns | Rejected |
| Fail closed on ambiguous columns | No silent error | Rejects otherwise valid uploads; adds the friction the owner asked to remove | Rejected |
| ML model owns decoding | Single source of truth | The model consumes canonical numeric values after parsing; it cannot recover an already mis-decoded column | Rejected |
| Per-column auto-detection (this ADR) | Works with no user action; handles the common `1/2` export; mixed coding degrades safely; keeps the canonical contract | A stray `2` in an otherwise canonical file changes the interpretation of the `1`s; an all-`1` column remains ambiguous | **Accepted** |

## Consequences

### Positive

- No sex-encoding control in the UI and no convention field in the API. Files work as exported.
- NHANES-style `1/2` exports in a generic `sex`/`gender` column score correctly without
  renaming.
- Undecodable values degrade per row with a visible warning instead of blocking the cohort.
- Canonical model inputs, thresholds, and the rule pack are unchanged.

### Negative / risks

- In a predominantly canonical file, a single stray `2` selects `1/2` for that column, so the
  `1`s are read as male instead of female. This is surfaced by the auto-detection warning, and
  an operator can correct the source value.
- A generic column containing only `1`s cannot be distinguished between canonical `1 = female`
  and NHANES `1 = male`. The warning states the chosen reading; `riagendr` removes it.
- Because the file is no longer rejected, a systematically malformed column produces many
  `Insufficient data` rows rather than a hard stop. The warning count and statuses make this
  visible in the results.

### Verification

- `tests/test_clinical_semantics.py` covers generic `1/2`, generic `0/1`, `riagendr`, mixed
  `0/2`, all-`1`, blanks, invalid values, both API endpoints without a field, a stale form
  field, and CSV export.
- The demo cohort aggregate is unchanged.

## References

- Superseded decision: [ADR-0001](0001-canonical-sex-encoding.md).
- Change record: [CHG-2026-11-19-002](../CHANGE_RECORD_2026-11-19_CLINICAL_SEMANTICS.md#revision-2--chg-2026-11-19-002-auto-detect-sex-encoding).
- Code: `nabdh/engine.py` (`detect_sex_convention`, `resolve_sex_convention`, `_parse_sex`,
  `_sex_warnings`, `normalise`, `score`); `app/api/routes.py`; `app/static/index.html`;
  `app/static/app.js`.
