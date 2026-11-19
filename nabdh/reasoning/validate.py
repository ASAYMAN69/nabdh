"""Strict schema and grounding validator for Layer 3 reasoning outputs."""
from __future__ import annotations

import re
from typing import Any

from nabdh.observations.schema import Observation
from nabdh.reasoning.base import ReasoningResult
from nabdh.rules.pack import rules_by_id

FORBIDDEN_DIAGNOSIS_KEYS = frozenset(
    {
        "diagnosis",
        "diagnoses",
        "diagnosis_confirmed",
        "assessment",
        "treatment",
        "prescription",
        "prescriptions",
        "medication",
        "dosage",
    }
)
_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9_.-])(-?\d+(?:\.\d+)?)(?![A-Za-z0-9_.-])")
_COMMA_THOUSANDS_RE = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")
_DIAGNOSIS_TERMS = (
    r"diabetes|prediabetes|dysglyca?emia|hyperglyc[ae]?mia|"
    r"hypertension|hypotension|"
    r"myocardial infarction|heart failure|coronary artery disease|"
    r"dyslipida?emia|hyperlipida?emia|"
    r"chronic kidney disease|kidney failure|renal failure|"
    r"cancer|carcinoma|tumou?r|malignancy|"
    r"stroke|transient ischa?emic attack|"
    r"copd|asthma|pneumonia|sepsis|infection|"
    r"ana?emia|thyroid disease|"
    r"disease|disorder|syndrome"
)
_FORBIDDEN_CLAIM_TEXT_RE = re.compile(
    r"(?i)(?:"
    r"\b(?:prescribe|prescribing|prescription\s*:)\b"
    r"|\bdiagnos(?:is|ed)\s*(?::|\bwith\b|\bis\b|\bof\b)"
    r"|\b(?:start|initiate)\s+(?:medication|treatment|therapy|aspirin|statin|metformin|insulin)\b"
    r"|\bdosage\s*:"
    r"|\b(?:confirms?|indicates?|proves?|establishes?)\b[^.;]{0,40}"
    r"\b(?:has|have|suffers?\s+from|suffering\s+from)\b(?!\s+(?:not|no)\b)"
    r"[^.;]{0,30}\b(?:" + _DIAGNOSIS_TERMS + r")\b"
    r"|\bdiagnostic\s+(?:of|for)\b"
    r"|\b(?:is|are)\s+(?:a\s+)?case\s+of\b"
    r"|\bconsistent\s+with\s+(?:a\s+)?diagnosis\b"
    r")"
)


def _find_forbidden_keys(obj: Any) -> set[str]:
    """Recursively collect any forbidden diagnostic/treatment keys in nested dicts/lists."""
    found: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            lk = str(k).strip().lower()
            if lk in FORBIDDEN_DIAGNOSIS_KEYS:
                found.add(lk)
            found.update(_find_forbidden_keys(v))
    elif isinstance(obj, list):
        for item in obj:
            found.update(_find_forbidden_keys(item))
    return found


def _numbers_in_text(text: str) -> list[float]:
    normalized = _COMMA_THOUSANDS_RE.sub("", text)
    out: list[float] = []
    for m in _NUMBER_RE.findall(normalized):
        try:
            out.append(float(m))
        except ValueError:
            continue
    return out


def _matches_input_numbers(
    claim_text: str,
    obs_values: list[float],
    rel_tol: float = 0.05,
) -> bool:
    """Ensure every number cited in a claim matches an input observation within tolerance."""
    nums = _numbers_in_text(claim_text)
    if not nums:
        return True
    if not obs_values:
        return False
    for n in nums:
        matched = False
        for ov in obs_values:
            tol = 1e-6 if ov == 0 else rel_tol * abs(ov)
            if abs(n - ov) <= tol:
                matched = True
                break
        if not matched:
            return False
    return True


def validate_reasoning_output(
    raw: dict[str, Any],
    observations: list[Observation],
) -> ReasoningResult:
    """Validate and ground raw Layer 3 JSON output against input observations and the rules pack.

    - Rejects any payload containing diagnosis/treatment-shaped keys.
    - Drops any claim whose ``rule_id`` does not resolve to ``RULES_PACK``.
    - Drops any claim citing numeric values absent from input observations (>5% drift).
    - Preserves ``refusal`` and ``insufficient_evidence`` as valid first-class states.
    """
    if not isinstance(raw, dict):
        return ReasoningResult(status="refusal", rationale="Invalid reasoning payload structure.")

    forbidden_found = _find_forbidden_keys(raw)
    if forbidden_found:
        raise ValueError(
            "Rejected reasoning output containing forbidden diagnostic/treatment fields: "
            + ", ".join(sorted(forbidden_found))
        )

    status = str(raw.get("status", "ok")).strip().lower()
    if status in ("refusal", "insufficient_evidence", "unavailable"):
        rationale = raw.get("rationale")
        if isinstance(rationale, str) and _FORBIDDEN_CLAIM_TEXT_RE.search(rationale):
            rationale = None
        return ReasoningResult(
            status=status,
            rationale=rationale,
            citations=[],
        )

    claims = raw.get("claims")
    if not isinstance(claims, list):
        return ReasoningResult(
            status="insufficient_evidence",
            rationale="Malformed or missing claims list in reasoning output.",
            citations=[],
        )

    pack = rules_by_id()
    obs_values = [o.value for o in observations if o.value is not None]

    grounded_claims: list[str] = []
    citations: list[dict[str, str]] = []
    seen_rules: set[str] = set()

    for claim in claims:
        if not isinstance(claim, dict):
            continue
        rid = str(claim.get("rule_id", "")).strip()
        text = str(claim.get("text", "")).strip()
        if text and _FORBIDDEN_CLAIM_TEXT_RE.search(text):
            raise ValueError(
                "Rejected reasoning output containing forbidden diagnostic/"
                "prescriptive statement in claim text."
            )
        if not rid or rid not in pack:
            continue
        if not text or not _matches_input_numbers(text, obs_values):
            continue
        grounded_claims.append(text)
        if rid not in seen_rules:
            seen_rules.add(rid)
            rule = pack[rid]
            citations.append(
                {
                    "rule_id": rid,
                    "guideline": rule["guideline"],
                    "citation": rule["citation"],
                    "version": rule["version"],
                }
            )

    if not grounded_claims:
        return ReasoningResult(
            status="insufficient_evidence",
            rationale="No grounded claims survived rules-pack and numeric validation.",
            citations=[],
        )

    return ReasoningResult(
        status="ok",
        rationale=" ".join(grounded_claims),
        citations=citations,
    )
