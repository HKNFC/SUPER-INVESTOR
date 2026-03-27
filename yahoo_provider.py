import logging
import pandas as pd
import numpy as np
from typing import Optional
from disk_cache import OHLCV_COLUMNS
from symbol_mapper import resolve_yahoo_symbol

logger = logging.getLogger("stock_screener.yahoo")


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

    symbol = resolve_yahoo_symbol(ticker, market)

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


def fetch_yahoo_fundamentals(ticker: str, market: Optional[str] = None) -> dict:
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not installed")
        return {}

    symbol = resolve_yahoo_symbol(ticker, market)

    try:
        stock = yf.Ticker(symbol)
        info = stock.info or {}

        if not info or info.get("trailingPegRatio") is None and info.get("marketCap") is None:
            logger.warning("Yahoo fundamentals: no data for %s (resolved: %s)", ticker, symbol)
            return {}

        def sf(val):
            if val is None:
                return np.nan
            try:
                v = float(val)
                return v
            except (ValueError, TypeError):
                return np.nan

        revenue = sf(info.get("totalRevenue"))
        net_income = sf(info.get("netIncomeToCommon"))
        gross_profit = sf(info.get("grossProfits"))
        ebitda = sf(info.get("ebitda"))
        total_debt = sf(info.get("totalDebt"))
        total_cash = sf(info.get("totalCash"))
        book_value = sf(info.get("bookValue"))
        shares = sf(info.get("sharesOutstanding"))
        equity_val = book_value * shares if not np.isnan(book_value) and not np.isnan(shares) else np.nan
        total_assets = sf(info.get("totalAssets"))

        operating_margins = sf(info.get("operatingMargins"))
        operating_income = operating_margins * revenue if not np.isnan(operating_margins) and not np.isnan(revenue) else np.nan

        net_margin_calc = np.nan
        if not np.isnan(net_income) and not np.isnan(revenue) and revenue != 0:
            net_margin_calc = net_income / revenue

        roic_calc = np.nan
        if not np.isnan(net_income) and not np.isnan(equity_val) and equity_val != 0:
            roic_calc = net_income / equity_val

        result = {
            "company_name": info.get("longName") or info.get("shortName") or ticker,
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "market_cap": sf(info.get("marketCap")),
            "pe": sf(info.get("trailingPE")),
            "pb": sf(info.get("priceToBook")),
            "ev_ebitda": sf(info.get("enterpriseToEbitda")),
            "peg": sf(info.get("trailingPegRatio") or info.get("pegRatio")),
            "revenue": revenue,
            "net_income": net_income,
            "gross_profit": gross_profit,
            "operating_income": operating_income,
            "ebitda": ebitda,
            "total_assets": total_assets,
            "total_debt": total_debt,
            "equity": equity_val,
            "cash": total_cash,
            "eps": sf(info.get("trailingEps")),
            "gross_margin": sf(info.get("grossMargins")),
            "net_margin": net_margin_calc if not np.isnan(net_margin_calc) else sf(info.get("profitMargins")),
            "operating_margin": operating_margins,
            "roe": sf(info.get("returnOnEquity")),
            "roa": sf(info.get("returnOnAssets")),
            "roic": roic_calc,
            "debt_to_equity": sf(info.get("debtToEquity")),
        }

        has_financials = any(
            result.get(f) is not None and not (isinstance(result.get(f), float) and np.isnan(result.get(f)))
            for f in ["revenue", "net_income", "equity"]
        )
        if has_financials:
            logger.info("Yahoo fundamentals OK for %s: revenue=%s, net_income=%s, equity=%s",
                        ticker, result.get("revenue"), result.get("net_income"), result.get("equity"))
        else:
            logger.info("Yahoo fundamentals: no financial data for %s", ticker)

        return result

    except Exception as e:
        logger.error("Yahoo fundamentals error for %s: %s — %s", ticker, type(e).__name__, e)
        return {}


def fetch_yahoo_benchmark(index_symbol: str) -> pd.DataFrame:
    from symbol_mapper import resolve_yahoo_benchmark
    resolved = resolve_yahoo_benchmark(index_symbol)
    return fetch_yahoo_history(resolved, period="2y", market=None)
