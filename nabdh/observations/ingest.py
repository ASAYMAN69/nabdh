"""Wide CSV and long-format observation ingestion into canonical Observation records."""
from __future__ import annotations

import math
from typing import Any, Iterable

import pandas as pd

from nabdh.observations.catalog import (
    compute_reference_range,
    evaluate_observation_quality,
    normalize_observation_value,
    resolve_test,
)
from nabdh.observations.schema import Observation


def _coerce_float(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
        return float(val)
    s = str(val).strip()
    if not s or s.lower() in {"na", "nan", "null", "none", "n/a", "."}:
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    return None if (math.isnan(f) or math.isinf(f)) else f


def _is_missing_cell(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, float) and math.isnan(val):
        return True
    s = str(val).strip()
    return not s or s.lower() in {"na", "nan", "null", "none", "n/a"}


def build_observation(
    *,
    patient_id: str,
    name_raw: str,
    raw_value: Any,
    source: str,
    age: float | None = None,
    sex: float | None = None,
    declared_unit: str | None = None,
    source_ref_low: float | None = None,
    source_ref_high: float | None = None,
    abnormal_flag: str | None = None,
    captured_at: str | None = None,
) -> Observation | None:
    """Build a single validated Observation, or None if the cell is empty."""
    if _is_missing_cell(raw_value):
        return None

    entry, unit, is_text = resolve_test(name_raw, declared_unit=declared_unit)
    num_val = _coerce_float(raw_value)
    raw_text = None if num_val is not None else str(raw_value).strip()

    if is_text or entry is None:
        return Observation(
            patient_id=patient_id,
            name_raw=name_raw,
            canonical=name_raw.strip().lower() if is_text else None,
            code=None,
            value=num_val,
            unit=unit,
            ref_low=source_ref_low,
            ref_high=source_ref_high,
            abnormal_flag=abnormal_flag,
            captured_at=captured_at,
            source=source,
            quality="unmapped" if not is_text else "non_numeric",
            severity_hint="unknown",
            raw_text=raw_text if raw_text is not None else str(raw_value).strip(),
        )

    if num_val is None:
        return Observation(
            patient_id=patient_id,
            name_raw=name_raw,
            canonical=entry["canonical"],
            code=entry.get("code"),
            value=None,
            unit=unit,
            ref_low=source_ref_low,
            ref_high=source_ref_high,
            abnormal_flag=abnormal_flag,
            captured_at=captured_at,
            source=source,
            quality="non_numeric",
            severity_hint="unknown",
            raw_text=raw_text,
        )

    ref_low, ref_high = compute_reference_range(entry, age=age, sex=sex)
    if ref_low is None and source_ref_low is not None:
        ref_low = source_ref_low
    if ref_high is None and source_ref_high is not None:
        ref_high = source_ref_high

    converted_value, converted_unit, was_converted = normalize_observation_value(
        entry, num_val, unit
    )
    quality, sev_hint = evaluate_observation_quality(
        entry,
        value=converted_value,
        unit=converted_unit,
        ref_low=ref_low,
        ref_high=ref_high,
    )
    return Observation(
        patient_id=patient_id,
        name_raw=name_raw,
        canonical=entry["canonical"],
        code=entry.get("code"),
        value=converted_value,
        unit=converted_unit,
        ref_low=ref_low,
        ref_high=ref_high,
        abnormal_flag=abnormal_flag,
        captured_at=captured_at,
        source=source,
        quality=quality,
        severity_hint=sev_hint,
        raw_value=num_val if was_converted else None,
        raw_unit=unit if was_converted else None,
    )


def capture_wide_dataframe(
    df_raw: pd.DataFrame,
    claimed_columns: set[str],
    ages: pd.Series | None = None,
    sexes: pd.Series | None = None,
    patient_ids: pd.Series | None = None,
) -> list[list[Observation]]:
    """Capture all unmapped wide-CSV columns as per-row Observation lists."""
    extra_cols = [c for c in df_raw.columns if str(c).strip().lower() not in claimed_columns]
    if not extra_cols:
        return [[] for _ in range(len(df_raw))]

    out: list[list[Observation]] = []
    for pos in range(len(df_raw)):
        row_obs: list[Observation] = []
        pid = (
            str(patient_ids.iloc[pos])
            if patient_ids is not None
            else str(pos + 1)
        )
        age_val = _coerce_float(ages.iloc[pos]) if ages is not None else None
        sex_val = _coerce_float(sexes.iloc[pos]) if sexes is not None else None
        for col in extra_cols:
            obs = build_observation(
                patient_id=pid,
                name_raw=str(col),
                raw_value=df_raw.iloc[pos][col],
                source="wide_csv",
                age=age_val,
                sex=sex_val,
            )
            if obs is not None:
                row_obs.append(obs)
        out.append(row_obs)
    return out


def ingest_long_observations(
    records: Iterable[dict[str, Any]],
    patient_meta: dict[str, tuple[float | None, float | None]] | None = None,
) -> dict[str, list[Observation]]:
    """Ingest long-format observation dicts (`patient_id`, `test_name`, `value`, `unit`, ...)."""
    grouped: dict[str, list[Observation]] = {}
    meta = patient_meta or {}
    for rec in records:
        pid = str(rec.get("patient_id") or rec.get("id") or "").strip()
        test_name = str(rec.get("test_name") or rec.get("name") or "").strip()
        if not pid or not test_name:
            continue
        age_val, sex_val = meta.get(pid, (None, None))
        obs = build_observation(
            patient_id=pid,
            name_raw=test_name,
            raw_value=rec.get("value"),
            source="long_csv",
            age=age_val,
            sex=sex_val,
            declared_unit=rec.get("unit"),
            source_ref_low=_coerce_float(rec.get("ref_low")),
            source_ref_high=_coerce_float(rec.get("ref_high")),
            abnormal_flag=rec.get("abnormal_flag"),
            captured_at=rec.get("captured_at"),
        )
        if obs is not None:
            grouped.setdefault(pid, []).append(obs)
    return grouped
