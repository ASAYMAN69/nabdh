"""Local CPU-capable quantised LLM reasoner (optional dependency: llama-cpp-python)."""
from __future__ import annotations

import json
from pathlib import Path

from nabdh.observations.schema import Observation
from nabdh.reasoning.base import ReasoningResult
from nabdh.reasoning.validate import validate_reasoning_output


class LocalReasoner:
    """Optional local quantised model wrapper; returns unavailable if unconfigured."""

    def __init__(self, model_path: str | Path | None = None, n_ctx: int = 2048) -> None:
        self.model_path = Path(model_path) if model_path else None
        self.n_ctx = n_ctx
        self._llm = None

    def is_available(self) -> bool:
        if not self.model_path or not self.model_path.exists():
            return False
        try:
            import llama_cpp  # noqa: F401
        except ImportError:
            return False
        return True

    def explain(
        self,
        patient_id: str,
        observations: list[Observation],
        candidate_rule_ids: list[str],
    ) -> ReasoningResult:
        if not self.is_available():
            return ReasoningResult(status="unavailable", rationale=None, citations=[])

        if self._llm is None:
            from llama_cpp import Llama

            self._llm = Llama(model_path=str(self.model_path), n_ctx=self.n_ctx, verbose=False)

        payload = {
            "patient_id": patient_id,
            "observations": [o.to_dict() for o in observations],
            "candidate_rule_ids": candidate_rule_ids,
        }
        prompt = (
            "Summarize only grounded preventive screening signals using the candidate_rule_ids. "
            "Never diagnose or prescribe. Return JSON: "
            '{"status":"ok","claims":[{"rule_id":"...","text":"..."}]}.\n'
            f"INPUT: {json.dumps(payload)}"
        )
        out = self._llm(prompt, max_tokens=256, temperature=0.0)
        text = out["choices"][0]["text"].strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return ReasoningResult(status="insufficient_evidence", rationale=None, citations=[])
        return validate_reasoning_output(parsed, observations)
