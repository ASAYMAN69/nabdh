"""Tests for Layer 2b versioned rules pack, Urgent Clinical Review, and CSV export."""
from __future__ import annotations

import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from nabdh.engine import score
from nabdh.rules import get_rule, load_rules_pack

client = TestClient(app)


def test_rules_pack_metadata_and_citations() -> None:
    pack = load_rules_pack()
    assert len(pack["rules"]) >= 20
    for r in pack["rules"]:
        assert r["rule_id"]
        assert r["version"]
        assert r["effective_date"]
        assert r["citation"]
        assert r["action"]


def test_urgent_cardiac_escalation_and_outreach_suppression() -> None:
    df = pd.DataFrame(
        [
            {
                "id": "CARD_URG",
                "age": 48,
                "sex": "M",
                "bmi": 24,
                "troponin_i": 0.18,
                "nt_probnp": 1400,
                "language": "AR",
            },
            {
                "id": "DM_URG",
                "age": 62,
                "sex": "F",
                "bmi": 30,
                "diagnosed_diabetes": "yes",
                "lvef_pct": 32,
            },
            {
                "id": "SUSP_UNIT",
                "age": 55,
                "sex": "M",
                "bmi": 25,
                "troponin_i_ng_ml": 4500,  # unit_suspect -> must NOT escalate
            },
        ]
    )
    res = score(df)
    by_id = {x["id"]: x for x in res["results"]}

    urg = by_id["CARD_URG"]
    assert urg["tier"] == "Urgent Clinical Review"
    assert urg["requires_signoff"] is True
    assert "outreach_preview" not in urg
    assert {a["rule_id"] for a in urg["urgent_alerts"]} == {"CV-TROP-01", "CV-NT-proBNP-01"}
    for a in urg["urgent_alerts"]:
        assert get_rule(a["rule_id"]) is not None
        assert a["citation"]

    # Known diabetic still escalates to Urgent Clinical Review on critical LVEF
    dm_urg = by_id["DM_URG"]
    assert dm_urg["tier"] == "Urgent Clinical Review"
    assert dm_urg["requires_signoff"] is True
    assert "outreach_preview" not in dm_urg

    # Unit-suspect observation must not trigger urgent escalation
    susp = by_id["SUSP_UNIT"]
    assert susp["tier"] != "Urgent Clinical Review"
    assert susp["urgent_alerts"] == []
    assert res["summary"]["observations_unit_suspect"] == 1
    assert res["summary"]["urgent"] == 2


def test_csv_export_includes_urgent_in_flagged() -> None:
    csv_text = (
        "id,age,sex,bmi,troponin_i\n"
        "U1,58,male,26,0.25\n"
        "L1,25,female,21,0.01\n"
    )
    r_flagged = client.post(
        "/api/score.csv",
        files={"file": ("u.csv", csv_text, "text/csv")},
        data={"min_tier": "flagged"},
    )
    assert r_flagged.status_code == 200
    assert "U1" in r_flagged.text
    assert "CV-TROP-01" in r_flagged.text
    assert "L1" not in r_flagged.text
