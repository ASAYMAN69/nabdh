# Deferred: ML, Clinical-Semantics & Privacy Review

**Purpose:** single holding file for audit findings that must **not** be changed by a
general-purpose coding pass. Everything here needs either the model owner, a clinician,
or a privacy owner to sign off before the code moves.

**Rule for this file**

- Do not retrain, recalibrate, re-tune, or rename model artefacts from a frontend/API task.
- Do not change clinical thresholds, stream routing, or rule semantics without sign-off.
- Web/API hardening is tracked separately and is already applied (see §6).

**Status legend:** `OPEN` · `NEEDS DECISION` · `PROPOSED PATCH` · `VERIFIED, DO NOT REGRESS`

---

## 1. ML model

### 1.1 "Calibrated ML suite" — wording is not supported by the code

**Status:** `NEEDS DECISION` · **Severity:** high (claim accuracy)

`README.md` and the demo narrative describe a calibrated suite. There is **no calibration
estimator** in the codebase:

```
grep -rn "CalibratedClassifierCV|isotonic|sigmoid|platt" --include=*.py nabdh app
→ NONE FOUND
```

What exists is only **reliability reporting** plus a misleading comment:

- `nabdh/model/train.py:145` — `_calibration_table(y, p, bins=10)` (bins observed vs predicted)
- `nabdh/model/train.py:208` — attaches the table to CV scores
- `nabdh/model/train.py:228` / `:249` — attaches tables to external/holdout scores
- `nabdh/model/train.py:209` — comment: `# Deploy calibrated linear model for O/E stability…`

The deployed objects are plain `LogisticRegression` pipelines. A calibration table
describes miscalibration; it does not correct it.

**Options (pick one, both require model-owner work):**

1. **Rename the claim** to "logistic regression with reliability tables". No retraining.
2. **Actually calibrate** with `CalibratedClassifierCV(..., method="isotonic"|"sigmoid")`
   inside nested CV, then regenerate **every** number in `models/metrics.json` and both
   docs. This changes model outputs and must not be done casually.

**Do not** simply delete the "calibrated" word from one file while leaving the others.

---

### 1.2 External-validation documentation overstates coverage

**Status:** `NEEDS DECISION` · **Severity:** high (claim accuracy)

Actual `models/metrics.json` layout, confirmed:

| Variant | `eval_set` field | Evaluation |
|---|---|---|
| `full__*` | `NHANES 2017-20 25% stratified held-out` | internal holdout |
| `nofamily__*` | `NHANES 2021-23 (temporal external, deployed model)` | external temporal |

So **only the `nofamily` variants are externally validated**. The `full` variants are
25% holdout on the training wave.

But the docs say all five:

- `README.md:10` — "…for 5 targets … trained on NHANES 2017–20 and temporally validated on
  NHANES 2021–23."
- `docs/DEMO_AND_LIMITATIONS.md:28` — "The 5 adult ML models … are trained on **U.S. NHANES
  2017–2020** and externally validated on **NHANES 2021–2023**."

**Required edit (docs only, after sign-off):** state that the deployed production path is
the `nofamily` variant (external 2021–23), and that `full` is an internal holdout variant
used only when family history is supplied. Decide which variant is actually claimed as
"the model".

---

### 1.3 Performance envelope — do not present as high accuracy

**Status:** `VERIFIED, DO NOT REGRESS` (numbers) · **Severity:** medium (communication)

Reproduced exactly this session:

| Target | full holdout AUC / O-E | nofamily external AUC / O-E |
|---|---|---|
| undiagnosed_dm | 0.76655 / 1.2546 | 0.78194 / 0.9263 |
| dysglycaemia | 0.74380 / 1.0062 | 0.73285 / 0.8464 |
| undiagnosed_htn | 0.70010 / 1.0792 | 0.67242 / 0.9719 |
| undiagnosed_dyslipidaemia | 0.65740 / 0.9564 | 0.68629 / 0.9591 |
| ckd_risk | 0.75900 / 1.0460 | 0.77671 / 1.0776 |

