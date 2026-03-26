import pandas as pd
import numpy as np
import requests
from typing import Optional
from config import TWELVE_DATA_API_KEY, TWELVE_DATA_BASE_URL, SUPPORTED_MARKETS
from data_model import (
    ensure_columns, coerce_numeric_columns, get_mock_data,
    safe_float, ALL_COLUMNS,
)


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
    Fetch fundamental data for a symbol from Twelve Data API.

    Returns a dict with fields matching the unified data model.
    Falls back to empty dict when the API key is not configured.
    """
    if not TWELVE_DATA_API_KEY:
        return {}

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
            return {}

        stats = data["statistics"]
        financials = stats.get("financials", {})
        valuations = stats.get("valuations_metrics", {})

        return {
            "ticker": symbol,
            "company_name": data.get("name", symbol),
            "market_cap": safe_float(valuations.get("market_capitalization")),
            "pe": safe_float(valuations.get("trailing_pe")),
            "pb": safe_float(valuations.get("price_to_book")),
            "ev_ebitda": safe_float(valuations.get("enterprise_to_ebitda")),
            "revenue": safe_float(financials.get("revenue")),
            "net_income": safe_float(financials.get("net_income")),
            "gross_profit": safe_float(financials.get("gross_profit")),
            "operating_income": safe_float(financials.get("operating_income")),
            "ebitda": safe_float(financials.get("ebitda")),
            "total_assets": safe_float(financials.get("total_assets")),
            "total_debt": safe_float(financials.get("total_debt")),
            "equity": safe_float(financials.get("stockholders_equity")),
            "cash": safe_float(financials.get("cash_and_equivalents")),
            "eps": safe_float(financials.get("diluted_eps")),
        }

    except (requests.RequestException, ValueError, KeyError):
        return {}


def enrich_price_fields(row: dict, price_data: pd.DataFrame) -> dict:
    """
    Enrich a stock record with price-derived fields from historical data.

    Computes: price, return_1m/3m/6m/12m, avg_volume_20d, distance_to_52w_high.
    """
    result = dict(row)

    if price_data is None or price_data.empty:
        return result

    closes = price_data["close"].values
    current = closes[-1]
    result["price"] = round(current, 2)

    periods = {"return_1m": 21, "return_3m": 63, "return_6m": 126, "return_12m": 252}
    for field, days in periods.items():
        if len(closes) >= days and closes[-days] != 0:
            result[field] = round((current / closes[-days] - 1) * 100, 2)

    if "volume" in price_data.columns and len(price_data) >= 20:
        result["avg_volume_20d"] = round(price_data["volume"].tail(20).mean(), 0)

    high_52w = price_data["high"].tail(252).max() if len(price_data) >= 21 else current
    if high_52w > 0:
        result["distance_to_52w_high"] = round((current / high_52w - 1) * 100, 2)

    return result


def fetch_market_data(market: str) -> pd.DataFrame:
    """
    Fetch data for all symbols in a given market.

    When no API key is configured, returns mock data from the unified data model.
    With an API key, fetches live data and enriches it with price-derived fields.
    """
    if market not in SUPPORTED_MARKETS:
        raise ValueError(f"Unsupported market: {market}. Choose from {list(SUPPORTED_MARKETS.keys())}")

    if not TWELVE_DATA_API_KEY:
        df = get_mock_data(market)
        df["price_data"] = df["ticker"].apply(
            lambda t: _generate_placeholder_price_data(t)
        )
        return df

    symbols = SUPPORTED_MARKETS[market]["symbols"]
    market_info = SUPPORTED_MARKETS[market]
    records = []

    for symbol in symbols:
        fundamentals = fetch_fundamentals(symbol)
        price_data = fetch_price_history(symbol)

        if not fundamentals.get("ticker"):
            fundamentals["ticker"] = symbol

        fundamentals["market"] = market
        fundamentals = enrich_price_fields(fundamentals, price_data)
        fundamentals["price_data"] = price_data

        records.append(fundamentals)

    df = pd.DataFrame(records)
    df = ensure_columns(df)
    df = coerce_numeric_columns(df)
    return df


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
