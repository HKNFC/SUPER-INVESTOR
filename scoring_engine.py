import pandas as pd
import numpy as np
from config import SCORING_WEIGHTS
from data_model import compute_derived_fields
from financial_metrics import (
    calculate_financial_strength,
    calculate_growth_score,
    calculate_margin_quality,
    calculate_valuation_score,
)
from momentum_metrics import calculate_momentum_score


def compute_rs_scores(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute the composite RS Score for each stock in the DataFrame.

    Steps:
    1. Compute derived fields (margins, growth rates, ratios) from raw fundamentals
    2. Calculate individual sub-scores for each category
    3. Compute weighted composite RS Score
    4. Sort by RS Score descending and assign ranks
    """
    result = df.copy()

    result = compute_derived_fields(result)

    result["financial_strength"] = result.apply(calculate_financial_strength, axis=1)
    result["growth"] = result.apply(calculate_growth_score, axis=1)
    result["margin_quality"] = result.apply(calculate_margin_quality, axis=1)
    result["valuation"] = result.apply(calculate_valuation_score, axis=1)
    result["momentum"] = result.apply(calculate_momentum_score, axis=1)

    result["rs_score"] = result.apply(_weighted_composite, axis=1)

    result = result.sort_values("rs_score", ascending=False).reset_index(drop=True)
    result["rank"] = result.index + 1

    return result


def _weighted_composite(row: pd.Series) -> float:
    """Calculate the weighted composite RS Score from sub-scores."""
    total_weight = 0.0
    weighted_sum = 0.0

    for category, weight in SCORING_WEIGHTS.items():
        value = row.get(category)
        if value is not None and np.isfinite(value):
            weighted_sum += value * weight
            total_weight += weight

    if total_weight == 0:
        return 0.0

    return round(weighted_sum / total_weight, 2)


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
        "financial_strength": _fmt(row.get("financial_strength")),
        "growth": _fmt(row.get("growth")),
        "margin_quality": _fmt(row.get("margin_quality")),
        "valuation": _fmt(row.get("valuation")),
        "momentum": _fmt(row.get("momentum")),
        "gross_margin": _fmt(row.get("gross_margin")),
        "operating_margin": _fmt(row.get("operating_margin")),
        "net_margin": _fmt(row.get("net_margin")),
        "ebitda_margin": _fmt(row.get("ebitda_margin")),
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
