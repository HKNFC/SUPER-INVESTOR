"""
Momentum Metrics Engine

Reusable functions for computing price-based momentum indicators from
daily OHLCV history. Each function is independent and can be called
standalone or as part of the master enrichment pipeline.

Metrics:
  - Period returns: 1M, 3M, 6M, 12M
  - Distance to 52-week high
  - Relative performance vs benchmark index (S&P 500 / XU100)
  - Moving average signals: 50-day and 200-day

Benchmark indices:
  - USA → SPX (S&P 500)
  - BIST → XU100 (BIST 100)
"""

import logging
import pandas as pd
import numpy as np
from typing import Optional, Dict

logger = logging.getLogger("stock_screener.momentum")

TRADING_DAYS_1M = 21
TRADING_DAYS_3M = 63
TRADING_DAYS_6M = 126
TRADING_DAYS_12M = 252


# ---------------------------------------------------------------------------
# Period Return Functions
# ---------------------------------------------------------------------------

def calc_return(closes: np.ndarray, days: int) -> Optional[float]:
    """
    Calculate the return over a given number of trading days.

    For an N-day return we need N+1 data points (N intervals).
    The base price is closes[-(days+1)], the current is closes[-1].

    Args:
        closes: Array of closing prices sorted ascending by date.
        days: Number of trading days to look back.

    Returns:
        Return as a percentage (e.g., 5.2 means +5.2%), or None if
        there is insufficient history or the base price is zero.
    """
    if closes is None or len(closes) < days + 1:
        return None
    base = closes[-(days + 1)]
    if base == 0 or not np.isfinite(base):
        return None
    current = closes[-1]
    if not np.isfinite(current):
        return None
    return round((current / base - 1) * 100, 2)


def calc_return_1m(closes: np.ndarray) -> Optional[float]:
    """1-month return (21 trading days) as a percentage."""
    return calc_return(closes, TRADING_DAYS_1M)


def calc_return_3m(closes: np.ndarray) -> Optional[float]:
    """3-month return (63 trading days) as a percentage."""
    return calc_return(closes, TRADING_DAYS_3M)


def calc_return_6m(closes: np.ndarray) -> Optional[float]:
    """6-month return (126 trading days) as a percentage."""
    return calc_return(closes, TRADING_DAYS_6M)


def calc_return_12m(closes: np.ndarray) -> Optional[float]:
    """12-month return (252 trading days) as a percentage."""
    return calc_return(closes, TRADING_DAYS_12M)


def calc_all_period_returns(closes: np.ndarray) -> Dict[str, Optional[float]]:
    """
    Calculate all four standard period returns from a closing price array.

    Returns a dict with keys return_1m, return_3m, return_6m, return_12m.
    Values are percentages or None if insufficient history.
    """
    return {
        "return_1m": calc_return_1m(closes),
        "return_3m": calc_return_3m(closes),
        "return_6m": calc_return_6m(closes),
        "return_12m": calc_return_12m(closes),
    }


def calc_returns_from_price_data(price_data: pd.DataFrame) -> Dict[str, Optional[float]]:
    """
    Calculate all period returns from a price DataFrame.

    Expects a DataFrame with a 'close' column sorted ascending by date.
    """
    if price_data is None or price_data.empty or "close" not in price_data.columns:
        return {
            "return_1m": None,
            "return_3m": None,
            "return_6m": None,
            "return_12m": None,
        }
    return calc_all_period_returns(price_data["close"].values)


# ---------------------------------------------------------------------------
# 52-Week High
# ---------------------------------------------------------------------------

def calc_distance_to_52w_high(price_data: pd.DataFrame) -> Optional[float]:
    """
    Calculate the percentage distance from the current price to the 52-week high.

    Returns a negative percentage (e.g., -5.0 means 5% below the 52-week high).
    Returns 0.0 if the current price equals the 52-week high.
    Returns None if insufficient data (less than 21 trading days).

    Args:
        price_data: DataFrame with 'close' and 'high' columns, sorted ascending.
    """
    if price_data is None or price_data.empty:
        return None
    if "high" not in price_data.columns or "close" not in price_data.columns:
        return None
    if len(price_data) < TRADING_DAYS_1M:
        return None

    lookback = min(TRADING_DAYS_12M, len(price_data))
    high_52w = float(price_data["high"].tail(lookback).max())
    current = float(price_data["close"].iloc[-1])

    if not np.isfinite(high_52w) or high_52w <= 0:
        return None
    if not np.isfinite(current):
        return None

    return round((current / high_52w - 1) * 100, 2)


