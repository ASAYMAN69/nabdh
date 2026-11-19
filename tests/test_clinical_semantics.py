"""Clinical-semantics hardening: sex auto-detection and reasoning diagnosis guard."""
from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from nabdh.engine import _parse_sex, score
from nabdh.observations.schema import Observation
from nabdh.reasoning.validate import validate_reasoning_output

client = TestClient(app)


def _obs(canonical: str = "troponin_i", value: float = 0.18) -> Observation:
    return Observation(
        patient_id="P",
        name_raw=canonical,
        canonical=canonical,
        code=None,
        value=value,
        unit=None,
        ref_low=None,
        ref_high=None,
        abnormal_flag=None,
        captured_at=None,
        source="csv",
        quality="ok",
    )


# ---------------------------------------------------------------------------
# Sex encoding: inferred from the column, never asked of the user
# ---------------------------------------------------------------------------


def test_parse_sex_obeys_explicit_conventions() -> None:
    assert list(_parse_sex(pd.Series([0, 1]), "sex", "01")) == [0.0, 1.0]
    assert list(_parse_sex(pd.Series([1, 2]), "sex", "12")) == [0.0, 1.0]
    assert list(_parse_sex(pd.Series([1, 2]), "riagendr", "auto")) == [0.0, 1.0]
    assert list(_parse_sex(pd.Series(["M", "F", "male", "female"]), "sex", "auto")) == [
        0.0,
        1.0,
        0.0,
        1.0,
    ]
    assert pd.isna(_parse_sex(pd.Series([3]), "sex", "01")[0])


def test_generic_one_two_column_is_auto_detected() -> None:
    res = score(
        pd.DataFrame(
            [
                {"id": "M40", "age": 40, "sex": 1, "bmi": 26},
                {"id": "F40", "age": 40, "sex": 2, "bmi": 26},
            ]
        )
    )
    by_id = {row["id"]: row for row in res["results"]}
    assert "Sex: Male" in " ".join(by_id["M40"]["reasons"])
    assert "Sex: Female" in " ".join(by_id["F40"]["reasons"])
    assert not any("Breast cancer" in flag for flag in by_id["M40"]["flags"])
    assert not any("Cervical" in flag for flag in by_id["M40"]["flags"])
    assert any("auto-detected" in warning for warning in res["warnings"])


def test_generic_zero_one_column_is_auto_detected() -> None:
    res = score(
        pd.DataFrame(
            [
                {"id": "M40", "age": 40, "sex": 0, "bmi": 26},
                {"id": "F40", "age": 40, "sex": 1, "bmi": 26},
            ]
        )
    )
    by_id = {row["id"]: row for row in res["results"]}
    assert "Sex: Male" in " ".join(by_id["M40"]["reasons"])
    assert "Sex: Female" in " ".join(by_id["F40"]["reasons"])


def test_mixed_zero_and_two_does_not_flip_the_cohort() -> None:
    res = score(
        pd.DataFrame(
            [
                {"id": "M0", "age": 45, "sex": 0, "bmi": 28},
                {"id": "F1", "age": 45, "sex": 1, "bmi": 28},
                {"id": "BAD2", "age": 45, "sex": 2, "bmi": 28},
            ]
        )
    )
    by_id = {row["id"]: row for row in res["results"]}
    assert "Sex: Male" in " ".join(by_id["M0"]["reasons"])
    assert "Sex: Female" in " ".join(by_id["F1"]["reasons"])
    assert by_id["BAD2"]["tier"] == "Insufficient data"
    assert any("invalid sex" in warning for warning in res["warnings"])


def test_all_ones_generic_column_warns_and_defaults_to_zero_one() -> None:
    res = score(pd.DataFrame([{"id": "A", "age": 45, "sex": 1, "bmi": 28}]))
    assert "Sex: Female" in " ".join(res["results"][0]["reasons"])
    assert any("only 1s" in warning for warning in res["warnings"])


def test_riagendr_column_is_auto_detected() -> None:
    res = score(
        pd.DataFrame(
            [
                {"id": "R1", "age": 45, "riagendr": 1, "bmi": 28},
                {"id": "R2", "age": 45, "riagendr": 2, "bmi": 28},
            ]
        )
    )
    by_id = {row["id"]: row for row in res["results"]}
    assert "Sex: Male" in " ".join(by_id["R1"]["reasons"])
    assert "Sex: Female" in " ".join(by_id["R2"]["reasons"])


