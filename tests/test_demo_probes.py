"""Regression tests for demo-critical clinician upload paths.

Each test is a probe a clinician may attempt live or in their own uploads. The
cases cover the silent-failure paths closed on 2026-11-19: non-canonical lab
units, hypertensive crisis / stage-2 BP, severe BP in pregnancy, and BP
escalation for a patient already known to have diabetes.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from nabdh.engine import score
from nabdh.rules import evaluate_vital_rules

ROOT = Path(__file__).resolve().parents[1]


def _one(row: dict) -> dict:
    return score(pd.DataFrame([{"id": "PROBE", **row}]))["results"][0]


def _warnings(row: dict) -> list[str]:
    return score(pd.DataFrame([{"id": "PROBE", **row}]))["warnings"]


# ---------------------------------------------------------------------------
# Non-canonical lab units must be converted, not silently dropped
# ---------------------------------------------------------------------------


def test_hba1c_mmol_mol_is_converted_and_lifts_to_high() -> None:
    row = {"age": 45, "sex": "male", "bmi": 31, "hba1c": 58}
    r = _one(row)
    assert r["tier"] == "High"
    assert any("Diagnostic glycaemic lab" in f for f in r["flags"])
    warnings = _warnings(row)
    assert any("mmol/mol" in w and "converted to %" in w for w in warnings)


def test_fpg_mmol_l_is_converted_and_lifts_to_high() -> None:
    row = {"age": 45, "sex": "male", "bmi": 31, "fpg": 7.0}
    r = _one(row)
    assert r["tier"] == "High"
    assert any("Diagnostic glycaemic lab" in f for f in r["flags"])
    assert any("mmol/L" in w and "mg/dL" in w for w in _warnings(row))


def test_troponin_ng_l_is_converted_and_urgent() -> None:
    r = _one({"age": 60, "sex": "male", "troponin_i_ng_l": 180})
    assert r["tier"] == "Urgent Clinical Review"
    assert [a["rule_id"] for a in r["urgent_alerts"]] == ["CV-TROP-01"]
    obs = {o["canonical"]: o for o in r["observations"]}
    assert obs["troponin_i"]["value"] == pytest.approx(0.18)
    assert obs["troponin_i"]["unit"] == "ng/mL"
    assert obs["troponin_i"]["quality"] == "ok"
    assert obs["troponin_i"]["raw_value"] == pytest.approx(180.0)
    assert obs["troponin_i"]["raw_unit"] == "ng/L"


def test_d_dimer_ug_ml_is_converted_and_urgent() -> None:
    r = _one({"age": 60, "sex": "male", "d_dimer_ug_ml": 2.5})
    assert r["tier"] == "Urgent Clinical Review"
    assert [a["rule_id"] for a in r["urgent_alerts"]] == ["CV-DDIMER-01"]
    obs = {o["canonical"]: o for o in r["observations"]}
    assert obs["d_dimer"]["value"] == pytest.approx(2500.0)
    assert obs["d_dimer"]["unit"] == "ng/mL FEU"
    assert obs["d_dimer"]["raw_value"] == pytest.approx(2.5)
    assert obs["d_dimer"]["raw_unit"] == "ug/mL"


def test_lvef_fraction_is_converted_and_urgent() -> None:
    r = _one({"age": 60, "sex": "male", "lvef_fraction": 0.30})
    assert r["tier"] == "Urgent Clinical Review"
    assert [a["rule_id"] for a in r["urgent_alerts"]] == ["CV-LVEF-01"]
    obs = {o["canonical"]: o for o in r["observations"]}
    assert obs["lvef_pct"]["value"] == pytest.approx(30.0)
    assert obs["lvef_pct"]["unit"] == "%"
    assert obs["lvef_pct"]["raw_value"] == pytest.approx(0.30)
    assert obs["lvef_pct"]["raw_unit"] == "fraction"


def test_implicit_troponin_magnitude_stays_unevaluated() -> None:
    """A bare 180 with no unit must warn, not be guessed into 0.18 ng/mL."""
    r = _one({"age": 60, "sex": "male", "troponin_i": 180})
    assert r["tier"] != "Urgent Clinical Review"
    assert any(o["quality"] == "unit_suspect" for o in r["observations"])
    assert not any(a["rule_id"] == "CV-TROP-01" for a in r["urgent_alerts"])


# ---------------------------------------------------------------------------
# Blood pressure escalation
# ---------------------------------------------------------------------------


def test_bp_crisis_escalates_adult_to_urgent() -> None:
    r = _one(
        {"age": 45, "sex": "male", "bmi": 31, "systolic_bp": 185, "diastolic_bp": 115}
    )
    assert r["tier"] == "Urgent Clinical Review"
    assert r["timing"] == "Immediate"
    assert [a["rule_id"] for a in r["urgent_alerts"]] == ["CV-BP-CRISIS-01"]
    assert any("Hypertensive crisis" in f for f in r["flags"])


def test_bp_stage2_escalates_adult_to_high() -> None:
    r = _one(
        {"age": 45, "sex": "male", "bmi": 31, "systolic_bp": 160, "diastolic_bp": 100}
    )
    assert r["tier"] == "High"
    assert r["timing"] == "Within 30 days"
    assert any("Stage 2 hypertension" in f for f in r["flags"])


def test_bp_below_stage2_does_not_escalate_tier() -> None:
    r = _one(
        {"age": 45, "sex": "male", "bmi": 31, "systolic_bp": 159, "diastolic_bp": 99}
    )
    assert r["tier"] not in ("Urgent Clinical Review", "High")
    assert not any("Hypertensive crisis" in f or "Stage 2 hypertension" in f for f in r["flags"])


def test_severe_bp_in_pregnancy_is_urgent_obstetric_review() -> None:
    r = _one(
        {
            "age": 28,
            "sex": "female",
            "bmi": 30,
            "pregnant": "yes",
            "systolic_bp": 165,
            "diastolic_bp": 110,
        }
    )
    assert r["tier"] == "Urgent Clinical Review"
    assert r["pathway"].startswith("Urgent obstetric review")
    assert [a["rule_id"] for a in r["urgent_alerts"]] == ["OB-BP-SEVERE-01"]
    assert any("Severe-range BP in pregnancy" in f for f in r["flags"])


def test_bp_below_severe_range_in_pregnancy_is_not_urgent() -> None:
    r = _one(
        {
            "age": 28,
            "sex": "female",
            "bmi": 30,
            "pregnant": "yes",
            "systolic_bp": 159,
            "diastolic_bp": 109,
        }
    )
    assert r["tier"] != "Urgent Clinical Review"
    assert not any(a["rule_id"] == "OB-BP-SEVERE-01" for a in r["urgent_alerts"])


def test_known_diabetic_with_bp_crisis_is_urgent() -> None:
    r = _one(
        {
            "age": 55,
            "sex": "female",
            "bmi": 33,
            "diagnosed_diabetes": "yes",
            "systolic_bp": 185,
            "diastolic_bp": 115,
        }
    )
    assert r["tier"] == "Urgent Clinical Review"
    assert r["risk_pct"] is None  # DM ML correctly withheld for known diabetes
    assert [a["rule_id"] for a in r["urgent_alerts"]] == ["CV-BP-CRISIS-01"]


# ---------------------------------------------------------------------------
# Rule-level boundary checks
# ---------------------------------------------------------------------------


def _vital(sbp: float, dbp: float, *, pregnant: bool = False):
    return evaluate_vital_rules(
        pd.Series({"systolic_bp": sbp, "diastolic_bp": dbp}), pregnant=pregnant
    )


def test_vital_rule_boundaries() -> None:
    assert _vital(159, 99) == ([], [])
    assert _vital(179, 119)[1][0]["rule_id"] == "CV-BP-STAGE2-01"
    assert _vital(180, 70)[0][0]["rule_id"] == "CV-BP-CRISIS-01"
    assert _vital(120, 120)[0][0]["rule_id"] == "CV-BP-CRISIS-01"
    assert _vital(160, 99)[1][0]["rule_id"] == "CV-BP-STAGE2-01"
    assert _vital(140, 105)[1][0]["rule_id"] == "CV-BP-STAGE2-01"
    assert _vital(159, 90) == ([], [])
    assert _vital(159, 109, pregnant=True) == ([], [])
    assert _vital(160, 100, pregnant=True)[0][0]["rule_id"] == "OB-BP-SEVERE-01"
    assert _vital(150, 110, pregnant=True)[0][0]["rule_id"] == "OB-BP-SEVERE-01"


def test_vital_alert_carries_version_and_citation() -> None:
    urgent, _ = _vital(185, 115)
    alert = urgent[0]
    assert alert["version"]
    assert alert["effective_date"]
    assert alert["guideline"] == "ACC/AHA"
    assert "2017 ACC/AHA" in alert["citation"]
    assert alert["requires_signoff"] is True


# ---------------------------------------------------------------------------
# Demo cohort invariance
# ---------------------------------------------------------------------------


def test_demo_cohort_aggregates_are_pinned() -> None:
    """The public demo numbers must not drift when rules or ingestion change."""
    demo = ROOT / "data" / "sample" / "uae_demo_cohort.csv"
    payload = score(pd.read_csv(demo))
    summary = payload["summary"]
    assert summary["rows"] == 60
    assert summary["adults_screenable"] == 51
    assert summary["children_adolescents"] == 8
    assert summary["urgent"] == 1
    assert summary["high"] == 9
    assert summary["elevated"] == 17
    assert summary["missed_by_age_rules"] == 4
    assert summary["observations_captured"] == 4
    assert summary["observations_unit_suspect"] == 1
    assert summary["expected_undiagnosed_diabetes_cases"] == pytest.approx(1.0)

    by_id = {r["id"]: r for r in payload["results"]}
    # Complementary suppression protects the aggregate count, not the row the
    # clinician uploaded; the AR preview must therefore agree with the row language.
    assert by_id["UAE-WOW-029"]["language"] == "AR"
    assert by_id["UAE-WOW-029"]["outreach_preview"]["language"] == "AR"
    ar_segment = next(
        s for s in summary["segments"] if s["dimension"] == "language" and s["segment"] == "AR"
    )
    assert ar_segment["suppressed"] is True
    # Primary small cells remain redacted at row level.
    assert by_id["UAE-SM-401"]["district"] == "<suppressed (<10)>"
    assert by_id["UAE-SM-401"]["language"] == "<suppressed (<10)>"

    # An unevaluated lab must not receive an automated outreach preview.
    assert "outreach_preview" not in by_id["UAE-UNIT-102"]
    assert any("Outreach withheld" in f for f in by_id["UAE-UNIT-102"]["flags"])


# ---------------------------------------------------------------------------
# Explicit unit-suffixed columns must map to the same lab
# ---------------------------------------------------------------------------


def test_hba1c_mmol_mol_column_maps_and_converts() -> None:
    r = _one({"age": 45, "sex": "male", "bmi": 31, "hba1c_mmol_mol": 58})
    assert r["tier"] == "High"
    assert any("Diagnostic glycaemic lab" in f for f in r["flags"])
    assert any("mmol/mol" in w and "converted to %" in w for w in _warnings(
        {"age": 45, "sex": "male", "bmi": 31, "hba1c_mmol_mol": 58}
    ))


def test_fpg_mmol_l_column_maps_and_converts() -> None:
    r = _one({"age": 45, "sex": "male", "bmi": 31, "fpg_mmol_l": 7.0})
    assert r["tier"] == "High"
    assert any("Diagnostic glycaemic lab" in f for f in r["flags"])
    assert any("mmol/L" in w and "mg/dL" in w for w in _warnings(
        {"age": 45, "sex": "male", "bmi": 31, "fpg_mmol_l": 7.0}
    ))


def test_ldl_mmol_l_column_maps_and_converts() -> None:
    r = _one({"age": 45, "sex": "male", "bmi": 31, "ldl_mmol_l": 7.0})
    assert any("lipid" in f.lower() for f in r["flags"])
    assert any("mmol/L" in w and "mg/dL" in w for w in _warnings(
        {"age": 45, "sex": "male", "bmi": 31, "ldl_mmol_l": 7.0}
    ))


# ---------------------------------------------------------------------------
# Cohort-level guardrails surfaced by the reviewer pass
# ---------------------------------------------------------------------------


def test_unit_suspect_warning_at_cohort_level() -> None:
    """A hidden urgent finding must be surfaced at cohort level, not only per row."""
    res = score(pd.DataFrame([{"id": "P", "age": 60, "sex": "male", "troponin_i": 4500}]))
    assert res["summary"]["observations_unit_suspect"] == 1
    assert any(
        "not checked" in w.lower() or "unit was unclear" in w.lower() for w in res["warnings"]
    )


def test_clinician_full_template_scores_cleanly() -> None:
    """The downloadable clinician template must upload and score without errors."""
    tpl = ROOT / "data" / "sample" / "clinician_template.csv"
    assert tpl.exists()
    payload = score(pd.read_csv(tpl))
    assert payload["summary"]["rows"] == 2
    tiers = {r["id"]: r["tier"] for r in payload["results"]}
    assert tiers["EX-001"] == "Elevated"
    assert tiers["EX-002"] == "High"


# ---------------------------------------------------------------------------
# Robustness: non-numeric education must degrade to missing, not crash
# ---------------------------------------------------------------------------


def test_non_numeric_education_is_coerced_not_crashed() -> None:
    """Text education (e.g. 'college') must not raise a raw sklearn error."""
    r = _one({"age": 50, "sex": "male", "bmi": 28, "education": "college"})
    assert r["tier"] in {"Low", "Routine", "Routine - overdue", "Elevated", "High"}
    assert any(
        "education" in w.lower()
        for w in _warnings({"age": 50, "sex": "male", "bmi": 28, "education": "college"})
    )


def test_empty_string_education_is_coerced_not_crashed() -> None:
    """An empty-string education cell must also degrade to missing."""
    r = _one({"age": 50, "sex": "male", "bmi": 28, "education": ""})
    assert r["tier"] in {"Low", "Routine", "Routine - overdue", "Elevated", "High"}