Talking points that are defensible: "moderate discrimination (AUC ≈ 0.67–0.77),
used for **prioritisation**, not diagnosis." Talking points that are not: "accurate
prediction", "calibrated", "clinically validated".

Note `full__undiagnosed_dm` O/E = **1.2546** (over-prediction on holdout; the pre-sign-constraint artifact was 1.3772). Any
deployment claim should mention recalibration on local data, which
`docs/DEMO_AND_LIMITATIONS.md` already does — keep that sentence.

---

### 1.4 Transportability (US NHANES → Abu Dhabi)

**Status:** `OPEN` · **Severity:** high (clinical)

NHANES is a US sample. There is no UAE/Malaffi evaluation in this repo. The docs already
state that intercept/slope recalibration on DoH/Malaffi cohorts is required before
clinical deployment. Do not weaken that statement. Any new claim of UAE validity needs
local data, not a code change.

---

### 1.5 Leakage controls — verified, protect them

**Status:** `VERIFIED, DO NOT REGRESS`

- SEQN intersection between 2017–20 and 2021–23 = **0**.
- `MCQ300C` exists in `P_MCQ.xpt` and not in `MCQ_L.xpt` — the dual-variant design is
  justified by the data, not invented.
- `features_for_target()` excludes BP for HTN, lipids for dyslipidaemia, etc.
- Lab/treatment variables are never features.

Any feature-set change must re-run the leakage checks in `data/DATASETS.md`.

---

## 2. Clinical semantics (high-judgement — do not hot-fix)

### 2.1 Numeric sex `1/2` is silently mis-decoded

**Status:** `RESOLVED 2026-11-19` · **Severity:** critical (was)

**Resolution:** the sex encoding is now inferred from the uploaded column, with no user
choice. Canonical encoding remains **`0 = male`, `1 = female`**. A generic `sex`/`gender`
column containing a `2` and no `0` is decoded as NHANES `1 = male`, `2 = female`; `riagendr`
is always `1 = male`, `2 = female`; a file containing both `0` and `2` is treated as `0/1`
and the `2`s degrade to missing. Undecodable values produce a response warning and row-level
`Insufficient data` instead of rejecting the file. The convention is derived from the column
as a whole, so batch invariance holds. The earlier explicit, fail-closed contract (ADR-0001)
was superseded because it added a user-facing encoding choice. See
[ADR-0002](adr/0002-auto-detect-sex-encoding.md) and the
[change record](CHANGE_RECORD_2026-11-19_CLINICAL_SEMANTICS.md).

**Original analysis and rejected proposal (historical; superseded by the resolution above):**

`nabdh/engine.py` `_parse_sex()` maps only `male/m/female/f` and `0/1` for the generic
`sex`/`gender` column. It does **not** handle the very common export convention
`1 = male, 2 = female`, except when the column is literally `riagendr`.

Measured:

```
_parse_sex([1, 2], "sex")      -> [1.0, nan]     # 1 becomes FEMALE, 2 becomes missing
_parse_sex([1, 2], "gender")   -> [1.0, nan]
_parse_sex([1, 2], "riagendr") -> [0.0, 1.0]     # correct
```

Clinical consequence (reproduced): a 40-year-old `sex=1` male is scored as **female** and
receives *"Breast cancer mammography due (female 40-74)"* and *"Cervical cancer screening
due (female 21-65)"*; a `sex=2` female becomes **Insufficient data**.

**Proposed patch (needs review, then a regression test):**

```python
def _parse_sex(raw: pd.Series, col_name: str = "sex") -> pd.Series:
    s = raw.copy()
    text = s.astype(str).str.strip().str.lower()
    out = text.map({"male": 0.0, "m": 0.0, "female": 1.0, "f": 1.0})

    num = pd.to_numeric(s, errors="coerce")
    if col_name.strip().lower() == "riagendr":
        num_map = num.map({1: 0.0, 2: 1.0})
    elif bool(num.dropna().isin([2]).any()):
        # Column contains a 2 -> 1/2 convention (1=male, 2=female)
        num_map = num.map({1: 0.0, 2: 1.0})
    else:
        # Existing 0/1 convention (0=female, 1=male)
        num_map = num.map({0: 0.0, 1: 1.0})

    out = out.fillna(num_map)
    return out.where(out.isin([0.0, 1.0]))
```

