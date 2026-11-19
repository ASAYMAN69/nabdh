"""Tests for Layer 3 reasoning protocol, grounding validator, and zero-call invariant."""
from __future__ import annotations

import pandas as pd
import pytest

from nabdh.engine import score
from nabdh.observations import build_observation
from nabdh.reasoning import (
    CloudReasoner,
    StubReasoner,
    minimize_cloud_payload,
    validate_reasoning_output,
)


def test_score_performs_zero_model_or_network_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.request

    def _boom(*args, **kwargs):
        raise AssertionError("score() must never perform network calls")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)

    df = pd.DataFrame(
        [
            {
                "id": "N1",
                "age": 60,
                "sex": "M",
                "bmi": 28,
                "troponin_i": 0.15,
                "ecg_finding": "TWI",
            },
        ]
    )
    res = score(df)
    row = res["results"][0]
    assert row["tier"] == "Urgent Clinical Review"
    assert row["reasoning"]["status"] == "unavailable"


def test_validator_grounds_claims_and_rejects_diagnosis() -> None:
    obs = [
        build_observation(
            patient_id="R1",
            name_raw="nt_probnp",
            raw_value=1450,
            source="wide_csv",
            age=65,
            sex=0,
        )
    ]
    assert obs[0] is not None

    # Rejects diagnosis-shaped fields
    with pytest.raises(ValueError, match="forbidden"):
        validate_reasoning_output({"diagnosis": "Heart failure", "claims": []}, obs)

    # Drops ungrounded rule_ids and hallucinated numbers; keeps grounded claim
    validated = validate_reasoning_output(
        {
            "status": "ok",
            "claims": [
                {"rule_id": "FAKE-999", "text": "NT-proBNP 1450 needs echo"},
                {"rule_id": "CV-NT-proBNP-01", "text": "NT-proBNP 9999 is critical"},
                {"rule_id": "CV-NT-proBNP-01", "text": "NT-proBNP 1450 exceeds threshold"},
            ],
        },
        obs,
    )
    assert validated.status == "ok"
    assert "1450" in (validated.rationale or "")
    assert "9999" not in (validated.rationale or "")
    assert len(validated.citations) == 1
    assert validated.citations[0]["rule_id"] == "CV-NT-proBNP-01"

    # First-class refusal state
    refused = validate_reasoning_output({"status": "refusal", "rationale": "Ambiguous input"}, obs)
    assert refused.status == "refusal"


def test_cloud_reasoner_requires_opt_in_and_minimises_payload() -> None:
    obs = [
        build_observation(
            patient_id="C1",
            name_raw="nt_probnp",
            raw_value=1450,
            source="wide_csv",
            age=65,
            sex=0,
        ),
        build_observation(
            patient_id="C1",
            name_raw="hs_crp",
            raw_value=1.0,
            source="wide_csv",
            age=65,
            sex=0,
        ),
    ]
    obs_clean = [o for o in obs if o is not None]

    # Disabled by default
    r_off = CloudReasoner().explain("C1", obs_clean, ["CV-NT-proBNP-01"])
    assert r_off.status == "unavailable"

    # Minimised payload keeps only abnormal/unmapped observations and pseudonymous ID
    payload = minimize_cloud_payload("C1", obs_clean, ["CV-NT-proBNP-01"])
    assert "patient_id" not in payload
    assert isinstance(payload.get("pseudo_id"), str) and len(payload["pseudo_id"]) == 12
    assert payload["pseudo_id"] != "C1"
    assert "C1" not in str(payload)
    assert len(payload["observations"]) == 1
    assert payload["observations"][0]["name"] == "nt_probnp"
    assert "raw_text" not in payload["observations"][0]

    # StubReasoner always returns unavailable
    assert StubReasoner().explain("C1", obs_clean, []).status == "unavailable"
