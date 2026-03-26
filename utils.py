import pandas as pd
import numpy as np


def format_number(value, decimals: int = 2, prefix: str = "", suffix: str = "") -> str:
    """Format a number for display, handling None and NaN."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "N/A"
    return f"{prefix}{value:,.{decimals}f}{suffix}"


def format_percentage(value, decimals: int = 2) -> str:
    """Format a value as a percentage string."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "N/A"
    return f"{value * 100:,.{decimals}f}%"


def format_market_cap(value) -> str:
    """Format market cap into human-readable form (B/M/T)."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "N/A"
    if value >= 1e12:
        return f"${value / 1e12:,.2f}T"
    if value >= 1e9:
        return f"${value / 1e9:,.2f}B"
    if value >= 1e6:
        return f"${value / 1e6:,.2f}M"
    return f"${value:,.0f}"


def score_color(score) -> str:
    """Return a color indicator based on score value."""
    if score is None or (isinstance(score, float) and np.isnan(score)):
        return "gray"
    if score >= 75:
        return "green"
    if score >= 50:
        return "orange"
    return "red"


def prepare_display_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Prepare a DataFrame for display in the UI by selecting
    and formatting the relevant columns.
    """
    display_cols = [
        "rank", "symbol", "last_close", "rs_score",
        "financial_strength", "growth", "margin_quality",
        "valuation", "momentum",
    ]

    available = [c for c in display_cols if c in df.columns]
    result = df[available].copy()

    score_cols = [
        "rs_score", "financial_strength", "growth",
        "margin_quality", "valuation", "momentum",
    ]
    for col in score_cols:
        if col in result.columns:
            result[col] = result[col].apply(
                lambda x: round(x, 1) if x is not None and np.isfinite(x) else None
            )

    if "last_close" in result.columns:
        result["last_close"] = result["last_close"].apply(
            lambda x: round(x, 2) if x is not None and np.isfinite(x) else None
        )

    return result
