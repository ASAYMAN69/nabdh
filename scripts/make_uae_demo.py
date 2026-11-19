"""Generate a 60-patient synthetic Abu Dhabi demo cohort for Challenge 04."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parents[1] / "data" / "sample" / "uae_demo_cohort.csv"


def main() -> None:
    rng = np.random.default_rng(20261120)
    rows: list[dict] = [
        # 1. Challenge 04 "Wow" case: 29yo missed by age-40 rule (family hx + high PRS + adiposity)
        {
            "id": "UAE-WOW-029",
            "age": 29,
            "sex": "female",
            "height_cm": 161,
            "weight_kg": 86,
            "bmi": 33.2,
            "waist": 102,
            "systolic_bp": 136,
            "diastolic_bp": 86,
            "family_hx_diabetes": "yes",
            "diagnosed_htn": "no",
            "high_chol": "no",
            "cvd_history": "no",
            "income_ratio": 2.2,
            "glucose_test_3y": "no",
            "diagnosed_diabetes": "no",
            "borderline_diabetes": "no",
            "prs_cardiometabolic": "high",
            "g6pd_status": "normal",
            "thalassemia_carrier": "no",
            "district": "Al Ain",
            "language": "AR",
        },
        # 2. Urgent cardiac troponin + NT-proBNP case (must suppress outreach)
        {
            "id": "UAE-URG-101",
            "age": 54,
            "sex": "male",
            "height_cm": 173,
            "weight_kg": 88,
            "bmi": 29.4,
            "waist": 103,
            "systolic_bp": 146,
            "diastolic_bp": 90,
            "family_hx_diabetes": "yes",
            "diagnosed_htn": "yes",
            "high_chol": "yes",
            "cvd_history": "yes",
            "income_ratio": 3.1,
            "glucose_test_3y": "yes",
            "diagnosed_diabetes": "no",
            "borderline_diabetes": "no",
            "troponin_i": 0.18,
            "nt_probnp": 1420,
            "lvef_pct": 36,
            "district": "Khalifa City",
            "language": "AR",
        },
        # 3. Unit-suspect cardiac case (4500 in ng/mL -> must flag unit_suspect, not escalate)
        {
            "id": "UAE-UNIT-102",
            "age": 58,
            "sex": "male",
            "height_cm": 175,
            "weight_kg": 79,
            "bmi": 25.8,
            "waist": 93,
            "systolic_bp": 124,
            "diastolic_bp": 78,
            "diagnosed_diabetes": "no",
            "troponin_i_ng_ml": 4500,
            "district": "Yas Island",
            "language": "EN",
        },
        # 4. Well-Child Visit: developmental delay + missed WCV + G6PD
        {
            "id": "UAE-WCV-201",
            "age": 3,
            "sex": "male",
            "height_cm": 96,
            "weight_kg": 15.2,
            "bmi": 16.5,
            "missed_well_child_visits": 2,
            "developmental_delay_flag": "yes",
            "immunization_status": "overdue",
            "g6pd_status": "deficient",
            "district": "Al Ain",
            "language": "AR",
        },
        # 5. Well-Child Visit: adolescent obesity + missed WCV
        {
            "id": "UAE-WCV-202",
            "age": 12,
            "sex": "female",
            "height_cm": 152,
            "weight_kg": 68,
            "bmi": 29.4,
            "missed_well_child_visits": 1,
            "thalassemia_carrier": "yes",
            "district": "Mussafah",
            "language": "AR",
        },
        # 6. Prenatal stream case (BP elevated in pregnancy)
        {
            "id": "UAE-PREG-301",
            "age": 31,
            "sex": "female",
            "height_cm": 162,
            "weight_kg": 74,
            "bmi": 28.2,
            "systolic_bp": 134,
            "diastolic_bp": 84,
            "pregnant": "yes",
            "district": "Khalifa City",
            "language": "AR",
        },
        # 7. Small-cell district (<10) demo case
        {
            "id": "UAE-SM-401",
            "age": 66,
            "sex": "female",
            "height_cm": 157,
            "weight_kg": 72,
            "bmi": 29.2,
            "waist": 96,
            "systolic_bp": 142,
            "diastolic_bp": 84,
            "smoker": "yes",
            "pack_years": 25,
            "district": "Liwa Oasis",
            "language": "TL",
        },
    ]

    districts = ["Al Ain", "Khalifa City", "Mussafah", "Yas Island"]
    langs = ["AR", "EN"]
    for idx in range(len(rows) + 1, 61):
        is_ped = idx % 10 == 0
        sex = "female" if rng.random() < 0.52 else "male"
        if is_ped:
            age = int(rng.integers(2, 18))
            ht = round(float(90 + age * 4.5 + rng.normal(0, 4)), 1)
            bmi = round(float(rng.uniform(15.5, 27.5)), 1)
            wt = round(bmi * (ht / 100.0) ** 2, 1)
            rows.append(
                {
                    "id": f"UAE-{idx:03d}",
                    "age": age,
                    "sex": sex,
                    "height_cm": ht,
                    "weight_kg": wt,
                    "bmi": bmi,
                    "missed_well_child_visits": int(rng.choice([0, 0, 1])),
                    "immunization_status": str(rng.choice(["up_to_date", "up_to_date", "overdue"])),
                    "district": str(rng.choice(districts)),
                    "language": str(rng.choice(langs)),
                }
            )
            continue

        age = int(rng.integers(22, 76))
        ht = round(float(rng.normal(162 if sex == "female" else 174, 7)), 1)
        bmi = round(float(np.clip(rng.normal(28.5, 5.2), 18.5, 45.0)), 1)
        wt = round(bmi * (ht / 100.0) ** 2, 1)
        waist = round(float(np.clip(44 + bmi * 1.85 + rng.normal(0, 5), 65, 138)), 1)
        sbp = round(float(np.clip(108 + 0.45 * age + rng.normal(0, 12), 92, 185)), 0)
        dbp = round(float(np.clip(68 + 0.15 * age + rng.normal(0, 8), 55, 110)), 0)
        rows.append(
            {
                "id": f"UAE-{idx:03d}",
                "age": age,
                "sex": sex,
                "height_cm": ht,
                "weight_kg": wt,
                "bmi": bmi,
                "waist": waist,
                "systolic_bp": sbp,
                "diastolic_bp": dbp,
                "family_hx_diabetes": "yes" if rng.random() < 0.30 else "no",
                "diagnosed_htn": "yes" if (sbp >= 148 and rng.random() < 0.4) else "no",
                "high_chol": "yes" if rng.random() < 0.25 else "no",
                "cvd_history": "yes" if (age > 55 and rng.random() < 0.15) else "no",
                "smoker": "yes" if (sex == "male" and rng.random() < 0.22) else "no",
                "sleep_hours": round(float(np.clip(rng.normal(7.0, 1.1), 4.5, 9.5)), 1),
                "income_ratio": round(float(rng.uniform(0.8, 5.0)), 2),
                "glucose_test_3y": "yes" if rng.random() < 0.45 else "no",
                "diagnosed_diabetes": "yes" if (age > 50 and rng.random() < 0.12) else "no",
                "borderline_diabetes": "yes" if rng.random() < 0.14 else "no",
                "prs_cardiometabolic": "high" if rng.random() < 0.15 else "low",
                "district": str(rng.choice(districts)),
                "language": str(rng.choice(langs)),
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"Wrote {len(rows)} rows -> {OUT}")


if __name__ == "__main__":
    main()
