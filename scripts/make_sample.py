"""Create a 600-row demo cohort CSV strictly from unseen NHANES 2021-23 data.

Zero rows come from the 2017-20 training cycle.
Includes:
- 520 adults (incl. screenable, known-DM, and borderline) from NHANES 2021-23
- 80 children/adolescents (ages 1-19y) from NHANES 2021-23
For 120 of the 520 adults, family_hx_diabetes is simulated (matching NHANES
baseline ~45% prevalence, anchored on clinical realism) alongside simulated
Abu Dhabi district and language fields so all pathways (`full`, `nofamily`,
and paediatric Well-Child) can be demoed without leaking training data.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from nabdh.data.nhanes import FEATURES, build_cycle

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "sample"

COLS = [
    "id",
    "age",
    "sex",
    "height_cm",
    "weight_kg",
    "bmi",
    "waist",
    "systolic_bp",
    "diastolic_bp",
    "family_hx_diabetes",
    "diagnosed_htn",
    "high_chol",
    "cvd_history",
    "income_ratio",
    "glucose_test_3y",
    "diagnosed_diabetes",
    "borderline_diabetes",
    "district",
    "language",
]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)

    c21 = build_cycle("nhanes_2021_2023")
    adults_21 = c21[(c21["age"] >= 20) & (~c21["_pregnant"]) & c21["_hba1c"].notna()].sample(
        520, random_state=7
    )
    peds_21 = c21[(c21["age"] >= 1) & (c21["age"] < 20) & c21["bmi"].notna()].sample(
        80, random_state=7
    )

    combined = pd.concat([adults_21, peds_21], ignore_index=True)
    combined = combined.sample(frac=1.0, random_state=7).reset_index(drop=True)

    # Simulate family_hx_diabetes on 120 adults from unseen 2021-23 cohort (zero training rows)
    adult_idx = combined.index[combined["age"] >= 20].to_numpy()
    sim_idx = rng.choice(adult_idx, size=120, replace=False)
    for idx in sim_idx:
        has_dys = pd.notna(combined.loc[idx, "_hba1c"]) and combined.loc[idx, "_hba1c"] >= 6.0
        p_fh = 0.55 if has_dys else 0.38
        combined.loc[idx, "family_hx_diabetes"] = float(rng.random() < p_fh)

    combined["id"] = [f"AD-{i:05d}" for i in range(len(combined))]
    combined["sex"] = combined["sex"].map({0.0: "male", 1.0: "female"})
    combined["diagnosed_diabetes"] = combined["_diagnosed_dm"]
    combined["borderline_diabetes"] = combined["_borderline_dm"]
    combined["district"] = rng.choice(
        ["Al Ain", "Khalifa City", "Mussafah", "Yas Island", "Al Dhafra", "Al Wathba"],
        len(combined),
        p=[0.28, 0.28, 0.20, 0.14, 0.09, 0.01],
    )
    combined["language"] = rng.choice(
        ["AR", "EN", "UR", "TL"], len(combined), p=[0.40, 0.35, 0.15, 0.10]
    )

    sample = combined[COLS]
    sample.to_csv(OUT_DIR / "cohort_sample.csv", index=False)

    truth = combined[["id", "_hba1c", "_fpg", "_diagnosed_dm", "_borderline_dm"]].rename(
        columns={
            "_hba1c": "hba1c",
            "_fpg": "fpg",
            "_diagnosed_dm": "dx_dm",
            "_borderline_dm": "borderline_dm",
        }
    )
    truth.to_csv(OUT_DIR / "cohort_sample_truth.csv", index=False)
    print(f"Wrote {sample.shape} strictly from 2021-23 using {len(FEATURES)} features")


if __name__ == "__main__":
    main()