def test_blank_sex_is_missing_not_invalid() -> None:
    res = score(
        pd.DataFrame(
            [
                {"id": "B1", "age": 45, "sex": None, "bmi": 28},
                {"id": "B2", "age": 45, "sex": "  ", "bmi": 28},
            ]
        )
    )
    assert all(row["tier"] == "Insufficient data" for row in res["results"])
    assert any("missing sex" in warning for warning in res["warnings"])
    assert not any("invalid sex" in warning for warning in res["warnings"])


def test_invalid_sex_degrades_to_missing_with_warning() -> None:
    res = score(pd.DataFrame([{"id": "A", "age": 45, "sex": "other", "bmi": 28}]))
    row = res["results"][0]
    assert row["tier"] == "Insufficient data"
    assert row["risk_pct"] is None
    assert any("invalid sex" in warning for warning in res["warnings"])


# ---------------------------------------------------------------------------
# API: the convention field is gone; both encodings just work
# ---------------------------------------------------------------------------


def test_api_scores_one_two_without_a_convention_field() -> None:
    csv = b"id,age,sex,bmi\nM,40,1,26\nF,40,2,26\n"
    r = client.post("/api/score", files={"file": ("c.csv", csv, "text/csv")})
    assert r.status_code == 200
    by_id = {row["id"]: row for row in r.json()["results"]}
    assert "Sex: Male" in " ".join(by_id["M"]["reasons"])
    assert not any("Breast cancer" in flag for flag in by_id["M"]["flags"])
    assert "Sex: Female" in " ".join(by_id["F"]["reasons"])


def test_api_scores_zero_one_without_a_convention_field() -> None:
    csv = b"id,age,sex,bmi\nM,40,0,26\nF,40,1,26\n"
    r = client.post("/api/score", files={"file": ("c.csv", csv, "text/csv")})
    assert r.status_code == 200
    by_id = {row["id"]: row for row in r.json()["results"]}
    assert "Sex: Male" in " ".join(by_id["M"]["reasons"])
    assert "Sex: Female" in " ".join(by_id["F"]["reasons"])


def test_api_ignores_a_stale_convention_form_field() -> None:
    csv = b"id,age,sex,bmi\nM,40,1,26\nF,40,2,26\n"
    r = client.post(
        "/api/score",
        files={"file": ("c.csv", csv, "text/csv")},
        data={"sex_convention": "bogus"},
    )
    assert r.status_code == 200
    assert "Sex: Male" in " ".join(r.json()["results"][0]["reasons"])


def test_csv_export_works_without_a_convention_field() -> None:
    csv = b"id,age,sex,bmi\nM,40,1,26\nF,40,2,26\n"
    r = client.post("/api/score.csv", files={"file": ("c.csv", csv, "text/csv")})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "Sex: Male" in r.text


# ---------------------------------------------------------------------------
# Reasoning guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Troponin 0.18 confirms the patient has diabetes",
        "Troponin 0.18 is diagnostic of myocardial infarction",
        "This is a case of undiagnosed diabetes",
    ],
)
def test_validator_blocks_assertive_diagnosis_frames(text: str) -> None:
    with pytest.raises(ValueError, match="forbidden"):
        validate_reasoning_output(
            {"status": "ok", "claims": [{"rule_id": "CV-TROP-01", "text": text}]},
            [_obs()],
        )


@pytest.mark.parametrize(
    "text",
    [
        "Elevated troponin indicates a need for cardiology review",
        "Troponin 0.18 warrants clinician review for diagnostic confirmation.",
    ],
)
def test_validator_allows_legitimate_screening_language(text: str) -> None:
    result = validate_reasoning_output(
        {"status": "ok", "claims": [{"rule_id": "CV-TROP-01", "text": text}]},
        [_obs()],
    )
    assert result.status == "ok"


def test_refusal_rationale_with_diagnosis_is_dropped() -> None:
    result = validate_reasoning_output(
        {
            "status": "refusal",
            "rationale": "Troponin 0.18 confirms the patient has diabetes",
            "claims": [],
        },
        [_obs()],
    )
    assert result.status == "refusal"
    assert result.rationale is None
