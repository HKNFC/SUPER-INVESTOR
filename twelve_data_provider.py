import time
import hashlib
import logging
import pandas as pd
import numpy as np
import requests
from typing import Optional, Dict, Any
from urllib.parse import urlencode
from price_provider import PriceProvider
from config import CACHE_TTL_HISTORY, CACHE_TTL_QUOTE

logger = logging.getLogger("stock_screener.twelve_data")

_CACHE: Dict[str, Dict[str, Any]] = {}

REQUEST_TIMEOUT = 20


def _cache_key(prefix: str, **kwargs) -> str:
    """Build a deterministic cache key from prefix and keyword args."""
    parts = [prefix] + [f"{k}={v}" for k, v in sorted(kwargs.items())]
    raw = "|".join(parts)
    return hashlib.md5(raw.encode()).hexdigest()


def _cache_get(key: str) -> Optional[Any]:
    """Retrieve a value from cache if it exists and hasn't expired."""
    entry = _CACHE.get(key)
    if entry is None:
        return None
    if time.time() > entry["expires"]:
        del _CACHE[key]
        return None
    return entry["value"]


def _cache_set(key: str, value: Any, ttl: int) -> None:
    """Store a value in cache with a TTL in seconds."""
    _CACHE[key] = {"value": value, "expires": time.time() + ttl}


def clear_cache() -> int:
    """Clear the entire cache. Returns the number of entries removed."""
    count = len(_CACHE)
    _CACHE.clear()
    return count


def get_cache_stats() -> dict:
    """Return cache size and number of expired entries."""
    now = time.time()
    expired = sum(1 for e in _CACHE.values() if now > e["expires"])
    return {"total": len(_CACHE), "expired": expired, "active": len(_CACHE) - expired}


