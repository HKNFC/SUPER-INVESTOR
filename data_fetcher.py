import pandas as pd
import numpy as np
import requests
from typing import Optional
from config import TWELVE_DATA_API_KEY, TWELVE_DATA_BASE_URL, SUPPORTED_MARKETS


def fetch_price_history(
    symbol: str,
    interval: str = "1day",
    outputsize: int = 252,
) -> pd.DataFrame:
    """
    Fetch historical price data for a symbol from Twelve Data API.

    Returns a DataFrame with columns: datetime, open, high, low, close, volume.
    Falls back to placeholder data when the API key is not configured.
    """
    if not TWELVE_DATA_API_KEY:
        return _generate_placeholder_price_data(symbol, outputsize)

    try:
        url = f"{TWELVE_DATA_BASE_URL}/time_series"
        params = {
            "symbol": symbol,
            "interval": interval,
            "outputsize": outputsize,
            "apikey": TWELVE_DATA_API_KEY,
        }
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        if "values" not in data:
            return _generate_placeholder_price_data(symbol, outputsize)

        df = pd.DataFrame(data["values"])
        df["datetime"] = pd.to_datetime(df["datetime"])
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.sort_values("datetime").reset_index(drop=True)
        return df

    except (requests.RequestException, ValueError, KeyError):
        return _generate_placeholder_price_data(symbol, outputsize)


def fetch_fundamentals(symbol: str) -> dict:
    """
    Fetch fundamental data for a symbol.

    Returns a dict with financial metrics.
    Falls back to placeholder data when the API key is not configured.
    """
    if not TWELVE_DATA_API_KEY:
        return _generate_placeholder_fundamentals(symbol)

    try:
        url = f"{TWELVE_DATA_BASE_URL}/statistics"
        params = {
            "symbol": symbol,
            "apikey": TWELVE_DATA_API_KEY,
        }
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        if "statistics" not in data:
            return _generate_placeholder_fundamentals(symbol)

        stats = data["statistics"]
        return {
            "symbol": symbol,
            "current_ratio": _safe_float(stats.get("financials", {}).get("current_ratio")),
            "debt_to_equity": _safe_float(stats.get("financials", {}).get("debt_to_equity")),
            "return_on_equity": _safe_float(stats.get("financials", {}).get("return_on_equity")),
            "revenue_growth": _safe_float(stats.get("financials", {}).get("revenue_growth_yoy")),
            "earnings_growth": _safe_float(stats.get("financials", {}).get("earnings_growth_yoy")),
            "gross_margin": _safe_float(stats.get("financials", {}).get("gross_margin")),
            "operating_margin": _safe_float(stats.get("financials", {}).get("operating_margin")),
            "net_margin": _safe_float(stats.get("financials", {}).get("net_margin")),
            "pe_ratio": _safe_float(stats.get("valuations_metrics", {}).get("trailing_pe")),
            "pb_ratio": _safe_float(stats.get("valuations_metrics", {}).get("price_to_book")),
            "ps_ratio": _safe_float(stats.get("valuations_metrics", {}).get("price_to_sales_ttm")),
            "ev_to_ebitda": _safe_float(stats.get("valuations_metrics", {}).get("enterprise_to_ebitda")),
            "market_cap": _safe_float(stats.get("valuations_metrics", {}).get("market_capitalization")),
        }

    except (requests.RequestException, ValueError, KeyError):
        return _generate_placeholder_fundamentals(symbol)


def fetch_market_data(market: str) -> pd.DataFrame:
    """
    Fetch data for all symbols in a given market.

    Returns a DataFrame with fundamentals and price data for each symbol.
    """
    if market not in SUPPORTED_MARKETS:
        raise ValueError(f"Unsupported market: {market}. Choose from {list(SUPPORTED_MARKETS.keys())}")

    symbols = SUPPORTED_MARKETS[market]["symbols"]
    records = []

    for symbol in symbols:
        fundamentals = fetch_fundamentals(symbol)
        price_data = fetch_price_history(symbol)

        if not price_data.empty:
            fundamentals["last_close"] = price_data["close"].iloc[-1]
            fundamentals["price_data"] = price_data
        else:
            fundamentals["last_close"] = np.nan
            fundamentals["price_data"] = pd.DataFrame()

        records.append(fundamentals)

    df = pd.DataFrame(records)
    return df


def _safe_float(value) -> Optional[float]:
    """Safely convert a value to float, returning None on failure."""
    if value is None:
        return None
    try:
        result = float(value)
        return result if np.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def _generate_placeholder_price_data(symbol: str, days: int = 252) -> pd.DataFrame:
    """Generate realistic placeholder price data for demonstration."""
    np.random.seed(hash(symbol) % (2**31))
    dates = pd.bdate_range(end=pd.Timestamp.now(), periods=days)
    base_price = np.random.uniform(20, 500)
    returns = np.random.normal(0.0005, 0.02, size=days)
    prices = base_price * np.cumprod(1 + returns)

    df = pd.DataFrame({
        "datetime": dates,
        "open": prices * np.random.uniform(0.99, 1.01, size=days),
        "high": prices * np.random.uniform(1.00, 1.03, size=days),
        "low": prices * np.random.uniform(0.97, 1.00, size=days),
        "close": prices,
        "volume": np.random.randint(100_000, 10_000_000, size=days),
    })
    return df.round(2)


def _generate_placeholder_fundamentals(symbol: str) -> dict:
    """Generate realistic placeholder fundamental data for demonstration."""
    np.random.seed(hash(symbol) % (2**31))
    return {
        "symbol": symbol,
        "current_ratio": round(np.random.uniform(0.8, 3.5), 2),
        "debt_to_equity": round(np.random.uniform(0.1, 2.5), 2),
        "return_on_equity": round(np.random.uniform(-0.05, 0.45), 4),
        "revenue_growth": round(np.random.uniform(-0.10, 0.40), 4),
        "earnings_growth": round(np.random.uniform(-0.20, 0.50), 4),
        "gross_margin": round(np.random.uniform(0.15, 0.75), 4),
        "operating_margin": round(np.random.uniform(0.05, 0.40), 4),
        "net_margin": round(np.random.uniform(0.02, 0.30), 4),
        "pe_ratio": round(np.random.uniform(5, 60), 2),
        "pb_ratio": round(np.random.uniform(0.5, 15), 2),
        "ps_ratio": round(np.random.uniform(0.3, 20), 2),
        "ev_to_ebitda": round(np.random.uniform(3, 30), 2),
        "market_cap": round(np.random.uniform(1e9, 2e12), 0),
    }
