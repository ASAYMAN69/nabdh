"""Tests for Challenge 04 genomic, Well-Child, outcome tracker, and UAE demo cohort."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from nabdh.engine import score

client = TestClient(app)


def test_genomic_and_well_child_rules() -> None:
    df = pd.DataFrame(
        [
            {
                "id": "GEN_ADULT",
                "age": 26,
                "sex": "F",
                "bmi": 22,
                "prs_cardiometabolic": "high",
                "thalassemia_carrier": "yes",
            },
            {
                "id": "WCV_CHILD",
                "age": 3,
                "sex": "M",
                "bmi": 16.5,
                "missed_well_child_visits": 2,
                "developmental_delay_flag": "yes",
                "immunization_status": "overdue",
                "g6pd_status": "deficient",
            },
        ]
    )
    by_id = {x["id"]: x for x in score(df)["results"]}

    ad = by_id["GEN_ADULT"]
    assert ad["tier"] == "Elevated"
    assert any("polygenic risk" in f for f in ad["flags"])
    assert any("Thalassemia" in f for f in ad["flags"])

    ch = by_id["WCV_CHILD"]
    assert ch["stream"] == "paediatric"
    assert ch["tier"] == "High"
    ch_flags = " | ".join(ch["flags"])
    assert "Developmental milestone concern" in ch_flags
    assert "Overdue Well-Child Visit" in ch_flags
    assert "immunisation overdue" in ch_flags
    assert "G6PD deficiency" in ch_flags


def test_outcomes_tracker_endpoints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NABDH_OUTCOMES_DB", str(tmp_path / "test_outcomes.db"))

    r0 = client.get("/api/outcomes")
    assert r0.status_code == 200
    assert r0.json()["total_recorded"] == 0

    r1 = client.post(
        "/api/outcomes",
        json={
            "patient_id": "UAE-WOW-029",
            "outreach_choice": "Confirm slot",
            "tier": "Elevated",
            "population": "adult",
        },
    )
    assert r1.status_code == 200
    assert r1.json()["confirmed"] == 1
    assert r1.json()["attendance_rate_pct"] == 0.0

    r2 = client.post(
        "/api/outcomes",
        json={"patient_id": "UAE-WOW-029", "completed_screening": True},
    )
    assert r2.status_code == 200
    assert r2.json()["completed_screenings"] == 1
    assert r2.json()["attendance_rate_pct"] == 100.0

    r3 = client.delete("/api/outcomes")
    assert r3.status_code == 200
    assert r3.json()["total_recorded"] == 0


def test_uae_demo_cohort_scores_cleanly() -> None:
    demo = Path(__file__).resolve().parents[1] / "data" / "sample" / "uae_demo_cohort.csv"
    assert demo.exists()
    r = client.post(
        "/api/score",
        files={"file": ("uae_demo_cohort.csv", demo.read_bytes(), "text/csv")},
    )
    assert r.status_code == 200
    payload = r.json()
    by_id = {x["id"]: x for x in payload["results"]}
    assert payload["summary"]["rows"] == 60
    assert by_id["UAE-URG-101"]["tier"] == "Urgent Clinical Review"
    assert "outreach_preview" not in by_id["UAE-URG-101"]
    assert by_id["UAE-UNIT-102"]["tier"] != "Urgent Clinical Review"
    assert by_id["UAE-WCV-201"]["tier"] == "High"
    assert by_id["UAE-SM-401"]["district"] == "<suppressed (<10)>"
