"""Tests for Layer 1 observation capture, catalog alias resolution, and unit sanity."""
from __future__ import annotations

import pandas as pd

from nabdh.observations import (
    capture_wide_dataframe,
    ingest_long_observations,
    resolve_test,
)


def test_catalog_alias_and_unit_suffix_resolution() -> None:
    entry, unit, is_text = resolve_test("nt_probnp_pg_ml")
    assert not is_text and entry is not None
    assert entry["canonical"] == "nt_probnp"
    assert unit == "pg/mL"

    entry_cac, unit_cac, _ = resolve_test("cac_score")
    assert entry_cac is not None
    assert entry_cac["canonical"] == "coronary_calcium_score"
    assert unit_cac == "AU"

    _, _, is_notes = resolve_test("clinical_notes")
    assert is_notes is True


def test_unit_sanity_and_quality_states() -> None:
    df = pd.DataFrame(
        [
            {
                "id": "P1",
                "age": 60,
                "sex": 0,
                "troponin_i_ng_ml": 4500,  # pg/mL magnitude in ng/mL -> unit_suspect
                "lvef_pct": 0.45,          # 0-1 fraction instead of % -> unit_suspect
                "hs_crp": "pending",       # non_numeric, never coerced to 0
                "mystery_marker": 12.3,    # unmapped
            },
            {
                "id": "P2",
                "age": None,
                "sex": 1,
                "nt_probnp": 250,          # age-banded ref range missing age -> no_reference_range
                "d_dimer": 999999,         # out_of_plausible_range
            },
        ]
    )
    obs_rows = capture_wide_dataframe(
        df,
        claimed_columns={"id", "age", "sex"},
        ages=df["age"],
        sexes=df["sex"],
        patient_ids=df["id"],
    )
    p1 = {o.name_raw: o for o in obs_rows[0]}
    assert p1["troponin_i_ng_ml"].quality == "unit_suspect"
    assert p1["lvef_pct"].quality == "unit_suspect"
    assert p1["hs_crp"].quality == "non_numeric"
    assert p1["hs_crp"].value is None
    assert p1["mystery_marker"].quality == "unmapped"

    p2 = {o.name_raw: o for o in obs_rows[1]}
    assert p2["nt_probnp"].quality == "no_reference_range"
    assert p2["d_dimer"].quality == "out_of_plausible_range"


def test_long_format_observation_ingest() -> None:
    grouped = ingest_long_observations(
        [
            {"patient_id": "L1", "test_name": "troponin_i", "value": 0.12, "unit": "ng/mL"},
            {"patient_id": "L1", "test_name": "nt_probnp", "value": 1200, "unit": "pg/mL"},
        ],
        patient_meta={"L1": (68.0, 0.0)},
    )
    assert len(grouped["L1"]) == 2
    assert grouped["L1"][0].quality == "ok"
    assert grouped["L1"][1].ref_high == 450.0
