import pandas as pd
import numpy as np
from typing import Optional
from data_model import safe_ratio


def filter_by_score(
    df: pd.DataFrame,
    min_rs_score: float = 0,
    top_n: Optional[int] = None,
) -> pd.DataFrame:
    """
    Filter stocks by minimum RS Score and optionally return only the top N.
    """
    filtered = df[df["rs_score"] >= min_rs_score].copy()

    if top_n is not None and top_n > 0:
        filtered = filtered.head(top_n)

    return filtered.reset_index(drop=True)


def filter_by_category_score(
    df: pd.DataFrame,
    category: str,
    min_score: float = 50,
) -> pd.DataFrame:
    """
    Filter stocks where a specific category score meets the minimum threshold.

    Valid categories: financial_strength, growth, margin_quality, valuation, momentum.
    """
    valid = [
        "financial_strength", "growth", "margin_quality",
        "valuation", "momentum",
    ]
    if category not in valid:
        raise ValueError(f"Invalid category '{category}'. Choose from {valid}")

    if category not in df.columns:
        return df

    mask = df[category].apply(
        lambda x: x is not None and np.isfinite(x) and x >= min_score
    )
    return df[mask].reset_index(drop=True)


def filter_by_fundamentals(
    df: pd.DataFrame,
    max_pe: Optional[float] = None,
    max_debt_to_equity: Optional[float] = None,
    min_roe: Optional[float] = None,
    min_gross_margin: Optional[float] = None,
    min_market_cap: Optional[float] = None,
    min_avg_volume: Optional[float] = None,
) -> pd.DataFrame:
    """
    Apply fundamental filters to the stock DataFrame.
    Only filters that are not None are applied.
    """
    filtered = df.copy()

    if max_pe is not None and "pe" in filtered.columns:
        filtered = filtered[
            filtered["pe"].apply(
                lambda x: x is None or (isinstance(x, (int, float)) and (np.isnan(x) or x <= max_pe))
            )
        ]

    if max_debt_to_equity is not None:
        def _check_de(row):
            de = safe_ratio(row.get("total_debt"), row.get("equity"))
            return np.isnan(de) or de <= max_debt_to_equity
        filtered = filtered[filtered.apply(_check_de, axis=1)]

    if min_roe is not None:
        def _check_roe(row):
            roe = safe_ratio(row.get("net_income"), row.get("equity"))
            return np.isfinite(roe) and roe >= min_roe
        filtered = filtered[filtered.apply(_check_roe, axis=1)]

    if min_gross_margin is not None:
        def _check_gm(row):
            gm = safe_ratio(row.get("gross_profit"), row.get("revenue"))
            return np.isfinite(gm) and gm >= min_gross_margin
        filtered = filtered[filtered.apply(_check_gm, axis=1)]

    if min_market_cap is not None and "market_cap" in filtered.columns:
        filtered = filtered[
            filtered["market_cap"].apply(
                lambda x: x is not None and np.isfinite(x) and x >= min_market_cap
            )
        ]

    if min_avg_volume is not None and "avg_volume_20d" in filtered.columns:
        filtered = filtered[
            filtered["avg_volume_20d"].apply(
                lambda x: x is not None and np.isfinite(x) and x >= min_avg_volume
            )
        ]

    return filtered.reset_index(drop=True)


def filter_by_sector(df: pd.DataFrame, sectors: list) -> pd.DataFrame:
    """Filter stocks to only include specified sectors."""
    if not sectors or "sector" not in df.columns:
        return df
    return df[df["sector"].isin(sectors)].reset_index(drop=True)


def filter_by_market(df: pd.DataFrame, market: str) -> pd.DataFrame:
    """Filter stocks to a specific market."""
    if "market" not in df.columns:
        return df
    return df[df["market"] == market].reset_index(drop=True)