def calc_52w_high(price_data: pd.DataFrame) -> Optional[float]:
    """
    Get the 52-week high price from daily history.

    Returns None if insufficient data.
    """
    if price_data is None or price_data.empty or "high" not in price_data.columns:
        return None
    if len(price_data) < TRADING_DAYS_1M:
        return None
    lookback = min(TRADING_DAYS_12M, len(price_data))
    return float(price_data["high"].tail(lookback).max())


# ---------------------------------------------------------------------------
# Benchmark / Relative Performance
# ---------------------------------------------------------------------------

def calc_relative_return(
    stock_closes: np.ndarray,
    index_closes: np.ndarray,
    days: int = TRADING_DAYS_12M,
) -> Optional[float]:
    """
    Calculate the relative performance of a stock vs a benchmark index.

    relative_return = stock_return - index_return

    A positive value means the stock outperformed the index over the period.

    Args:
        stock_closes: Stock closing prices, sorted ascending.
        index_closes: Benchmark index closing prices, sorted ascending.
        days: Number of trading days for the comparison period.

    Returns:
        Relative return as a percentage, or None if either series
        has insufficient data.
    """
    stock_ret = calc_return(stock_closes, days)
    index_ret = calc_return(index_closes, days)

    if stock_ret is None or index_ret is None:
        return None

    return round(stock_ret - index_ret, 2)


def calc_relative_return_aligned(
    stock_data: pd.DataFrame,
    index_data: pd.DataFrame,
    days: int = TRADING_DAYS_12M,
) -> Optional[float]:
    """
    Calculate relative return using date-aligned closing prices.

    Aligns the stock and index DataFrames on their 'datetime' column
    before computing returns, preventing calendar-mismatch distortion.

    Args:
        stock_data: Stock OHLCV DataFrame with 'datetime' and 'close'.
        index_data: Index OHLCV DataFrame with 'datetime' and 'close'.
        days: Number of trading days for the comparison.

    Returns:
        Relative return as a percentage, or None if alignment fails.
    """
    if stock_data is None or stock_data.empty:
        return None
    if index_data is None or index_data.empty:
        return None
    if "datetime" not in stock_data.columns or "datetime" not in index_data.columns:
        stock_closes = stock_data["close"].values if "close" in stock_data.columns else np.array([])
        index_closes = index_data["close"].values if "close" in index_data.columns else np.array([])
        return calc_relative_return(stock_closes, index_closes, days)
    if "close" not in stock_data.columns or "close" not in index_data.columns:
        return None

    stock_ts = stock_data[["datetime", "close"]].copy()
    stock_ts.columns = ["datetime", "stock_close"]
    index_ts = index_data[["datetime", "close"]].copy()
    index_ts.columns = ["datetime", "index_close"]

    stock_ts["datetime"] = pd.to_datetime(stock_ts["datetime"])
    index_ts["datetime"] = pd.to_datetime(index_ts["datetime"])

    merged = pd.merge(stock_ts, index_ts, on="datetime", how="inner")
    merged = merged.sort_values("datetime").reset_index(drop=True)

    if len(merged) < days + 1:
        return calc_relative_return(
            stock_data["close"].values,
            index_data["close"].values,
            days,
        )

    stock_ret = calc_return(merged["stock_close"].values, days)
    index_ret = calc_return(merged["index_close"].values, days)

    if stock_ret is None or index_ret is None:
        return None

    return round(stock_ret - index_ret, 2)


