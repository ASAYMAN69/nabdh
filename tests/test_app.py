"""API, ML, and safety regression tests (run after: python -m nabdh.model.train)."""
from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from nabdh.data.nhanes import RAW, build_task_a
from nabdh.engine import score
from nabdh.outreach import format_outreach_preview

client = TestClient(app)

CSV = (
    b"resident_id,age,sex,bmi,waist,systolic_bp,diastolic_bp,family_hx_diabetes,glucose_test_3y\n"
    b"R001,29,F,33,104,138,86,yes,no\n"
    b"R002,42,M,24,84,118,76,no,yes\n"
    b"R003,66,M,36,118,150,92,yes,no\n"
    b"K001,9,M,24.5,,,,,\n"
)


def test_health_endpoint() -> None:
    assert client.get("/health").json()["status"] == "ok"


def test_index_serves_html() -> None:
    r = client.get("/")
    assert r.status_code == 200 and "Nabdh" in r.text


def test_score_real_engine_and_young_high_risk() -> None:
    r = client.post("/api/score", files={"file": ("c.csv", CSV, "text/csv")})
    assert r.status_code == 200
    p = r.json()
    assert p["summary"]["rows"] == 4
    by_id = {x["id"]: x for x in p["results"]}
    assert by_id["R001"]["risk_pct"] > by_id["R002"]["risk_pct"]
    assert by_id["R001"]["tier"] in ("Elevated", "High")
    assert "raises" in by_id["R001"]["reasons"][0]
    assert "Missed by age-40 screening rule (<40)" in by_id["R001"]["flags"]
    assert by_id["R003"]["tier"] in ("High", "Elevated")
    assert by_id["K001"]["population"] == "child/adolescent"
    assert by_id["K001"]["tier"] == "High"
    assert all(x["reasons"] for x in p["results"])


def test_known_diabetes_excluded_adults_and_peds() -> None:
    csv = b"id,age,sex,bmi,diagnosed_diabetes\nA1,60,M,30,yes\nP1,12,M,28,yes\n"
    p = client.post("/api/score", files={"file": ("c.csv", csv, "text/csv")}).json()
    assert p["results"][0]["tier"] == "Excluded"
    assert p["results"][1]["tier"] == "Excluded"
    assert p["results"][1]["population"] == "child/adolescent"
    assert p["summary"]["children_adolescents"] == 0


def test_pediatric_under5_and_late_adolescent_coverage() -> None:
    csv = b"id,age,sex,bmi\nT1,3,M,22.0\nT2,19.5,F,33.0\n"
    p = client.post("/api/score", files={"file": ("c.csv", csv, "text/csv")}).json()
    by_id = {x["id"]: x for x in p["results"]}
    assert by_id["T1"]["tier"] == "High"
    assert "WHO 2006 (0-5y)" in by_id["T1"]["reasons"][0]
    assert by_id["T2"]["tier"] == "High"
    assert "WHO 2007 (5-19y)" in by_id["T2"]["reasons"][0]


def test_sex_zero_one_coding_and_blanks() -> None:
    csv_01 = b"id,age,sex,bmi\nA,45,0,28\nB,45,1,28\nC,45,,28\n"
    p01 = client.post("/api/score", files={"file": ("c.csv", csv_01, "text/csv")}).json()
    by_id = {row["id"]: row for row in p01["results"]}
    assert "Sex: Male" in " ".join(by_id["A"]["reasons"])
    assert "Sex: Female" in " ".join(by_id["B"]["reasons"])
    assert by_id["C"]["tier"] == "Insufficient data"
    assert any("missing sex" in w for w in p01["warnings"])

    csv_12 = b"id,age,sex,bmi\nA,40,1,26\nB,40,2,26\n"
    p12 = client.post("/api/score", files={"file": ("c.csv", csv_12, "text/csv")}).json()
    by_id_12 = {row["id"]: row for row in p12["results"]}
    assert "Sex: Male" in " ".join(by_id_12["A"]["reasons"])
    assert "Sex: Female" in " ".join(by_id_12["B"]["reasons"])


def test_height_zero_and_bounds_do_not_crash() -> None:
    csv = (
        b"id,age,sex,height_cm,weight_kg,waist,sleep_hours\n"
        b"Z0,45,M,0,75,95,8\n"
        b"BAD_AGE,250,F,165,70,85,8\n"
        b"NEG_AGE,-5,M,170,70,85,30\n"
    )
    r = client.post("/api/score", files={"file": ("c.csv", csv, "text/csv")})
    assert r.status_code == 200
    p = r.json()
    by_id = {x["id"]: x for x in p["results"]}
    assert by_id["Z0"]["risk_pct"] is not None
    assert by_id["BAD_AGE"]["tier"] == "Insufficient data"
    assert by_id["NEG_AGE"]["tier"] == "Insufficient data"
    assert any("out-of-range" in w for w in p["warnings"])


