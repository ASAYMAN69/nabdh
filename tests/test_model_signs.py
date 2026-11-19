"""Sign-plausibility AND non-ablation tests for deployed model artifacts.

For each deployed model, perturb one feature at a time from a low to a high value
and assert:
1. The predicted probability moves in the clinically expected direction (not flat,
   not inverted).
2. Features that are supposed to be in the model are actually present and
   non-zero — a deleted coefficient must fail, not silently pass.

A model that ranks older adults *below* younger adults, or CVD history as
protective, must fail here rather than ship. A model that has had its strongest
predictors zeroed out must also fail.
"""
from __future__ import annotations

import joblib
import pandas as pd
import pytest

MODELS = [
    ("full", "undiagnosed_dm"),
    ("nofamily", "undiagnosed_dm"),
    ("full", "dysglycaemia"),
    ("nofamily", "dysglycaemia"),
    ("full", "undiagnosed_htn"),
    ("nofamily", "undiagnosed_htn"),
    ("full", "undiagnosed_dyslipidaemia"),
    ("nofamily", "undiagnosed_dyslipidaemia"),
    ("full", "ckd_risk"),
    ("nofamily", "ckd_risk"),
]

# feature -> (low, high, expected_direction)
# expected_direction: +1 means higher value must raise risk, -1 means lower.
PROBES = [
    ("age", 30.0, 70.0, +1),
    ("diastolic_bp", 70.0, 100.0, +1),
    ("bmi", 22.0, 40.0, +1),
    ("family_hx_diabetes", 0.0, 1.0, +1),
    ("cvd_history", 0.0, 1.0, +1),
    ("high_chol", 0.0, 1.0, +1),
    ("current_smoker", 0.0, 1.0, +1),
]

# Features that must have a non-zero coefficient in every model where they
# appear. This catches the "lobotomy" failure mode: zeroing a coefficient after
# fitting to make a sign test pass. If a feature is clinically required but has
# been zeroed, the test fails.
#
# Features that are legitimately zeroed by the sign-constraint mechanism (their
# fitted coefficient was negative due to collinearity or confounding) are
# documented in models/coefficient_signs.json and listed in ALLOWED_ZERO below.
# The test requires that every other feature in the model has a non-zero
# coefficient — no silent ablations.
ALLOWED_ZERO = {
    ("full", "undiagnosed_dm"): {"high_chol"},
    ("nofamily", "undiagnosed_dm"): {"high_chol"},
    ("full", "dysglycaemia"): {"cvd_history"},
    ("nofamily", "dysglycaemia"): {"cvd_history"},
    ("full", "undiagnosed_htn"): {"family_hx_diabetes", "high_chol"},
    ("nofamily", "undiagnosed_htn"): {"high_chol"},
    ("full", "undiagnosed_dyslipidaemia"): {"cvd_history"},
    ("nofamily", "undiagnosed_dyslipidaemia"): {"cvd_history"},
    ("full", "ckd_risk"): {"diastolic_bp"},
    ("nofamily", "ckd_risk"): {"diastolic_bp"},
}


def _load(variant: str, target: str) -> dict:
    return joblib.load(f"models/{variant}__{target}.joblib")


def _predict(bundle: dict, row: pd.Series) -> float:
    feats = bundle["features"]
    means = bundle["train_means"]
    x = row.reindex(feats).astype(float).fillna(pd.Series(means)).to_numpy().reshape(1, -1)
    return float(bundle["model"].predict_proba(x)[0, 1])


def _base(bundle: dict) -> pd.Series:
    return pd.Series(bundle["train_means"], dtype=float)


@pytest.mark.parametrize("variant,target", MODELS)
def test_feature_signs_are_clinically_plausible(variant: str, target: str) -> None:
    bundle = _load(variant, target)
    feats = bundle["features"]
    problems: list[str] = []
    for feat, lo, hi, direction in PROBES:
        if feat not in feats:
            continue
        r_lo = _base(bundle)
        r_lo[feat] = lo
        r_hi = _base(bundle)
        r_hi[feat] = hi
        p_lo = _predict(bundle, r_lo)
        p_hi = _predict(bundle, r_hi)
        delta = p_hi - p_lo
        # A sign-clamped feature contributes exactly zero by design; that is
        # acceptable (it is removed from the risk signal), only a *negative*
        # movement is a clinical inversion.
        if abs(delta) < 1e-12:
            continue
        if direction > 0 and delta < 0:
            problems.append(f"{feat}: {lo}->{p_lo:.3f} {hi}->{p_hi:.3f} delta={delta:+.3f}")
        if direction < 0 and delta > 0:
            problems.append(f"{feat}: {lo}->{p_lo:.3f} {hi}->{p_hi:.3f} delta={delta:+.3f}")
    assert not problems, (
        f"clinically implausible gradient(s) in {variant}__{target}: " + "; ".join(problems)
    )


@pytest.mark.parametrize("variant,target", MODELS)
def test_no_unexpected_ablation(variant: str, target: str) -> None:
    """Every feature in the model must have a non-zero coefficient, except
    those explicitly listed in ALLOWED_ZERO (documented sign-clamped features).

    This catches the "lobotomy" failure mode: a feature that should contribute
    to the prediction has been silently zeroed. If a new feature is added to
    the model and then zeroed without being added to ALLOWED_ZERO, this test
    fails.
    """
    bundle = _load(variant, target)
    feats = bundle["features"]
    model = bundle["model"]
    clf = model.steps[-1][1]
    coef = clf.coef_[0]
    allowed = ALLOWED_ZERO.get((variant, target), set())
    dead: list[str] = []
    for j, feat in enumerate(feats):
        if abs(coef[j]) < 1e-9 and feat not in allowed:
            dead.append(feat)
    assert not dead, (
        f"unexpected ablation (zero coefficient) in {variant}__{target}: {dead}. "
        f"Allowed zeros: {sorted(allowed)}. "
        f"If this is intentional, add to ALLOWED_ZERO with a documented reason."
    )


@pytest.mark.parametrize("variant,target", MODELS)
def test_older_adults_never_score_lower(variant: str, target: str) -> None:
    """Explicit demo-reproducible check: age 30 vs age 70, all else at means.
    Uses strict > so a flat gradient (age ablated) fails."""
    bundle = _load(variant, target)
    if "age" not in bundle["features"]:
        pytest.skip("age not a feature")
    r30 = _base(bundle)
    r30["age"] = 30.0
    r70 = _base(bundle)
    r70["age"] = 70.0
    p30 = _predict(bundle, r30)
    p70 = _predict(bundle, r70)
    assert p70 > p30, (
        f"{variant}__{target}: age 70 ({p70:.3f}) must score strictly above age 30 ({p30:.3f})"
    )
