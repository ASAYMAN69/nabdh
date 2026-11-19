"""Regression tests for cloud PII minimization, reasoning validation, outcomes, and safeguards."""
from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from nabdh.observations import build_observation
from nabdh.outcomes import get_outcomes_summary, record_outcome
from nabdh.reasoning import (
    CloudReasoner,
    minimize_cloud_payload,
    validate_reasoning_output,
)
from nabdh.safeguards import SMALL_CELL, harden_segment_suppression


def _make_obs(name: str, value: float, raw_text: str | None = None):
    obs = build_observation(
        patient_id="SECRET-PII-999",
        name_raw=name,
        raw_value=value,
        source="wide_csv",
        age=65,
        sex=0,
    )
    assert obs is not None
    if raw_text is not None:
        obs = replace(obs, raw_text=raw_text)
    return obs


def test_minimize_cloud_payload_strips_patient_id_and_raw_text() -> None:
    obs = [
        _make_obs(
            "nt_probnp",
            1450.0,
            raw_text="Patient John Doe SSN 123-45-6789 complains of dyspnea.",
        )
    ]
    payload = minimize_cloud_payload("SECRET-PII-999", obs, ["CV-NT-proBNP-01"])

    expected_pseudo = hashlib.sha256(b"nabdh:SECRET-PII-999").hexdigest()[:12]
    assert "patient_id" not in payload
    assert payload["pseudo_id"] == expected_pseudo
    assert "SECRET-PII-999" not in str(payload)
    assert len(payload["observations"]) == 1
    assert "raw_text" not in payload["observations"][0]
    assert "John Doe" not in str(payload)

    captured: list[dict] = []

    def _transport(p: dict) -> dict:
        captured.append(p)
        return {
            "status": "ok",
            "claims": [
                {"rule_id": "CV-NT-proBNP-01", "text": "NT-proBNP 1,450 warrants clinician review."}
            ],
        }

    res = CloudReasoner(allow_cloud_reasoning=True, transport=_transport).explain(
        "SECRET-PII-999", obs, ["CV-NT-proBNP-01"]
    )
    assert res.status == "ok"
    assert len(captured) == 1
    assert "patient_id" not in captured[0]
    assert "raw_text" not in captured[0]["observations"][0]


def test_validate_numeric_tolerance_and_comma_normalization() -> None:
    trop_obs = [_make_obs("troponin_i", 0.04)]
    # 0.08 is 100% drift from 0.04 and must be rejected (no 1.0 floor)
    bad = validate_reasoning_output(
        {
            "status": "ok",
            "claims": [{"rule_id": "CV-TROP-01", "text": "Troponin 0.08 is elevated."}],
        },
        trop_obs,
    )
    assert bad.status == "insufficient_evidence"

    # Within 5% relative tolerance (0.041 vs 0.04) is accepted
    good = validate_reasoning_output(
        {
            "status": "ok",
            "claims": [{"rule_id": "CV-TROP-01", "text": "Troponin 0.041 requires review."}],
        },
        trop_obs,
    )
    assert good.status == "ok"

    # Zero observation uses tight 1e-6 abs_tol
    zero_obs = [_make_obs("hs_crp", 0.0)]
    zero_bad = validate_reasoning_output(
        {
            "status": "ok",
            "claims": [{"rule_id": "CV-CRP-01", "text": "hs-CRP 0.01 noted."}],
        },
        zero_obs,
    )
    assert zero_bad.status == "insufficient_evidence"

    # Comma-formatted numbers normalize cleanly (1,200 -> 1200.0)
    bnp_obs = [_make_obs("nt_probnp", 1200.0)]
    comma_ok = validate_reasoning_output(
        {
            "status": "ok",
            "claims": [
                {
                    "rule_id": "CV-NT-proBNP-01",
                    "text": "NT-proBNP 1,200 exceeds threshold; diagnostic confirmation advised.",
                }
            ],
        },
        bnp_obs,
    )
    assert comma_ok.status == "ok"


