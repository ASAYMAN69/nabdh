# Change Record — Clinical Semantics Hardening

**Change ID:** `CHG-2026-11-19-001`
**Date:** 2026-11-19
**Status:** Applied and verified; owner-approved design, pending owner countersignature below
**Design:** [2026-11-19-clinical-semantics-hardening-design.md](superpowers/specs/2026-11-19-clinical-semantics-hardening-design.md)
**Plan:** [2026-11-19-clinical-semantics-hardening-plan.md](superpowers/plans/2026-11-19-clinical-semantics-hardening-plan.md)
**ADR:** [ADR-0001](adr/0001-canonical-sex-encoding.md)
**Deferred backlog:** [DEFERRED_ML_AND_CLINICAL_REVIEW.md](DEFERRED_ML_AND_CLINICAL_REVIEW.md) §2.1, §2.2

> **Revision 2 (`CHG-2026-11-19-002`, appended at the end) supersedes the sex-encoding portions
> of this record.** The `sex_convention` field and the UI selector described in §2–§9 were
> removed; encoding is now auto-detected from the uploaded column under
> [ADR-0002](adr/0002-auto-detect-sex-encoding.md). The reasoning guard is unchanged. Use
> §R2.4 for current hashes.

---

## 1. Why

Two clinical-safety defects in the deterministic path were reproduced against the live API:

1. **Sex was half-decoded.** A `sex` column using NHANES coding decoded `1` as female and `2` as
   missing. A 40-year-old male received breast-cancer and cervical-cancer screening flags; a
   female with `sex=2` became `Insufficient data`.
2. **The reasoning validator accepted assertive diagnoses.** `Troponin 0.18 confirms the patient
   has diabetes`, `… is diagnostic of myocardial infarction`, and `This is a case of …` all
   passed. A `refusal` rationale containing the same text was returned verbatim.

Neither is an ML issue. No model, threshold, rule-pack semantic, or stream-routing rule was
changed.

## 2. Decision

**Sex encoding is declared, never guessed.** Canonical output remains `0 = male`, `1 = female`.

| Declaration | Decoding |
|---|---|
| `auto` (default) | `12` for a `riagendr` column, otherwise `01` |
| `01` | `0 = male`, `1 = female` |
| `12` | `1 = male`, `2 = female` |

- `male`/`m`/`female`/`f` always accepted.
- Blank / whitespace / null-token → row-level `Insufficient data` (not a file error).
- Non-blank and undecodable under the declared convention → `SexContractError` → HTTP `422`,
  **nothing scored**, with count, examples, and remediation.
- `riagendr` is a real alias; explicit `01` + `riagendr` is a contradictory declaration → `422`.
- Decoding is per-column, so batch invariance is preserved.

**Reasoning guard.** Added assertive frames (`confirms/indicates/proves/establishes … has/have`,
`diagnostic of/for`, `is a case of`, `consistent with a diagnosis`) with an explicit disease-term
constraint so legitimate screening language still validates. `refusal` /
`insufficient_evidence` / `unavailable` rationales are scanned; unsafe text is dropped while the
status is preserved.

## 3. Behaviour changes

| Input | Before | After |
|---|---|---|
| `sex=1/2` under default | `1` silently female; `2` missing | `422` with remediation |
| `sex=1/2` + `sex_convention=12` | not available | `1 = male`, `2 = female` |
| `sex=2` | row `Insufficient data` + generic warning | `422` (contract violation) |
| `sex=other` | row `Insufficient data` | `422` |
| blank sex | row `Insufficient data` | unchanged |
| `riagendr`-only CSV | `422 Missing required column 'sex'` | scores correctly under `auto` |
| diagnosis claim text | accepted | `ValueError` |
| diagnosis text in refusal rationale | returned verbatim | rationale dropped, status kept |

## 4. Files and hashes

No git repository exists (`git status` → `fatal: not a git repository`). SHA-256 is the audit
trail.

### 4.1 Modified — hashes captured before the change

