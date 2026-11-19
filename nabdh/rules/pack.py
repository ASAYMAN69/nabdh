"""Versioned deterministic clinical rules pack evaluator (Layer 2b)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from nabdh.observations.schema import Observation

PACK_PATH = Path(__file__).with_name("rules_pack.json")


@lru_cache(maxsize=1)
def load_rules_pack() -> dict[str, Any]:
    """Load the versioned JSON rules pack."""
    return json.loads(PACK_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def rules_by_id() -> dict[str, dict[str, Any]]:
    """Index all rules by ``rule_id``."""
    return {r["rule_id"]: r for r in load_rules_pack().get("rules", [])}


def get_rule(rule_id: str) -> dict[str, Any] | None:
    """Return a rule definition by ``rule_id`` or None."""
    return rules_by_id().get(rule_id)


def _alert_fields(
    rule_id: str,
    test: str,
    value: Any,
    unit: str | None,
    threshold: str,
) -> dict[str, Any]:
    """Build a versioned alert payload from a rule and a measured value."""
    rule = rules_by_id()[rule_id]
    return {
        "rule_id": rule_id,
        "version": rule["version"],
        "effective_date": rule["effective_date"],
        "test": test,
        "value": value,
        "unit": unit,
        "threshold": threshold,
        "guideline": rule["guideline"],
        "citation": rule["citation"],
        "severity": rule["severity"],
        "action": rule["action"],
        "requires_signoff": bool(rule["requires_signoff"]),
    }


def _alert_from_rule(rule_id: str, obs: Observation, threshold: str) -> dict[str, Any]:
    return _alert_fields(
        rule_id,
        obs.canonical or obs.name_raw,
        obs.value,
        obs.unit,
        threshold,
    )


def _as_float(value: Any) -> float | None:
    """Coerce a scalar to float, treating missing/invalid values as absent."""
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def evaluate_vital_rules(
    r: pd.Series,
    *,
    pregnant: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Evaluate BP crisis, stage-2 hypertension, and severe-range pregnancy rules.

    Returns ``(urgent_alerts, high_alerts)``. The caller is responsible for applying
    the returned minimum tier; these are tier overrides, not observation alerts.
    """
    sbp = _as_float(r.get("systolic_bp"))
    dbp = _as_float(r.get("diastolic_bp"))
    urgent: list[dict[str, Any]] = []
    high: list[dict[str, Any]] = []
    if sbp is None and dbp is None:
        return urgent, high

    if sbp is not None and dbp is not None:
        reading = f"{sbp:g}/{dbp:g}"
    elif sbp is not None:
        reading = f"{sbp:g}/?"
    else:
        reading = f"?/{dbp:g}"

    if pregnant:
        # ACOG severe-range threshold in pregnancy is >=160 systolic or >=110 diastolic.
        if (sbp is not None and sbp >= 160.0) or (dbp is not None and dbp >= 110.0):
            urgent.append(
                _alert_fields(
                    "OB-BP-SEVERE-01",
                    "blood_pressure",
                    reading,
                    "mmHg",
                    ">=160/110 mmHg",
                )
            )
        return urgent, high

    if (sbp is not None and sbp >= 180.0) or (dbp is not None and dbp >= 120.0):
        urgent.append(
            _alert_fields(
                "CV-BP-CRISIS-01",
                "blood_pressure",
                reading,
                "mmHg",
                ">=180/120 mmHg",
            )
        )
    elif (sbp is not None and sbp >= 160.0) or (dbp is not None and dbp >= 100.0):
        high.append(
            _alert_fields(
                "CV-BP-STAGE2-01",
                "blood_pressure",
                reading,
                "mmHg",
                ">=160/100 mmHg",
            )
        )
    return urgent, high


