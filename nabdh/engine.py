"""Scoring engine: schema validation -> rules -> ML risk -> pathway -> explanation.

Population prioritisation only. Not a clinical diagnosis; requires clinician sign-off.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from nabdh.data.nhanes import FEATURES, TARGETS
from nabdh.observations.ingest import capture_wide_dataframe
from nabdh.outreach import format_outreach_preview
from nabdh.reasoning.base import StubReasoner
from nabdh.rules.pack import (
    evaluate_observation_rules,
    evaluate_peds_genomic_and_wcv_rules,
    evaluate_preventive_rules,
    evaluate_vital_rules,
)

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
WHO = ROOT / "data" / "raw" / "who_growth_standards"
SMALL_CELL = 10

SEX_CONVENTIONS: dict[str, dict[float, float]] = {
    "01": {0.0: 0.0, 1.0: 1.0},  # 0=male, 1=female
    "12": {1.0: 0.0, 2.0: 1.0},  # 1=male, 2=female
}
SEX_CONVENTION_CHOICES = ("auto", "01", "12")
_SEX_STRINGS = {"m": 0.0, "male": 0.0, "f": 1.0, "female": 1.0}
_SEX_NULL_TOKENS = frozenset({"", "nan", "none", "null", "na", "n/a", "<na>"})


ALIASES = {
    "age": ["age", "age_years", "ridageyr"],
    "sex": ["sex", "gender", "riagendr"],
    "bmi": ["bmi", "bmxbmi"],
    "waist": ["waist", "waist_cm", "bmxwaist"],
    "height_cm": ["height_cm", "height", "bmxht"],
    "weight_kg": ["weight_kg", "weight", "bmxwt"],
    "whtr": ["whtr", "waist_to_height", "waist_height_ratio"],
    "systolic_bp": ["systolic_bp", "sbp", "systolic"],
    "diastolic_bp": ["diastolic_bp", "dbp", "diastolic"],
    "family_hx_diabetes": ["family_hx_diabetes", "family_history_diabetes", "fh_diabetes"],
    "family_hx_cvd": ["family_hx_cvd", "family_history_cvd", "fh_cvd"],
    "diagnosed_htn": ["diagnosed_htn", "hypertension", "htn"],
    "high_chol": ["high_chol", "high_cholesterol"],
    "cvd_history": ["cvd_history", "cvd"],
    "ckd": ["ckd", "kidney_disease"],
    "smoker": ["smoker", "current_smoker", "ever_smoker"],
    "pack_years": ["pack_years", "smoking_pack_years"],
    "sleep_hours": ["sleep_hours", "sleep"],
    "income_ratio": ["income_ratio"],
    "education": ["education", "education_level", "dmdeduc2"],
    "pregnant": ["pregnant", "is_pregnant"],
    "glucose_test_3y": ["glucose_test_3y", "glucose_test_past_3y", "recent_glucose_test"],
    "chol_test_5y": ["chol_test_5y", "cholesterol_test_5y"],
    "colorectal_screen_10y": ["colorectal_screen_10y", "colonoscopy_10y", "crc_screen"],
    "mammogram_2y": ["mammogram_2y", "mammography_2y"],
    "cervical_screen_3y": ["cervical_screen_3y", "pap_3y"],
    "hba1c": ["hba1c", "a1c", "lbxgh", "hba1c_mmol_mol", "hba1c_ifcc"],
    "fpg": ["fpg", "fasting_glucose", "lbxglu", "fpg_mmol_l", "glucose_mmol_l"],
    "total_chol": ["total_chol", "cholesterol", "lbxtc", "total_chol_mmol_l", "cholesterol_mmol_l"],
    "hdl": ["hdl", "hdl_chol", "lbdhdd", "hdl_mmol_l"],
    "ldl": ["ldl", "ldl_chol", "lbdldl", "ldl_mmol_l"],
    "triglycerides": ["triglycerides", "tg", "lbxtr", "triglycerides_mmol_l", "tg_mmol_l"],
    "egfr": ["egfr", "gfr"],
    "prs_cardiometabolic": ["prs_cardiometabolic", "prs", "polygenic_risk"],
    "g6pd_status": ["g6pd_status", "g6pd"],
    "thalassemia_carrier": ["thalassemia_carrier", "thalassemia"],
    "missed_well_child_visits": ["missed_well_child_visits", "missed_wcv"],
    "developmental_delay_flag": ["developmental_delay_flag", "developmental_milestone_flag"],
    "immunization_status": ["immunization_status", "immunization_overdue", "vaccine_overdue"],
    "healthcare_visit_12m": ["healthcare_visit_12m", "visit_past_year"],
    "id": ["id", "resident_id", "patient_id", "seqn"],
    "diagnosed_diabetes": ["diagnosed_diabetes", "diabetes", "known_diabetes"],
    "borderline_diabetes": ["borderline_diabetes", "prediabetes", "known_prediabetes"],
    "language": ["language", "preferred_language"],
    "district": ["district", "area"],
}

LABELS = {
    "age": "Age",
    "sex": "Sex",
    "whtr": "Central adiposity (WHtR)",
    "bmi": "BMI",
    "systolic_bp": "Systolic BP",
    "diastolic_bp": "Diastolic BP",
    "family_hx_diabetes": "Family history of diabetes",
    "diagnosed_htn": "Diagnosed hypertension",
    "high_chol": "High cholesterol",
    "cvd_history": "Cardiovascular disease history",
    "current_smoker": "Current smoking",
    "sleep_hours": "Sleep duration",
    "income_ratio": "Income level",
    "education": "Education level",
}

BOOL = {
    "yes": 1.0,
    "y": 1.0,
    "true": 1.0,
    "1": 1.0,
    "1.0": 1.0,
    "no": 0.0,
    "n": 0.0,
    "false": 0.0,
    "0": 0.0,
    "0.0": 0.0,
}

BOUNDS: dict[str, tuple[float, float]] = {
    "age": (0.0, 120.0),
    "bmi": (10.0, 100.0),
    "waist": (35.0, 250.0),
    "height_cm": (45.0, 250.0),
    "weight_kg": (2.0, 350.0),
    "whtr": (0.25, 1.5),
    "systolic_bp": (60.0, 260.0),
    "diastolic_bp": (30.0, 160.0),
    "sleep_hours": (1.0, 20.0),
    "income_ratio": (0.0, 10.0),
    "pack_years": (0.0, 150.0),
    "hba1c": (3.0, 20.0),
    "fpg": (30.0, 800.0),
    "total_chol": (50.0, 800.0),
    "hdl": (5.0, 200.0),
    "ldl": (10.0, 500.0),
    "triglycerides": (15.0, 3000.0),
    "egfr": (2.0, 200.0),
    "missed_well_child_visits": (0.0, 20.0),
}

# WHO 2006 Child Growth Standards (0-60 months BMI-for-age) LMS anchor tables
_WHO_0_5_ANCHORS = {
    1: np.array([
        [0, -0.3053, 13.4069, 0.09560],
        [6, 0.2003, 15.6107, 0.08859],
        [12, -0.1197, 16.7570, 0.08182],
        [24, -0.6187, 16.0189, 0.07785],
        [36, -0.3101, 15.5988, 0.07931],
        [48, -0.4283, 15.4411, 0.08711],
        [60, -0.7151, 15.2679, 0.08366],
    ]),
    2: np.array([
        [0, -0.0631, 13.3363, 0.09272],
        [6, 0.2688, 15.1380, 0.09472],
        [12, -0.0382, 16.0247, 0.08854],
        [24, -0.5684, 15.6881, 0.08454],
        [36, -0.5684, 15.3968, 0.08535],
        [48, -0.5684, 15.2285, 0.09062],
        [60, -0.8702, 15.2453, 0.09646],
    ]),
}


@lru_cache(maxsize=16)
def _bundle(variant: str, target: str) -> dict:
    bundle = joblib.load(MODELS / f"{variant}__{target}.joblib")
    _apply_sign_constraints(bundle)
    return bundle


def _apply_sign_constraints(bundle: dict) -> None:
    """Zero out standardized coefficients that contradict clinical expectations.

    Mirrors the training-time guardrail so a stale or hand-edited artifact can
    never ship a clinically inverted gradient. Features whose higher value must
    raise risk are listed in nabdh.data.nhanes.POSITIVE_SIGN_FEATURES.
    """
    from nabdh.data.nhanes import POSITIVE_SIGN_FEATURES

    model = bundle.get("model")
    feats = bundle.get("features", [])
    if model is None or not hasattr(model, "steps"):
        return
    clf = model.steps[-1][1]
    coef = clf.coef_[0].copy()
    for j, feat in enumerate(feats):
        if feat in POSITIVE_SIGN_FEATURES and coef[j] < 0:
            coef[j] = 0.0
    clf.coef_[0] = coef


@lru_cache(maxsize=1)
def _lms() -> dict[int, pd.DataFrame]:
    p = WHO / "who_5_19y_bfawho2007.txt"
    if not p.exists():
        return {}
    df = pd.read_csv(p, sep="\t")
    return {int(s): g.set_index("age") for s, g in df.groupby("sex")}


def bmi_zscore(sex: float, age_years: float, bmi: float) -> float | None:
    """WHO BMI-for-age z-score covering 0-19.99y (0-5y anchors + 5-19y table)."""
    if pd.isna(bmi) or pd.isna(age_years) or age_years < 0 or age_years >= 20 or bmi <= 0:
        return None
    who_sex = 2 if sex == 1 else 1
    months = int(round(float(age_years) * 12.0))
    if months < 60:
        a = _WHO_0_5_ANCHORS[who_sex]
        L = float(np.interp(months, a[:, 0], a[:, 1]))
        M = float(np.interp(months, a[:, 0], a[:, 2]))
        S = float(np.interp(months, a[:, 0], a[:, 3]))
    else:
        table = _lms().get(who_sex)
        if table is None:
            return None
        lookup_m = min(max(months, 60), 229)
        if lookup_m not in table.index:
            return None
        L, M, S = table.loc[lookup_m, ["l", "m", "s"]]
    z = (np.log(bmi / M) / S) if L == 0 else ((bmi / M) ** L - 1) / (L * S)
    return float(z)


def validate_sex_convention(convention: str) -> str:
    """Return the canonical sex-convention choice: 'auto', '01', or '12'."""
    choice = str(convention or "auto").strip().lower()
    aliases = {"0/1": "01", "m/f": "01", "1/2": "12", "nhanes": "12"}
    choice = aliases.get(choice, choice)
    if choice not in SEX_CONVENTION_CHOICES:
        raise ValueError(
            f"Unsupported sex_convention: {convention!r}. "
            "Use 'auto', '01' (0=male, 1=female), or '12' (1=male, 2=female)."
        )
    return choice


def detect_sex_convention(raw: pd.Series, col_name: str = "sex") -> str:
    """Infer 0/1 vs 1/2 from the column so the caller never has to ask.

    A `2` is impossible under 0/1, so it selects 1/2 unless a `0` is also present.
    A `0` is impossible under 1/2, so a mixed 0/2 column is treated as 0/1 and the
    2s degrade to missing rather than silently flipping the whole file. A column
    literally named `riagendr` is always 1/2.
    """
    source = str(col_name or "sex").strip().lower()
    if source == "riagendr":
        return "12"
    num = pd.to_numeric(raw, errors="coerce")
    has_zero = bool((num == 0).any())
    has_two = bool((num == 2).any())
    if has_two and not has_zero:
        return "12"
    return "01"


def resolve_sex_convention(
    convention: str, col_name: str = "sex", raw: pd.Series | None = None
) -> str:
    """Resolve 'auto' for a column and reject contradictory explicit declarations."""
    choice = validate_sex_convention(convention)
    source = str(col_name or "sex").strip().lower()
    if choice == "auto":
        return detect_sex_convention(raw if raw is not None else pd.Series(dtype=float), source)
    if choice == "01" and source == "riagendr":
        raise ValueError(
            "Column 'riagendr' is NHANES-coded (1=male, 2=female), which conflicts "
            "with sex_convention='01'. Omit sex_convention or set it to '12'."
        )
    return choice


def _parse_sex(raw: pd.Series, col_name: str = "sex", convention: str = "auto") -> pd.Series:
    """Parse sex per-row deterministically under the inferred or explicit convention."""
    resolved = resolve_sex_convention(convention, col_name, raw)
    num = pd.to_numeric(raw, errors="coerce")
    parsed = num.map(SEX_CONVENTIONS[resolved])
    non_num = num.isna() & raw.notna()
    if non_num.any():
        str_vals = raw[non_num].astype(str).str.strip().str.lower().map(_SEX_STRINGS)
        parsed = parsed.copy()
        parsed.loc[non_num] = str_vals
    return parsed.astype(float)


def _row_phrase(count: int) -> str:
    """Pluralise a row count for operator-facing warnings."""
    return f"{count} row has" if count == 1 else f"{count} rows have"


def _sex_warnings(
    raw: pd.Series,
    parsed: pd.Series,
    convention: str,
    col_name: str,
) -> list[str]:
    """Warn about invalid or ambiguous sex values without rejecting the upload."""
    text = raw.astype(str).str.strip().str.lower()
    missing = raw.isna() | text.isin(_SEX_NULL_TOKENS)
    invalid = (~missing) & parsed.isna()
    warnings: list[str] = []

    if invalid.any():
        examples = raw[invalid].astype(str).str.strip().drop_duplicates().head(3).tolist()
        shown = ", ".join(repr(value[:24]) for value in examples)
        label = "0=male / 1=female" if convention == "01" else "1=male / 2=female"
        warnings.append(
            f"{_row_phrase(int(invalid.sum()))} invalid sex under the detected {label} "
            f"convention (examples: {shown}); scored as 'Insufficient data'."
        )

    source = str(col_name or "sex").strip().lower()
    if source != "riagendr":
        if convention == "12":
            warnings.append("sex column auto-detected as 1=male / 2=female (NHANES coding).")
        else:
            num = pd.to_numeric(raw, errors="coerce")
            if (num == 1).any() and not (num == 0).any() and not (num == 2).any():
                warnings.append(
                    "sex column contains only 1s; interpreted as 1=female under the "
                    "canonical 0/1 convention. Rename the column to 'riagendr' if this "
                    "is NHANES 1/2 coding."
                )
    return warnings


def _apply_bounds(df: pd.DataFrame, col: str, warnings: list[str]) -> None:
    lo, hi = BOUNDS[col]
    s = df[col].replace([np.inf, -np.inf], np.nan)
    bad = s.notna() & ((s < lo) | (s > hi))
    if bad.any():
        warnings.append(
            f"{int(bad.sum())} rows had out-of-range '{col}' (valid {lo:g}-{hi:g}); "
            "treated as missing."
        )
        s = s.where(~bad, np.nan)
    df[col] = s


def _interpret_units(out: pd.DataFrame, warnings: list[str]) -> None:
    """Convert unambiguous non-canonical lab units before bounds validation.

    Only values that cannot be valid in the canonical unit are converted, so a
    plausible canonical value is never rewritten. Every conversion is warned about
    so the clinician can see exactly what was interpreted.
    """
    rules: list[tuple[str, float, Any, str, str, str | None]] = [
        ("hba1c", 20.0, lambda v: 0.09148 * v + 2.152, "mmol/mol", "%", "NGSP"),
        ("fpg", 30.0, lambda v: v * 18.018, "mmol/L", "mg/dL", None),
        ("total_chol", 20.0, lambda v: v * 38.67, "mmol/L", "mg/dL", None),
        ("hdl", 10.0, lambda v: v * 38.67, "mmol/L", "mg/dL", None),
        ("ldl", 10.0, lambda v: v * 38.67, "mmol/L", "mg/dL", None),
        ("triglycerides", 15.0, lambda v: v * 88.57, "mmol/L", "mg/dL", None),
    ]
    for col, upper, convert, from_unit, to_unit, note in rules:
        if col not in out:
            continue
        values = out[col]
        if col == "hba1c":
            # HbA1c in % is 3-20; IFCC mmol/mol values are above that range.
            mask = values.notna() & (values > upper)
        else:
            mask = values.notna() & (values > 0) & (values < upper)
        if not mask.any():
            continue
        count = int(mask.sum())
        out.loc[mask, col] = values[mask].map(convert)
        method = f" ({note})" if note else ""
        warnings.append(
            f"{count} {'row' if count == 1 else 'rows'} had '{col}' reported in "
            f"{from_unit}; interpreted and converted to {to_unit}{method}."
        )


def normalise(
    df: pd.DataFrame, *, sex_convention: str = "auto"
) -> tuple[pd.DataFrame, list[str]]:
    """Map aliases, coerce types, validate clinical bounds, derive BMI/WHtR."""
    warnings: list[str] = []
    cols = {c.strip().lower(): c for c in df.columns}
    out = pd.DataFrame(index=df.index)
    src_col: dict[str, str] = {}
    for canon, names in ALIASES.items():
        for n in names:
            if n in cols:
                out[canon] = df[cols[n]]
                src_col[canon] = n
                break
    if "age" not in out:
        raise ValueError(
            "Missing required column 'age'. Add age in years (0-120) and re-upload."
        )
    if "sex" not in out:
        raise ValueError(
            "Missing required column 'sex'. Add a sex column coded male/female, "
            "0/1 (0=male, 1=female), or 1/2 (1=male, 2=female); the encoding is "
            "detected automatically per file."
        )

    out["age"] = pd.to_numeric(out["age"], errors="coerce")
    _apply_bounds(out, "age", warnings)
    sex_source = src_col.get("sex", "sex")
    raw_sex = out["sex"].copy()
    resolved_sex = resolve_sex_convention(sex_convention, sex_source, raw_sex)
    parsed_sex = _parse_sex(raw_sex, sex_source, resolved_sex)
    warnings.extend(_sex_warnings(raw_sex, parsed_sex, resolved_sex, sex_source))
    out["sex"] = parsed_sex

    num_cols = [
        "bmi",
        "waist",
        "height_cm",
        "weight_kg",
        "whtr",
        "diastolic_bp",
        "sleep_hours",
        "income_ratio",
        "pack_years",
        "hba1c",
        "fpg",
        "total_chol",
        "hdl",
        "ldl",
        "triglycerides",
        "egfr",
        "missed_well_child_visits",
    ]
    for c in num_cols:
        if c in out:
            out[c] = pd.to_numeric(out[c], errors="coerce").astype(float)
    _interpret_units(out, warnings)
    for c in num_cols:
        if c in out:
            _apply_bounds(out, c, warnings)

    # Education is a numeric 1-5 SES feature. Coerce text (e.g. "college", "PhD",
    # or an empty string) to NaN with a warning instead of letting a raw string
    # reach the model pipeline and surface an sklearn "mean strategy" error.
    if "education" in out:
        edu_raw = out["education"]
        edu_num = pd.to_numeric(edu_raw, errors="coerce")
        bad_edu = edu_raw.notna() & edu_num.isna()
        if bad_edu.any():
            examples = edu_raw[bad_edu].astype(str).str.strip().drop_duplicates().head(3).tolist()
            shown = ", ".join(repr(v[:24]) for v in examples)
            warnings.append(
                f"{_row_phrase(int(bad_edu.sum()))} non-numeric education ({shown}); "
                "treated as missing (mean-imputed)."
            )
        out["education"] = edu_num

    bool_cols = [
        "family_hx_diabetes",
        "family_hx_cvd",
        "diagnosed_htn",
        "high_chol",
        "cvd_history",
        "ckd",
        "smoker",
        "pregnant",
        "glucose_test_3y",
        "chol_test_5y",
        "colorectal_screen_10y",
        "mammogram_2y",
        "cervical_screen_3y",
        "healthcare_visit_12m",
        "diagnosed_diabetes",
        "borderline_diabetes",
        "thalassemia_carrier",
        "developmental_delay_flag",
    ]
    for c in bool_cols:
        if c in out:
            out[c] = out[c].astype(str).str.strip().str.lower().map(BOOL).astype(float)

    # Per-row BMI backfill where height_cm and weight_kg are valid
    if "bmi" not in out:
        out["bmi"] = np.nan
    if {"height_cm", "weight_kg"} <= set(out.columns):
        can_bmi = (
            out["bmi"].isna()
            & out["height_cm"].notna()
            & out["weight_kg"].notna()
            & (out["height_cm"] > 0)
        )
        if can_bmi.any():
            out.loc[can_bmi, "bmi"] = (
                out.loc[can_bmi, "weight_kg"] / (out.loc[can_bmi, "height_cm"] / 100.0) ** 2
            )
            _apply_bounds(out, "bmi", warnings)

    # Direct WHtR calculation where waist and height_cm are valid
    if "whtr" not in out:
        out["whtr"] = np.nan
    if {"waist", "height_cm"} <= set(out.columns):
        can_whtr = (
            out["whtr"].isna()
            & out["waist"].notna()
            & out["height_cm"].notna()
            & (out["height_cm"] > 0)
        )
        if can_whtr.any():
            out.loc[can_whtr, "whtr"] = out.loc[can_whtr, "waist"] / out.loc[can_whtr, "height_cm"]
            _apply_bounds(out, "whtr", warnings)

    if len(out) > 0 and out["age"].isna().any():
        warnings.append(
            f"{_row_phrase(int(out['age'].isna().sum()))} missing/invalid age; "
            "flagged as 'Insufficient data'."
        )
    if len(out) > 0 and out["sex"].isna().any():
        warnings.append(
            f"{_row_phrase(int(out['sex'].isna().sum()))} missing sex; "
            "scored as 'Insufficient data'."
        )

    for c in [
        *FEATURES,
        "bmi",
        "waist",
        "height_cm",
        "weight_kg",
        "diastolic_bp",
        "high_chol",
        "cvd_history",
        "ckd",
        "smoker",
        "pregnant",
        "pack_years",
        "sleep_hours",
        "glucose_test_3y",
        "chol_test_5y",
        "colorectal_screen_10y",
        "mammogram_2y",
        "cervical_screen_3y",
        "hba1c",
        "fpg",
        "total_chol",
        "hdl",
        "ldl",
        "triglycerides",
        "egfr",
        "missed_well_child_visits",
        "developmental_delay_flag",
        "thalassemia_carrier",
        "diagnosed_diabetes",
        "borderline_diabetes",
    ]:
        if c not in out:
            out[c] = np.nan

    # Normalize genomic & immunisation text/boolean inputs
    if "prs_cardiometabolic" in out:
        prs_str = out["prs_cardiometabolic"].astype(str).str.strip().str.lower()
        prs_num = pd.to_numeric(out["prs_cardiometabolic"], errors="coerce")
        out["prs_high"] = np.where(
            prs_str.isin(["high", "very high", "elevated"]) | (prs_num >= 0.80),
            1.0,
            np.where(prs_str.isin(["low", "medium", "moderate", "normal"]), 0.0, np.nan),
        )
    else:
        out["prs_high"] = np.nan

    if "g6pd_status" in out:
        g6 = out["g6pd_status"].astype(str).str.strip().str.lower()
        out["g6pd_deficient"] = np.where(
            g6.isin(["deficient", "yes", "true", "1", "1.0", "positive"]),
            1.0,
            np.where(g6.isin(["normal", "no", "false", "0", "0.0", "negative"]), 0.0, np.nan),
        )
    else:
        out["g6pd_deficient"] = np.nan

    if "immunization_status" in out:
        imm = out["immunization_status"].astype(str).str.strip().str.lower()
        out["immunization_overdue"] = np.where(
            imm.isin(["overdue", "incomplete", "missed", "yes", "true", "1", "1.0"]),
            1.0,
            np.where(
                imm.isin(["up_to_date", "up-to-date", "complete", "no", "false", "0"]),
                0.0,
                np.nan,
            ),
        )
    else:
        out["immunization_overdue"] = np.nan

    # Sync ML feature name `current_smoker` with `smoker`
    out["current_smoker"] = out["current_smoker"].where(
        out["current_smoker"].notna(), out["smoker"]
    )
    out["smoker"] = out["current_smoker"]

    if "id" not in out:
        out["id"] = np.arange(1, len(out) + 1)

    if len(out) > 0:
        not_supplied = [
            c
            for c in FEATURES
            if out[c].isna().all()
            and not (c == "whtr" and (out["waist"].notna().any() or out["bmi"].notna().any()))
        ]
        if not_supplied:
            warnings.append(
                "Model features not supplied (no effect on ranking): " + ", ".join(not_supplied)
            )
    return out, warnings


def _apply_linear(row: pd.Series, spec: dict, sex_fallback: float = 0.51) -> float:
    val = spec["intercept"]
    for f, coef in zip(spec["features"], spec["coef"]):
        v = sex_fallback if (f == "sex" and pd.isna(row[f])) else float(row[f])
        val += coef * v
    return float(val)


def _derive_adiposity(
    df: pd.DataFrame,
    imputers: dict,
    sex_fallback: float = 0.51,
) -> tuple[pd.Series, pd.Series]:
    """Conditionally derive missing WHtR / waist from available anthropometrics."""
    whtr = df["whtr"].copy()
    waist_est = df["waist"].copy()
    for idx in df.index:
        r = df.loc[idx]
        if pd.isna(r["age"]):
            continue
        if pd.isna(whtr.loc[idx]):
            if pd.notna(r["waist"]) and pd.notna(r["bmi"]):
                val = _apply_linear(r, imputers["whtr_from_waist_bmi"], sex_fallback)
                whtr.loc[idx] = float(np.clip(val, 0.30, 1.00))
            elif pd.notna(r["waist"]):
                val = _apply_linear(r, imputers["whtr_from_waist"], sex_fallback)
                whtr.loc[idx] = float(np.clip(val, 0.30, 1.00))
            elif pd.notna(r["bmi"]):
                val = _apply_linear(r, imputers["whtr_from_bmi"], sex_fallback)
                whtr.loc[idx] = float(np.clip(val, 0.30, 1.00))
        if pd.isna(waist_est.loc[idx]) and pd.notna(r["bmi"]):
            val = _apply_linear(r, imputers["waist_from_bmi"], sex_fallback)
            waist_est.loc[idx] = float(np.clip(val, 45.0, 200.0))
    return whtr, waist_est


def _contribs(bundle: dict, X: pd.DataFrame) -> np.ndarray:
    """Per-feature log-odds contribution from the unified model."""
    m = bundle["explainer_model"]
    feats = bundle["features"]
    if bundle["kind"] == "logreg":
        imp, sc, lr = m.steps[0][1], m.steps[1][1], m.steps[2][1]
        z = sc.transform(imp.transform(X[feats]))
        c = z * lr.coef_[0]
        c[X[feats].isna().to_numpy()] = 0.0
        c[np.abs(c) < 1e-9] = 0.0
        return c
    return m.predict(X[feats], pred_contrib=True)[:, :-1]


def _format_reason(
    f: str,
    r: pd.Series,
    contrib_val: float,
    obs_whtr: bool,
    obs_waist: bool,
    obs_bmi: bool,
) -> str:
    sign = "raises" if contrib_val > 0 else "lowers"
    if f == "whtr":
        if obs_whtr:
            return f"Central adiposity (WHtR {r['whtr']:.2f}) {sign} risk"
        if obs_waist and obs_bmi:
            return (
                f"Central adiposity (waist {r['waist']:.0f} cm, BMI {r['bmi']:.1f}) {sign} risk"
            )
        if obs_waist:
            return f"Waist circumference ({r['waist']:.0f} cm) {sign} risk"
        if obs_bmi:
            return f"BMI ({r['bmi']:.1f}) {sign} risk"
    v = r[f]
    if f == "sex":
        shown = "Female" if v == 1 else "Male"
    elif f in ("age", "bmi", "diastolic_bp", "sleep_hours", "income_ratio"):
        shown = f"{v:.1f}".rstrip("0").rstrip(".")
    else:
        shown = "Yes" if v == 1 else "No"
    return f"{LABELS[f]}: {shown} {sign} risk"


def _has_metabolic_triad(r: pd.Series, waist_est: float) -> bool:
    """Age-independent triad: central obesity + elevated BP + family/prediabetes history."""
    waist_cutoff = 88.0 if r["sex"] == 1.0 else 102.0 if r["sex"] == 0.0 else 95.0
    central_obesity = (
        (pd.notna(r["bmi"]) and r["bmi"] >= 30.0)
        or (pd.notna(r["whtr"]) and r["whtr"] >= 0.58)
        or (pd.notna(waist_est) and waist_est >= waist_cutoff)
    )
    elevated_bp = (
        r["diagnosed_htn"] == 1.0
        or (pd.notna(r.get("systolic_bp")) and r.get("systolic_bp") >= 130.0)
        or (pd.notna(r["diastolic_bp"]) and r["diastolic_bp"] >= 80.0)
    )
    predisposition = r["family_hx_diabetes"] == 1.0 or r["borderline_diabetes"] == 1.0
    return bool(central_obesity and elevated_bp and predisposition)


def _tier_and_pathway(
    p_dm: float,
    p_dys: float,
    due: bool,
    overdue: bool,
    borderline: bool,
    triad: bool,
) -> tuple[str, str, str]:
    """Age-monotonic tiering & pathway mapping (no age-threshold cliffs)."""
    if p_dm >= 0.09 or ((p_dm >= 0.04 or p_dys >= 0.80) and triad):
        return (
            "High",
            "Accelerated adult comprehensive screening - metabolic track "
            "(HbA1c + fasting glucose, lipids, BP)",
            "Within 30 days",
        )
    if p_dm >= 0.045 or triad or p_dys >= 0.88 or (borderline and overdue):
        return (
            "Elevated",
            "Adult comprehensive screening - cardiometabolic track",
            "Within 90 days",
        )
    if due and overdue:
        return (
            "Routine - overdue",
            "Adult comprehensive screening - standard track (guideline-due, no recent test)",
            "Within 6 months",
        )
    if due:
        return (
            "Routine",
            "Adult comprehensive screening - standard track",
            "At next routine cycle (12 months)",
        )
    return (
        "Low",
        "No accelerated action; age-appropriate routine recall",
        "Per routine recall",
    )


def _is_due(r: pd.Series, waist_est: float) -> bool:
    """ADA-aligned adult diabetes screening eligibility."""
    age = r["age"]
    if age >= 35.0:
        return True
    bmi_high = pd.notna(r["bmi"]) and r["bmi"] >= 25.0
    bmi_obese = pd.notna(r["bmi"]) and r["bmi"] >= 30.0
    bmi_fh = pd.notna(r["bmi"]) and r["bmi"] >= 23.0
    waist_cutoff = 88.0 if r["sex"] == 1.0 else 102.0 if r["sex"] == 0.0 else 95.0
    central_high = (pd.notna(waist_est) and waist_est >= waist_cutoff) or (
        pd.notna(r["whtr"]) and r["whtr"] >= 0.50
    )
    extra_rf = (
        r["family_hx_diabetes"] == 1.0
        or r["diagnosed_htn"] == 1.0
        or (pd.notna(r.get("systolic_bp")) and r.get("systolic_bp") >= 130.0)
        or (pd.notna(r["diastolic_bp"]) and r["diastolic_bp"] >= 80.0)
        or r["high_chol"] == 1.0
        or r["cvd_history"] == 1.0
        or r["borderline_diabetes"] == 1.0
        or bmi_obese
    )
    if (bmi_high or central_high) and extra_rf:
        return True
    if r["family_hx_diabetes"] == 1.0 and bmi_fh:
        return True
    return False


def _score_peds_row(base: dict, r: pd.Series, comp: float) -> dict:
    age = float(r["age"])
    z = bmi_zscore(r["sex"], age, r["bmi"])
    flags: list[str] = []
    reasons: list[str] = []
    tier = "Routine"
    pathway = "Well-Child Visit - standard schedule"
    timing = "Per national schedule"
    if z is not None:
        std = "WHO 2006 (0-5y)" if age < 5.0 else "WHO 2007 (5-19y)"
        reasons.append(f"BMI-for-age z-score {z:+.1f} ({std})")
        if age < 5.0:
            if z > 3.0:
                tier = "High"
                pathway = "Well-Child Visit - paediatric weight and metabolic review"
                timing = "Within 30 days"
                flags.append("Early-childhood obesity range (z>+3)")
            elif z > 2.0:
                tier = "Elevated"
                pathway = "Well-Child Visit - growth and nutrition review"
                timing = "Within 90 days"
                flags.append("Early-childhood overweight range (z>+2)")
            elif z > 1.0:
                flags.append("Risk of overweight (z>+1)")
            elif z < -2.0:
                tier = "Elevated"
                pathway = "Well-Child Visit - growth faltering review"
                timing = "Within 90 days"
                flags.append("Wasting / thinness range (z<-2)")
        else:
            if z > 2.0:
                tier = "High"
                pathway = "Well-Child Visit - paediatric weight and metabolic review"
                timing = "Within 30 days"
                flags.append("Obesity range (z>+2)")
            elif z > 1.0:
                tier = "Elevated"
                pathway = "Well-Child Visit - growth and nutrition review"
                timing = "Within 90 days"
                flags.append("Overweight range (z>+1)")
            elif z < -2.0:
                tier = "Elevated"
                pathway = "Well-Child Visit - growth faltering review"
                timing = "Within 90 days"
                flags.append("Thinness range (z<-2)")
    else:
        reasons.append(
            "No growth z-score available (BMI or sex missing): rule-based Well-Child schedule only"
        )

    ped_tracks, ped_flags, min_tier = evaluate_peds_genomic_and_wcv_rules(r)
    for pf in ped_flags:
        if pf not in flags:
            flags.append(pf)
    if min_tier == "High" and tier != "High":
        tier = "High"
        pathway = "Well-Child Visit - priority developmental & paediatric review"
        timing = "Within 30 days"
    elif min_tier == "Elevated" and tier == "Routine":
        tier = "Elevated"
        pathway = "Well-Child Visit - catch-up preventive & immunisation review"
        timing = "Within 90 days"

    return {
        **base,
        "population": "child/adolescent",
        "tier": tier,
        "pathway": pathway,
        "timing": timing,
        "risk_pct": None,
        "dysglycaemia_pct": None,
        "screening_tracks": ["Paediatric growth & preventive well-child review", *ped_tracks],
        "confidence": "Medium" if z is not None else "Low",
        "completeness": round(comp, 2),
        "reasons": reasons,
        "flags": flags,
        "method": "WHO BMI-for-age growth standard + Well-Child & genomic rules (<20y)",
    }


def _suppressed_values(
    df: pd.DataFrame,
    adult_elig: pd.Series,
    segs: list[dict],
    col: str,
) -> set[str]:
    """Identify segment labels requiring row-level redaction.

    Only primary small cells are redacted at row level. Complementary suppression is
    an aggregate disclosure control: the complement can remain visible in the row the
    clinician uploaded without revealing the small cell's exact count.
    """
    suppressed = {
        s["segment"]
        for s in segs
        if s["dimension"] == col
        and s["suppressed"]
        and s["n"] != "suppressed (complementary)"
    }
    if col not in df:
        return suppressed
    for mask in (pd.Series(True, index=df.index), adult_elig):
        vals = df.loc[mask, col].dropna().astype(str)
        if not vals.empty:
            counts = vals.value_counts()
            suppressed.update(counts[counts < SMALL_CELL].index.tolist())
    return suppressed


def _segments(rows: list[dict], raw_districts: pd.Series, raw_languages: pd.Series) -> list[dict]:
    """Segment audit with primary AND complementary small-cell suppression."""
    adult_idx = [
        i
        for i, r in enumerate(rows)
        if r["population"] == "adult" and r["tier"] != "Excluded"
    ]
    if not adult_idx:
        return []
    df = pd.DataFrame([rows[i] for i in adult_idx])
    df["district"] = raw_districts.iloc[adult_idx].to_numpy()
    df["language"] = raw_languages.iloc[adult_idx].to_numpy()
    df["age_band"] = pd.cut(df["age"], [19, 39, 59, 200], labels=["20-39", "40-59", "60+"])

    out: list[dict] = []
    for col in ("age_band", "district", "language"):
        if col not in df or df[col].isna().all():
            continue
        groups = [(str(k), g) for k, g in df.groupby(col, observed=True) if len(g) > 0]
        small = [k for k, g in groups if len(g) < SMALL_CELL]
        comp_target = None
        if len(small) == 1:
            large = [(k, len(g)) for k, g in groups if len(g) >= SMALL_CELL]
            if large:
                comp_target = min(large, key=lambda x: x[1])[0]

        for key, g in groups:
            n = len(g)
            if n < SMALL_CELL:
                out.append(
                    {"dimension": col, "segment": key, "n": f"<{SMALL_CELL}", "suppressed": True}
                )
            elif key == comp_target:
                out.append(
                    {
                        "dimension": col,
                        "segment": key,
                        "n": "suppressed (complementary)",
                        "suppressed": True,
                    }
                )
            else:
                out.append(
                    {
                        "dimension": col,
                        "segment": key,
                        "n": n,
                        "suppressed": False,
                        "flagged_pct": round(
                            float(
                                100
                                * g["tier"]
                                .isin(["Urgent Clinical Review", "High", "Elevated"])
                                .mean()
                            ),
                            1,
                        ),
                        "mean_risk_pct": round(float(g["risk_pct"].mean()), 1),
                    }
                )
    return out


def _preventive_screenings(
    r: pd.Series,
    age: float,
    p_htn: float | None,
    p_lip: float | None,
    p_ckd: float | None,
) -> tuple[list[str], list[str], bool, set[str]]:
    """Evaluate migrated ADA/USPSTF/KDIGO preventive rules via the versioned rules pack."""
    tracks, flags, rule_ids, escalate = evaluate_preventive_rules(r, age, p_htn, p_lip, p_ckd)
    return tracks, flags, escalate, set(rule_ids)


def score(df_raw: pd.DataFrame, *, sex_convention: str = "auto") -> dict:
    """Validate, apply rules + ML risk scoring, explain, and audit cohort."""
    df, warnings = normalise(df_raw, sex_convention=sex_convention)
    n = len(df)
    if n == 0:
        return {
            "summary": {
                "rows": 0,
                "adults_screenable": 0,
                "children_adolescents": 0,
                "urgent": 0,
                "high": 0,
                "elevated": 0,
                "missed_by_age_rules": 0,
                "expected_undiagnosed_diabetes_cases": 0.0,
                "observations_captured": 0,
                "observations_unmapped": 0,
                "observations_unit_suspect": 0,
                "model_variant": "none",
                "segments": [],
                "disclaimer": (
                    "Population prioritisation, not individual diagnosis. "
                    "Requires clinician sign-off. Individuals may decline."
                ),
            },
            "warnings": warnings,
            "results": [],
        }

    claimed_cols = {a.lower() for vals in ALIASES.values() for a in vals}
    row_observations = capture_wide_dataframe(
        df_raw,
        claimed_columns=claimed_cols,
        ages=df["age"],
        sexes=df["sex"],
        patient_ids=df["id"],
    )
    stub_reasoner = StubReasoner()

    # Preserve observed flags before conditional anthropometric imputation
    obs_whtr = df["whtr"].notna()
    obs_waist = df["waist"].notna()
    obs_bmi = df["bmi"].notna()
    obs_adiposity = obs_whtr | obs_waist | obs_bmi

    b_full_dm = _bundle("full", "undiagnosed_dm")
    b_full_dys = _bundle("full", "dysglycaemia")
    b_nf_dm = _bundle("nofamily", "undiagnosed_dm")
    b_nf_dys = _bundle("nofamily", "dysglycaemia")
    b_full_htn = _bundle("full", "undiagnosed_htn")
    b_nf_htn = _bundle("nofamily", "undiagnosed_htn")
    b_full_lip = _bundle("full", "undiagnosed_dyslipidaemia")
    b_nf_lip = _bundle("nofamily", "undiagnosed_dyslipidaemia")
    b_full_ckd = _bundle("full", "ckd_risk")
    b_nf_ckd = _bundle("nofamily", "ckd_risk")

    sex_mean = float(b_full_dm.get("train_means", {}).get("sex", 0.51))
    imputers = b_full_dm["anthro_imputers"]
    df["whtr"], waist_est = _derive_adiposity(df, imputers, sex_mean)

    raw_districts = (
        df["district"].copy() if "district" in df else pd.Series(None, index=df.index)
    )
    raw_languages = (
        df["language"].copy() if "language" in df else pd.Series(None, index=df.index)
    )

    peds = df["age"].notna() & (df["age"] < 20.0) & df["sex"].notna()
    pregnant = df["pregnant"].fillna(0.0) == 1.0
    preg_male = pregnant & (df["sex"] == 0.0)
    if preg_male.any():
        warnings.append(
            f"{int(preg_male.sum())} rows had pregnant=yes with male sex; pregnancy flag ignored."
        )
    valid_pregnant = pregnant & (~preg_male)
    known_dm = df["diagnosed_diabetes"].fillna(0.0) == 1.0
    borderline_dm = df["borderline_diabetes"].fillna(0.0) == 1.0
    known_htn = df["diagnosed_htn"].fillna(0.0) == 1.0
    known_chol = df["high_chol"].fillna(0.0) == 1.0
    known_ckd = df["ckd"].fillna(0.0) == 1.0

    adult_stream = df["age"].notna() & (df["age"] >= 20.0) & df["sex"].notna() & (~valid_pregnant)
    adult_elig = adult_stream & (~known_dm) & (~borderline_dm)
    has_fh = df["family_hx_diabetes"].notna()

    # Batch-invariant per-row variant predictions (full vs nofamily) across all 5 ML targets
    p_dm = np.zeros(n, dtype=float)
    p_dys = np.zeros(n, dtype=float)
    p_htn = np.full(n, np.nan, dtype=float)
    p_lip = np.full(n, np.nan, dtype=float)
    p_ckd = np.full(n, np.nan, dtype=float)
    row_contribs: list[tuple[list[str], np.ndarray]] = [([], np.array([]))] * n
    # Per-target contributions so "Why Flagged" can explain the model that
    # actually drove the tier, not always the diabetes model.
    row_contribs_by_target: dict[str, list[tuple[list[str], np.ndarray]]] = {
        t: [([], np.array([]))] * n for t in TARGETS
    }
    variants_used: set[str] = set()

    for mask, b_dm, b_dys, vname in (
        (adult_elig & has_fh, b_full_dm, b_full_dys, "full"),
        (adult_elig & (~has_fh), b_nf_dm, b_nf_dys, "nofamily"),
    ):
        idx = np.flatnonzero(mask.to_numpy())
        if len(idx) == 0:
            continue
        variants_used.add(vname)
        sub = df.iloc[idx]
        p_dm[idx] = b_dm["model"].predict_proba(sub[b_dm["features"]])[:, 1]
        p_dys[idx] = b_dys["model"].predict_proba(sub[b_dys["features"]])[:, 1]
        c_mat = _contribs(b_dm, sub)
        c_mat_dys = _contribs(b_dys, sub)
        for k, row_i in enumerate(idx):
            row_contribs[row_i] = (b_dm["features"], c_mat[k])
            row_contribs_by_target["undiagnosed_dm"][row_i] = (b_dm["features"], c_mat[k])
            row_contribs_by_target["dysglycaemia"][row_i] = (b_dys["features"], c_mat_dys[k])

    for target, mask_base, out_arr, b_full_t, b_nf_t in (
        ("undiagnosed_htn", adult_stream & (~known_htn), p_htn, b_full_htn, b_nf_htn),
        ("undiagnosed_dyslipidaemia", adult_stream & (~known_chol), p_lip, b_full_lip, b_nf_lip),
        ("ckd_risk", adult_stream & (~known_ckd), p_ckd, b_full_ckd, b_nf_ckd),
    ):
        for fh_flag, bundle in ((True, b_full_t), (False, b_nf_t)):
            m = mask_base & (has_fh if fh_flag else (~has_fh))
            idx = np.flatnonzero(m.to_numpy())
            if len(idx) > 0:
                sub = df.iloc[idx]
                out_arr[idx] = bundle["model"].predict_proba(sub[bundle["features"]])[:, 1]
                c_mat_t = _contribs(bundle, sub)
                for k, row_i in enumerate(idx):
                    row_contribs_by_target[target][row_i] = (
                        bundle["features"],
                        c_mat_t[k],
                    )

    # Completeness computed over original supplied core clinical fields
    obs_matrix = pd.DataFrame({f: df[f].notna() for f in FEATURES}, index=df.index)
    obs_matrix["whtr"] = obs_adiposity
    completeness = obs_matrix.mean(axis=1)

    rows: list[dict] = []
    for i in range(n):
        r = df.iloc[i]
        rid = r["id"]
        age = r["age"]
        base = {
            "id": rid.item() if hasattr(rid, "item") else rid,
            "age": None if pd.isna(age) else float(age),
            "district": (
                None if pd.isna(raw_districts.iloc[i]) else str(raw_districts.iloc[i])
            ),
            "language": (
                None if pd.isna(raw_languages.iloc[i]) else str(raw_languages.iloc[i])
            ),
        }
        comp = float(completeness.iloc[i])
        sex_val = r["sex"]
        if pd.isna(age) or pd.isna(sex_val):
            miss_reasons = []
            if pd.isna(age):
                miss_reasons.append("Age missing or invalid")
            if pd.isna(sex_val):
                miss_reasons.append("Sex missing or invalid")
            rows.append(
                {
                    **base,
                    "population": "unknown",
                    "stream": "insufficient_data",
                    "tier": "Insufficient data",
                    "pathway": "Data correction needed",
                    "timing": "-",
                    "risk_pct": None,
                    "dysglycaemia_pct": None,
                    "htn_risk_pct": None,
                    "dyslipidaemia_risk_pct": None,
                    "ckd_risk_pct": None,
                    "screening_tracks": [],
                    "confidence": "Low",
                    "completeness": round(comp, 2),
                    "reasons": miss_reasons,
                    "flags": [],
                }
            )
            continue

        if valid_pregnant.iloc[i]:
            bp_high = (
                (pd.notna(r.get("systolic_bp")) and r.get("systolic_bp") >= 130.0)
                or (pd.notna(r["diastolic_bp"]) and r["diastolic_bp"] >= 80.0)
            )
            vital_urgent, _vital_high = evaluate_vital_rules(r, pregnant=True)
            p_flags = ["Prenatal stream - non-pregnant adult ML models withheld"]
            if bp_high:
                p_flags.append("Elevated BP in pregnancy - obstetrics BP evaluation")
            for alert in vital_urgent:
                if alert["action"] not in p_flags:
                    p_flags.append(alert["action"])
            if vital_urgent:
                tier_preg = "Urgent Clinical Review"
                pathway_preg = "Urgent obstetric review — severe-range BP in pregnancy"
                timing_preg = "Immediate"
            else:
                tier_preg = "Elevated" if bp_high else "Routine"
                pathway_preg = "Prenatal cardiometabolic & GDM screening track"
                timing_preg = "Within 30 days" if bp_high else "Per prenatal schedule"
            rows.append(
                {
                    **base,
                    "population": "child/adolescent" if age < 20.0 else "adult",
                    "stream": "prenatal",
                    "tier": tier_preg,
                    "pathway": pathway_preg,
                    "timing": timing_preg,
                    "risk_pct": None,
                    "dysglycaemia_pct": None,
                    "htn_risk_pct": None,
                    "dyslipidaemia_risk_pct": None,
                    "ckd_risk_pct": None,
                    "screening_tracks": ["Prenatal BP & gestational diabetes screening"],
                    "confidence": "High",
                    "completeness": round(comp, 2),
                    "reasons": ["Routed to prenatal stream to avoid adult non-pregnant ML bias"],
                    "flags": p_flags,
                    "_vital_alerts": vital_urgent,
                }
            )
            continue

        htn_prob = None if np.isnan(p_htn[i]) else float(p_htn[i])
        lip_prob = None if np.isnan(p_lip[i]) else float(p_lip[i])
        ckd_prob = None if np.isnan(p_ckd[i]) else float(p_ckd[i])

        # Exclude known diabetics in BOTH adults and children from DM ML,
        # while still attaching non-DM preventive screenings for adults.
        if known_dm.iloc[i]:
            is_ped = bool(peds.iloc[i])
            tracks_dm, flags_dm, _escalate_dm, _rules_dm = (
                ([], [], False, set())
                if is_ped
                else _preventive_screenings(r, float(age), htn_prob, lip_prob, ckd_prob)
            )
            vital_urgent, vital_high = (
                ([], []) if is_ped else evaluate_vital_rules(r)
            )
            for alert in vital_urgent + vital_high:
                if alert["action"] not in flags_dm:
                    flags_dm.append(alert["action"])
            if vital_urgent:
                tier_dm = "Urgent Clinical Review"
                pathway_dm = "Urgent clinical review — immediate clinician evaluation required"
                timing_dm = "Immediate"
            elif vital_high:
                tier_dm = "High"
                pathway_dm = "Existing diabetes — accelerated BP review and treatment"
                timing_dm = "Within 30 days"
            else:
                tier_dm = "Excluded"
                pathway_dm = (
                    "Existing diabetes - paediatric endocrine management pathway"
                    if is_ped
                    else "Existing diabetes - routine management pathway"
                )
                timing_dm = "-"
            rows.append(
                {
                    **base,
                    "population": "child/adolescent" if is_ped else "adult",
                    "stream": "paediatric" if is_ped else "adult_preventive",
                    "tier": tier_dm,
                    "pathway": pathway_dm,
                    "timing": timing_dm,
                    "risk_pct": None,
                    "dysglycaemia_pct": None,
                    "htn_risk_pct": None if htn_prob is None else round(100.0 * htn_prob, 1),
                    "dyslipidaemia_risk_pct": (
                        None if lip_prob is None else round(100.0 * lip_prob, 1)
                    ),
                    "ckd_risk_pct": None if ckd_prob is None else round(100.0 * ckd_prob, 1),
                    "screening_tracks": tracks_dm,
                    "confidence": "High",
                    "completeness": round(comp, 2),
                    "reasons": ["Known diabetes: not a diabetes screening candidate"],
                    "flags": flags_dm,
                    "_vital_alerts": vital_urgent + vital_high,
                }
            )
            continue

        if peds.iloc[i]:
            ped_row = _score_peds_row(base, r, comp)
            ped_row["stream"] = "paediatric"
            ped_row["htn_risk_pct"] = None
            ped_row["dyslipidaemia_risk_pct"] = None
            ped_row["ckd_risk_pct"] = None
            rows.append(ped_row)
            continue

        pm = float(p_dm[i])
        pd_val = float(p_dys[i])
        w_est_i = float(waist_est.iloc[i]) if pd.notna(waist_est.iloc[i]) else np.nan
        due = _is_due(r, w_est_i)
        overdue = r["glucose_test_3y"] == 0.0 or pd.isna(r["glucose_test_3y"])
        borderline = r["borderline_diabetes"] == 1.0
        triad = _has_metabolic_triad(r, w_est_i)
        tier, pathway, timing = _tier_and_pathway(pm, pd_val, due, overdue, borderline, triad)

        # Choose the model whose score actually drove the tier, so the
        # explanation matches the decision shown next to it.
        if tier == "High" and pm >= 0.09:
            driver = "undiagnosed_dm"
        elif tier == "High" and (pd_val >= 0.80 or (pd_val >= 0.045 and triad)):
            driver = "dysglycaemia"
        elif tier == "Elevated" and pd_val >= 0.88:
            driver = "dysglycaemia"
        elif tier == "Elevated" and pm >= 0.045:
            driver = "undiagnosed_dm"
        elif not np.isnan(p_lip[i]) and p_lip[i] >= 0.55:
            driver = "undiagnosed_dyslipidaemia"
        elif not np.isnan(p_htn[i]) and p_htn[i] >= 0.55:
            driver = "undiagnosed_htn"
        elif not np.isnan(p_ckd[i]) and p_ckd[i] >= 0.20:
            driver = "ckd_risk"
        else:
            driver = "undiagnosed_dm"

        feats, c_vec = row_contribs_by_target.get(driver, row_contribs)[i]
        if len(feats) == 0:
            feats, c_vec = row_contribs[i]
        observed_indices = []
        for j, f in enumerate(feats):
            is_obs = (
                bool(obs_adiposity.iloc[i]) and pd.notna(r["whtr"])
                if f == "whtr"
                else pd.notna(r[f])
            )
            if is_obs and abs(float(c_vec[j])) >= 1e-9:
                observed_indices.append(j)
        if tier in ("High", "Elevated", "Routine - overdue"):
            observed_indices.sort(
                key=lambda j: (0 if float(c_vec[j]) > 0 else 1, -abs(float(c_vec[j])))
            )
        else:
            observed_indices.sort(key=lambda j: -abs(float(c_vec[j])))
        reasons = [
            _format_reason(
                feats[j],
                r,
                float(c_vec[j]),
                bool(obs_whtr.iloc[i]),
                bool(obs_waist.iloc[i]),
                bool(obs_bmi.iloc[i]),
            )
            for j in observed_indices[:4]
        ]
        if triad and pm < 0.09:
            has_fh_i = r["family_hx_diabetes"] == 1.0
            has_bd_i = borderline
            if has_fh_i and has_bd_i:
                predisp = "family history + prior prediabetes"
            elif has_fh_i:
                predisp = "family history"
            else:
                predisp = "prior prediabetes"
            reasons = [
                f"Cardiometabolic syndrome triad (central obesity + elevated BP + {predisp}) "
                "raises priority",
                *reasons[:3],
            ]
        if not reasons:
            if borderline:
                reasons = [
                    "Prior borderline/prediabetes history: undiagnosed-DM ML withheld "
                    "(out-of-distribution); rule-based screening applied"
                ]
            else:
                reasons = ["Insufficient observed predictors for attribution"]

        flags: list[str] = []
        if preg_male.iloc[i]:
            flags.append("Data quality: pregnant=yes with male sex — pregnancy flag ignored")
        if (
            (pd.notna(r.get("systolic_bp")) and r.get("systolic_bp") >= 130.0)
            or (pd.notna(r["diastolic_bp"]) and r["diastolic_bp"] >= 80.0)
        ) and r["diagnosed_htn"] != 1.0:
            flags.append("Elevated BP without hypertension diagnosis - BP follow-up")
        if borderline:
            flags.append("Prior borderline/prediabetes history")
        if age < 40.0 and tier in ("High", "Elevated"):
            flags.append("Missed by age-40 screening rule (<40)")
        if overdue and (due or tier in ("High", "Elevated")):
            flags.append("Guideline-due with no glucose test in 3 years")

        extra_tracks, extra_flags, escalate_multi, extra_rule_ids = _preventive_screenings(
            r, float(age), htn_prob, lip_prob, ckd_prob
        )
        for ef in extra_flags:
            if ef not in flags:
                flags.append(ef)
        if "DM-LAB-01" in extra_rule_ids and tier not in (
            "Urgent Clinical Review",
            "High",
        ):
            tier = "High"
            pathway = (
                "Accelerated adult comprehensive screening - metabolic track "
                "(HbA1c + fasting glucose, lipids, BP)"
            )
            timing = "Within 30 days"
        elif escalate_multi and tier in ("Routine", "Routine - overdue", "Low"):
            tier = "Elevated"
            pathway = "Multi-domain preventive screening - cardiometabolic & renal track"
            timing = "Within 90 days"

        vital_urgent, vital_high = evaluate_vital_rules(r)
        for alert in vital_urgent + vital_high:
            if alert["action"] not in flags:
                flags.append(alert["action"])
        if vital_urgent:
            tier = "Urgent Clinical Review"
            pathway = "Urgent clinical review — immediate clinician evaluation required"
            timing = "Immediate"
        elif vital_high and tier not in ("Urgent Clinical Review", "High"):
            tier = "High"
            pathway = (
                "Accelerated adult comprehensive screening - metabolic track "
                "(HbA1c + fasting glucose, lipids, BP)"
            )
            timing = "Within 30 days"

        conf = "High" if comp >= 0.85 else "Medium" if comp >= 0.65 else "Low"
        if conf == "Low":
            reasons.append("Low data completeness - verify missing fields before acting")

        vlabel = "full" if has_fh.iloc[i] else "nofamily"
        b_used = b_full_dm if has_fh.iloc[i] else b_nf_dm
        rows.append(
            {
                **base,
                "population": "adult",
                "stream": "adult_preventive",
                "tier": tier,
                "pathway": pathway,
                "timing": timing,
                "risk_pct": None if borderline else round(100.0 * pm, 1),
                "dysglycaemia_pct": None if borderline else round(100.0 * pd_val, 1),
                "htn_risk_pct": None if htn_prob is None else round(100.0 * htn_prob, 1),
                "dyslipidaemia_risk_pct": None if lip_prob is None else round(100.0 * lip_prob, 1),
                "ckd_risk_pct": None if ckd_prob is None else round(100.0 * ckd_prob, 1),
                "screening_tracks": extra_tracks,
                "confidence": conf,
                "completeness": round(comp, 2),
                "reasons": reasons,
                "flags": flags,
                "guideline_due": bool(due or tier in ("High", "Elevated") or extra_tracks),
                "method": (
                    f"Multi-target survey-weighted {b_used['kind']} ({vlabel}) "
                    "+ ADA/USPSTF preventive rules"
                ),
                "_vital_alerts": vital_urgent + vital_high,
            }
        )

    for i, row in enumerate(rows):
        obs_list = row_observations[i]
        age_i = row["age"]
        vital_alerts = row.pop("_vital_alerts", [])
        urgent_alerts, elev_obs_alerts = evaluate_observation_rules(obs_list, age=age_i)
        urgent_alerts = [
            alert for alert in vital_alerts if alert.get("severity") == "urgent"
        ] + urgent_alerts
        bounded_obs = [
            o.to_dict()
            for o in obs_list
            if o.quality != "ok" or o.severity_hint in ("abnormal", "critical")
        ]
        row["observations"] = bounded_obs
        row["urgent_alerts"] = urgent_alerts
        row["reasoning"] = stub_reasoner.explain(
            str(row["id"]), obs_list, [a["rule_id"] for a in urgent_alerts + elev_obs_alerts]
        ).to_dict()

        for al in elev_obs_alerts:
            if al["action"] not in row["flags"]:
                row["flags"].append(al["action"])
            if row["tier"] in ("Routine", "Routine - overdue", "Low"):
                row["tier"] = "Elevated"
                row["pathway"] = "Elevated cardiovascular marker — preventive cardiology review"
                row["timing"] = "Within 90 days"

        # Escalation invariant: Urgent Clinical Review overrides any non-urgent or DM-Excluded tier
        if urgent_alerts:
            row["tier"] = "Urgent Clinical Review"
            # Keep a stream-specific urgent pathway (e.g. obstetric review) when set.
            if not str(row.get("pathway", "")).startswith("Urgent"):
                row["pathway"] = (
                    "Urgent clinical review — immediate clinician evaluation required"
                )
            row["timing"] = "Immediate"
            row["requires_signoff"] = True
            for al in urgent_alerts:
                if al["action"] not in row["flags"]:
                    row["flags"].append(al["action"])
        else:
            row["requires_signoff"] = bool(
                row["tier"] in ("Urgent Clinical Review", "High", "Elevated", "Routine - overdue")
            )

    adults = [r for r in rows if r["population"] == "adult" and r["tier"] != "Excluded"]
    n_urg = sum(r["tier"] == "Urgent Clinical Review" for r in rows)
    n_hi = sum(r["tier"] == "High" for r in rows)
    n_el = sum(r["tier"] == "Elevated" for r in rows)
    n_miss = sum("Missed by age-40 screening rule (<40)" in r["flags"] for r in adults)
    exp_cases = float(sum(r["risk_pct"] for r in adults if r["risk_pct"] is not None) / 100.0)
    if variants_used == {"full", "nofamily"}:
        variant_label = "per-row (full + nofamily)"
    elif variants_used:
        variant_label = next(iter(variants_used))
    else:
        variant_label = "none"

    segs = _segments(rows, raw_districts, raw_languages)
    supp_dist = _suppressed_values(df, adult_elig, segs, "district")
    supp_lang = _suppressed_values(df, adult_elig, segs, "language")
    for row in rows:
        raw_lang = row["language"]
        if row["district"] is not None and row["district"] in supp_dist:
            row["district"] = "<suppressed (<10)>"
        if row["language"] is not None and row["language"] in supp_lang:
            row["language"] = "<suppressed (<10)>"
        # Safety invariant: suppress automated outreach for Urgent Clinical Review
        # and for any row with an observation that was not clinically evaluated.
        unevaluated = any(
            o.get("quality") in ("unit_suspect", "out_of_plausible_range")
            for o in row.get("observations", [])
        )
        if row["tier"] == "Urgent Clinical Review":
            row.pop("outreach_preview", None)
        elif unevaluated:
            row.pop("outreach_preview", None)
            note = "Outreach withheld — confirm ambiguous lab unit before contact"
            if note not in row["flags"]:
                row["flags"].append(note)
        elif row["population"] in ("adult", "child/adolescent") and row["tier"] in (
            "High",
            "Elevated",
            "Routine - overdue",
        ):
            lang_for_msg = "EN" if raw_lang is None else str(raw_lang)
            row["outreach_preview"] = format_outreach_preview(
                str(row["id"]),
                row["pathway"],
                row["timing"],
                lang_for_msg,
                population=row["population"],
            )

    summary = {
        "rows": n,
        "adults_screenable": len(adults),
        "children_adolescents": int((peds & (~known_dm)).sum()),
        "urgent": n_urg,
        "high": n_hi,
        "elevated": n_el,
        "missed_by_age_rules": n_miss,
        "expected_undiagnosed_diabetes_cases": round(exp_cases, 1),
        "observations_captured": sum(len(x) for x in row_observations),
        "observations_unmapped": sum(
            o.quality == "unmapped" for x in row_observations for o in x
        ),
        "observations_unit_suspect": sum(
            o.quality == "unit_suspect" for x in row_observations for o in x
        ),
        "model_variant": variant_label,
        "segments": segs,
        "disclaimer": (
            "Population prioritisation, not individual diagnosis. "
            "Requires clinician sign-off. Individuals may decline."
        ),
    }
    suspect_n = int(summary["observations_unit_suspect"])
    if suspect_n:
        warnings.append(
            f"{suspect_n} result(s) were not checked because the unit was unclear or "
            "implausible. Confirm the unit before using this list; an urgent finding "
            "may be hidden in these rows."
        )
    return {"summary": summary, "warnings": warnings, "results": rows}
