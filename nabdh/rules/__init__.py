"""Clinical guideline rules for adult screening, WHO paediatric growth, and versioned rules pack."""
from __future__ import annotations

from nabdh.rules.pack import (
    evaluate_observation_rules,
    evaluate_preventive_rules,
    evaluate_vital_rules,
    get_rule,
    load_rules_pack,
    rules_by_id,
)

_ENGINE_EXPORTS = frozenset({"_has_metabolic_triad", "_is_due", "_tier_and_pathway", "bmi_zscore"})


def __getattr__(name: str):
    if name in _ENGINE_EXPORTS:
        from nabdh import engine

        return getattr(engine, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "_has_metabolic_triad",
    "_is_due",
    "_tier_and_pathway",
    "bmi_zscore",
    "evaluate_observation_rules",
    "evaluate_preventive_rules",
    "evaluate_vital_rules",
    "get_rule",
    "load_rules_pack",
    "rules_by_id",
]
