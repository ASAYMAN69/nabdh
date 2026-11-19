"""Regression tests for observation catalog, unit sanity, and preventive rule fixes."""
from __future__ import annotations

import pandas as pd

from nabdh.engine import score
from nabdh.observations import capture_wide_dataframe, ingest_long_observations
from nabdh.rules import evaluate_preventive_rules


def test_d_dimer_ug_l_unit_alias_resolves_ok() -> None:
    grouped = ingest_long_observations(
        [
            {"patient_id": "D1", "test_name": "d_dimer", "value": 250.0, "unit": "ug/L"},
            {"patient_id": "D2", "test_name": "d_dimer", "value": 250.0, "unit": "ug_l"},
            {"patient_id": "D3", "test_name": "d_dimer", "value": 250.0, "unit": "ng/mL FEU"},
            {"patient_id": "D4", "test_name": "d_dimer", "value": 0.8, "unit": "mg/L"},
        ],
        patient_meta={"D1": (45.0, 0.0), "D2": (45.0, 0.0), "D3": (45.0, 0.0), "D4": (45.0, 0.0)},
    )
    assert grouped["D1"][0].quality == "ok"
    assert grouped["D1"][0].severity_hint == "normal"
    assert grouped["D2"][0].quality == "ok"
    assert grouped["D3"][0].quality == "ok"
    # Explicit mg/L is converted to ng/mL FEU: 0.8 mg/L = 800 ng/mL FEU.
    assert grouped["D4"][0].quality == "ok"
    assert grouped["D4"][0].severity_hint == "abnormal"
    assert grouped["D4"][0].value == 800.0
    assert grouped["D4"][0].unit == "ng/mL FEU"
    assert grouped["D4"][0].raw_value == 0.8
    assert grouped["D4"][0].raw_unit == "mg/L"


def test_lvef_negative_and_zero_are_out_of_plausible_range() -> None:
    df = pd.DataFrame(
        [
            {"id": "L_ZERO", "age": 60, "sex": 0, "lvef_pct": 0.0},
            {"id": "L_NEG", "age": 60, "sex": 0, "lvef_pct": -5.0},
            {"id": "L_FRAC", "age": 60, "sex": 0, "lvef_pct": 0.45},
            {"id": "L_ONE", "age": 60, "sex": 0, "lvef_pct": 1.0},
            {"id": "L_LOW", "age": 60, "sex": 0, "lvef_pct": 3.0},
            {"id": "L_OK", "age": 60, "sex": 0, "lvef_pct": 55.0},
        ]
    )
    obs_rows = capture_wide_dataframe(
        df,
        claimed_columns={"id", "age", "sex"},
        ages=df["age"],
        sexes=df["sex"],
        patient_ids=df["id"],
    )
    qualities = {obs_rows[i][0].patient_id: obs_rows[i][0].quality for i in range(len(obs_rows))}
    assert qualities["L_ZERO"] == "out_of_plausible_range"
    assert qualities["L_NEG"] == "out_of_plausible_range"
    assert qualities["L_FRAC"] == "unit_suspect"
    assert qualities["L_ONE"] == "unit_suspect"
    assert qualities["L_LOW"] == "out_of_plausible_range"
    assert qualities["L_OK"] == "ok"


def test_d_dimer_value_based_unit_sanity() -> None:
    df = pd.DataFrame(
        [
            {"id": "DD_SUSP_08", "age": 55, "sex": 1, "d_dimer": 0.8},
            {"id": "DD_SUSP_49", "age": 55, "sex": 1, "d_dimer": 4.99},
            {"id": "DD_ZERO", "age": 55, "sex": 1, "d_dimer": 0.0},
            {"id": "DD_OK_NORM", "age": 55, "sex": 1, "d_dimer": 250.0},
            {"id": "DD_OK_HIGH", "age": 60, "sex": 1, "d_dimer": 800.0},
        ]
    )
    obs_rows = capture_wide_dataframe(
        df,
        claimed_columns={"id", "age", "sex"},
        ages=df["age"],
        sexes=df["sex"],
        patient_ids=df["id"],
    )
    by_id = {obs_rows[i][0].patient_id: obs_rows[i][0] for i in range(len(obs_rows))}
    assert by_id["DD_SUSP_08"].quality == "unit_suspect"
    assert by_id["DD_SUSP_49"].quality == "unit_suspect"
    assert by_id["DD_ZERO"].quality == "ok"
    assert by_id["DD_OK_NORM"].quality == "ok"
    assert by_id["DD_OK_NORM"].severity_hint == "normal"
    assert by_id["DD_OK_HIGH"].quality == "ok"
    assert by_id["DD_OK_HIGH"].severity_hint == "abnormal"

    grouped = ingest_long_observations(
        [{"patient_id": "DL1", "test_name": "d_dimer", "value": 0.8, "unit": "ug/L"}],
        patient_meta={"DL1": (55.0, 1.0)},
    )
    assert grouped["DL1"][0].quality == "unit_suspect"


