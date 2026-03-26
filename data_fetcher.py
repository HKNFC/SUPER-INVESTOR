import logging
import pandas as pd
import numpy as np
from typing import Optional
from config import TWELVE_DATA_API_KEY, TWELVE_DATA_BASE_URL, SUPPORTED_MARKETS
from data_model import (
    ensure_columns, coerce_numeric_columns, get_mock_data,
    safe_float, ALL_COLUMNS,
)
from price_provider import PriceProvider

logger = logging.getLogger("stock_screener.fetcher")

_provider_instance: Optional[PriceProvider] = None


def get_provider() -> Optional[PriceProvider]:
    """
    Get or create the active price data provider.

    Returns None if no API key is configured (mock data will be used instead).
    Provider instance is reused across calls to preserve cache.
    """
    global _provider_instance

    if _provider_instance is not None:
        return _provider_instance

    if not TWELVE_DATA_API_KEY:
        return None

    try:
        from twelve_data_provider import TwelveDataProvider
        _provider_instance = TwelveDataProvider(
            api_key=TWELVE_DATA_API_KEY,
            base_url=TWELVE_DATA_BASE_URL,
        )
        logger.info("Twelve Data provider initialized")
        return _provider_instance
    except (ImportError, ValueError) as e:
        logger.error("Failed to initialize price provider: %s", e)
        return None


def reset_provider() -> None:
    """Reset the provider instance (useful for testing or key rotation)."""
    global _provider_instance
    _provider_instance = None


def fetch_price_history(
    ticker: str,
    outputsize: int = 252,
    market: Optional[str] = None,
) -> pd.DataFrame:
    """
    Fetch daily OHLCV history for a ticker.

    Uses the configured provider if available, otherwise returns placeholder data.
    """
    provider = get_provider()
    if provider is None:
        return _generate_placeholder_price_data(ticker, outputsize)

    try:
        history = provider.get_daily_history(ticker, outputsize=outputsize, market=market)

        if history.empty:
            logger.warning("Provider returned empty history for %s — using placeholder", ticker)
            return _generate_placeholder_price_data(ticker, outputsize)

        return history

    except Exception as e:
        logger.error("Error fetching history for %s: %s", ticker, type(e).__name__)
        return _generate_placeholder_price_data(ticker, outputsize)


def fetch_latest_price(ticker: str, market: Optional[str] = None) -> Optional[float]:
    """
    Get the most recent price for a ticker.

    Uses the provider's quote endpoint with fallback to last close.
    """
    provider = get_provider()
    if provider is None:
        return None

    try:
        return provider.get_latest_price(ticker, market=market)
    except Exception as e:
        logger.error("Error fetching latest price for %s: %s", ticker, type(e).__name__)
        return None


def fetch_period_returns(ticker: str, market: Optional[str] = None) -> dict:
    """
    Calculate 1M, 3M, 6M, 12M returns for a ticker.

    Returns a dict with keys return_1m, return_3m, return_6m, return_12m.
    """
    provider = get_provider()
    if provider is None:
        return {}

    try:
        return provider.get_period_returns(ticker, market=market)
    except Exception as e:
        logger.error("Error calculating returns for %s: %s", ticker, type(e).__name__)
        return {}


def fetch_52w_high(ticker: str, market: Optional[str] = None) -> Optional[float]:
    """Get the 52-week high price for a ticker."""
    provider = get_provider()
    if provider is None:
        return None

    try:
        return provider.get_52w_high(ticker, market=market)
    except Exception as e:
        logger.error("Error fetching 52w high for %s: %s", ticker, type(e).__name__)
        return None


def fetch_avg_volume_20d(ticker: str, market: Optional[str] = None) -> Optional[float]:
    """Get the 20-day average volume for a ticker."""
    provider = get_provider()
    if provider is None:
        return None

    try:
        return provider.get_avg_volume_20d(ticker, market=market)
    except Exception as e:
        logger.error("Error fetching avg volume for %s: %s", ticker, type(e).__name__)
        return None


def fetch_fundamentals(symbol: str) -> dict:
    """
    Fetch fundamental data for a symbol from Twelve Data API.

    Returns a dict with fields matching the unified data model.
    Falls back to empty dict when the API key is not configured.
    """
    if not TWELVE_DATA_API_KEY:
        return {}

    try:
        import requests
        url = f"{TWELVE_DATA_BASE_URL}/statistics"
        params = {
            "symbol": symbol,
            "apikey": TWELVE_DATA_API_KEY,
        }
        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()

        if "status" in data and data["status"] == "error":
            logger.warning("Twelve Data statistics error for %s: %s", symbol, data.get("message", ""))
            return {}

        if "statistics" not in data:
            logger.warning("No statistics data for %s", symbol)
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

    except Exception as e:
        logger.error("Error fetching fundamentals for %s: %s", symbol, type(e).__name__)
        return {}


def fetch_market_data(market: str) -> pd.DataFrame:
    """
    Fetch data for all symbols in a given market.

    When no API key is configured, returns mock data from the unified data model.
    With an API key, fetches live data via the provider and enriches with price fields.

    Tickers that fail to fetch are skipped with a log warning.
    """
    if market not in SUPPORTED_MARKETS:
        raise ValueError(f"Unsupported market: {market}. Choose from {list(SUPPORTED_MARKETS.keys())}")

    from momentum_metrics import append_momentum_fields, get_benchmark_history

    provider = get_provider()

    if provider is None:
        logger.info("No API key configured — using mock data for %s", market)
        df = get_mock_data(market)
        df["price_data"] = df["ticker"].apply(
            lambda t: _generate_placeholder_price_data(t)
        )
        benchmark = get_benchmark_history(market)
        df = append_momentum_fields(df, benchmark_history=benchmark)
        return df

    symbols = SUPPORTED_MARKETS[market]["symbols"]
    records = []
    skipped = []

    for symbol in symbols:
        try:
            fundamentals = fetch_fundamentals(symbol)

            if not fundamentals.get("ticker"):
                fundamentals["ticker"] = symbol

            fundamentals["market"] = market
            fundamentals["sector"] = fundamentals.get("sector", "")
            fundamentals["industry"] = fundamentals.get("industry", "")

            enriched = provider.enrich_record(fundamentals)
            records.append(enriched)

            logger.info(
                "Fetched %s: price=%s, returns=%s/%s/%s/%s",
                symbol,
                enriched.get("price", "N/A"),
                enriched.get("return_1m", "N/A"),
                enriched.get("return_3m", "N/A"),
                enriched.get("return_6m", "N/A"),
                enriched.get("return_12m", "N/A"),
            )

        except Exception as e:
            logger.warning("Skipping %s due to error: %s", symbol, e)
            skipped.append(symbol)
            continue

    if skipped:
        logger.warning("Skipped %d tickers: %s", len(skipped), ", ".join(skipped))

    if not records:
        logger.error("No data fetched for market %s — falling back to mock data", market)
        df = get_mock_data(market)
        df["price_data"] = df["ticker"].apply(
            lambda t: _generate_placeholder_price_data(t)
        )
        benchmark = get_benchmark_history(market)
        df = append_momentum_fields(df, benchmark_history=benchmark)
        return df

    df = pd.DataFrame(records)
    df = ensure_columns(df)
    df = coerce_numeric_columns(df)

    benchmark = get_benchmark_history(market)
    df = append_momentum_fields(df, benchmark_history=benchmark)

    return df


def _generate_placeholder_price_data(symbol: str, days: int = 260) -> pd.DataFrame:
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