| File | Pre-change SHA-256 | Post-change SHA-256 |
|---|---|---|
| `nabdh/engine.py` | `e51b3147c17d342908443bbdadcc41a18be0f045111560276fe31d958d08c0c6` | `51c1dfd44a4a82a27603f358f109f6d49cf500f947b3e8dfcdd44820dfba089e` |
| `app/api/routes.py` | `a93e5826bb3ef77217ea321003e991edf99c5d2e24c0e27e41bd61f55d4a875b` | `d6815ab1d62145cc89295133487f81031fe2d845b70e32c17f016fff724e53ad` |
| `app/static/index.html` | `f34e327ade9804a4ef22b8fcdb5af7b7473254d7db9aa2f42a4fa1ad02956ccf` | `54b4ce3edcc7842c650844c078782c5fb56355069c22dbf6971f350abf6cbebf` |
| `app/static/app.js` | `d3d3746514b3d41f7c7023e57b8844fbea5cf5323bf160fa287da790512156ab` | `58a4f43425ac6136c9dc97f5ea7fff447ba4ee1108694152a6c22a424bea3a07` |
| `docs/PATIENT_DATA_CURATION.md` | `375822cc61dfd92cff7733bded7353b546254060ef657a5ebe0b5a340e52b348` | `8adf2d15b9130e316edc3403f7fcd6abf9e6476ff3f8bfbed68022cea04ca198` |
| `data/DATASETS.md` | `f6fda48c2a92d0950e32fde7b26fa9fbd16badd6565ca228195a256077017cc7` | `68844132c54ac0d2177d2ae66641898a1be6c28b3207d87f231f396e9fd65829` |
| `docs/DEFERRED_ML_AND_CLINICAL_REVIEW.md` | `1e5a562ef13d9bd3a8ab026759c751ef45dc41c63572934fa8a884260422e301` | `4a5d087aa297d03cf67cfba6aaf301e53cef10920d10f02d81b2ab932011f5d9` |
| `tests/test_app.py` | `2d6f5bcbbdd24017c431688710978cc5b5b57f42d11cf57ffdf6d47541be4274` | `5673edee1eecfce11d567047ff57902a336700e544e6ed414b2bc02fb15a233a` |
| `tests/test_audit_engine.py` | `b317eeb2c4a3e9da28859ad9fc705b7dbe9c159019dfffb36e3d63de7332a1d0` | `6a8be34c10e4adfd488d388c1a74e4ab2a79dab09bfc27f28d9509bde66c5213` |

### 4.2 Modified — pre-change hash not captured live (recorded honestly)

| File | Pre-change SHA-256 | Post-change SHA-256 | Note |
|---|---|---|---|
| `nabdh/reasoning/validate.py` | `1d15e1848e10ff82866df324204da73574321ebb8d37339473423323d2543afe` *(reconstructed)* | `59a4a9a333c5c78b34aa0f7d4fc343825ba620f50187c43802d302af886d577e` | Pre-hash reconstructed by reversing the two exact edit hunks; not captured live. The reverse-patched file is at `/tmp/opencode/nabdh-smoke/validate.pre.py`. |
| `app/static/styles.css` | `8228bd71e97d0ec1cdbbbdf5a58bc05e2d93c80f6dc8ca8f15cdd55e7f818028` *(reconstructed)* | `008b174ec19dbfc949ad6b79affd093738633be689ff63e9eb52fef751b8dace` | Single-line edit: `.action-bar { align-items: center }` → `flex-end`. Pre-hash reconstructed by reversing that line; reverse-patched copy at `/tmp/opencode/nabdh-smoke/styles.pre.css`. |

**Exact pre-change hunks (reproducible without `/tmp`):**

`nabdh/reasoning/validate.py` — the old forbidden-text block was:

```python
_FORBIDDEN_CLAIM_TEXT_RE = re.compile(
    r"(?i)(?:"
    r"\b(?:prescribe|prescribing|prescription\s*:)\b"
    r"|\bdiagnos(?:is|ed)\s*(?::|\bwith\b|\bis\b|\bof\b)"
    r"|\b(?:start|initiate)\s+(?:medication|treatment|therapy|aspirin|statin|metformin|insulin)\b"
    r"|\bdosage\s*:"
    r")"
)
```

and the old early return was:

```python
    status = str(raw.get("status", "ok")).strip().lower()
    if status in ("refusal", "insufficient_evidence", "unavailable"):
        return ReasoningResult(
            status=status,
            rationale=raw.get("rationale"),
            citations=[],
        )
```