def test_batch_invariance_per_row_variant() -> None:
    df_a = pd.DataFrame(
        [
            {"id": "TARGET", "age": 48, "sex": "M", "bmi": 30, "family_hx_diabetes": None},
            {"id": "P2", "age": 48, "sex": "F", "bmi": 28, "family_hx_diabetes": "yes"},
            {"id": "P3", "age": 48, "sex": "F", "bmi": 28, "family_hx_diabetes": "yes"},
        ]
    )
    df_b = pd.DataFrame(
        [
            {"id": "TARGET", "age": 48, "sex": "M", "bmi": 30, "family_hx_diabetes": None},
            {"id": "P2", "age": 48, "sex": "F", "bmi": 28, "family_hx_diabetes": None},
            {"id": "P3", "age": 48, "sex": "F", "bmi": 28, "family_hx_diabetes": None},
        ]
    )
    ra = score(df_a)["results"][0]["risk_pct"]
    rb = score(df_b)["results"][0]["risk_pct"]
    assert ra == rb


def test_no_unknown_imputed_in_reasons() -> None:
    csv = b"id,age,sex,bmi\nS1,32,F,21.5\n"
    p = client.post("/api/score", files={"file": ("c.csv", csv, "text/csv")}).json()
    reasons_text = " | ".join(p["results"][0]["reasons"])
    assert "unknown (imputed)" not in reasons_text


def test_complementary_small_cell_suppression_and_redaction() -> None:
    # 1. Big(12) + Tiny(5): complementary suppression hides BOTH aggregate counts,
    # but only the primary small cell is redacted in the row-level upload view.
    rows = [f"B{i},{35 + i},M,Big" for i in range(12)] + [
        f"T{i},{35 + i},M,Tiny" for i in range(5)
    ]
    csv = ("id,age,sex,district\n" + "\n".join(rows) + "\n").encode()
    p = client.post("/api/score", files={"file": ("c.csv", csv, "text/csv")}).json()
    segs = [s for s in p["summary"]["segments"] if s["dimension"] == "district"]
    assert all(s["suppressed"] for s in segs)
    by_id = {r["id"]: r for r in p["results"]}
    assert all(by_id[f"T{i}"]["district"] == "<suppressed (<10)>" for i in range(5))
    assert all(by_id[f"B{i}"]["district"] == "Big" for i in range(12))

    # 2. <10-row upload still redacts small-cell district
    csv_small = ("id,age,sex,district\n" + "\n".join(
        f"S{i},40,M,TinyClinic" for i in range(5)
    ) + "\n").encode()
    p_small = client.post("/api/score", files={"file": ("s.csv", csv_small, "text/csv")}).json()
    assert all(r["district"] == "<suppressed (<10)>" for r in p_small["results"])

    # 3. 5 adults + 7 kids in MixedDistrict (total 12 >= 10, adult count 5 < 10)
    mixed = [f"A{i},40,M,,MixedDistrict" for i in range(5)] + [
        f"K{i},8,M,17,MixedDistrict" for i in range(7)
    ]
    csv_mix = ("id,age,sex,bmi,district\n" + "\n".join(mixed) + "\n").encode()
    p_mix = client.post("/api/score", files={"file": ("m.csv", csv_mix, "text/csv")}).json()
    assert all(r["district"] == "<suppressed (<10)>" for r in p_mix["results"])


def test_zero_row_csv_and_formula_injection_sanitization() -> None:
    r0 = client.post("/api/score", files={"file": ("empty_rows.csv", b"age,sex\n", "text/csv")})
    assert r0.status_code == 200
    assert r0.json()["summary"]["rows"] == 0

    r0_csv = client.post(
        "/api/score.csv", files={"file": ("empty_rows.csv", b"age,sex\n", "text/csv")}
    )
    assert r0_csv.status_code == 200

    inj_rows = "\n".join(f"=CMD|'/C calc'!A{i},55,M,+EVIL()" for i in range(10))
    inj = ("id,age,sex,district\n" + inj_rows + "\n").encode()
    r_inj = client.post("/api/score.csv", files={"file": ("inj.csv", inj, "text/csv")})
    assert r_inj.status_code == 200
    body = r_inj.text
    assert "'=CMD" in body and "'+EVIL()" in body


def test_missing_required_column_and_empty_file() -> None:
    r_miss = client.post("/api/score", files={"file": ("c.csv", b"age\n30\n", "text/csv")})
    assert r_miss.status_code == 422
    assert client.post("/api/score", files={"file": ("e.csv", b"", "text/csv")}).status_code == 400


