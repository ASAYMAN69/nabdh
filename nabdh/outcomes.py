"""SQLite-backed outcome & recall conversion tracker for Challenge 04 evaluation."""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "outcomes.db"
VALID_CHOICES = frozenset({"Confirm slot", "Reschedule", "Opt out"})


def _db_path() -> Path:
    env = os.environ.get("NABDH_OUTCOMES_DB")
    p = Path(env) if env else DEFAULT_DB
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(_db_path(), timeout=10.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS outcomes (
            patient_id TEXT PRIMARY KEY,
            outreach_choice TEXT,
            completed_screening INTEGER NOT NULL DEFAULT 0,
            tier TEXT,
            pathway TEXT,
            population TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    return con


def record_outcome(
    patient_id: str,
    *,
    outreach_choice: str | None = None,
    completed_screening: bool | None = None,
    tier: str | None = None,
    pathway: str | None = None,
    population: str | None = None,
) -> dict[str, Any]:
    """Insert or update a patient's outreach response and screening completion status."""
    pid = str(patient_id).strip()
    if not pid:
        raise ValueError("patient_id is required.")
    if outreach_choice is not None and outreach_choice not in VALID_CHOICES:
        raise ValueError(f"Unsupported outreach_choice: {outreach_choice}")

    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        existing = con.execute(
            "SELECT * FROM outcomes WHERE patient_id = ?", (pid,)
        ).fetchone()
        new_choice = (
            outreach_choice
            if outreach_choice is not None
            else (existing["outreach_choice"] if existing else None)
        )
        new_completed = (
            int(completed_screening)
            if completed_screening is not None
            else (int(existing["completed_screening"]) if existing else 0)
        )
        new_tier = tier if tier is not None else (existing["tier"] if existing else None)
        new_pathway = (
            pathway if pathway is not None else (existing["pathway"] if existing else None)
        )
        new_pop = (
            population if population is not None else (existing["population"] if existing else None)
        )
        con.execute(
            """
            INSERT INTO outcomes (
                patient_id, outreach_choice, completed_screening,
                tier, pathway, population, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(patient_id) DO UPDATE SET
                outreach_choice = excluded.outreach_choice,
                completed_screening = excluded.completed_screening,
                tier = excluded.tier,
                pathway = excluded.pathway,
                population = excluded.population,
                updated_at = excluded.updated_at
            """,
            (pid, new_choice, new_completed, new_tier, new_pathway, new_pop, now),
        )
    return get_outcomes_summary()


def get_outcomes_summary() -> dict[str, Any]:
    """Return aggregate conversion funnel counts and per-patient recorded states."""
    with _conn() as con:
        rows = con.execute("SELECT * FROM outcomes").fetchall()

    confirmed = sum(1 for r in rows if r["outreach_choice"] == "Confirm slot")
    rescheduled = sum(1 for r in rows if r["outreach_choice"] == "Reschedule")
    opted_out = sum(1 for r in rows if r["outreach_choice"] == "Opt out")
    completed = sum(1 for r in rows if int(r["completed_screening"]) == 1)
    engaged = confirmed + rescheduled
    engaged_completed = sum(
        1
        for r in rows
        if int(r["completed_screening"]) == 1
        and r["outreach_choice"] in ("Confirm slot", "Reschedule")
    )
    attendance_rate = round(100.0 * engaged_completed / engaged, 1) if engaged > 0 else 0.0

    by_patient = {
        r["patient_id"]: {
            "outreach_choice": r["outreach_choice"],
            "completed_screening": bool(r["completed_screening"]),
            "tier": r["tier"],
            "pathway": r["pathway"],
            "population": r["population"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    }
    return {
        "total_recorded": len(rows),
        "confirmed": confirmed,
        "rescheduled": rescheduled,
        "opted_out": opted_out,
        "completed_screenings": completed,
        "attendance_rate_pct": attendance_rate,
        "by_patient": by_patient,
    }


def reset_outcomes() -> dict[str, Any]:
    """Clear all recorded outcomes (useful for resetting a live demo)."""
    with _conn() as con:
        con.execute("DELETE FROM outcomes")
    return get_outcomes_summary()
