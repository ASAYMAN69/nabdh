"""Layer 3 optional clinical reasoning protocol and default no-op StubReasoner."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from nabdh.observations.schema import Observation


@dataclass(frozen=True, slots=True)
class ReasoningResult:
    """Validated reasoning payload attached to a patient row or /api/explain response."""

    status: str  # "ok" | "unavailable" | "pending" | "refusal" | "insufficient_evidence"
    rationale: str | None = None
    citations: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Reasoner(Protocol):
    """Pluggable clinical reasoning interface (never a source of thresholds)."""

    def explain(
        self,
        patient_id: str,
        observations: list[Observation],
        candidate_rule_ids: list[str],
    ) -> ReasoningResult:
        """Interpret unmapped/free-text observations and narrate cited pack rules."""
        ...


class StubReasoner:
    """Default zero-call reasoner used when Layer 3 is unconfigured."""

    def explain(
        self,
        patient_id: str,
        observations: list[Observation],
        candidate_rule_ids: list[str],
    ) -> ReasoningResult:
        return ReasoningResult(status="unavailable", rationale=None, citations=[])
