import pandas as pd
import numpy as np
from typing import Optional


def calculate_momentum_score(row: pd.Series) -> Optional[float]:
    """
    Calculate a momentum score (0-100) based on pre-computed return fields
    and price data.

    Uses return_1m/3m/6m/12m from the unified data model plus
    moving average signals from price_data when available.
    """
    sub_scores = []

    ret_1m = row.get("return_1m")
    if ret_1m is not None and np.isfinite(ret_1m):
        score = _return_to_score(ret_1m / 100, scale=0.15)
        sub_scores.append(("1m_return", score, 0.15))

    ret_3m = row.get("return_3m")
    if ret_3m is not None and np.isfinite(ret_3m):
        score = _return_to_score(ret_3m / 100, scale=0.30)
        sub_scores.append(("3m_return", score, 0.25))

    ret_6m = row.get("return_6m")
    if ret_6m is not None and np.isfinite(ret_6m):
        score = _return_to_score(ret_6m / 100, scale=0.40)
        sub_scores.append(("6m_return", score, 0.25))

    ret_12m = row.get("return_12m")
    if ret_12m is not None and np.isfinite(ret_12m):
        score = _return_to_score(ret_12m / 100, scale=0.60)
        sub_scores.append(("12m_return", score, 0.10))

    dist = row.get("distance_to_52w_high")
    if dist is not None and np.isfinite(dist):
        dist_score = min(max((dist + 30) / 30, 0), 1) * 100
        sub_scores.append(("52w_high", dist_score, 0.10))

    rel_ret = row.get("relative_return_vs_index")
    if rel_ret is not None and np.isfinite(rel_ret):
        rel_score = _return_to_score(rel_ret / 100, scale=0.30)
        sub_scores.append(("rel_return", rel_score, 0.10))

    price_data = row.get("price_data")
    if isinstance(price_data, pd.DataFrame) and not price_data.empty:
        closes = price_data["close"].values
        current_price = closes[-1]

        if len(closes) >= 50:
            ma50 = np.mean(closes[-50:])
            ma50_score = min(max((current_price / ma50 - 0.90) / 0.20, 0), 1) * 100
            sub_scores.append(("ma50", ma50_score, 0.03))

        if len(closes) >= 200:
            ma200 = np.mean(closes[-200:])
            ma200_score = min(max((current_price / ma200 - 0.85) / 0.30, 0), 1) * 100
            sub_scores.append(("ma200", ma200_score, 0.02))

    if not sub_scores:
        return None

    total_weight = sum(w for _, _, w in sub_scores)
    weighted_score = sum(s * w for _, s, w in sub_scores) / total_weight

    return round(min(max(weighted_score, 0), 100), 2)


def calculate_returns_from_price_data(price_data: pd.DataFrame) -> dict:
    """
    Calculate return metrics from raw price data.

    Returns a dict with return_1m, return_3m, return_6m, return_12m as percentages.
    """
    if price_data is None or price_data.empty:
        return {}

    closes = price_data["close"].values
    current = closes[-1]
    results = {}

    periods = {"return_1m": 21, "return_3m": 63, "return_6m": 126, "return_12m": 252}
    for label, days in periods.items():
        if len(closes) >= days and closes[-days] != 0:
            results[label] = round((current / closes[-days] - 1) * 100, 2)

    return results


def _return_to_score(ret: float, scale: float = 0.30) -> float:
    """Convert a return value to a 0-100 score using sigmoid-like scaling."""
    normalized = ret / scale
    score = 1 / (1 + np.exp(-5 * normalized))
    return score * 100