@pytest.mark.parametrize(
    "payload",
    [
        {"claims": [{"rule_id": "CV-NT-proBNP-01", "diagnosis": "HF", "text": "NT-proBNP 1450"}]},
        {
            "claims": [
                {
                    "rule_id": "CV-NT-proBNP-01",
                    "meta": {"dosage": "40mg"},
                    "text": "NT-proBNP 1450",
                }
            ]
        },
        {"prescriptions": ["aspirin"], "claims": []},
        {
            "claims": [
                {"rule_id": "CV-NT-proBNP-01", "text": "Prescribe aspirin for NT-proBNP 1450"}
            ]
        },
        {
            "claims": [
                {
                    "rule_id": "CV-NT-proBNP-01",
                    "text": "Diagnosis: acute myocardial infarction at NT-proBNP 1450",
                }
            ]
        },
    ],
)
def test_validate_rejects_nested_forbidden_keys_and_prescriptive_text(payload: dict) -> None:
    obs = [_make_obs("nt_probnp", 1450.0)]
    with pytest.raises(ValueError, match="forbidden"):
        validate_reasoning_output(payload, obs)


def test_validate_allows_legitimate_screening_language_and_guards_malformed_claims() -> None:
    obs = [_make_obs("nt_probnp", 1450.0)]
    ok = validate_reasoning_output(
        {
            "status": "ok",
            "claims": [
                {
                    "rule_id": "CV-NT-proBNP-01",
                    "text": "NT-proBNP 1450 warrants clinician review for diagnostic confirmation.",
                }
            ],
        },
        obs,
    )
    assert ok.status == "ok"

    for bad_claims in (None, "not-a-list", 123, {"a": 1}):
        res = validate_reasoning_output({"status": "ok", "claims": bad_claims}, obs)
        assert res.status == "insufficient_evidence"


def test_outcomes_attendance_rate_capped_and_wal_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_file = tmp_path / "outcomes_audit.db"
    monkeypatch.setenv("NABDH_OUTCOMES_DB", str(db_file))

    # P1 engages and completes screening
    record_outcome("P1", outreach_choice="Confirm slot", completed_screening=True)
    # P2 opts out (not engaged) but still has completed_screening=True
    record_outcome("P2", outreach_choice="Opt out", completed_screening=True)
    # P3 has no outreach_choice yet but completed_screening=True
    record_outcome("P3", completed_screening=True)

    summary = get_outcomes_summary()
    assert summary["completed_screenings"] == 3
    assert summary["confirmed"] == 1
    assert summary["attendance_rate_pct"] == 100.0

    with sqlite3.connect(db_file) as con:
        mode = con.execute("PRAGMA journal_mode").fetchone()[0]
    assert str(mode).lower() == "wal"


def test_harden_segment_suppression_edge_cases() -> None:
    # 1 small cell + 2 large cells -> complementary suppression on smallest large cell
    segs_1 = [
        {"dimension": "district", "segment": "SmallA", "n": 4, "suppressed": False},
        {
            "dimension": "district",
            "segment": "LargeB",
            "n": 15,
            "suppressed": False,
            "flagged_pct": 10.0,
        },
        {
            "dimension": "district",
            "segment": "LargeC",
            "n": 40,
            "suppressed": False,
            "flagged_pct": 20.0,
        },
    ]
    out_1 = harden_segment_suppression(segs_1, small_cell=SMALL_CELL)
    by_seg_1 = {s["segment"]: s for s in out_1}
    assert by_seg_1["SmallA"]["suppressed"] is True
    assert by_seg_1["LargeB"]["suppressed"] is True
    assert by_seg_1["LargeB"]["n"] == "suppressed (complementary)"
    assert "flagged_pct" not in by_seg_1["LargeB"]
    assert by_seg_1["LargeC"]["suppressed"] is False

    # 1-cell <10 cohort -> suppressed cleanly
    segs_single = [{"dimension": "district", "segment": "OnlyOne", "n": 3, "suppressed": False}]
    out_single = harden_segment_suppression(segs_single, small_cell=SMALL_CELL)
    assert out_single[0]["suppressed"] is True
    assert out_single[0]["n"] == f"<{SMALL_CELL}"

    # 2 small cells + 1 large cell -> lone large cell also suppressed to prevent total subtraction
    segs_2_1 = [
        {"dimension": "language", "segment": "S1", "n": 2, "suppressed": False},
        {"dimension": "language", "segment": "S2", "n": 3, "suppressed": False},
        {
            "dimension": "language",
            "segment": "L1",
            "n": 25,
            "suppressed": False,
            "flagged_pct": 12.0,
        },
    ]
    out_2_1 = harden_segment_suppression(segs_2_1, small_cell=SMALL_CELL)
    assert all(s["suppressed"] is True for s in out_2_1)
