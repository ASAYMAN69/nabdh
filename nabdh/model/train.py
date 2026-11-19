"""Train and evaluate screening-prioritisation models without test-set leakage.

Two variants (NHANES 2021-23 dropped family-history questions):
  full      : all 14 biological features (for cohorts with family history)
  nofamily  : 13 biological features without family_hx_diabetes

Targets:
  undiagnosed_dm : HbA1c >= 6.5% or FPG >= 126 mg/dL (among strictly undiagnosed)
  dysglycaemia   : HbA1c >= 5.7% or FPG >= 100 mg/dL (among strictly undiagnosed)

Model class: both logreg and lightgbm are evaluated by 5-fold StratifiedKFold CV
inside NHANES 2017-20. Logreg is always deployed because the system requires
exact per-feature attribution (Shapley values) and stable calibration; the LightGBM
numbers are kept as the GBDT benchmark in metrics.json. This is a deliberate
choice, not a claim that CV selects the model.

Clinical sign guardrails: after fitting, any feature whose standardized main
effect contradicts the clinically expected direction (age, BMI, BP, family
history, CVD, smoking, high cholesterol must all RAISE risk) is sign-constrained
to zero. This prevents correlated-collinearity sign flips (e.g. systolic BP
negative in the diabetes model) from producing clinically inverted gradients.
The applied masks are recorded in coefficient_signs.json and enforced by
tests/test_model_signs.py.
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from nabdh.data.nhanes import (
    POSITIVE_SIGN_FEATURES,
    TARGETS,
    build_target_cohort,
    features_for_target,
)

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "models"


def _gbm() -> lgb.LGBMClassifier:
    return lgb.LGBMClassifier(
        n_estimators=200,
        learning_rate=0.03,
        num_leaves=15,
        min_child_samples=40,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.8,
        reg_lambda=5.0,
        random_state=0,
        verbose=-1,
    )


def _lr() -> make_pipeline:
    return make_pipeline(
        SimpleImputer(strategy="mean"),
        StandardScaler(),
        LogisticRegression(max_iter=2000, C=1.0),
    )


def _norm_weights(w: pd.Series) -> np.ndarray:
    vals = pd.to_numeric(w, errors="coerce").to_numpy(dtype=float)
    med = np.nanmedian(vals[vals > 0]) if np.any(vals > 0) else 1.0
    vals = np.where(np.isnan(vals) | (vals <= 0), med, vals)
    return vals / np.mean(vals)


def _fit_with_weights(estimator, X: pd.DataFrame, y: pd.Series, w: np.ndarray):
    est = clone(estimator)
    if hasattr(est, "steps"):
        last_name = est.steps[-1][0]
        est.fit(X, y, **{f"{last_name}__sample_weight": w})
    else:
        est.fit(X, y, sample_weight=w)
    return est


def _sign_constrain(estimator, features: list[str]) -> dict:
    """Zero out standardized coefficients that contradict clinical expectations.

    Returns a mapping of feature -> raw coefficient (only entries that changed).
    """
    if not hasattr(estimator, "steps"):
        return {}
    clf = estimator.steps[-1][1]
    coef = clf.coef_[0].copy()
    changed: dict[str, float] = {}
    for j, feat in enumerate(features):
        if feat not in POSITIVE_SIGN_FEATURES:
            continue
        # standardized coef = raw coef / feature scale; negative means inverse
        if coef[j] < 0:
            changed[feat] = round(float(coef[j]), 4)
            coef[j] = 0.0
    clf.coef_[0] = coef
    return changed


def _oof_probs(estimator, X: pd.DataFrame, y: pd.Series, w: np.ndarray) -> np.ndarray:
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    oof = np.zeros(len(X), dtype=float)
    for tr_idx, va_idx in skf.split(X, y):
        fitted = _fit_with_weights(estimator, X.iloc[tr_idx], y.iloc[tr_idx], w[tr_idx])
        _sign_constrain(fitted, list(X.columns))
        oof[va_idx] = fitted.predict_proba(X.iloc[va_idx])[:, 1]
    return oof


def _metrics(y, p, w: np.ndarray | None = None) -> dict:
    y_arr = np.asarray(y, dtype=float)
    p_arr = np.asarray(p, dtype=float)
    order = np.argsort(-p_arr)
    prev = float(np.mean(y_arr))
    pred = float(np.mean(p_arr))
    brier = float(brier_score_loss(y_arr, p_arr))
    brier_null = float(brier_score_loss(y_arr, np.full_like(p_arr, prev)))
    out = {
        "n": int(len(y_arr)),
        "prevalence": round(prev, 5),
        "mean_pred": round(pred, 5),
        "o_e_ratio": round(prev / pred, 4) if pred > 0 else None,
        "auc": round(float(roc_auc_score(y_arr, p_arr)), 5),
        "pr_auc": round(float(average_precision_score(y_arr, p_arr)), 5),
        "brier": round(brier, 5),
        "brier_skill": round(1.0 - brier / brier_null, 5) if brier_null > 0 else 0.0,
    }
    for q in (0.1, 0.3):
        k = max(1, int(len(y_arr) * q))
        out[f"capture_top{int(q * 100)}pct"] = round(
            float(y_arr[order[:k]].sum() / max(1.0, np.sum(y_arr))), 4
        )
    if w is not None:
        w_arr = np.asarray(w, dtype=float)
        w_prev = float(np.average(y_arr, weights=w_arr))
        w_pred = float(np.average(p_arr, weights=w_arr))
        w_brier = float(brier_score_loss(y_arr, p_arr, sample_weight=w_arr))
        w_brier_null = float(
            brier_score_loss(y_arr, np.full_like(p_arr, w_prev), sample_weight=w_arr)
        )
        out["weighted_prevalence"] = round(w_prev, 5)
        out["weighted_mean_pred"] = round(w_pred, 5)
        out["weighted_o_e_ratio"] = round(w_prev / w_pred, 4) if w_pred > 0 else None
        out["weighted_auc"] = round(float(roc_auc_score(y_arr, p_arr, sample_weight=w_arr)), 5)
        out["weighted_brier_skill"] = (
            round(1.0 - w_brier / w_brier_null, 5) if w_brier_null > 0 else 0.0
        )
    return out


def _binary_age_rule_metrics(y, age: pd.Series, cutoff: int = 40) -> dict:
    y_arr = np.asarray(y, dtype=int)
    flagged = (age.fillna(0).to_numpy() >= cutoff).astype(int)
    tp = int(((flagged == 1) & (y_arr == 1)).sum())
    fp = int(((flagged == 1) & (y_arr == 0)).sum())
    fn = int(((flagged == 0) & (y_arr == 1)).sum())
    tn = int(((flagged == 0) & (y_arr == 0)).sum())
    return {
        "cutoff": cutoff,
        "screen_rate": round(float(flagged.mean()), 4),
        "sensitivity": round(tp / max(1, tp + fn), 4),
        "specificity": round(tn / max(1, tn + fp), 4),
        "ppv": round(tp / max(1, tp + fp), 4),
        "auc": round(float(roc_auc_score(y_arr, flagged)), 5),
    }


def _calibration_table(y, p, bins: int = 10) -> list[dict]:
    df = pd.DataFrame({"y": np.asarray(y), "p": p})
    df["bin"] = pd.qcut(df["p"], bins, duplicates="drop")
    g = df.groupby("bin", observed=True).agg(pred=("p", "mean"), obs=("y", "mean"), n=("y", "size"))
    return g.round(4).to_dict("records")


def _fit_anthro_imputers(df: pd.DataFrame) -> dict:
    specs = {
        "whtr_from_waist_bmi": (["waist", "bmi", "age", "sex"], "whtr"),
        "whtr_from_waist": (["waist", "age", "sex"], "whtr"),
        "whtr_from_bmi": (["bmi", "age", "sex"], "whtr"),
        "waist_from_bmi": (["bmi", "age", "sex"], "waist"),
    }
    imputers = {}
    for name, (xcols, ycol) in specs.items():
        sub = df[xcols + [ycol]].dropna()
        reg = LinearRegression().fit(sub[xcols], sub[ycol])
        imputers[name] = {
            "features": xcols,
            "target": ycol,
            "coef": [float(c) for c in reg.coef_],
            "intercept": float(reg.intercept_),
            "r2": round(float(reg.score(sub[xcols], sub[ycol])), 4),
        }
    return imputers


def _age_band_quantiles(age: pd.Series, p: np.ndarray) -> dict[str, dict[str, float]]:
    bands = pd.cut(age, [19, 39, 59, 200], labels=["20-39", "40-59", "60+"])
    out: dict[str, dict[str, float]] = {}
    for label in ("20-39", "40-59", "60+"):
        vals = p[bands == label]
        if len(vals):
            out[label] = {
                "p80": round(float(np.percentile(vals, 80)), 5),
                "p90": round(float(np.percentile(vals, 90)), 5),
            }
    return out


def run() -> dict:
    MODELS.mkdir(exist_ok=True)
    dm_tr = build_target_cohort("nhanes_2017_2020", "dysglycaemia")
    anthro_imputers = _fit_anthro_imputers(dm_tr)
    report: dict = {}
    sign_report: dict = {}

    for tname in TARGETS:
        tr_all = build_target_cohort("nhanes_2017_2020", tname)
        ext_all = build_target_cohort("nhanes_2021_2023", tname)
        w_all = _norm_weights(tr_all["_sample_weight"])
        w_ext = _norm_weights(ext_all["_sample_weight"])

        for variant in ("full", "nofamily"):
            feats = features_for_target(tname, include_family=(variant == "full"))
            key = f"{variant}__{tname}"
            res: dict = {}

            # 1. CV benchmark (logreg + lightgbm). Logreg is always deployed for
            # attribution and calibration stability; see module docstring.
            cv_scores = {}
            for mname, mk in (("logreg", _lr), ("lightgbm", _gbm)):
                oof_p = _oof_probs(mk(), tr_all[feats], tr_all["y"], w_all)
                cv_scores[mname] = _metrics(tr_all["y"], oof_p, w_all)
                cv_scores[mname]["calibration"] = _calibration_table(tr_all["y"], oof_p)
            best = "logreg"
            res["cv_2017_2020"] = cv_scores
            res["selected"] = best
            res["selection_rule"] = (
                "logreg deployed for exact attribution + calibration stability; "
                "lightgbm kept as benchmark"
            )

            # 2. Fit deployed logreg on 100% of 2017-20 with survey weights,
            #    then apply the clinical sign constraints.
            final = _fit_with_weights(_lr(), tr_all[feats], tr_all["y"], w_all)
            clamped = _sign_constrain(final, feats)
            sign_report[key] = clamped

            # 3. Honest evaluation of the shipped model / split
            if variant == "nofamily":
                res["eval_set"] = "NHANES 2021-23 (temporal external, deployed model)"
                p_ext = final.predict_proba(ext_all[feats])[:, 1]
                res["logreg"] = _metrics(ext_all["y"], p_ext, w_ext)
                res["logreg"]["calibration"] = _calibration_table(ext_all["y"], p_ext)
                # LightGBM benchmark fit on 2017-20 for reference
                m_gbm = _fit_with_weights(_gbm(), tr_all[feats], tr_all["y"], w_all)
                _sign_constrain(m_gbm, feats)
                p_gbm_ext = m_gbm.predict_proba(ext_all[feats])[:, 1]
                res["lightgbm"] = _metrics(ext_all["y"], p_gbm_ext, w_ext)
                res["age_continuous_ranking"] = _metrics(
                    ext_all["y"], ext_all["age"].to_numpy(dtype=float) / 100.0, w_ext
                )
                res["age_ge40_binary_rule"] = _binary_age_rule_metrics(
                    ext_all["y"], ext_all["age"], cutoff=40
                )
            else:
                res["eval_set"] = "NHANES 2017-20 25% stratified held-out"
                idx_tr, idx_te = train_test_split(
                    np.arange(len(tr_all)),
                    test_size=0.25,
                    random_state=42,
                    stratify=tr_all["y"],
                )
                tr_s, te_s = tr_all.iloc[idx_tr], tr_all.iloc[idx_te]
                w_tr, w_te = w_all[idx_tr], w_all[idx_te]
                m_split = _fit_with_weights(_lr(), tr_s[feats], tr_s["y"], w_tr)
                _sign_constrain(m_split, feats)
                p_te = m_split.predict_proba(te_s[feats])[:, 1]
                res["logreg"] = _metrics(te_s["y"], p_te, w_te)
                res["logreg"]["calibration"] = _calibration_table(te_s["y"], p_te)
                m_gbm = _fit_with_weights(_gbm(), tr_s[feats], tr_s["y"], w_tr)
                _sign_constrain(m_gbm, feats)
                p_gbm_te = m_gbm.predict_proba(te_s[feats])[:, 1]
                res["lightgbm"] = _metrics(te_s["y"], p_gbm_te, w_te)
                res["age_continuous_ranking"] = _metrics(
                    te_s["y"], te_s["age"].to_numpy(dtype=float) / 100.0, w_te
                )
                res["age_ge40_binary_rule"] = _binary_age_rule_metrics(
                    te_s["y"], te_s["age"], cutoff=40
                )

            coefs = {
                f: round(float(c), 4)
                for f, c in zip(feats, final.steps[-1][1].coef_[0])
            }
            res["deployed_coefficients"] = coefs
            res["sign_clamped_features"] = list(clamped.keys())

            p_tr_deployed = final.predict_proba(tr_all[feats])[:, 1]
            report[key] = res

            # Unified model: explainer_model IS the exact deployed probability pipeline
            joblib.dump(
                {
                    "model": final,
                    "explainer_model": final,
                    "features": feats,
                    "kind": best,
                    "target": tname,
                    "variant": variant,
                    "train_means": tr_all[feats].mean().to_dict(),
                    "train_medians": tr_all[feats].median().to_dict(),
                    "anthro_imputers": anthro_imputers,
                    "age_band_quantiles": _age_band_quantiles(tr_all["age"], p_tr_deployed),
                },
                MODELS / f"{key}.joblib",
            )

    (MODELS / "metrics.json").write_text(json.dumps(report, indent=2))
    (MODELS / "coefficient_signs.json").write_text(json.dumps(sign_report, indent=2))
    return report


if __name__ == "__main__":
    rep = run()
    for k, v in rep.items():
        print(f"\n{k} | selected={v['selected']} | eval={v['eval_set']}")
        if "deployed_coefficients" in v:
            print("  coefs:", v["deployed_coefficients"])
        for m in ("logreg", "lightgbm", "age_continuous_ranking"):
            r = v[m]
            print(
                f"  {m:22s} auc={r['auc']:.4f} pr={r['pr_auc']:.4f} "
                f"O/E={r['o_e_ratio']} bss={r['brier_skill']:+.4f} "
                f"top10%={r['capture_top10pct']:.3f} top30%={r['capture_top30pct']:.3f}"
            )
        b = v["age_ge40_binary_rule"]
        print(
            f"  age_ge40_binary_rule   auc={b['auc']:.4f} screen={b['screen_rate']:.3f} "
            f"sens={b['sensitivity']:.3f} spec={b['specificity']:.3f} ppv={b['ppv']:.3f}"
        )