def test_onc_lung_01_requires_20_pack_years() -> None:
    # Current smoker aged 60 with 0 or missing pack-years must NOT trigger ONC-LUNG-01
    for py in (0.0, None, 19.9):
        row = pd.Series({"sex": 0.0, "current_smoker": 1.0, "pack_years": py})
        _tracks, _flags, rule_ids, _esc = evaluate_preventive_rules(row, 60.0, None, None, None)
        assert "ONC-LUNG-01" not in rule_ids
        assert "PREV-TOBACCO-01" in rule_ids

    # Former/non-current smoker aged 60 with >= 20 pack-years DOES trigger ONC-LUNG-01
    row_ok = pd.Series({"sex": 0.0, "current_smoker": 0.0, "pack_years": 20.0})
    _tracks, _flags, rule_ids_ok, _esc = evaluate_preventive_rules(row_ok, 60.0, None, None, None)
    assert "ONC-LUNG-01" in rule_ids_ok

    # Outside age 50-80 must NOT trigger ONC-LUNG-01 even with >= 20 pack-years
    for out_age in (49.0, 81.0):
        row_age = pd.Series({"sex": 0.0, "current_smoker": 1.0, "pack_years": 30.0})
        _tracks, _flags, rule_ids_age, _esc = evaluate_preventive_rules(
            row_age, out_age, None, None, None
        )
        assert "ONC-LUNG-01" not in rule_ids_age


def test_dm_lab_01_skipped_for_known_diabetic() -> None:
    for diag_val in (True, 1.0, "yes"):
        row = pd.Series({"sex": 1.0, "diagnosed_diabetes": diag_val, "hba1c": 7.5, "fpg": 150.0})
        tracks, _flags, rule_ids, escalate = evaluate_preventive_rules(row, 55.0, None, None, None)
        assert "DM-LAB-01" not in rule_ids
        assert "DM-LAB-02" not in rule_ids
        assert "Diabetes diagnostic confirmation" not in tracks
        assert escalate is False

    # Undiagnosed patient with HbA1c >= 6.5% DOES trigger DM-LAB-01
    row_new = pd.Series({"sex": 1.0, "diagnosed_diabetes": 0.0, "hba1c": 6.8})
    tracks_new, _flags_new, rule_ids_new, escalate_new = evaluate_preventive_rules(
        row_new, 55.0, None, None, None
    )
    assert "DM-LAB-01" in rule_ids_new
    assert "Diabetes diagnostic confirmation" in tracks_new
    assert escalate_new is True

    # End-to-end score() check for known diabetic with elevated HbA1c
    df = pd.DataFrame(
        [
            {
                "id": "KNOWN_DM",
                "age": 55,
                "sex": "F",
                "bmi": 28,
                "diagnosed_diabetes": "yes",
                "hba1c": 7.5,
            },
            {
                "id": "NEW_DM",
                "age": 55,
                "sex": "F",
                "bmi": 28,
                "diagnosed_diabetes": "no",
                "hba1c": 7.5,
            },
        ]
    )
    res = score(df)
    by_id = {x["id"]: x for x in res["results"]}
    dm_action = (
        "Diagnostic glycaemic lab (HbA1c >=6.5% or FPG >=126 mg/dL) — "
        "confirm with repeat testing"
    )
    assert dm_action not in by_id["KNOWN_DM"]["flags"]
    assert dm_action in by_id["NEW_DM"]["flags"]
    assert by_id["NEW_DM"]["tier"] == "High"
