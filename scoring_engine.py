import pandas as pd
import numpy as np
from config import SCORING_WEIGHTS
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

    Applies individual sub-scores for each category and then computes
    a weighted composite score. Returns the DataFrame sorted by RS Score (descending).
    """
    result = df.copy()

    result["financial_strength"] = result.apply(calculate_financial_strength, axis=1)
    result["growth"] = result.apply(calculate_growth_score, axis=1)
    result["margin_quality"] = result.apply(calculate_margin_quality, axis=1)
    result["valuation"] = result.apply(calculate_valuation_score, axis=1)

    result["momentum"] = result.apply(
        lambda row: calculate_momentum_score(row.get("price_data")),
        axis=1,
    )

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
    Return a breakdown of all sub-scores and the composite RS Score
    for a single stock.
    """
    return {
        "symbol": row.get("symbol", "N/A"),
        "rs_score": row.get("rs_score", 0),
        "financial_strength": row.get("financial_strength"),
        "growth": row.get("growth"),
        "margin_quality": row.get("margin_quality"),
        "valuation": row.get("valuation"),
        "momentum": row.get("momentum"),
    }
