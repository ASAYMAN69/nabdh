"""Build the adult screening-prioritisation cohort from raw NHANES XPT files.

Task A: among adults WITHOUT diagnosed or borderline diabetes, who has
undiagnosed dysglycaemia (HbA1c >= 5.7% or FPG >= 100 mg/dL) or undiagnosed
diabetes (HbA1c >= 6.5% or FPG >= 126 mg/dL)?

The label comes strictly from complete dual-assay laboratory measurements
(fasting subsample with both HbA1c and FPG), and laboratory / treatment
variables are never used as features (see data/DATASETS.md).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

RAW = Path(__file__).resolve().parents[2] / "data" / "raw"

# Canonical biological/epidemiological ML feature schema shared by training and inference
#
# Design notes:
# - systolic_bp is omitted: r=0.65 with diastolic_bp. When both are in the model,
#   systolic gets a small negative weight (over-correction artifact) while diastolic
#   carries the positive signal. Diastolic BP is the better independent predictor of
#   cardiometabolic events and is retained as the single BP measure.
# - age is excluded from the dyslipidaemia target (see TARGET_EXCLUDES): after
#   conditioning on high_chol==0 and controlling for WHtR, age has no independent
#   predictive signal for *undiagnosed* dyslipidaemia (partial r=0.002). Its
#   negative sign was a selection artifact, not a clinical finding.
# - bmi and current_smoker are excluded from the CKD target: BMI shows the obesity
#   paradox (lower BMI associated with worse CKD outcomes due to reverse causation),
#   and current_smoker is confounded by sick-quitter bias. Both are documented
#   limitations, not model errors.
FEATURES = [
    "age",
    "sex",
    "whtr",
    "bmi",
    "diastolic_bp",
    "family_hx_diabetes",
    "diagnosed_htn",
    "high_chol",
    "cvd_history",
    "current_smoker",
    "sleep_hours",
    "income_ratio",
    "education",
]

# Per-target feature exclusions to prevent target leakage or constant-gate columns
TARGET_EXCLUDES: dict[str, set[str]] = {
    "dysglycaemia": set(),
    "undiagnosed_dm": set(),
    "undiagnosed_htn": {"diastolic_bp", "diagnosed_htn"},
    "undiagnosed_dyslipidaemia": {"high_chol", "age"},
    "ckd_risk": {"bmi", "current_smoker"},
}

# Features whose higher value must raise predicted risk. Any fitted standardized
# coefficient pointing the other way is sign-constrained to zero at training and
# inference time (see nabdh.engine._apply_sign_constraints).
#
# education and income_ratio are intentionally excluded: both are protective
# (higher SES → lower cardiometabolic risk), so a negative coefficient is correct.
POSITIVE_SIGN_FEATURES = frozenset(
    {
        "age",
        "whtr",
        "diastolic_bp",
        "family_hx_diabetes",
        "diagnosed_htn",
        "high_chol",
        "cvd_history",
        "current_smoker",
    }
)

# Signs derived from the deployed model artifacts (standardized scale). Used by
# inference to clamp any negative main-effect coefficient to zero so a single
# correlated feature can never invert the clinically expected direction.
COEFFICIENT_SIGNS_FILE = Path(__file__).resolve().parents[2] / "models" / "coefficient_signs.json"

TARGETS = (
    "undiagnosed_dm",
    "dysglycaemia",
    "undiagnosed_htn",
    "undiagnosed_dyslipidaemia",
    "ckd_risk",
)


def features_for_target(target: str, include_family: bool = True) -> list[str]:
    """Return ordered ML feature names for a target and variant."""
    excl = set(TARGET_EXCLUDES.get(target, set()))
    if not include_family:
        excl.add("family_hx_diabetes")
    return [f for f in FEATURES if f not in excl]


def _read(folder: str, name: str, cols: list[str]) -> pd.DataFrame:
    path = RAW / folder / f"{name}.xpt"
    if not path.exists():
        return pd.DataFrame({"SEQN": []})
    df = pd.read_sas(path, format="xport", encoding="utf-8")
    keep = ["SEQN"] + [c for c in cols if c in df.columns]
    return df[keep]


def _yn(s: pd.Series) -> pd.Series:
    """Map NHANES binary codes: 1=yes -> 1.0, 2=no -> 0.0, 7/9/other -> NaN."""
    return s.map({1.0: 1.0, 2.0: 0.0})


def _read_cycle_raw(cycle: str) -> pd.DataFrame:
    p = cycle == "nhanes_2017_2020"
    pre = "P_" if p else ""
    suf = "" if p else "_L"

    def r(mod: str, cols: list[str]) -> pd.DataFrame:
        return _read(cycle, f"{pre}{mod}{suf}", cols)

    wt_mec = "WTMECPRP" if p else "WTMEC2YR"
    wt_faf = "WTSAFPRP" if p else "WTSAF2YR"
    df = r("DEMO", ["RIDAGEYR", "RIAGENDR", "INDFMPIR", "RIDEXPRG", "RIDRETH3", wt_mec])
    if "DMDEDUC2" not in df.columns:
        demo_full = r("DEMO", ["DMDEDUC2"])
        if "DMDEDUC2" in demo_full.columns:
            df = df.merge(demo_full[["SEQN", "DMDEDUC2"]], on="SEQN", how="left")
    for part in [
        r("BMX", ["BMXBMI", "BMXWAIST", "BMXHT", "BMXWT"]),
        r("BPXO", [f"BPXOSY{i}" for i in (1, 2, 3)] + [f"BPXODI{i}" for i in (1, 2, 3)]),
        r("GHB", ["LBXGH"]),
        r("GLU", ["LBXGLU", wt_faf]),
        r("DIQ", ["DIQ010", "DIQ160", "DIQ180"]),
        r("MCQ", ["MCQ300C", "MCQ300A", "MCQ160B", "MCQ160C", "MCQ160D", "MCQ160E", "MCQ160F"]),
        r("BPQ", ["BPQ020", "BPQ080"]),
        r("KIQ_U", ["KIQ022"]),
        r("SMQ", ["SMQ020", "SMQ040", "SMQ041"]),
        r("SLQ", ["SLD012"]),
        r("HUQ", ["HUQ030", "HUQ051"]),
        r("TCHOL", ["LBXTC"]),
        r("HDL", ["LBDHDD"]),
    ]:
        df = df.merge(part, on="SEQN", how="left")
    return df


def build_cycle(cycle: str) -> pd.DataFrame:
    """Build unified clinical + label table for an NHANES cycle."""
    p = cycle == "nhanes_2017_2020"
    wt_mec_col = "WTMECPRP" if p else "WTMEC2YR"
    wt_faf_col = "WTSAFPRP" if p else "WTSAF2YR"
    df = _read_cycle_raw(cycle)

    out = pd.DataFrame({"seqn": df["SEQN"]})
    out["age"] = df["RIDAGEYR"]
    out["sex"] = df["RIAGENDR"].map({1.0: 0.0, 2.0: 1.0})  # 0=male, 1=female
    out["height_cm"] = df.get("BMXHT")
    out["weight_kg"] = df.get("BMXWT")
    out["bmi"] = df.get("BMXBMI")
    out["waist"] = df.get("BMXWAIST")
    out["whtr"] = out["waist"] / out["height_cm"]

    sy = df[[c for c in df.columns if c.startswith("BPXOSY")]]
    di = df[[c for c in df.columns if c.startswith("BPXODI")]]
    out["systolic_bp"] = sy.mean(axis=1)
    out["diastolic_bp"] = di.mean(axis=1)

    out["family_hx_diabetes"] = _yn(df["MCQ300C"]) if "MCQ300C" in df else np.nan
    out["family_hx_cvd"] = _yn(df["MCQ300A"]) if "MCQ300A" in df else np.nan
    out["diagnosed_htn"] = _yn(df["BPQ020"])
    out["high_chol"] = _yn(df["BPQ080"])

    cvd_cols = [c for c in df.columns if c.startswith("MCQ160")]
    if cvd_cols:
        cvd = pd.concat([_yn(df[c]) for c in cvd_cols], axis=1)
        out["cvd_history"] = cvd.max(axis=1)
    else:
        out["cvd_history"] = np.nan

    out["ckd"] = _yn(df["KIQ022"]) if "KIQ022" in df else np.nan

    # Current smoking status (not lifetime 100-cigarette history)
    if "SMQ020" in df and "SMQ040" in df:
        cur_smk = np.where(
            df["SMQ020"] == 2.0,
            0.0,
            np.where(
                df["SMQ040"].isin([1.0, 2.0]),
                1.0,
                np.where(df["SMQ040"] == 3.0, 0.0, np.nan),
            ),
        )
    else:
        cur_smk = np.nan
    out["current_smoker"] = cur_smk
    out["smoker"] = out["current_smoker"]

    out["sleep_hours"] = df.get("SLD012")
    out["income_ratio"] = df["INDFMPIR"]

    # Education (DMDEDUC2): 1=<9, 2=9-11, 3=HS/GED, 4=some college, 5=college grad;
    # 7/9 = don't know/refused -> NaN. Higher = more education.
    if "DMDEDUC2" in df:
        out["education"] = df["DMDEDUC2"].map(
            lambda v: float(v) if v in (1.0, 2.0, 3.0, 4.0, 5.0) else np.nan
        )
    else:
        out["education"] = np.nan

    out["pack_years"] = np.nan
    out["glucose_test_3y"] = _yn(df["DIQ180"]) if "DIQ180" in df else np.nan
    out["routine_care_place"] = (
        df["HUQ030"].map({1.0: 1.0, 3.0: 1.0, 2.0: 0.0}) if "HUQ030" in df else np.nan
    )
    if "HUQ051" in df:
        out["healthcare_visit_12m"] = df["HUQ051"].map(
            lambda v: np.nan if pd.isna(v) or v > 20 else float(v >= 1)
        )
    else:
        out["healthcare_visit_12m"] = np.nan

    # Labels, exclusions, and survey metadata (never used as model features)
    diq010 = df["DIQ010"]
    out["_diq010"] = diq010
    out["_diagnosed_dm"] = (diq010 == 1.0).astype(float).where(diq010.isin([1.0, 2.0, 3.0]))
    diq160_yes = df["DIQ160"] == 1.0 if "DIQ160" in df else pd.Series(False, index=df.index)
    out["_borderline_dm"] = (
        ((diq010 == 3.0) | diq160_yes).astype(float).where(diq010.isin([1.0, 2.0, 3.0]))
    )
    out["_hba1c"] = df.get("LBXGH")
    out["_fpg"] = df.get("LBXGLU")
    out["_total_chol"] = df.get("LBXTC")
    out["_hdl"] = df.get("LBDHDD")
    out["_pregnant"] = df["RIDEXPRG"] == 1.0 if "RIDEXPRG" in df else False
    out["_race_eth"] = df.get("RIDRETH3")

    wt_faf = df[wt_faf_col] if wt_faf_col in df else pd.Series(np.nan, index=df.index)
    wt_mec = df[wt_mec_col] if wt_mec_col in df else pd.Series(np.nan, index=df.index)
    out["_wt_mec"] = wt_mec
    out["_sample_weight"] = wt_faf.where(wt_faf.notna() & (wt_faf > 0), wt_mec)
    return out


def build_task_a(cycle: str) -> pd.DataFrame:
    """Adults (>=20, non-pregnant, no diagnosed/borderline DM) with dual-assay labs."""
    d = build_cycle(cycle)
    d = d[
        (d["age"] >= 20)
        & (~d["_pregnant"])
        & (d["_diagnosed_dm"] == 0)
        & (d["_borderline_dm"] == 0)
        & (d["_diq010"] == 2.0)
        & d["_hba1c"].notna()
        & d["_fpg"].notna()
        & d["_sample_weight"].notna()
        & (d["_sample_weight"] > 0)
    ].copy()
    dysgly = (d["_hba1c"] >= 5.7) | (d["_fpg"] >= 100.0)
    undx_dm = (d["_hba1c"] >= 6.5) | (d["_fpg"] >= 126.0)
    d["y_dysglycaemia"] = dysgly.astype(int)
    d["y_undiagnosed_dm"] = undx_dm.astype(int)
    d["cycle"] = cycle
    return d.reset_index(drop=True)


def build_target_cohort(cycle: str, target: str) -> pd.DataFrame:
    """Build condition-gated adult cohort and binary outcome `y` for a preventive target."""
    if target in ("dysglycaemia", "undiagnosed_dm"):
        d = build_task_a(cycle)
        d["y"] = d[f"y_{target}"].astype(int)
        return d

    base = build_cycle(cycle)
    base = base[(base["age"] >= 20) & (~base["_pregnant"])].copy()

    if target == "undiagnosed_htn":
        elig = base[
            (base["diagnosed_htn"] == 0)
            & base["systolic_bp"].notna()
            & base["diastolic_bp"].notna()
            & base["_wt_mec"].notna()
            & (base["_wt_mec"] > 0)
        ].copy()
        elig["y"] = ((elig["systolic_bp"] >= 130.0) | (elig["diastolic_bp"] >= 80.0)).astype(int)
        elig["_sample_weight"] = elig["_wt_mec"]
    elif target == "undiagnosed_dyslipidaemia":
        elig = base[
            (base["high_chol"] == 0)
            & base["_total_chol"].notna()
            & base["_hdl"].notna()
            & base["_wt_mec"].notna()
            & (base["_wt_mec"] > 0)
        ].copy()
        low_hdl = ((elig["sex"] == 0.0) & (elig["_hdl"] < 40.0)) | (
            (elig["sex"] == 1.0) & (elig["_hdl"] < 50.0)
        )
        elig["y"] = ((elig["_total_chol"] >= 240.0) | low_hdl).astype(int)
        elig["_sample_weight"] = elig["_wt_mec"]
    elif target == "ckd_risk":
        elig = base[
            base["ckd"].isin([0.0, 1.0])
            & base["_wt_mec"].notna()
            & (base["_wt_mec"] > 0)
        ].copy()
        elig["y"] = (elig["ckd"] == 1.0).astype(int)
        elig["_sample_weight"] = elig["_wt_mec"]
    else:
        raise ValueError(f"Unknown preventive target: {target}")

    elig["cycle"] = cycle
    return elig.reset_index(drop=True)