`app/static/styles.css` — the old rule was `.action-bar { align-items: center; }`; only
`center` was replaced by `flex-end`.

### 4.3 Created

| File | SHA-256 |
|---|---|
| `tests/test_clinical_semantics.py` | `14e2e36bd406a8833794d72cc8e7ea139e9dca3dbb732c1803e11e8382e7e768` |
| `docs/adr/README.md` | `81e7f0470b4bbfc1f3f985fb72d1da95fd198a5cf09b55ad78ede548e388c146` |
| `docs/adr/template.md` | `82a7cbe7a9f436e0691bd51697604249135f17c45a4f14d76ff7b3cb49342cac` |
| `docs/adr/0001-canonical-sex-encoding.md` | `ce3901ffefc1dc637039c5be7cb1152278a415ca9f26e64997a0c4a4301a614e` |
| `docs/superpowers/specs/2026-11-19-clinical-semantics-hardening-design.md` | `07ae212b7f8377c4f8b9faeaf6b8ca1dc9ab37e2e7f3706cc12df42b70957710` |
| `docs/superpowers/plans/2026-11-19-clinical-semantics-hardening-plan.md` | `bf2c3ecd6a80ea115c4d3ecb3311d71fa222868d6ecaa86f3bdcf7cf79af6510` |

> **Hash note:** post-change hashes were generated with `sha256sum` after the final
> documentation edits. `nabdh/reasoning/validate.py` and `app/static/styles.css` are the only
> pre-change hashes that were not captured live; their reconstruction method is stated in §4.2.

## 5. Tests

### 5.1 Added — `tests/test_clinical_semantics.py` (18 tests)

- `_parse_sex` matrix for `01`, `12`, `riagendr`, strings, blanks, and an out-of-range value.
- NHANES male (`sex=1`, convention `12`) receives no breast or cervical flags.
- Contract violation rejects the file with count, label, and remediation.
- `12` rejects `0`.
- Blank / whitespace sex is a row-level `Insufficient data`, not a contract violation.
- `riagendr` auto-detection.
- `riagendr` + explicit `01` conflict.
- API accepts `sex_convention`; rejects an unknown convention before reading the file; maps a
  contract violation to `422` with no results.
- CSV export honours the convention.
- Batch invariance within one convention.
- Three assertive diagnosis frames blocked; two legitimate screening sentences accepted.
- Refusal rationale with diagnosis text dropped, status preserved.

### 5.2 Updated without weakening intent

| Test | Change |
|---|---|
| `tests/test_app.py::test_sex_zero_one_coding_and_blanks` | Split old mixed test; adds explicit `12` path |
| `tests/test_app.py::test_out_of_contract_sex_two_is_rejected` | `sex=2` now asserts `SexContractError` |
| `tests/test_audit_engine.py::test_missing_sex_routed_to_insufficient_data` | Missing-only rows |
| `tests/test_audit_engine.py::test_invalid_sex_is_a_contract_violation` | `"other"` and `2` raise |
| `tests/test_audit_engine.py::test_parse_sex_is_batch_invariant_and_supports_riagendr` | Explicit `12`; preserves identical-`risk_pct` and `riagendr` assertions |

## 6. Verification evidence

Commands run from `/mnt/ee/aprojects/nabdh`.

### 6.1 Full suite

```
.venv/bin/pytest
76 passed, 1 warning in 12.78s
```

(The single warning is the upstream Starlette `TestClient`/`httpx` deprecation notice.)

### 6.2 Static checks

```
.venv/bin/ruff check app/ nabdh/ tests/
All checks passed!

node --check app/static/app.js
(exit 0)
```

### 6.3 Demo cohort regression (engine)

```
{'rows': 60, 'adults_screenable': 51, 'children_adolescents': 8, 'urgent': 1,
 'high': 10, 'elevated': 16, 'missed_by_age_rules': 4, 'observations_captured': 4,
 'observations_unmapped': 0, 'observations_unit_suspect': 1}
strings-under-12-identical: True
```

Matches the pre-change baseline exactly. The demo uses `male`/`female`, which are
convention-independent.

