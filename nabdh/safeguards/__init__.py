"""Equity auditing, small-cell suppression, and row-level redaction safeguards."""
from __future__ import annotations

from typing import Any

from nabdh.engine import SMALL_CELL, _segments, _suppressed_values


def harden_segment_suppression(
    segments: list[dict[str, Any]],
    *,
    small_cell: int = SMALL_CELL,
) -> list[dict[str, Any]]:
    """Apply complementary suppression across segment dimensions for small-cell edge cases.

    Ensures:
    - Any segment with integer ``n < small_cell`` is suppressed.
    - If a dimension has exactly 1 suppressed cell and >=1 unsuppressed cell, the
      smallest unsuppressed cell is also suppressed (complementary suppression).
    - If a dimension has >=1 suppressed cell and only 1 unsuppressed cell remaining,
      that lone unsuppressed cell is also suppressed to prevent subtraction against
      the cohort total.
    """
    copied = [dict(s) for s in segments]
    by_dim: dict[str, list[dict[str, Any]]] = {}
    for seg in copied:
        by_dim.setdefault(str(seg.get("dimension", "")), []).append(seg)

    for dim_segs in by_dim.values():
        for seg in dim_segs:
            n_val = seg.get("n")
            if isinstance(n_val, int) and n_val < small_cell:
                seg["n"] = f"<{small_cell}"
                seg["suppressed"] = True
                seg.pop("flagged_pct", None)
                seg.pop("mean_risk_pct", None)

        suppressed_count = sum(1 for s in dim_segs if s.get("suppressed"))
        unsuppressed = [s for s in dim_segs if not s.get("suppressed")]

        if (
            suppressed_count > 0
            and unsuppressed
            and (suppressed_count == 1 or len(unsuppressed) == 1)
        ):
            target = min(
                unsuppressed,
                key=lambda s: s["n"] if isinstance(s.get("n"), int) else float("inf"),
            )
            target["n"] = "suppressed (complementary)"
            target["suppressed"] = True
            target.pop("flagged_pct", None)
            target.pop("mean_risk_pct", None)

    return copied


__all__ = ["SMALL_CELL", "_segments", "_suppressed_values", "harden_segment_suppression"]
