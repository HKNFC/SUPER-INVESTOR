"""
RS Score Engine

Computes a 0-100 composite Relative Strength score for each stock
using percentile ranking across the selected universe.

Approach:
  1. Compute derived financial and momentum metrics
  2. Winsorize extreme outliers
  3. Percentile-rank each metric within the universe
  4. Reverse-score metrics where lower is better
  5. Combine into weighted sub-scores and final RS Score
  6. Assign RS Category labels
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from config import (
    SCORING_WEIGHTS,
    FINANCIAL_STRENGTH_WEIGHTS,
    GROWTH_WEIGHTS,
    MARGIN_QUALITY_WEIGHTS,
    VALUATION_WEIGHTS,
    MOMENTUM_WEIGHTS,
    REVERSE_SCORED_METRICS,
    RS_CATEGORIES,
    WINSORIZE_LOWER,
    WINSORIZE_UPPER,
)
from data_model import compute_derived_fields
from technical_signals import append_technical_scores


def compute_rs_scores(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute the composite RS Score for each stock in the DataFrame.

    Steps:
      1. Compute derived fields (margins, growth rates, ratios)
      2. Winsorize extreme values
      3. Percentile-rank each metric across the universe
      4. Compute weighted sub-scores for each category
      5. Compute final weighted RS Score
      6. Assign RS Category and rank
    """
    if df.empty:
        return df

    result = compute_derived_fields(df.copy())

    result = _compute_margin_trend(result)

    all_metrics = _collect_all_metrics()
    result = _winsorize_metrics(result, all_metrics)

    percentiles = _percentile_rank_all(result, all_metrics)

    result["financial_strength"] = _weighted_sub_score(
        percentiles, FINANCIAL_STRENGTH_WEIGHTS
    )
    result["growth"] = _weighted_sub_score(
        percentiles, GROWTH_WEIGHTS
    )
    result["margin_quality"] = _weighted_sub_score(
        percentiles, MARGIN_QUALITY_WEIGHTS
    )
    result["valuation"] = _weighted_sub_score(
        percentiles, VALUATION_WEIGHTS
    )
    result["momentum"] = _weighted_sub_score(
        percentiles, MOMENTUM_WEIGHTS
    )

    sub_score_cols = list(SCORING_WEIGHTS.keys())
    result["rs_score"] = _final_rs_score(result, sub_score_cols)

    result["rs_category"] = result["rs_score"].apply(_categorize)

    result = append_technical_scores(result)

    result = result.sort_values("rs_score", ascending=False).reset_index(drop=True)
    result["rank"] = result.index + 1

    return result


# ---------------------------------------------------------------------------
# Margin Trend
# ---------------------------------------------------------------------------