**Why this is deferred:** the `0/1` vs `1/2` ambiguity is a data-contract decision.
Confirm the accepted convention with the cohort owner and add explicit tests for:
`[1,2]`, `[0,1]`, `['1','2']`, `['male','female']`, `['M','F']`, and `riagendr`.

---

### 2.2 Reasoning validator accepts diagnosis claims

**Status:** `RESOLVED 2026-11-19` · **Severity:** critical (was)

**Resolution:** `_FORBIDDEN_CLAIM_TEXT_RE` now blocks the assertive frames
`confirms/indicates/proves/establishes … has/have`, `diagnostic of/for`, `is a case of`, and
`consistent with a diagnosis`, using an explicit disease-term constraint so legitimate
screening language ("indicates a need for…", "warrants clinician review for diagnostic
confirmation") still validates. `refusal` / `insufficient_evidence` / `unavailable` paths now
scan `rationale`; unsafe text is dropped (rationale set to `None`) while the status is
preserved. Claim violations still raise `ValueError`.

**Residual limitation:** this is a grammatical frame guard, not a semantic classifier. Novel
phrasings can still evade it. A production LLM path should add an allow-list of claim templates
or a second-pass classifier, plus adversarial tests. See the
[change record](CHANGE_RECORD_2026-11-19_CLINICAL_SEMANTICS.md).

**Original analysis (historical):**

`nabdh/reasoning/validate.py:26-33` blocks `diagnosis:`, `diagnosed with/is/of`,
`prescribe…`, `start/initiate <drug>`, `dosage:`. It does **not** block assertive
natural-language diagnosis. Reproduced with `status = ok`:

- `"Troponin 0.18 confirms the patient has diabetes"`
- `"Troponin 0.18 is diagnostic of myocardial infarction"`

Blocked correctly: "Prescribe statin…", "Start metformin…", forbidden keys.

**Gap:** the regex is a keyword blocklist; it encodes grammatical frames, not semantics.

**Minimum patch (add to `_FORBIDDEN_CLAIM_TEXT_RE`):**

```python
r"|\b(?:confirms?|indicates?|proves?|establishes?)\b.{0,40}\b(?:has|have|suffers?\s+from)\b"
r"|\bdiagnostic\s+of\b"
r"|\bconsistent\s+with\s+(?:a\s+)?diagnosis\b"
r"|\bis\s+(?:a\s+)?case\s+of\b"
```

A regex cannot be complete. For anything beyond a demo, use an allow-list of claim
templates or a second-pass classifier, and add adversarial tests.

**Why deferred:** patient-facing safety language; needs clinical sign-off on the phrase
list and false-positive risk.

---

### 2.3 NT-proBNP threshold vs age-banded reference

**Status:** `NEEDS DECISION` · **Severity:** medium

`nabdh/observations/catalog.json` defines age-banded reference highs for `nt_probnp`
(125 / 225 / … by decade), but the urgent rule
`CV-NT-proBNP-01` uses a fixed `nt_probnp >= 900 pg/mL` for every age.

This is defensible as a deliberately conservative "markedly elevated" escalation, but the
two layers are not obviously aligned. Decide and document:

- keep 900 as an age-independent urgent threshold (add rationale to the rule citation), or
- derive the rule threshold from the catalog age band (e.g. band high × multiplier).

Do not change without cardiology sign-off.

---

### 2.4 Stream routing and urgent override — verified

**Status:** `VERIFIED, DO NOT REGRESS`

Urgent override beats every stream: Excluded, paediatric, prenatal, insufficient-data and
male-pregnant rows all become `Urgent Clinical Review`, `requires_signoff = True`, and
suppress outreach. Condition gating nulls only the matching target. Keep these tests.

---

## 3. Privacy & safeguards

### 3.1 `harden_segment_suppression()` is not wired into production

**Status:** `PROPOSED PATCH` (not applied) · **Severity:** medium

Defined at `nabdh/safeguards/__init__.py:9`, exported at `:58`, and referenced **only** by
`tests/test_audit_safeguards.py`. No production call site. The engine's own
`_segments` / `_suppressed_values` path does apply small-cell and complementary
suppression, so the app is not unprotected — but the "hardened" function is dead code.

**Decision:** either call it in `engine.score()` after `_segments` (and update the
segment tests), or delete it and keep one suppression implementation. Two implementations
is the worst outcome.

---

### 3.2 Suppressed language cells leak through outreach

**Status:** `NEEDS DECISION` · **Severity:** medium

Segment audit complementary-suppresses the `AR` language cell:

```
{'dimension': 'language', 'segment': 'AR', 'n': 'suppressed (complementary)'}
```

Yet 17 rows ship `outreach_preview.language = "AR"`, and row-level `language` is
`<suppressed (<10)>`. So the suppressed attribute is recoverable from the outreach field.
`UAE-WOW-029` demonstrates it in a single row.

**Options:**

1. Gate outreach language on segment suppression (drop `language` from the preview when
   the cell is suppressed) — safest, but changes demo UX.
2. Stop suppressing the language dimension once outreach reveals it (admits the leak).
3. Keep both, and document that outreach language is intentionally disclosed to the
   patient but not to the analyst. Confirm this is actually acceptable under the privacy
   model.

Needs the privacy owner, not a quick patch.

---

## 4. Packaging accuracy (low risk)

| Item | Status | Detail |
|---|---|---|
| `PREV-TOB-01` | `NEEDS DECISION` | Does not exist. Actual ID: `PREV-TOBACCO-01` (`nabdh/rules/rules_pack.json`). |
| `GEN-PRS-01` as "Why Flagged driver" | `NEEDS DECISION` | For `UAE-WOW-029` it is a **flag**, not in `reasons`. Demo doc wording overstates. |
| "17 edge-case/privacy/demo-breaking bugs fixed" | `OPEN` | No git history / changelog. Cannot be verified. Recommend `git init` + `CHANGELOG.md` going forward. |

---

## 5. Regression tests to add when any of the above is fixed

1. `_parse_sex` matrix (§2.1) — including the 40-year-old male breast-screening case.
2. Validator adversarial phrases (§2.2) — both bypasses above must raise.
3. NT-proBNP boundary at 899 / 900 / 901 for two age bands (§2.3).
4. One suppression implementation only (§3.1) — assert the chosen function is called.
5. Outreach/segment coherence (§3.2) — a suppressed language segment must not be
   recoverable from the preview, or the exception must be explicitly asserted.

---

## 6. Already fixed in the web/API layer (this pass)

For traceability — **these are done**, do not re-open as ML issues:

- Upload cap (64 MB) enforced while reading, before parsing.
- Column cap (1,000) and row cap (200,000) enforced.
- Binary input rejected (`\x00` check).
- UTF-8 BOM handling (`utf-8-sig`).
- Delimiter sniffing for `,` `;` tab `|` — Excel-in-`;` exports now work.
- Parser errors return clean 400 messages instead of leaking exception text.
- `min_tier` validated before scoring.
- CSV export sends `X-Content-Type-Options: nosniff` and `Cache-Control: no-store`.
- Security headers + strict app CSP (`script-src 'self'`), docs routes exempted so
  Swagger/ReDoc keep working.
- Inline theme script moved to `/static/theme-init.js` so the strict CSP holds.
- Frontend: upload-size guard, 300 s abort timeout, non-JSON error handling.
- Frontend: all data-derived interpolations now go through `esc()` / `fmtNum()`;
  `NaN%`/`undefined%` rendering eliminated.

---

**Owner sign-off required before §1, §2, or §3 changes land.**
