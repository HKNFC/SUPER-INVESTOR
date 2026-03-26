import logging
import pandas as pd
import numpy as np
from typing import Optional
from disk_cache import OHLCV_COLUMNS

logger = logging.getLogger("stock_screener.yahoo")

BIST_SUFFIX = ".IS"


def _resolve_yahoo_symbol(ticker: str, market: Optional[str] = None) -> str:
    clean = ticker.replace(":BIST", "")
    if market and market.upper() == "BIST":
        if not clean.endswith(BIST_SUFFIX):
            return f"{clean}{BIST_SUFFIX}"
    return clean


def fetch_yahoo_history(
    ticker: str,
    period: str = "2y",
    market: Optional[str] = None,
) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not installed")
        return pd.DataFrame(columns=OHLCV_COLUMNS)

    symbol = _resolve_yahoo_symbol(ticker, market)

    try:
        data = yf.download(
            symbol,
            period=period,
            interval="1d",
            auto_adjust=True,
            progress=False,
            timeout=15,
        )

        if data is None or data.empty:
            logger.warning("Yahoo Finance: no data for %s (resolved: %s)", ticker, symbol)
            return pd.DataFrame(columns=OHLCV_COLUMNS)

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        df = pd.DataFrame()
        df["datetime"] = data.index
        df["open"] = data["Open"].values
        df["high"] = data["High"].values
        df["low"] = data["Low"].values
        df["close"] = data["Close"].values
        df["volume"] = data["Volume"].values

        df["datetime"] = pd.to_datetime(df["datetime"]).dt.tz_localize(None)

        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=["close"])
        df = df.sort_values("datetime").reset_index(drop=True)

        logger.info(
            "Yahoo Finance: fetched %d rows for %s (resolved: %s)",
            len(df), ticker, symbol,
        )
        return df

    except Exception as e:
        logger.error(
            "Yahoo Finance error for %s (resolved: %s): %s — %s",
            ticker, symbol, type(e).__name__, e,
        )
        return pd.DataFrame(columns=OHLCV_COLUMNS)


def fetch_yahoo_benchmark(index_symbol: str) -> pd.DataFrame:
    yahoo_map = {
        "XU100": "XU100.IS",
        "SPX": "^GSPC",
        "^GSPC": "^GSPC",
    }
    resolved = yahoo_map.get(index_symbol, index_symbol)
    return fetch_yahoo_history(resolved, period="2y", market=None)