### 6.4 Real `uvicorn` smoke test

`uvicorn app.main:app --host 127.0.0.1 --port 8123` (process stopped after the checks).

| Check | Result |
|---|---|
| `GET /health` | `200` `{"status":"ok","service":"nabdh","version":"0.1.0"}` |
| `GET /` | `200`; `script-src 'self'`; `x-content-type-options: nosniff`; `theme-init.js` present |
| `POST /api/score` `sex_convention=12`, male `sex=1` | `200`; `Sex: Male`; **no** breast/cervical flags |
| `POST /api/score` `sex_convention=01`, `sex=2` | `422`; detail names `0=male / 1=female`, `sex_convention=12` |
| `POST /api/score` `riagendr` only | `200`; `R1 = Male`, `R2 = Female` |
| `POST /api/score` demo cohort | `200`; aggregates identical to §6.3 |
| `POST /api/score.csv` demo, `min_tier=flagged` | `200`; `text/csv`; `nosniff`; header row correct |

Exact 422 detail:

```
sex column contains 1 value(s) that are invalid under the declared 0=male / 1=female
convention (examples: '2'). Nothing was scored. Fix: recode to 0/1, leave unknown cells
blank, rename the column to 'riagendr' (1=male, 2=female), or resend with sex_convention=12.
```

## 7. Rollback

No git history exists. To revert this change:

1. Restore each file in §4.1 to its pre-change hash. The changed regions are limited to:
   - `nabdh/engine.py`: sex constants/helpers, sex block in `normalise`, warning text,
     `score` signature, `ALIASES["sex"]`.
   - `app/api/routes.py`: import line, `sex_convention` parameters, convention validation and
     `SexContractError` handling on both scoring endpoints.
   - `app/static/index.html`: the `#sex-convention` field in `.action-bar`.
   - `app/static/app.js`: `sexConvention` helper and two `FormData` appends.
   - `app/static/styles.css`: one `align-items` value.
   - `nabdh/reasoning/validate.py`: the `_DIAGNOSIS_TERMS` / `_FORBIDDEN_CLAIM_TEXT_RE` block and
     the rationale scan in the early return. The reverse-patched copy at
     `/tmp/opencode/nabdh-smoke/validate.pre.py` reproduces the pre-change hash
     `1d15e184…` exactly.
   - Docs and tests: revert to the hashes in §4.1/§4.2.
2. Delete `tests/test_clinical_semantics.py` and the new ADR files.
3. Re-run `.venv/bin/pytest`, `.venv/bin/ruff check app/ nabdh/ tests/`, and
   `node --check app/static/app.js`.
4. Re-check the demo cohort against §6.3.

Rollback has no ML impact: no model artefact, threshold, feature set, or rule pack was touched.

## 8. Residual risks and open items

| Item | Status |
|---|---|
| The diagnosis guard is a grammatical frame list, not a semantic classifier. Bare assertions such as "The patient has diabetes" or "confirms myocardial infarction" can still evade it; novel phrasings can too. | Documented in `DEFERRED_ML_AND_CLINICAL_REVIEW.md` §2.2; a production LLM path needs an allow-list or second-pass classifier. |
| A single mistyped non-blank sex value rejects the whole upload. | Accepted "fail closed" trade-off, owner-approved. A quarantine mode would be a separate decision. |
| The warning now says "missing sex" only; operators who keyed off the old "unrecognised sex" text must update. | Documented in the curation guide. |
| No git repository, so the audit trail is hashes + this record. | `git init` recommended as a separate change. |
| Pre-change hashes for `validate.py` and `styles.css` were reconstructed, not captured live. | Recorded in §4.2 with the reverse-patched files. |
| ML/clinical/privacy items (§1, §2.3, §2.4, §3, §4) remain unchanged. | Tracked in `DEFERRED_ML_AND_CLINICAL_REVIEW.md`. |

## 9. Sign-off

| Role | Name | Decision | Date |
|---|---|---|---|
| Project owner (design + fail-closed policy) | — | Approved in session | 2026-11-19 |
| Implementation / verification | Agent | Applied, 76 tests passed, smoke-verified | 2026-11-19 |
| Clinical / cardiology | — | Not required: no threshold, rule, or routing change. Residual regex limitation flagged for any future LLM path. | — |
| Privacy owner | — | Not required: no privacy surface changed. | — |