def evaluate_observation_rules(
    observations: list[Observation],
    age: float | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Evaluate quality=='ok' observations against critical & elevated rules in the pack.

    Returns ``(urgent_alerts, elevated_alerts)``. Observations with ``unit_suspect``,
    ``out_of_plausible_range``, ``no_reference_range``, ``non_numeric``, or ``unmapped``
    are never clinically evaluated.
    """
    urgent: list[dict[str, Any]] = []
    elevated: list[dict[str, Any]] = []

    for obs in observations:
        if obs.quality != "ok" or obs.value is None or obs.canonical is None:
            continue
        v = obs.value
        name = obs.canonical

        if name == "troponin_i" and v >= 0.04:
            urgent.append(_alert_from_rule("CV-TROP-01", obs, ">= 0.04 ng/mL"))
        elif name == "nt_probnp" and v >= 900.0:
            urgent.append(_alert_from_rule("CV-NT-proBNP-01", obs, ">= 900 pg/mL"))
        elif name == "lvef_pct" and v < 40.0:
            urgent.append(_alert_from_rule("CV-LVEF-01", obs, "< 40 %"))
        elif name == "coronary_calcium_score":
            if v >= 300.0:
                urgent.append(_alert_from_rule("CV-CAC-01", obs, ">= 300 AU"))
            elif v >= 100.0:
                elevated.append(_alert_from_rule("CV-CAC-02", obs, "100-299 AU"))
        elif name == "d_dimer":
            limit = obs.ref_high if obs.ref_high is not None else (
                age * 10.0 if (age is not None and age > 50.0) else 500.0
            )
            if v >= limit:
                urgent.append(_alert_from_rule("CV-DDIMER-01", obs, f">= {limit:g} ng/mL FEU"))
        elif name == "hs_crp" and v >= 10.0:
            elevated.append(_alert_from_rule("CV-HSCRP-01", obs, ">= 10.0 mg/L"))
        elif name == "lp_a" and v >= 125.0:
            elevated.append(_alert_from_rule("CV-LPA-01", obs, ">= 125 nmol/L"))

    return urgent, elevated


def evaluate_preventive_rules(
    r: pd.Series,
    age: float,
    p_htn: float | None,
    p_lip: float | None,
    p_ckd: float | None,
) -> tuple[list[str], list[str], list[str], bool]:
    """Evaluate migrated ADA/USPSTF/KDIGO preventive screening rules from the pack.

    Returns ``(tracks, flags, cited_rule_ids, escalate_to_elevated)``.
    """
    pack = rules_by_id()
    tracks: list[str] = []
    flags: list[str] = []
    rule_ids: list[str] = []
    escalate = False
    sex = r.get("sex")

    def _fire(rid: str, track: str | None = None, *, sets_escalate: bool = False) -> None:
        nonlocal escalate
        rule = pack[rid]
        if track:
            tracks.append(track)
        flags.append(rule["action"])
        rule_ids.append(rid)
        if sets_escalate:
            escalate = True

    if p_htn is not None and p_htn >= 0.55:
        _fire("CM-HTN-ML-01", "Hypertension cuff screening", sets_escalate=True)
    if p_lip is not None and p_lip >= 0.55:
        _fire("CM-LIPID-ML-01", "Fasting lipid panel", sets_escalate=True)
    if p_ckd is not None and p_ckd >= 0.20:
        _fire("RN-CKD-ML-01", "Kidney function (eGFR + urine ACR)", sets_escalate=True)

    diag_dm_raw = r.get("diagnosed_diabetes")
    known_diabetic = (
        diag_dm_raw is True
        or diag_dm_raw == 1.0
        or (isinstance(diag_dm_raw, str) and diag_dm_raw.strip().lower() in {"yes", "true", "1"})
    )
    hba1c = r.get("hba1c")
    fpg = r.get("fpg")
    if not known_diabetic:
        if (pd.notna(hba1c) and hba1c >= 6.5) or (pd.notna(fpg) and fpg >= 126.0):
            _fire("DM-LAB-01", "Diabetes diagnostic confirmation", sets_escalate=True)
        elif (pd.notna(hba1c) and hba1c >= 5.7) or (pd.notna(fpg) and fpg >= 100.0):
            _fire("DM-LAB-02", "Prediabetes lifestyle & repeat testing")

    tc = r.get("total_chol")
    hdl = r.get("hdl")
    ldl = r.get("ldl")
    tg = r.get("triglycerides")
    low_hdl = pd.notna(hdl) and (
        (sex == 0.0 and hdl < 40.0) or (sex == 1.0 and hdl < 50.0) or (pd.isna(sex) and hdl < 45.0)
    )
    if (
        (pd.notna(tc) and tc >= 240.0)
        or (pd.notna(ldl) and ldl >= 160.0)
        or (pd.notna(tg) and tg >= 200.0)
        or low_hdl
    ):
        _fire("CM-LIPID-LAB-01", "Lipid management review", sets_escalate=True)

    egfr = r.get("egfr")
    if pd.notna(egfr) and egfr < 60.0:
        _fire("RN-EGFR-LAB-01", "Nephrology / CKD follow-up", sets_escalate=True)

    if 45.0 <= age <= 75.0 and r.get("colorectal_screen_10y") != 1.0:
        _fire("ONC-CRC-01", "Colorectal cancer screening (FIT / colonoscopy)")
    if sex == 1.0 and 40.0 <= age <= 74.0 and r.get("mammogram_2y") != 1.0:
        _fire("ONC-BREAST-01", "Breast cancer screening (mammography)")
    if sex == 1.0 and 21.0 <= age <= 65.0 and r.get("cervical_screen_3y") != 1.0:
        _fire("ONC-CERV-01", "Cervical cancer screening (Pap / hrHPV)")

    pack_years = r.get("pack_years")
    smoker = r.get("current_smoker") == 1.0 or r.get("smoker") == 1.0
    if 50.0 <= age <= 80.0 and pd.notna(pack_years) and float(pack_years) >= 20.0:
        _fire("ONC-LUNG-01", "Lung cancer screening eligibility (LDCT)")
    if sex == 1.0 and age >= 65.0:
        _fire("BONE-DEXA-01", "Osteoporosis screening (DEXA)")

    if smoker:
        _fire("PREV-TOBACCO-01", "Tobacco cessation counselling")
    sleep_h = r.get("sleep_hours")
    if pd.notna(sleep_h) and sleep_h < 6.0:
        _fire("PREV-SLEEP-01")
    if r.get("chol_test_5y") == 0.0 and age >= 40.0:
        _fire("PREV-CHOL-GAP-01")

    if r.get("prs_high") == 1.0:
        _fire("GEN-PRS-01", "Genomic-informed cardiometabolic review", sets_escalate=True)
    if r.get("g6pd_deficient") == 1.0:
        _fire("GEN-G6PD-01", "G6PD medication safety alert")
    if r.get("thalassemia_carrier") == 1.0:
        _fire("GEN-THAL-01", "Thalassemia genetic counselling")

    return tracks, flags, rule_ids, escalate


def evaluate_peds_genomic_and_wcv_rules(
    r: pd.Series,
) -> tuple[list[str], list[str], str | None]:
    """Evaluate Well-Child Visit, developmental, immunisation, and genomic rules for <20y.

    Returns ``(tracks, flags, min_tier)`` where ``min_tier`` is ``"High"``, ``"Elevated"``, or None.
    """
    pack = rules_by_id()
    tracks: list[str] = []
    flags: list[str] = []
    min_tier: str | None = None

    if r.get("developmental_delay_flag") == 1.0:
        flags.append(pack["PED-DEV-01"]["action"])
        tracks.append("Paediatric developmental evaluation")
        min_tier = "High"
    missed = r.get("missed_well_child_visits")
    if pd.notna(missed) and float(missed) >= 1.0:
        flags.append(pack["PED-WCV-01"]["action"])
        tracks.append("Well-Child Visit catch-up")
        if min_tier is None:
            min_tier = "Elevated"
    if r.get("immunization_overdue") == 1.0:
        flags.append(pack["PED-IMM-01"]["action"])
        tracks.append("Catch-up immunisation")
        if min_tier is None:
            min_tier = "Elevated"
    if r.get("g6pd_deficient") == 1.0:
        flags.append(pack["GEN-G6PD-01"]["action"])
        tracks.append("G6PD medication safety alert")
    if r.get("thalassemia_carrier") == 1.0:
        flags.append(pack["GEN-THAL-01"]["action"])
        tracks.append("Thalassemia genetic counselling")

    return tracks, flags, min_tier
