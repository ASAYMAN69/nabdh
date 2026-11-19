"""FastAPI endpoints for health checks, cohort scoring, and sanitized CSV export."""
from __future__ import annotations

from io import BytesIO, StringIO
from typing import Any

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from nabdh import __version__
from nabdh.engine import score
from nabdh.outcomes import get_outcomes_summary, record_outcome, reset_outcomes

router = APIRouter()
MAX_ROWS = 200_000
MAX_UPLOAD_BYTES = 64 * 1024 * 1024
MAX_COLUMNS = 1_000
_DELIMITERS = (",", ";", "\t", "|")
_CSV_HEADERS = {
    "Content-Disposition": "attachment; filename=nabdh_screening_priority.csv",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
}
VALID_TIERS = {
    "Urgent Clinical Review",
    "High",
    "Elevated",
    "Routine - overdue",
    "Routine",
    "Low",
    "Excluded",
    "Insufficient data",
}
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class OutcomeRecordRequest(BaseModel):
    patient_id: str
    outreach_choice: str | None = None
    completed_screening: bool | None = None
    tier: str | None = None
    pathway: str | None = None
    population: str | None = None


@router.get("/api/outcomes", tags=["outcomes"])
def read_outcomes() -> dict[str, Any]:
    return get_outcomes_summary()


@router.post("/api/outcomes", tags=["outcomes"])
def write_outcome(body: OutcomeRecordRequest) -> dict[str, Any]:
    try:
        return record_outcome(
            body.patient_id,
            outreach_choice=body.outreach_choice,
            completed_screening=body.completed_screening,
            tier=body.tier,
            pathway=body.pathway,
            population=body.population,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.delete("/api/outcomes", tags=["outcomes"])
def clear_outcomes() -> dict[str, Any]:
    return reset_outcomes()


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health_check() -> HealthResponse:
    return HealthResponse(status="ok", service="nabdh", version=__version__)


def _sniff_delimiter(sample: bytes) -> str:
    """Pick the most likely field delimiter from the CSV header line."""
    lines = sample.decode("utf-8-sig", errors="replace").splitlines()
    if not lines:
        return ","
    header = lines[0]
    counts = {delim: header.count(delim) for delim in _DELIMITERS}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


async def _read(file: UploadFile) -> pd.DataFrame:
    """Read and bound an uploaded CSV before it reaches the scoring engine."""
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if not raw:
        raise HTTPException(400, "Uploaded file is empty.")
    if len(raw) > MAX_UPLOAD_BYTES:
        if MAX_UPLOAD_BYTES >= 1024 * 1024:
            limit = f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB"
        else:
            limit = f"{MAX_UPLOAD_BYTES} bytes"
        raise HTTPException(413, f"Uploaded file exceeds the {limit} limit.")
    if b"\x00" in raw[:8192]:
        raise HTTPException(400, "Uploaded file is not a text CSV.")
    try:
        df = pd.read_csv(
            BytesIO(raw),
            sep=_sniff_delimiter(raw[:8192]),
            encoding="utf-8-sig",
        )
    except pd.errors.EmptyDataError as exc:
        raise HTTPException(400, "CSV file contains no columns.") from exc
    except (pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise HTTPException(
            400, "CSV could not be parsed; check the delimiter, quoting, and UTF-8 encoding."
        ) from exc
    except Exception as exc:
        raise HTTPException(400, "Invalid CSV file.") from exc
    if df.shape[1] > MAX_COLUMNS:
        raise HTTPException(413, f"Too many columns (max {MAX_COLUMNS}).")
    if len(df) > MAX_ROWS:
        raise HTTPException(413, f"Too many rows (max {MAX_ROWS}).")
    return df


def _sanitize_cell(val: Any) -> Any:
    """Neutralize spreadsheet formula-injection payloads in CSV string cells."""
    if not isinstance(val, str) or not val:
        return val
    stripped = val.lstrip(" ")
    if stripped and stripped[0] in _FORMULA_PREFIXES:
        try:
            float(val)
            return val
        except ValueError:
            return "'" + val
    return val


@router.post("/api/score", tags=["scoring"])
async def score_cohort(file: UploadFile = File(...)):
    df = await _read(file)
    try:
        return score(df)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except MemoryError as exc:
        raise HTTPException(413, "Cohort is too large to score in memory.") from exc


@router.post("/api/score.csv", response_class=PlainTextResponse, tags=["scoring"])
async def score_cohort_csv(
    file: UploadFile = File(...),
    min_tier: str = Form("all"),
):
    if min_tier not in VALID_TIERS and min_tier not in {"all", "flagged"}:
        raise HTTPException(422, f"Unsupported min_tier: {min_tier}")

    df = await _read(file)
    try:
        res = score(df)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except MemoryError as exc:
        raise HTTPException(413, "Cohort is too large to score in memory.") from exc

    results = res["results"]
    if not results:
        empty_cols = [
            "id",
            "age",
            "district",
            "language",
            "population",
            "tier",
            "pathway",
            "timing",
            "risk_pct",
            "dysglycaemia_pct",
            "confidence",
            "completeness",
            "reasons",
            "flags",
        ]
        buf = StringIO()
        pd.DataFrame(columns=empty_cols).to_csv(buf, index=False)
        return PlainTextResponse(
            buf.getvalue(),
            media_type="text/csv",
            headers=_CSV_HEADERS,
        )

    out = pd.DataFrame(results)
    for col in ("reasons", "flags"):
        if col in out:
            out[col] = out[col].map(lambda v: " | ".join(v) if isinstance(v, list) else v)
    if "urgent_alerts" in out:
        out["urgent_alerts"] = out["urgent_alerts"].map(
            lambda v: " | ".join(f"{a['rule_id']}: {a['action']}" for a in v)
            if isinstance(v, list)
            else v
        )
    if "outreach_preview" in out:
        out["outreach_preview"] = out["outreach_preview"].map(
            lambda v: v.get("message", "") if isinstance(v, dict) else v
        )

    if min_tier == "flagged":
        out = out[out["tier"].isin(["Urgent Clinical Review", "High", "Elevated"])]
    elif min_tier != "all":
        out = out[out["tier"] == min_tier]

    if "risk_pct" in out:
        out = out.sort_values("risk_pct", ascending=False, na_position="last")

    for col in out.columns:
        if out[col].dtype == object or pd.api.types.is_string_dtype(out[col]):
            out[col] = out[col].map(_sanitize_cell)

    buf = StringIO()
    out.to_csv(buf, index=False)
    return PlainTextResponse(
        buf.getvalue(),
        media_type="text/csv",
        headers=_CSV_HEADERS,
    )