**Owner countersignature:** ____________________  **Date:** ____________

---

# Revision 2 — `CHG-2026-11-19-002`: Auto-detect sex encoding

**Date:** 2026-11-19
**Status:** Applied and verified
**Supersedes:** the `sex_convention` portions of §2–§9 above
**ADR:** [ADR-0002](adr/0002-auto-detect-sex-encoding.md) (supersedes ADR-0001)
**Directive:** project owner — remove the frontend sex-encoding control; zero friction; the
encoding must come from the ML model or the uploaded CSV, never from a user choice.

Revision 1 remains above as the historical record of `CHG-2026-11-19-001`. Its post-change
hashes were accurate at the time but are no longer the current file hashes; §R2.4 below is
authoritative. The reasoning-validator work from revision 1 is unchanged.

## R2.1 Why

Revision 1 fixed the half-decoding bug but added a **Sex encoding** selector to the upload card
and a `sex_convention` field to both scoring endpoints. The owner rejected that friction: a user
should not have to understand `0/1` versus NHANES `1/2`, and a clinic export should work as
exported. The new requirement is zero friction, with the encoding inferred from the file.

No ML model, threshold, stream-routing rule, rule-pack semantic, or privacy surface was changed.

## R2.2 Decision

**Infer the numeric sex encoding from each uploaded column. Never ask.**

Precedence:

1. Column named `riagendr` → `1 = male`, `2 = female`.
2. Otherwise, a numeric `2` present and no numeric `0` → `1 = male`, `2 = female`.
3. Otherwise → canonical `0 = male`, `1 = female`.

Supporting rules:

- `male`/`m`/`female`/`f` always accepted.
- Mixed `0` and `2` → treated as `0/1`; the `2`s become row-level `Insufficient data` rather
  than flipping the cohort.
- Generic column containing only `1`s → `1 = female` with an ambiguity warning.
- Blank / whitespace / null-token → row-level `Insufficient data`.
- Undecodable non-blank values → response warning with count and examples; affected rows are
  `Insufficient data`. The file is **not** rejected.
- The `sex_convention` field is removed from the web UI and from both API endpoints. The engine
  retains a private keyword override for tests and advanced callers.
- The convention is derived per column, so batch invariance is preserved.

**Reasoning guard:** unchanged from revision 1.

## R2.3 Behaviour changes relative to revision 1

| Input | Revision 1 | Revision 2 |
|---|---|---|
| UI / API | Sex encoding selector + form field | No control, no field |
| Generic `sex=1/2`, default | `422`, nothing scored | Auto-detected `1/2`; scores correctly |
| Generic `sex=0/1` | Scores correctly | Unchanged |
| `riagendr` | Scores correctly | Unchanged |
| Mixed `0` and `2` | `422` under `01` | Treated as `0/1`; `2`s are `Insufficient data` + warning |
| Generic column of only `1`s | `1 = female` (silent) | `1 = female` + explicit ambiguity warning |
| `sex=other` | `422`, nothing scored | Warning; that row is `Insufficient data` |
| Blank sex | Row `Insufficient data` | Unchanged |
| Stale `sex_convention` form field | Validated and applied | Ignored; file still scores |

## R2.4 Files and hashes

No git repository exists; SHA-256 is the audit trail. "Pre-R2" is the revision-1 post-change
hash. The three frontend files returned **exactly** to their pre-ADR-0001 hashes, which confirms
the selector and its wiring were removed completely rather than merely hidden.

### Modified

