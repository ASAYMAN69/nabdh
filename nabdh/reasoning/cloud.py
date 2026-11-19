"""Opt-in cloud reasoner with strict payload minimisation."""
from __future__ import annotations

import hashlib
from typing import Any, Callable

from nabdh.observations.schema import Observation
from nabdh.reasoning.base import ReasoningResult
from nabdh.reasoning.validate import validate_reasoning_output


def minimize_cloud_payload(
    patient_id: str,
    observations: list[Observation],
    candidate_rule_ids: list[str],
) -> dict[str, Any]:
    """Strip all identifiers and non-observation fields before any cloud call."""
    minimal_obs = [
        {
            "name": o.canonical or o.name_raw,
            "value": o.value,
            "unit": o.unit,
            "quality": o.quality,
        }
        for o in observations
        if o.quality != "ok" or o.severity_hint in ("abnormal", "critical")
    ]
    pseudo_id = hashlib.sha256(f"nabdh:{patient_id}".encode()).hexdigest()[:12]
    return {
        "pseudo_id": pseudo_id,
        "observations": minimal_obs,
        "candidate_rule_ids": list(candidate_rule_ids),
    }


class CloudReasoner:
    """Explicit opt-in cloud reasoner; refuses to send data unless allow_cloud_reasoning=True."""

    def __init__(
        self,
        *,
        allow_cloud_reasoning: bool = False,
        transport: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.allow_cloud_reasoning = allow_cloud_reasoning
        self.transport = transport

    def explain(
        self,
        patient_id: str,
        observations: list[Observation],
        candidate_rule_ids: list[str],
    ) -> ReasoningResult:
        if not self.allow_cloud_reasoning or self.transport is None:
            return ReasoningResult(status="unavailable", rationale=None, citations=[])
        payload = minimize_cloud_payload(patient_id, observations, candidate_rule_ids)
        raw = self.transport(payload)
        return validate_reasoning_output(raw, observations)
