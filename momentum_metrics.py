import pandas as pd
import numpy as np
from typing import Optional


def calculate_momentum_score(price_data: pd.DataFrame) -> Optional[float]:
    """
    Calculate a momentum score (0-100) based on:
    - 1-month return
    - 3-month return
    - 6-month return
    - 12-month return
    - Relative strength vs. moving averages (50-day, 200-day)

    Weights favor medium-term momentum (3-6 months).
    """
    if price_data is None or price_data.empty or len(price_data) < 21:
        return None

    try:
        closes = price_data["close"].values
        current_price = closes[-1]

        sub_scores = []

        if len(closes) >= 21:
            ret_1m = (current_price / closes[-21] - 1)
            ret_1m_score = _return_to_score(ret_1m, scale=0.15)
            sub_scores.append(("1m_return", ret_1m_score, 0.15))

        if len(closes) >= 63:
            ret_3m = (current_price / closes[-63] - 1)
            ret_3m_score = _return_to_score(ret_3m, scale=0.30)
            sub_scores.append(("3m_return", ret_3m_score, 0.25))

        if len(closes) >= 126:
            ret_6m = (current_price / closes[-126] - 1)
            ret_6m_score = _return_to_score(ret_6m, scale=0.40)
            sub_scores.append(("6m_return", ret_6m_score, 0.30))

        if len(closes) >= 252:
            ret_12m = (current_price / closes[-252] - 1)
            ret_12m_score = _return_to_score(ret_12m, scale=0.60)
            sub_scores.append(("12m_return", ret_12m_score, 0.15))

        if len(closes) >= 50:
            ma50 = np.mean(closes[-50:])
            ma50_score = min(max((current_price / ma50 - 0.90) / 0.20, 0), 1) * 100
            sub_scores.append(("ma50", ma50_score, 0.10))

        if len(closes) >= 200:
            ma200 = np.mean(closes[-200:])
            ma200_score = min(max((current_price / ma200 - 0.85) / 0.30, 0), 1) * 100
            sub_scores.append(("ma200", ma200_score, 0.05))

        if not sub_scores:
            return None

        total_weight = sum(w for _, _, w in sub_scores)
        weighted_score = sum(s * w for _, s, w in sub_scores) / total_weight

        return round(min(max(weighted_score, 0), 100), 2)

    except (ValueError, IndexError, ZeroDivisionError):
        return None


def calculate_returns(price_data: pd.DataFrame) -> dict:
    """
    Calculate return metrics from price data.

    Returns a dict with 1m, 3m, 6m, and 12m returns.
    """
    if price_data is None or price_data.empty:
        return {}

    closes = price_data["close"].values
    current = closes[-1]
    results = {}

    periods = {"1m": 21, "3m": 63, "6m": 126, "12m": 252}
    for label, days in periods.items():
        if len(closes) >= days:
            results[f"return_{label}"] = round((current / closes[-days] - 1) * 100, 2)

    return results


def _return_to_score(ret: float, scale: float = 0.30) -> float:
    """Convert a return value to a 0-100 score using sigmoid-like scaling."""
    normalized = ret / scale
    score = 1 / (1 + np.exp(-5 * normalized))
    return score * 100