class TwelveDataProvider(PriceProvider):
    """
    Twelve Data API implementation of the PriceProvider interface.

    Supports US tickers (e.g., AAPL) and BIST tickers. For BIST, the provider
    maps bare tickers to their exchange-suffixed form automatically.

    Rate limiting: Twelve Data free tier allows 8 requests/minute and 800/day.
    The provider logs warnings when approaching limits.
    """

    BIST_EXCHANGE_SUFFIX = ":BIST"

    def __init__(self, api_key: str, base_url: str = "https://api.twelvedata.com"):
        if not api_key:
            raise ValueError("TWELVE_DATA_API_KEY is required but empty")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._request_count = 0
        self._request_timestamps: list[float] = []

    def _resolve_symbol(self, ticker: str, market: Optional[str] = None) -> str:
        """
        Resolve a ticker to the Twelve Data symbol format.

        For BIST tickers, appends the exchange suffix if not already present.
        For US tickers, returns as-is.
        """
        if market and market.upper() == "BIST":
            if not ticker.endswith(self.BIST_EXCHANGE_SUFFIX):
                return f"{ticker}{self.BIST_EXCHANGE_SUFFIX}"
        return ticker

    def _api_request(self, endpoint: str, params: dict) -> Optional[dict]:
        """
        Make a request to the Twelve Data API with error handling and logging.

        Returns the parsed JSON response, or None on failure.
        """
        url = f"{self._base_url}/{endpoint}"
        params["apikey"] = self._api_key

        self._track_rate()

        try:
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)

            if response.status_code == 429:
                logger.warning("Rate limit hit for Twelve Data API — waiting before retry")
                time.sleep(10)
                response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)

            response.raise_for_status()
            data = response.json()

            if "status" in data and data["status"] == "error":
                msg = data.get("message", "Unknown API error")
                code = data.get("code", 0)
                logger.warning(
                    "Twelve Data API error for %s (endpoint=%s): [%s] %s",
                    params.get("symbol", "?"), endpoint, code, msg,
                )
                return None

            return data

        except requests.Timeout:
            logger.warning("Timeout fetching %s for ticker %s", endpoint, params.get("symbol", "?"))
            return None
        except requests.ConnectionError:
            logger.error("Connection error to Twelve Data API (endpoint=%s)", endpoint)
            return None
        except requests.HTTPError as e:
            logger.warning(
                "HTTP %s error for %s (endpoint=%s)",
                e.response.status_code if e.response else "?",
                params.get("symbol", "?"),
                endpoint,
            )
            return None
        except (ValueError, KeyError) as e:
            logger.warning("Failed to parse Twelve Data response for %s: %s", params.get("symbol", "?"), type(e).__name__)
            return None

    def _track_rate(self) -> None:
        """Track request rate and warn if approaching limits."""
        now = time.time()
        self._request_count += 1
        self._request_timestamps.append(now)

        self._request_timestamps = [t for t in self._request_timestamps if now - t < 60]
        recent = len(self._request_timestamps)

        if recent >= 7:
            logger.warning("Approaching Twelve Data rate limit: %d requests in last 60s", recent)

    def get_daily_history(
        self,
        ticker: str,
        outputsize: int = 252,
        market: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Fetch daily OHLCV history from Twelve Data.

        Results are cached using TTL from config.CACHE_TTL_HISTORY.
        Returns a copy to prevent cache mutation.
        """
        symbol = self._resolve_symbol(ticker, market)
        ck = _cache_key("history", symbol=symbol, outputsize=outputsize)

        cached = _cache_get(ck)
        if cached is not None:
            return cached.copy()

        data = self._api_request("time_series", {
            "symbol": symbol,
            "interval": "1day",
            "outputsize": outputsize,
        })

        if data is None or "values" not in data:
            logger.warning("No history data for %s — returning empty DataFrame", ticker)
            return pd.DataFrame(columns=["datetime", "open", "high", "low", "close", "volume"])

        df = pd.DataFrame(data["values"])
        df["datetime"] = pd.to_datetime(df["datetime"])
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.sort_values("datetime").reset_index(drop=True)

        _cache_set(ck, df, ttl=CACHE_TTL_HISTORY)
        return df.copy()

    def get_quote(
        self,
        ticker: str,
        market: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Fetch the latest real-time quote from Twelve Data.

        Results are cached using TTL from config.CACHE_TTL_QUOTE.
        """
        symbol = self._resolve_symbol(ticker, market)
        ck = _cache_key("quote", symbol=symbol)

        cached = _cache_get(ck)
        if cached is not None:
            return dict(cached)

        data = self._api_request("quote", {"symbol": symbol})

        if data is None or "close" not in data:
            logger.warning("No quote data for %s", ticker)
            return None

        result = {
            "price": _safe_float(data.get("close")),
            "open": _safe_float(data.get("open")),
            "high": _safe_float(data.get("high")),
            "low": _safe_float(data.get("low")),
            "volume": _safe_float(data.get("volume")),
            "change": _safe_float(data.get("change")),
            "percent_change": _safe_float(data.get("percent_change")),
            "fifty_two_week_high": _safe_float(data.get("fifty_two_week", {}).get("high")),
            "fifty_two_week_low": _safe_float(data.get("fifty_two_week", {}).get("low")),
            "name": data.get("name", ticker),
            "exchange": data.get("exchange", ""),
        }

        _cache_set(ck, result, ttl=CACHE_TTL_QUOTE)
        return dict(result)

    def get_52w_high(
        self,
        ticker: str,
        market: Optional[str] = None,
    ) -> Optional[float]:
        """
        Get the 52-week high, preferring quote data, falling back to history.
        """
        quote = self.get_quote(ticker, market=market)
        if quote and quote.get("fifty_two_week_high") is not None:
            return quote["fifty_two_week_high"]

        return super().get_52w_high(ticker, market=market)

    def enrich_record(self, record: dict) -> dict:
        """
        Enrich a stock record with all price-derived fields from Twelve Data.

        Fetches history once and derives all fields from it.
        """
        ticker = record.get("ticker", "")
        market = record.get("market")
        if not ticker:
            return record

        result = dict(record)

        history = self.get_daily_history(ticker, outputsize=252, market=market)
        result["price_data"] = history

        if history.empty:
            logger.warning("No history for %s — skipping enrichment", ticker)
            return result

        closes = history["close"].values
        current = closes[-1]
        result["price"] = round(float(current), 2)

        periods = {"return_1m": 21, "return_3m": 63, "return_6m": 126, "return_12m": 252}
        for field, days in periods.items():
            if len(closes) >= days and closes[-days] != 0:
                result[field] = round((current / closes[-days] - 1) * 100, 2)

        if "volume" in history.columns and len(history) >= 20:
            result["avg_volume_20d"] = round(float(history["volume"].tail(20).mean()), 0)

        if "high" in history.columns and len(history) >= 21:
            high_52w = float(history["high"].tail(min(252, len(history))).max())
            if high_52w > 0:
                result["distance_to_52w_high"] = round((current / high_52w - 1) * 100, 2)

        quote = self.get_quote(ticker, market=market)
        if quote and quote.get("name"):
            if not result.get("company_name"):
                result["company_name"] = quote["name"]

        return result


def _safe_float(value) -> Optional[float]:
    """Safely convert a value to float, returning None on failure."""
    if value is None:
        return None
    try:
        result = float(value)
        return result if np.isfinite(result) else None
    except (ValueError, TypeError):
        return None