def get_benchmark_history(market: str) -> pd.DataFrame:
    """
    Fetch the benchmark index history for a market.

    Uses the price provider if an API key is configured, otherwise
    generates placeholder index data.

    Benchmark mapping (from config.BENCHMARK_INDEX):
      - USA → SPX (S&P 500)
      - BIST → XU100 (BIST 100)
    """
    from config import BENCHMARK_INDEX
    from data_fetcher import get_provider, _generate_placeholder_price_data

    index_ticker = BENCHMARK_INDEX.get(market)
    if not index_ticker:
        logger.warning("No benchmark index configured for market %s", market)
        return pd.DataFrame()

    provider = get_provider()
    if provider is None:
        return _generate_placeholder_price_data(index_ticker, days=TRADING_DAYS_12M + 10)

    try:
        history = provider.get_daily_history(
            index_ticker,
            outputsize=TRADING_DAYS_12M,
            market=market,
        )
        if history.empty:
            logger.warning(
                "Empty history for benchmark %s — using placeholder",
                index_ticker,
            )
            return _generate_placeholder_price_data(index_ticker, days=TRADING_DAYS_12M + 10)
        return history
    except Exception as e:
        logger.error(
            "Error fetching benchmark %s: %s", index_ticker, type(e).__name__
        )
        return _generate_placeholder_price_data(index_ticker, days=TRADING_DAYS_12M + 10)


# ---------------------------------------------------------------------------
# Moving Average Signals
# ---------------------------------------------------------------------------

def calc_ma_ratio(closes: np.ndarray, window: int) -> Optional[float]:
    """
    Calculate the ratio of current price to its moving average.

    A ratio > 1.0 means price is above the MA (bullish).
    A ratio < 1.0 means price is below the MA (bearish).

    Returns None if insufficient data for the given window.
    """
    if closes is None or len(closes) < window:
        return None
    ma = np.mean(closes[-window:])
    if ma == 0 or not np.isfinite(ma):
        return None
    current = closes[-1]
    if not np.isfinite(current):
        return None
    return round(current / ma, 4)


def calc_ma50_ratio(closes: np.ndarray) -> Optional[float]:
    """Ratio of current price to 50-day simple moving average."""
    return calc_ma_ratio(closes, 50)


def calc_ma200_ratio(closes: np.ndarray) -> Optional[float]:
    """Ratio of current price to 200-day simple moving average."""
    return calc_ma_ratio(closes, 200)


# ---------------------------------------------------------------------------
# Average Volume
# ---------------------------------------------------------------------------

def calc_avg_volume_20d(price_data: pd.DataFrame) -> Optional[float]:
    """
    Calculate the 20-day average trading volume.

    Returns None if insufficient data (less than 20 trading days)
    or volume column is missing.
    """
    if price_data is None or price_data.empty:
        return None
    if "volume" not in price_data.columns:
        return None
    if len(price_data) < 20:
        return None
    return round(float(price_data["volume"].tail(20).mean()), 0)


# ---------------------------------------------------------------------------
# Master DataFrame Enrichment
# ---------------------------------------------------------------------------

MOMENTUM_COLUMNS = [
    "return_1m",
    "return_3m",
    "return_6m",
    "return_12m",
    "distance_to_52w_high",
    "relative_return_vs_index",
]