def test_csv_export_filters() -> None:
    r = client.post(
        "/api/score.csv",
        files={"file": ("c.csv", CSV, "text/csv")},
        data={"min_tier": "flagged"},
    )
    assert r.status_code == 200
    lines = r.text.strip().splitlines()
    assert len(lines) >= 3  # header + R001, R003, K001


@pytest.mark.skipif(
    not (RAW / "nhanes_2017_2020" / "P_DEMO.xpt").exists()
    or not (RAW / "nhanes_2021_2023" / "DEMO_L.xpt").exists(),
    reason="raw NHANES files are not committed; see data/DATASETS.md",
)
def test_task_a_has_no_missing_fpg_or_borderline() -> None:
    for cyc in ("nhanes_2017_2020", "nhanes_2021_2023"):
        d = build_task_a(cyc)
        assert d["_fpg"].isna().sum() == 0
        assert (d["_diq010"] == 2.0).all()
        assert (d["_borderline_dm"] == 0.0).all()


def test_age_monotonicity_no_39_to_40_downgrade() -> None:
    rank = {"Low": 0, "Routine": 1, "Routine - overdue": 2, "Elevated": 3, "High": 4}
    df = pd.DataFrame(
        [
            {
                "id": "A39",
                "age": 39,
                "sex": "M",
                "bmi": 33,
                "waist": 104,
                "systolic_bp": 135,
                "glucose_test_3y": "no",
            },
            {
                "id": "A40",
                "age": 40,
                "sex": "M",
                "bmi": 33,
                "waist": 104,
                "systolic_bp": 135,
                "glucose_test_3y": "no",
            },
        ]
    )
    res = score(df)["results"]
    assert res[1]["risk_pct"] >= res[0]["risk_pct"]
    assert rank[res[1]["tier"]] >= rank[res[0]["tier"]]


def test_missing_sex_bmi18_lowers_risk_vs_bmi35() -> None:
    df = pd.DataFrame(
        [
            {"id": "VALID_BMI18", "age": 45, "sex": "F", "bmi": 18.0},
            {"id": "VALID_BMI35", "age": 45, "sex": "F", "bmi": 35.0},
        ]
    )
    res = score(df)["results"]
    assert res[0]["risk_pct"] < res[1]["risk_pct"]
    assert "BMI (18.0) lowers risk" in res[0]["reasons"]


def test_all_female_zero_one_sex_coding() -> None:
    solo = score(pd.DataFrame([{"id": "F1", "age": 50, "sex": 1, "bmi": 30}]))["results"][0]
    mixed = score(
        pd.DataFrame(
            [
                {"id": "F1", "age": 50, "sex": 1, "bmi": 30},
                {"id": "M1", "age": 50, "sex": 0, "bmi": 30},
            ]
        )
    )["results"][0]
    assert solo["risk_pct"] == mixed["risk_pct"]
    assert "Sex: Female" in " ".join(solo["reasons"])


def test_triad_reasons_borderline_and_high_escalation() -> None:
    # Borderline prediabetes + no family history -> triad must say "prior prediabetes"
    df_bd = pd.DataFrame(
        [
            {
                "id": "BD1",
                "age": 32,
                "sex": "F",
                "bmi": 33,
                "waist": 104,
                "systolic_bp": 138,
                "family_hx_diabetes": "no",
                "borderline_diabetes": "yes",
            }
        ]
    )
    r_bd = score(df_bd)["results"][0]
    assert r_bd["tier"] == "Elevated"
    assert "prior prediabetes" in r_bd["reasons"][0]
    assert "family history" not in r_bd["reasons"][0]

    # 4.5% <= risk < 9.0% + triad -> escalated to High and triad reason included
    df_hi = pd.DataFrame(
        [
            {
                "id": "HI_TRIAD",
                "age": 50,
                "sex": "M",
                "bmi": 34,
                "waist": 112,
                "systolic_bp": 140,
                "family_hx_diabetes": "yes",
            }
        ]
    )
    r_hi = score(df_hi)["results"][0]
    assert r_hi["tier"] == "High"
    assert "Cardiometabolic syndrome triad" in r_hi["reasons"][0]


