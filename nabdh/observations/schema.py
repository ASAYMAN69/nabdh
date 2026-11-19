"""Canonical observation schema for arbitrary / niche clinical test ingestion."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

VALID_QUALITIES = frozenset(
    {
        "ok",
        "unmapped",
        "unit_suspect",
        "non_numeric",
        "out_of_plausible_range",
        "no_reference_range",
    }
)


@dataclass(frozen=True, slots=True)
class Observation:
    """Structured clinical observation captured from wide CSV, long CSV/JSON, or FHIR."""

    patient_id: str
    name_raw: str
    canonical: str | None
    code: str | None
    value: float | None
    unit: str | None
    ref_low: float | None
    ref_high: float | None
    abnormal_flag: str | None
    captured_at: str | None
    source: str
    quality: str
    severity_hint: str | None = None
    raw_text: str | None = None
    raw_value: float | None = None
    raw_unit: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe dictionary, omitting absent provenance fields."""
        d = asdict(self)
        for key in ("raw_text", "raw_value", "raw_unit"):
            if d[key] is None:
                d.pop(key)
        return d
