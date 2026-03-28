import numpy as np
import pandas as pd
from typing import Dict, List, Optional

INST_QUALITY_WEIGHTS = {
    "roic": 0.35,
    "net_margin": 0.25,
    "equity_to_assets": 0.20,
    "debt_to_equity": 0.20,
}

INST_GROWTH_WEIGHTS = {
    "revenue_growth": 0.25,
    "earnings_growth": 0.30,
    "eps_cagr_3y": 0.20,
    "margin_trend": 0.25,
}

INST_VALUATION_WEIGHTS = {
    "peg": 0.45,
    "pe": 0.30,
    "pb": 0.25,
}

INST_MOMENTUM_WEIGHTS = {
    "return_3m": 0.20,
    "return_6m": 0.25,
    "return_12m": 0.25,
    "relative_return_vs_index": 0.15,
    "distance_to_52w_high": 0.15,
}

INST_FLOW_WEIGHTS = {
    "mfi": 0.30,
    "obv_slope": 0.25,
    "volume_ratio": 0.25,
    "distance_to_52w_high": 0.20,
}

INST_CATEGORY_WEIGHTS = {
    "inst_quality": 0.25,
    "inst_growth": 0.20,
    "inst_valuation": 0.15,
    "inst_momentum": 0.25,
    "inst_flow": 0.15,
}

INST_REVERSE_SCORED = {
    "debt_to_equity",
    "pe",
    "pb",
    "peg",
}

INST_VALUATION_POSITIVES = {"pe", "pb", "peg"}

INST_CATEGORIES = [
    (85, 100, "Elit"),
    (70, 85, "Güçlü"),
    (55, 70, "İzleme"),
    (0, 55, "Zayıf"),
]

WINSORIZE_LOWER = 0.05
WINSORIZE_UPPER = 0.95


def _collect_all_metrics() -> List[str]:
    metrics = set()
    for w in [INST_QUALITY_WEIGHTS, INST_GROWTH_WEIGHTS, INST_VALUATION_WEIGHTS,
              INST_MOMENTUM_WEIGHTS, INST_FLOW_WEIGHTS]:
        metrics.update(w.keys())
    return sorted(metrics)


def _winsorize(df: pd.DataFrame, metrics: List[str]) -> pd.DataFrame:
    result = df.copy()
    for col in metrics:
        if col not in result.columns:
            continue
        series = result[col].dropna()
        if len(series) < 3:
            continue
        lo = series.quantile(WINSORIZE_LOWER)
        hi = series.quantile(WINSORIZE_UPPER)
        result[col] = result[col].clip(lower=lo, upper=hi)
    return result


def _percentile_rank(
    df: pd.DataFrame,
    metrics: List[str],
) -> pd.DataFrame:
    ranked = pd.DataFrame(index=df.index)

    for col in metrics:
        if col not in df.columns:
            ranked[col] = np.nan
            continue

        series = df[col].copy()

        if col in INST_VALUATION_POSITIVES:
            series = series.where(series > 0, np.nan)

        valid_mask = series.notna()
        n_valid = valid_mask.sum()

        if n_valid < 2:
            ranked[col] = np.where(valid_mask, 50.0, np.nan)
            continue

        dense_rank = series.rank(method="average", na_option="keep")
        pct = ((dense_rank - 1) / (n_valid - 1)) * 100

        if col in INST_REVERSE_SCORED:
            pct = pct.where(~valid_mask, 100 - pct)

        ranked[col] = pct.round(2)

    return ranked


def _adaptive_weighted_score(
    percentiles: pd.DataFrame,
    weights: Dict[str, float],
) -> pd.Series:
    cols = list(weights.keys())
    wts = np.array([weights[c] for c in cols])

    scores = np.full(len(percentiles), np.nan)

    for i in range(len(percentiles)):
        values = np.array([
            percentiles[c].iloc[i] if c in percentiles.columns else np.nan
            for c in cols
        ])

        valid = ~np.isnan(values)
        if not valid.any():
            continue

        active_wts = wts[valid]
        active_vals = values[valid]
        total_wt = active_wts.sum()
        if total_wt == 0:
            continue

        scores[i] = round(np.sum(active_vals * active_wts) / total_wt, 2)

    return pd.Series(scores, index=percentiles.index)


def _categorize(score: float) -> str:
    if not np.isfinite(score):
        return "N/A"
    for lower, upper, label in INST_CATEGORIES:
        if lower <= score < upper:
            return label
    if score >= 100:
        return "Elit"
    return "N/A"


def append_institutional_scores(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()

    all_metrics = _collect_all_metrics()
    winsorized = _winsorize(result, all_metrics)
    pct = _percentile_rank(winsorized, all_metrics)

    result["inst_quality"] = _adaptive_weighted_score(pct, INST_QUALITY_WEIGHTS)
    result["inst_growth"] = _adaptive_weighted_score(pct, INST_GROWTH_WEIGHTS)
    result["inst_valuation"] = _adaptive_weighted_score(pct, INST_VALUATION_WEIGHTS)
    result["inst_momentum"] = _adaptive_weighted_score(pct, INST_MOMENTUM_WEIGHTS)
    result["inst_flow"] = _adaptive_weighted_score(pct, INST_FLOW_WEIGHTS)

    sub_cols = list(INST_CATEGORY_WEIGHTS.keys())
    cat_wts = np.array([INST_CATEGORY_WEIGHTS[c] for c in sub_cols])

    inst_scores = np.full(len(result), np.nan)
    for i in range(len(result)):
        values = np.array([
            result[c].iloc[i] if c in result.columns else np.nan
            for c in sub_cols
        ])
        valid = ~np.isnan(values)
        if not valid.any():
            inst_scores[i] = 0.0
            continue
        active_wts = cat_wts[valid]
        active_vals = values[valid]
        total_wt = active_wts.sum()
        if total_wt == 0:
            inst_scores[i] = 0.0
            continue
        inst_scores[i] = round(np.sum(active_vals * active_wts) / total_wt, 2)

    result["institutional_score"] = inst_scores
    result["inst_category"] = pd.Series(inst_scores, index=result.index).apply(_categorize)

    return result