| File | Pre-R2 SHA-256 | Post-R2 SHA-256 |
|---|---|---|
| `nabdh/engine.py` | `51c1dfd44a4a82a27603f358f109f6d49cf500f947b3e8dfcdd44820dfba089e` | `817317fa88fb0b7dbe8110d82cd612b1b4a6cc6146997dcdcb2547c33187e188` |
| `app/api/routes.py` | `d6815ab1d62145cc89295133487f81031fe2d845b70e32c17f016fff724e53ad` | `36796da504d5081e6bf2a57cca8a31c7d09675b32f4b8441f9b280d6585aadfa` |
| `app/static/index.html` | `54b4ce3edcc7842c650844c078782c5fb56355069c22dbf6971f350abf6cbebf` | `f34e327ade9804a4ef22b8fcdb5af7b7473254d7db9aa2f42a4fa1ad02956ccf` *(= pre-ADR-0001)* |
| `app/static/app.js` | `58a4f43425ac6136c9dc97f5ea7fff447ba4ee1108694152a6c22a424bea3a07` | `d3d3746514b3d41f7c7023e57b8844fbea5cf5323bf160fa287da790512156ab` *(= pre-ADR-0001)* |
| `app/static/styles.css` | `008b174ec19dbfc949ad6b79affd093738633be689ff63e9eb52fef751b8dace` | `8228bd71e97d0ec1cdbbbdf5a58bc05e2d93c80f6dc8ca8f15cdd55e7f818028` *(= pre-ADR-0001)* |
| `tests/test_app.py` | `5673edee1eecfce11d567047ff57902a336700e544e6ed414b2bc02fb15a233a` | `723bdf5903b2651278c00bf5639544e84a5408c1d9086110aedf6ed21e7dd3e3` |
| `tests/test_audit_engine.py` | `6a8be34c10e4adfd488d388c1a74e4ab2a79dab09bfc27f28d9509bde66c5213` | `2c12792a46bf19870ca0feed34030d82f8df3a64d2d00121f54900515240c479` |
| `tests/test_clinical_semantics.py` | `14e2e36bd406a8833794d72cc8e7ea139e9dca3dbb732c1803e11e8382e7e768` | `693d44a0b97da2754d2dfeda7d066041e2e0708668f80a61b35752520927f39e` |
| `docs/PATIENT_DATA_CURATION.md` | `8adf2d15b9130e316edc3403f7fcd6abf9e6476ff3f8bfbed68022cea04ca198` | `f2a6e7004a8682a4270da3df882771fa6f82d58ea038955abd7b1d1ea35409df` |
| `data/DATASETS.md` | `68844132c54ac0d2177d2ae66641898a1be6c28b3207d87f231f396e9fd65829` | `3dcc7778be1a6818a664ca39c7f3a6366fb448456a7f584e2641d63eaa056ff3` |
| `docs/DEFERRED_ML_AND_CLINICAL_REVIEW.md` | `4a5d087aa297d03cf67cfba6aaf301e53cef10920d10f02d81b2ab932011f5d9` | `f9195a1325bfb8ae8514c46237483add3bd8401ae82ce93aa72cbab69d94ca8a` |
| `docs/adr/README.md` | `81e7f0470b4bbfc1f3f985fb72d1da95fd198a5cf09b55ad78ede548e388c146` | `1c95b41c25e2f15f3a3fefc009f1ef1694c44db3033de3c8e13fb7e60b5cde81` |
| `docs/adr/0001-canonical-sex-encoding.md` | `ce3901ffefc1dc637039c5be7cb1152278a415ca9f26e64997a0c4a4301a614e` | `733d3580283b04df27492bd31f1f134fc620f39d6d1236ec5faebacefdf004c6` |
| `docs/superpowers/specs/2026-11-19-clinical-semantics-hardening-design.md` | `07ae212b7f8377c4f8b9faeaf6b8ca1dc9ab37e2e7f3706cc12df42b70957710` | `c094abad69358824d0196b61ec4daa2375480d1a250fb230c27e5cb732937d20` |
| `docs/superpowers/plans/2026-11-19-clinical-semantics-hardening-plan.md` | `bf2c3ecd6a80ea115c4d3ecb3311d71fa222868d6ecaa86f3bdcf7cf79af6510` | `e6bfcde0d4d0ca68b9ab105690498f0ded422f03222175495ff7f5e2ee13b43f` |

### Created

| File | SHA-256 |
|---|---|
| `docs/adr/0002-auto-detect-sex-encoding.md` | `b050b163109dcc228a2b5319fc50f927cd5a390ab6e7b6db68171548f5a068b7` |

### Unchanged by revision 2

`nabdh/reasoning/validate.py`, `docs/adr/template.md`, and every other application, data, or
documentation file not listed above. The demo fixture is unchanged.

