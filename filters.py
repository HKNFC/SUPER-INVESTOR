import pandas as pd
import numpy as np
from typing import Optional


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
) -> pd.DataFrame:
    """
    Apply fundamental filters to the stock DataFrame.
    Only filters that are not None are applied.
    """
    filtered = df.copy()

    if max_pe is not None and "pe_ratio" in filtered.columns:
        filtered = filtered[
            filtered["pe_ratio"].apply(
                lambda x: x is None or (np.isfinite(x) and x <= max_pe)
            )
        ]

    if max_debt_to_equity is not None and "debt_to_equity" in filtered.columns:
        filtered = filtered[
            filtered["debt_to_equity"].apply(
                lambda x: x is None or (np.isfinite(x) and x <= max_debt_to_equity)
            )
        ]

    if min_roe is not None and "return_on_equity" in filtered.columns:
        filtered = filtered[
            filtered["return_on_equity"].apply(
                lambda x: x is not None and np.isfinite(x) and x >= min_roe
            )
        ]

    if min_gross_margin is not None and "gross_margin" in filtered.columns:
        filtered = filtered[
            filtered["gross_margin"].apply(
                lambda x: x is not None and np.isfinite(x) and x >= min_gross_margin
            )
        ]

    return filtered.reset_index(drop=True)
