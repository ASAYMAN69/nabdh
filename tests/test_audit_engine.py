"""Regression tests for engine audit fixes (outreach, summary, prenatal, borderline, signoff)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from nabdh.engine import _parse_sex, score
from nabdh.outreach import format_outreach_preview


def test_arabic_outreach_survives_small_cell_suppression() -> None:
    demo = Path(__file__).resolve().parents[1] / "data" / "sample" / "uae_demo_cohort.csv"
    df = pd.read_csv(demo)
    res = score(df)
    by_id = {x["id"]: x for x in res["results"]}

    wow = by_id["UAE-WOW-029"]
    assert "outreach_preview" in wow
    assert wow["outreach_preview"]["language"] == "AR"
    assert "اختيارية" in wow["outreach_preview"]["message"]

    # Every flagged non-urgent Arabic patient in uae_demo_cohort.csv must receive AR outreach
    raw_langs = dict(zip(df["id"], df["language"]))
    for row in res["results"]:
        if (
            raw_langs.get(row["id"]) == "AR"
            and row["tier"] in ("High", "Elevated", "Routine - overdue")
            and row["population"] in ("adult", "child/adolescent")
        ):
            assert row["outreach_preview"]["language"] == "AR", f"{row['id']} got EN instead of AR"


def test_outreach_language_normalization_and_pathways() -> None:
    for lang in ("ar", "AR", "ar-AE", "ar-ae", "arabic", "Arabic"):
        out = format_outreach_preview(
            "P1",
            "Prenatal cardiometabolic & GDM screening track",
            "Per prenatal schedule",
            lang,
        )
        assert out["language"] == "AR"
        assert "المتابعة الوقائية الموصى بها" not in out["message"]
        assert "في أقرب وقت مناسب" not in out["message"]

    for pathway in (
        "Multi-domain preventive screening - cardiometabolic & renal track",
        "Elevated cardiovascular marker — preventive cardiology review",
        "Well-Child Visit - priority developmental & paediatric review",
        "Well-Child Visit - catch-up preventive & immunisation review",
    ):
        out = format_outreach_preview("P2", pathway, "Within 90 days", "ar-ae")
        assert out["language"] == "AR"
        assert "المتابعة الوقائية الموصى بها" not in out["message"]


def test_summary_counts_include_paediatric_and_prenatal() -> None:
    demo = Path(__file__).resolve().parents[1] / "data" / "sample" / "uae_demo_cohort.csv"
    df = pd.read_csv(demo)
    res = score(df)
    summary = res["summary"]
    results = res["results"]

    assert summary["high"] == sum(1 for r in results if r["tier"] == "High")
    assert summary["elevated"] == sum(1 for r in results if r["tier"] == "Elevated")
    assert summary["urgent"] == sum(1 for r in results if r["tier"] == "Urgent Clinical Review")


def test_prenatal_male_and_minor_gating() -> None:
    df = pd.DataFrame(
        [
            {
                "id": "MALE_PREG",
                "age": 30,
                "sex": "M",
                "bmi": 28,
                "pregnant": "yes",
                "systolic_bp": 122,
            },
            {
                "id": "MINOR_PREG",
                "age": 16,
                "sex": "F",
                "bmi": 24,
                "pregnant": "yes",
                "systolic_bp": 134,
            },
        ]
    )
    res = score(df)
    by_id = {x["id"]: x for x in res["results"]}

    male = by_id["MALE_PREG"]
    assert male["stream"] != "prenatal"
    assert male["stream"] == "adult_preventive"
    assert male["risk_pct"] is not None
    assert any("pregnant=yes" in f for f in male["flags"])
    assert any("pregnant=yes with male sex" in w for w in res["warnings"])

    minor = by_id["MINOR_PREG"]
    assert minor["stream"] == "prenatal"
    assert minor["risk_pct"] is None
    assert minor["htn_risk_pct"] is None
    assert minor["tier"] == "Elevated"
    assert "Prenatal BP & gestational diabetes screening" in minor["screening_tracks"]


def test_borderline_diabetes_gated_from_ml() -> None:
    df = pd.DataFrame(
        [
            {
                "id": "BD_ONLY",
                "age": 48,
                "sex": "F",
                "bmi": 27,
                "borderline_diabetes": "yes",
                "glucose_test_3y": "no",
            }
        ]
    )
    row = score(df)["results"][0]
    assert row["risk_pct"] is None
    assert row["dysglycaemia_pct"] is None
    assert row["tier"] == "Elevated"
    assert "Prior borderline/prediabetes history" in row["flags"]


def test_requires_signoff_on_all_actionable_tiers() -> None:
    df = pd.DataFrame(
        [
            {"id": "OVERDUE_ADULT", "age": 45, "sex": "F", "bmi": 22, "glucose_test_3y": "no"},
            {
                "id": "ROUTINE_ADULT",
                "age": 45,
                "sex": "F",
                "bmi": 22,
                "glucose_test_3y": "yes",
                "chol_test_5y": "yes",
                "cervical_screen_3y": "yes",
                "mammogram_2y": "yes",
                "colorectal_screen_10y": "yes",
            },
            {"id": "EXCL_DM", "age": 55, "sex": "M", "bmi": 29, "diagnosed_diabetes": "yes"},
        ]
    )
    by_id = {x["id"]: x for x in score(df)["results"]}
    assert by_id["OVERDUE_ADULT"]["tier"] == "Routine - overdue"
    assert by_id["OVERDUE_ADULT"]["requires_signoff"] is True
    assert by_id["ROUTINE_ADULT"]["requires_signoff"] is False
    assert by_id["EXCL_DM"]["requires_signoff"] is False


def test_missing_sex_routed_to_insufficient_data() -> None:
    df = pd.DataFrame(
        [
            {"id": "S_NONE", "age": 45, "sex": None, "bmi": 30},
            {"id": "S_EMPTY", "age": 45, "sex": "", "bmi": 30},
        ]
    )
    res = score(df)
    for row in res["results"]:
        assert row["stream"] == "insufficient_data"
        assert row["tier"] == "Insufficient data"
        assert row["risk_pct"] is None
        assert "Sex missing or invalid" in row["reasons"]


def test_invalid_sex_degrades_to_insufficient_data() -> None:
    res = score(pd.DataFrame([{"id": "S_BAD", "age": 45, "sex": "other", "bmi": 30}]))
    row = res["results"][0]
    assert row["stream"] == "insufficient_data"
    assert row["tier"] == "Insufficient data"
    assert any("invalid sex" in warning for warning in res["warnings"])


def test_sex_auto_detection_and_riagendr() -> None:
    df_12 = pd.DataFrame(
        [
            {"id": "X", "age": 50, "sex": 1, "bmi": 30},
            {"id": "Y", "age": 50, "sex": 2, "bmi": 30},
        ]
    )
    auto = score(df_12)["results"][0]
    explicit = score(df_12, sex_convention="12")["results"][0]
    assert auto["risk_pct"] == explicit["risk_pct"]
    assert "Sex: Male" in " ".join(auto["reasons"])

    df_01 = pd.DataFrame(
        [
            {"id": "X", "age": 50, "sex": 0, "bmi": 30},
            {"id": "Y", "age": 50, "sex": 1, "bmi": 30},
        ]
    )
    auto_01 = score(df_01)["results"][0]
    assert "Sex: Male" in " ".join(auto_01["reasons"])

    ria = _parse_sex(pd.Series([1, 2]), col_name="riagendr")
    assert list(ria) == [0.0, 1.0]