## R2.5 Verification evidence

Commands run from `/mnt/ee/aprojects/nabdh`.

### Full suite

```
.venv/bin/pytest
76 passed, 1 warning in 13.30s
```

(The warning is the upstream Starlette `TestClient`/`httpx` deprecation notice.)

### Static checks

```
.venv/bin/ruff check app/ nabdh/ tests/   → All checks passed!
node --check app/static/app.js             → exit 0
```

### Demo cohort regression

```
{'rows': 60, 'adults_screenable': 51, 'children_adolescents': 8, 'urgent': 1, 'high': 10,
 'elevated': 16, 'missed_by_age_rules': 4, 'observations_captured': 4,
 'observations_unmapped': 0, 'observations_unit_suspect': 1}
```

Identical to the revision-1 baseline. The demo cohort uses `male`/`female`.

### Real `uvicorn` smoke test

`uvicorn app.main:app --host 127.0.0.1 --port 8123` (stopped after the checks). The normal dev
server on port 8000 remained running.

| Check | Result |
|---|---|
| `GET /health` | `200` `{"status":"ok","service":"nabdh","version":"0.1.0"}` |
| `GET /` | `200`; CSP `script-src 'self'`; `nosniff`; **no `#sex-convention` element** |
| `POST /api/score` generic `sex=1/2`, no field | `200`; `M` → Male, `F` → Female; no breast/cervical flags on `M`; auto-detect warning present |
| `POST /api/score` generic `sex=0/1`, no field | `200`; `0` → Male, `1` → Female |
| `POST /api/score` `riagendr` only | `200`; `1` → Male, `2` → Female |
| `POST /api/score` mixed `0/2`, no field | `200`; `0` → Male, `1` → Female, `2` → `Insufficient data` + invalid-sex warning |
| `POST /api/score` stale `sex_convention=bogus` | `200`; field ignored; file scores |
| `POST /api/score` demo cohort | `200`; aggregates identical to the regression above |
| `POST /api/score.csv` demo, `min_tier=flagged` | `200`; `text/csv`; `nosniff`; sex reasons present |

## R2.6 Residual risks

| Item | Status |
|---|---|
| A stray `2` in a predominantly canonical file selects `1/2`, so the `1`s are read as male. | Surfaced by the auto-detection warning; source correction or `riagendr` naming resolves it. Documented in ADR-0002. |
| A generic column containing only `1`s cannot distinguish canonical `1 = female` from NHANES `1 = male`. | Defaults to `1 = female` with an explicit warning; `riagendr` removes the ambiguity. |
| Undecodable values no longer reject the file. | Intentional friction removal; warnings and row-level `Insufficient data` keep the issue visible. |
| The engine still exposes a private `sex_convention` keyword. | Test/advanced-caller surface only; not reachable from the web UI or endpoints. |
| Reasoning-validator residual limitation (bare assertions). | Unchanged from revision 1; tracked in `DEFERRED_ML_AND_CLINICAL_REVIEW.md` §2.2. |
| No git repository. | Hashes + this record remain the audit trail; `git init` still recommended. |

## R2.7 Rollback

1. Restore each file in §R2.4 to its pre-R2 hash.
2. Delete `docs/adr/0002-auto-detect-sex-encoding.md` and revert the ADR-0001 status/note,
   `docs/adr/README.md`, and the two superseded banners.
3. Re-run `.venv/bin/pytest`, `.venv/bin/ruff check app/ nabdh/ tests/`, and
   `node --check app/static/app.js`.
4. Re-check the demo cohort against §R2.5.

Rollback has no ML impact: no model artefact, threshold, feature set, rule pack, or routing rule
was touched.

## R2.8 Sign-off

| Role | Name | Decision | Date |
|---|---|---|---|
| Project owner (zero-friction directive) | — | Directed in session: remove the control; encoding from the file/model | 2026-11-19 |
| Implementation / verification | Agent | Applied, 76 tests passed, static checks clean, live smoke verified | 2026-11-19 |
| Clinical / cardiology | — | Not required: no threshold, rule, or routing change | — |
| Privacy owner | — | Not required: no privacy surface changed | — |

**Owner countersignature:** ____________________  **Date:** ____________