def test_sex_two_is_auto_detected_and_mixed_coding_degrades() -> None:
    df = pd.DataFrame(
        [
            {"id": "M0", "age": 50, "sex": 0, "bmi": 30},
            {"id": "F1", "age": 50, "sex": 1, "bmi": 30},
        ]
    )
    by_id = {x["id"]: x for x in score(df)["results"]}
    assert "Sex: Male" in " ".join(by_id["M0"]["reasons"])
    assert "Sex: Female" in " ".join(by_id["F1"]["reasons"])

    # A lone 2 selects 1/2 coding, so it is female rather than a file error.
    lone = score(pd.DataFrame([{"id": "F2", "age": 50, "sex": 2, "bmi": 30}]))["results"][0]
    assert "Sex: Female" in " ".join(lone["reasons"])

    # A file containing both 0 and 2 is treated as 0/1; the 2 degrades to missing.
    mixed = score(
        pd.DataFrame(
            [
                {"id": "M0", "age": 50, "sex": 0, "bmi": 30},
                {"id": "BAD2", "age": 50, "sex": 2, "bmi": 30},
            ]
        )
    )
    mixed_by_id = {x["id"]: x for x in mixed["results"]}
    assert "Sex: Male" in " ".join(mixed_by_id["M0"]["reasons"])
    assert mixed_by_id["BAD2"]["tier"] == "Insufficient data"
    assert any("invalid sex" in w for w in mixed["warnings"])


def test_outreach_preview_bilingual_and_wired() -> None:
    ar = format_outreach_preview(
        "AD-1",
        "Accelerated adult comprehensive screening - metabolic track "
        "(HbA1c + fasting glucose, lipids, BP)",
        "Within 30 days",
        "AR",
    )
    assert ar["language"] == "AR" and "اختيارية" in ar["message"]
    assert "Within" not in ar["message"] and "Accelerated" not in ar["message"]

    ur_fallback = format_outreach_preview(
        "AD-2", "Adult comprehensive screening - cardiometabolic track", "Within 90 days", "UR"
    )
    assert ur_fallback["language"] == "EN"
    assert "within Within" not in ur_fallback["message"]
    assert "within 90 days" in ur_fallback["message"]

    r = client.post("/api/score", files={"file": ("c.csv", CSV, "text/csv")}).json()
    by_id = {x["id"]: x for x in r["results"]}
    assert "outreach_preview" in by_id["R001"]
    assert "within Within" not in by_id["R001"]["outreach_preview"]["message"]
    assert by_id["R001"]["outreach_preview"]["choices"] == ["Confirm slot", "Reschedule", "Opt out"]
    assert "outreach_preview" in by_id["K001"]
    assert "parent/caregiver" in by_id["K001"]["outreach_preview"]["message"]


def test_multi_stream_routing_and_uspstf_screenings() -> None:
    df = pd.DataFrame(
        [
            {"id": "PREG1", "age": 29, "sex": "F", "pregnant": "yes", "systolic_bp": 136},
            {"id": "PED1", "age": 10, "sex": "M", "bmi": 22},
            {"id": "UNK1", "age": None, "sex": "F"},
            {
                "id": "ADULT_MULTI",
                "age": 55,
                "sex": "F",
                "bmi": 29,
                "waist": 95,
                "systolic_bp": 124,
                "smoker": "yes",
                "pack_years": 25,
            },
        ]
    )
    by_id = {x["id"]: x for x in score(df)["results"]}
    assert by_id["PREG1"]["stream"] == "prenatal"
    assert by_id["PREG1"]["risk_pct"] is None
    assert by_id["PREG1"]["htn_risk_pct"] is None
    assert by_id["PREG1"]["tier"] == "Elevated"

    assert by_id["PED1"]["stream"] == "paediatric"
    assert by_id["PED1"]["htn_risk_pct"] is None

    assert by_id["UNK1"]["stream"] == "insufficient_data"
    assert by_id["UNK1"]["tier"] == "Insufficient data"

    ad = by_id["ADULT_MULTI"]
    assert ad["stream"] == "adult_preventive"
    assert ad["htn_risk_pct"] is not None
    assert ad["dyslipidaemia_risk_pct"] is not None
    assert ad["ckd_risk_pct"] is not None
    tracks = " | ".join(ad["screening_tracks"])
    assert "Colorectal cancer screening" in tracks
    assert "Breast cancer screening" in tracks
    assert "Cervical cancer screening" in tracks
    assert "Lung cancer screening" in tracks
    assert "Tobacco cessation" in tracks


def test_known_diabetes_gets_non_dm_screenings_and_lab_flags() -> None:
    df = pd.DataFrame(
        [
            {
                "id": "DM_MULTI",
                "age": 66,
                "sex": "F",
                "bmi": 31,
                "diagnosed_diabetes": "yes",
                "egfr": 48,
                "total_chol": 255,
            }
        ]
    )
    row = score(df)["results"][0]
    assert row["tier"] == "Excluded"
    assert row["risk_pct"] is None
    assert row["htn_risk_pct"] is not None
    assert row["ckd_risk_pct"] is not None
    flags = " | ".join(row["flags"])
    assert "Reduced eGFR" in flags
    assert "Abnormal lipid lab" in flags
    assert "Osteoporosis DEXA" in flags