def append_momentum_fields(
    df: pd.DataFrame,
    benchmark_history: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Append all momentum-derived fields to the master DataFrame.

    Computes from each row's 'price_data' column (daily OHLCV DataFrame):
      - return_1m, return_3m, return_6m, return_12m
      - distance_to_52w_high
      - relative_return_vs_index (requires benchmark_history)
      - avg_volume_20d

    Existing values in these columns are overwritten with freshly
    computed results. If a row lacks price_data, fields are set to NaN.

    Args:
        df: Master DataFrame with a 'price_data' column per stock.
        benchmark_history: Daily OHLCV DataFrame for the benchmark index.
            If None, relative_return_vs_index is set to NaN.
    """
    result = df.copy()

    returns_1m = []
    returns_3m = []
    returns_6m = []
    returns_12m = []
    dist_52w = []
    rel_returns = []
    avg_vols = []

    for _, row in result.iterrows():
        price_data = row.get("price_data")

        if not isinstance(price_data, pd.DataFrame) or price_data.empty:
            returns_1m.append(np.nan)
            returns_3m.append(np.nan)
            returns_6m.append(np.nan)
            returns_12m.append(np.nan)
            dist_52w.append(np.nan)
            rel_returns.append(np.nan)
            avg_vols.append(np.nan)
            continue

        closes = price_data["close"].values if "close" in price_data.columns else np.array([])

        r1 = calc_return_1m(closes)
        returns_1m.append(r1 if r1 is not None else np.nan)

        r3 = calc_return_3m(closes)
        returns_3m.append(r3 if r3 is not None else np.nan)

        r6 = calc_return_6m(closes)
        returns_6m.append(r6 if r6 is not None else np.nan)

        r12 = calc_return_12m(closes)
        returns_12m.append(r12 if r12 is not None else np.nan)

        d52 = calc_distance_to_52w_high(price_data)
        dist_52w.append(d52 if d52 is not None else np.nan)

        if benchmark_history is not None and not benchmark_history.empty:
            rel = calc_relative_return_aligned(price_data, benchmark_history)
        else:
            rel = None
        rel_returns.append(rel if rel is not None else np.nan)

        vol = calc_avg_volume_20d(price_data)
        avg_vols.append(vol if vol is not None else np.nan)

    result["return_1m"] = returns_1m
    result["return_3m"] = returns_3m
    result["return_6m"] = returns_6m
    result["return_12m"] = returns_12m
    result["distance_to_52w_high"] = dist_52w
    result["relative_return_vs_index"] = rel_returns
    result["avg_volume_20d"] = avg_vols

    return result


# ---------------------------------------------------------------------------
# Momentum Score (used by scoring_engine.py)
# ---------------------------------------------------------------------------

def calculate_momentum_score(row: pd.Series) -> Optional[float]:
    """
    Calculate a composite momentum score (0-100) from pre-computed fields
    and raw price data.

    Scoring components and weights:
      - 1M return:   15%  (recent trend)
      - 3M return:   25%  (medium trend)
      - 6M return:   25%  (intermediate trend)
      - 12M return:  10%  (long trend)
      - 52W high:    10%  (proximity to peak)
      - Relative vs index: 10%  (market outperformance)
      - MA50 signal:  3%  (short-term trend)
      - MA200 signal: 2%  (long-term trend)

    Returns None if no sub-metric could be computed.
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
        # 0% from high scores 100, -30% from high scores 0
        dist_score = min(max((dist + 30) / 30, 0), 1) * 100
        sub_scores.append(("52w_high", dist_score, 0.10))

    rel_ret = row.get("relative_return_vs_index")
    if rel_ret is not None and np.isfinite(rel_ret):
        rel_score = _return_to_score(rel_ret / 100, scale=0.30)
        sub_scores.append(("rel_return", rel_score, 0.10))

    price_data = row.get("price_data")
    if isinstance(price_data, pd.DataFrame) and not price_data.empty:
        closes = price_data["close"].values if "close" in price_data.columns else np.array([])

        ma50 = calc_ma50_ratio(closes)
        if ma50 is not None:
            # Price at 90% of MA50 scores 0, at 110% scores 100
            ma50_score = min(max((ma50 - 0.90) / 0.20, 0), 1) * 100
            sub_scores.append(("ma50", ma50_score, 0.03))

        ma200 = calc_ma200_ratio(closes)
        if ma200 is not None:
            # Price at 85% of MA200 scores 0, at 115% scores 100
            ma200_score = min(max((ma200 - 0.85) / 0.30, 0), 1) * 100
            sub_scores.append(("ma200", ma200_score, 0.02))

    if not sub_scores:
        return None

    total_weight = sum(w for _, _, w in sub_scores)
    weighted_score = sum(s * w for _, s, w in sub_scores) / total_weight

    return round(min(max(weighted_score, 0), 100), 2)


def _return_to_score(ret: float, scale: float = 0.30) -> float:
    """
    Convert a return value to a 0-100 score using sigmoid-like scaling.

    Returns close to 100 for strong positive returns and close to 0
    for strong negative returns, with 50 at zero return.
    """
    normalized = ret / scale
    score = 1 / (1 + np.exp(-5 * normalized))
    return score * 100
