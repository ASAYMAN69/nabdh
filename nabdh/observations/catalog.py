"""Versioned clinical test catalog: alias resolution, reference ranges, and unit sanity."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

CATALOG_PATH = Path(__file__).with_name("catalog.json")

_UNIT_SUFFIXES: dict[str, str] = {
    "_pg_ml": "pg/mL",
    "_ng_ml": "ng/mL",
    "_ng_l": "ng/L",
    "_mg_dl": "mg/dL",
    "_mg_l": "mg/L",
    "_nmol_l": "nmol/L",
    "_ug_l": "ug/L",
    "_ug_ml": "ug/mL",
    "_feu": "ng/mL FEU",
    "_au": "AU",
    "_pct": "%",
    "_fraction": "fraction",
}


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, Any]:
    """Load the bundled JSON clinical test catalog."""
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _alias_index() -> tuple[dict[str, dict[str, Any]], set[str]]:
    cat = load_catalog()
    idx: dict[str, dict[str, Any]] = {}
    for entry in cat.get("tests", []):
        idx[entry["canonical"].lower()] = entry
        for alias in entry.get("aliases", []):
            idx[alias.strip().lower()] = entry
    passthrough = {t.strip().lower() for t in cat.get("text_passthrough", [])}
    return idx, passthrough


def _normalize_key(raw_name: str) -> str:
    return raw_name.strip().lower().replace(" ", "_").replace("-", "_")


def resolve_test(
    raw_name: str,
    declared_unit: str | None = None,
) -> tuple[dict[str, Any] | None, str | None, bool]:
    """Resolve raw test/column name and optional unit suffix to (catalog_entry, unit, is_text).

    Strips known unit suffixes (e.g. ``nt_probnp_pg_ml`` -> ``nt_probnp``, ``pg/mL``).
    """
    idx, passthrough = _alias_index()
    key = _normalize_key(raw_name)
    inferred_unit = (
        declared_unit.strip()
        if isinstance(declared_unit, str) and declared_unit.strip()
        else None
    )

    if key in passthrough:
        return None, inferred_unit, True

    if key in idx:
        entry = idx[key]
        return entry, inferred_unit or entry.get("unit"), False

    for suffix, unit_val in _UNIT_SUFFIXES.items():
        if key.endswith(suffix):
            stem = key[: -len(suffix)]
            if stem in idx:
                entry = idx[stem]
                mapped_unit = entry.get("unit_aliases", {}).get(suffix.lstrip("_"), unit_val)
                return entry, inferred_unit or mapped_unit, False

    return None, inferred_unit, False


_UNIT_CONVERSIONS: dict[str, dict[str, tuple[float, str]]] = {
    # Troponin: 1 ng/L = 1 pg/mL = 0.001 ng/mL
    "troponin_i": {
        "ng_l": (0.001, "ng/mL"),
        "pg_ml": (0.001, "ng/mL"),
    },
    # D-dimer FEU: 1 ug/mL = 1 mg/L = 1000 ng/mL FEU
    "d_dimer": {
        "ug_ml": (1000.0, "ng/mL FEU"),
        "ug_ml_feu": (1000.0, "ng/mL FEU"),
        "mg_l": (1000.0, "ng/mL FEU"),
    },
    # hs-CRP: 1 mg/dL = 10 mg/L
    "hs_crp": {
        "mg_dl": (10.0, "mg/L"),
    },
    # LVEF entered as a 0-1 fraction rather than a percentage
    "lvef_pct": {
        "fraction": (100.0, "%"),
        "ratio": (100.0, "%"),
    },
}


def _norm_unit(unit: str) -> str:
    """Normalize a unit label for comparison (case, spaces, micro sign)."""
    return (
        unit.strip()
        .lower()
        .replace("µ", "u")
        .replace("μ", "u")
        .replace(" ", "_")
        .replace("/", "_")
    )


def normalize_observation_value(
    entry: dict[str, Any],
    value: float | None,
    unit: str | None,
) -> tuple[float | None, str | None, bool]:
    """Convert an explicitly declared alternate unit to the catalog unit.

    Returns ``(value, unit, converted)``. Conversion only happens when the unit is
    explicit and the factor is unambiguous. Implicit magnitude suspicion remains
    ``unit_suspect`` so the clinician confirms rather than the engine guessing.
    """
    if value is None or not unit:
        return value, unit, False
    canonical = entry.get("unit")
    norm = _norm_unit(unit)
    if canonical and norm == _norm_unit(canonical):
        return value, canonical, False

    factor_target = _UNIT_CONVERSIONS.get(entry["canonical"], {}).get(norm)
    if factor_target is not None:
        factor, target = factor_target
        return round(value * factor, 10), target, True

    # Aliases such as ug/L -> ng/mL FEU are numerically identical; keep the value.
    aliases = entry.get("unit_aliases", {})
    mapped = aliases.get(norm) or aliases.get(norm.replace("_", "/"))
    if mapped and canonical and mapped.lower() == canonical.lower():
        return value, canonical, False

    return value, unit, False


def _units_compatible(entry: dict[str, Any], unit: str | None) -> bool:
    """Return True if unit matches the catalog's primary unit (or equivalent pg/mL == ng/L)."""
    if not unit:
        return True
    canon_unit = entry.get("unit", "")
    if unit.lower() == canon_unit.lower():
        return True
    norm = unit.strip().lower().replace(" ", "_")
    unit_aliases = entry.get("unit_aliases", {})
    mapped = unit_aliases.get(norm) or unit_aliases.get(norm.replace("/", "_"))
    if mapped and mapped.lower() == canon_unit.lower():
        return True
    # pg/mL and ng/L are numerically identical for NT-proBNP
    if entry["canonical"] == "nt_probnp" and norm in ("pg/ml", "pg_ml", "ng/l", "ng_l"):
        return True
    return False