def _compute_margin_trend(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute margin_trend as the change in net margin vs the implied
    previous-year net margin.

    margin_trend = net_margin - (net_income_prev_year / revenue_prev_year)

    A positive value means margins are expanding.
    """
    result = df.copy()

    def _trend(row):
        current_nm = row.get("net_margin")
        ni_prev = row.get("net_income_prev_year")
        rev_prev = row.get("revenue_prev_year")

        if (current_nm is None or not np.isfinite(current_nm)):
            return np.nan

        if (ni_prev is None or rev_prev is None):
            return np.nan

        try:
            ni_p = float(ni_prev)
            rev_p = float(rev_prev)
            if rev_p <= 0 or not np.isfinite(ni_p) or not np.isfinite(rev_p):
                return np.nan
            prev_nm = ni_p / rev_p
            return current_nm - prev_nm
        except (ValueError, TypeError):
            return np.nan

    result["margin_trend"] = result.apply(_trend, axis=1)
    return result


# ---------------------------------------------------------------------------
# Winsorization
# ---------------------------------------------------------------------------

def _winsorize_metrics(
    df: pd.DataFrame,
    metrics: List[str],
) -> pd.DataFrame:
    """
    Winsorize metric columns to cap extreme outliers at the
    configured lower and upper percentile bounds.

    Values below the lower bound are clipped up; values above
    the upper bound are clipped down. NaN values are preserved.
    """
    result = df.copy()
    for col in metrics:
        if col not in result.columns:
            continue
        series = result[col].dropna()
        if len(series) < 3:
            continue
        lower = series.quantile(WINSORIZE_LOWER)
        upper = series.quantile(WINSORIZE_UPPER)
        result[col] = result[col].clip(lower=lower, upper=upper)
    return result


# ---------------------------------------------------------------------------
# Percentile Ranking
# ---------------------------------------------------------------------------

def _percentile_rank_all(
    df: pd.DataFrame,
    metrics: List[str],
) -> pd.DataFrame:
    """
    Compute percentile ranks (0-100) for all metric columns.

    Uses true 0-100 scaling: (rank - 1) / (n - 1) * 100, where n is
    the count of non-NaN values. The best value scores 100, the worst 0.

    For reverse-scored metrics (lower is better), the percentile
    is inverted: 100 - rank, so the lowest raw value gets 100.

    Non-positive valuation multiples (PE, PB, EV/EBITDA, PEG) are
    treated as NaN before ranking since negative values are not meaningful.

    NaN values receive NaN percentile ranks.
    """
    ranked = pd.DataFrame(index=df.index)

    valuation_metrics = {"pe", "pb", "ev_ebitda", "peg"}

    for col in metrics:
        if col not in df.columns:
            ranked[col] = np.nan
            continue

        series = df[col].copy()

        if col in valuation_metrics:
            series = series.where(series > 0, np.nan)

        valid_mask = series.notna()
        n_valid = valid_mask.sum()

        if n_valid < 2:
            if n_valid == 1:
                ranked[col] = series.where(~valid_mask, 50.0)
            else:
                ranked[col] = np.nan
            continue

        dense_rank = series.rank(method="average", na_option="keep")
        pct = ((dense_rank - 1) / (n_valid - 1)) * 100

        if col in REVERSE_SCORED_METRICS:
            pct = pct.where(~valid_mask, 100 - pct)

        ranked[col] = pct.round(2)

    return ranked


# ---------------------------------------------------------------------------
# Weighted Sub-Scores
# ---------------------------------------------------------------------------

def _weighted_sub_score(
    percentiles: pd.DataFrame,
    weights: Dict[str, float],
) -> pd.Series:
    """
    Compute a weighted average sub-score from percentile-ranked metrics.

    If a metric has NaN for a given stock, that metric's weight is
    redistributed proportionally among the available metrics.

    Returns a Series of scores (0-100), or NaN if all metrics are NaN.
    """
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


# ---------------------------------------------------------------------------
# Final RS Score
# ---------------------------------------------------------------------------

def _final_rs_score(
    df: pd.DataFrame,
    sub_score_cols: List[str],
) -> pd.Series:
    """
    Compute the final weighted RS Score from sub-scores.

    Uses the same proportional weight redistribution for missing sub-scores.
    """
    wts = np.array([SCORING_WEIGHTS[c] for c in sub_score_cols])
    scores = np.full(len(df), np.nan)

    for i in range(len(df)):
        values = np.array([
            df[c].iloc[i] if c in df.columns else np.nan
            for c in sub_score_cols
        ])

        valid = ~np.isnan(values)
        if not valid.any():
            scores[i] = 0.0
            continue

        active_wts = wts[valid]
        active_vals = values[valid]

        total_wt = active_wts.sum()
        if total_wt == 0:
            scores[i] = 0.0
            continue

        scores[i] = round(np.sum(active_vals * active_wts) / total_wt, 2)

    return pd.Series(scores, index=df.index)


# ---------------------------------------------------------------------------
# RS Category
# ---------------------------------------------------------------------------

def _categorize(score: float) -> str:
    """
    Assign an RS category label based on the score.

    85-100:  Elite
    70-<85:  Strong
    55-<70:  Watchlist
    40-<55:  Weak
    0-<40:   Avoid
    """
    if not np.isfinite(score):
        return "N/A"
    for lower, upper, label in RS_CATEGORIES:
        if lower <= score < upper:
            return label
    if score >= 100:
        return "Elite"
    return "N/A"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_all_metrics() -> List[str]:
    """Collect the full list of metrics used across all sub-scores."""
    metrics = set()
    for weights_dict in [
        FINANCIAL_STRENGTH_WEIGHTS,
        GROWTH_WEIGHTS,
        MARGIN_QUALITY_WEIGHTS,
        VALUATION_WEIGHTS,
        MOMENTUM_WEIGHTS,
    ]:
        metrics.update(weights_dict.keys())
    return sorted(metrics)


def get_score_breakdown(row: pd.Series) -> dict:
    """
    Return a breakdown of all sub-scores, derived metrics, and the
    composite RS Score for a single stock.
    """
    def _fmt(val):
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return None
        return val

    return {
        "ticker": row.get("ticker", "N/A"),
        "company_name": row.get("company_name", "N/A"),
        "rs_score": _fmt(row.get("rs_score")),
        "rs_category": row.get("rs_category", "N/A"),
        "financial_strength": _fmt(row.get("financial_strength")),
        "growth": _fmt(row.get("growth")),
        "margin_quality": _fmt(row.get("margin_quality")),
        "valuation": _fmt(row.get("valuation")),
        "momentum": _fmt(row.get("momentum")),
        "gross_margin": _fmt(row.get("gross_margin")),
        "operating_margin": _fmt(row.get("operating_margin")),
        "net_margin": _fmt(row.get("net_margin")),
        "ebitda_margin": _fmt(row.get("ebitda_margin")),
        "margin_trend": _fmt(row.get("margin_trend")),
        "roe": _fmt(row.get("roe")),
        "roa": _fmt(row.get("roa")),
        "roic": _fmt(row.get("roic")),
        "debt_to_equity": _fmt(row.get("debt_to_equity")),
        "equity_to_assets": _fmt(row.get("equity_to_assets")),
        "net_income_to_assets": _fmt(row.get("net_income_to_assets")),
        "revenue_growth": _fmt(row.get("revenue_growth")),
        "earnings_growth": _fmt(row.get("earnings_growth")),
        "revenue_cagr_3y": _fmt(row.get("revenue_cagr_3y")),
        "eps_cagr_3y": _fmt(row.get("eps_cagr_3y")),
    }