def compute_reference_range(
    entry: dict[str, Any],
    age: float | None,
    sex: float | None,
) -> tuple[float | None, float | None]:
    """Compute (ref_low, ref_high) from catalog metadata using age/sex when applicable."""
    ref = entry.get("ref") or {}
    if "age_bands" in ref:
        if age is None:
            return None, None
        for band in ref["age_bands"]:
            if age <= float(band["max_age"]):
                return (
                    float(band["low"]) if "low" in band else None,
                    float(band["high"]) if "high" in band else None,
                )
        return None, None

    if "age_adjusted_gt50_multiplier" in ref:
        if age is None:
            return None, None
        base_high = float(ref.get("high", 500.0))
        high = float(age) * float(ref["age_adjusted_gt50_multiplier"]) if age > 50.0 else base_high
        return None, round(high, 2)

    low = float(ref["low"]) if "low" in ref else None
    high = float(ref["high"]) if "high" in ref else None
    return low, high


def evaluate_observation_quality(
    entry: dict[str, Any],
    value: float | None,
    unit: str | None,
    ref_low: float | None,
    ref_high: float | None,
) -> tuple[str, str | None]:
    """Validate unit sanity, plausibility bounds, and compute informational severity_hint."""
    if value is None:
        return "non_numeric", "unknown"

    if not _units_compatible(entry, unit):
        return "unit_suspect", "unknown"

    plausible = entry.get("plausible")
    if plausible and value <= 0.0 and value < float(plausible[0]):
        return "out_of_plausible_range", "unknown"

    suspect_gt = entry.get("unit_suspect_gt")
    if suspect_gt is not None and value > float(suspect_gt):
        return "unit_suspect", "unknown"

    suspect_le = entry.get("unit_suspect_le")
    if suspect_le is not None and value <= float(suspect_le):
        return "unit_suspect", "unknown"

    suspect_lt = entry.get("unit_suspect_lt")
    if suspect_lt is not None and 0.0 < value < float(suspect_lt):
        return "unit_suspect", "unknown"

    if plausible and (value < float(plausible[0]) or value > float(plausible[1])):
        return "out_of_plausible_range", "unknown"

    if ref_low is None and ref_high is None:
        return "no_reference_range", "unknown"

    is_abnormal = (ref_low is not None and value < ref_low) or (
        ref_high is not None and value > ref_high
    )
    return "ok", ("abnormal" if is_abnormal else "normal")
