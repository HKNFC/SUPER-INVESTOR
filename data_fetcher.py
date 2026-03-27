import logging
import time
import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from config import (
    TWELVE_DATA_API_KEY, TWELVE_DATA_BASE_URL, SUPPORTED_MARKETS,
    API_REQUEST_TIMEOUT, LOG_LEVEL,
    REQUIRED_FIELDS_FOR_SCORING, MIN_ROWS_FOR_SCORING,
)
from data_model import (
    ensure_columns, coerce_numeric_columns,
    safe_float, ALL_COLUMNS,
)
from price_provider import PriceProvider

logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger("stock_screener.fetcher")

_provider_instance: Optional[PriceProvider] = None


@dataclass
class FetchDiagnostics:
    market: str = ""
    total_tickers: int = 0
    fetched_tickers: int = 0
    failed_tickers: int = 0
    failed_symbols: List[str] = field(default_factory=list)
    incomplete_rows: int = 0
    incomplete_symbols: List[str] = field(default_factory=list)
    missing_fields_summary: Dict[str, int] = field(default_factory=dict)
    used_mock: bool = False
    fallback_triggered: bool = False
    timestamp: float = 0.0
    duration_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)

    @property
    def timestamp_str(self) -> str:
        if self.timestamp == 0:
            return "N/A"
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.timestamp))


_last_diagnostics: Optional[FetchDiagnostics] = None


def get_last_diagnostics() -> Optional[FetchDiagnostics]:
    return _last_diagnostics


def get_provider() -> Optional[PriceProvider]:
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
    global _provider_instance
    _provider_instance = None


def _try_yahoo_fallback(ticker: str, market: Optional[str] = None, outputsize: int = 300) -> pd.DataFrame:
    try:
        from yahoo_provider import fetch_yahoo_history
        df = fetch_yahoo_history(ticker, period="2y", market=market)
        if not df.empty:
            df["data_source"] = "yahoo"
            if len(df) > outputsize:
                df = df.tail(outputsize).reset_index(drop=True)
        return df
    except Exception as e:
        logger.error("Yahoo fallback error for %s: %s", ticker, e)
        return pd.DataFrame()


def fetch_price_history(
    ticker: str,
    outputsize: int = 252,
    market: Optional[str] = None,
) -> pd.DataFrame:
    provider = get_provider()
    if provider is None:
        df = _try_yahoo_fallback(ticker, market=market, outputsize=outputsize)
        if not df.empty:
            return df
        return _generate_placeholder_price_data(ticker, outputsize)
    try:
        history = provider.get_daily_history(ticker, outputsize=outputsize, market=market)
        if history.empty:
            logger.warning("Empty history for %s — trying Yahoo fallback", ticker)
            df = _try_yahoo_fallback(ticker, market=market, outputsize=outputsize)
            if not df.empty:
                return df
            return _generate_placeholder_price_data(ticker, outputsize)
        return history
    except Exception as e:
        logger.error("Error fetching history for %s: %s — %s", ticker, type(e).__name__, e)
        df = _try_yahoo_fallback(ticker, market=market, outputsize=outputsize)
        if not df.empty:
            return df
        return _generate_placeholder_price_data(ticker, outputsize)


def fetch_latest_price(ticker: str, market: Optional[str] = None) -> Optional[float]:
    provider = get_provider()
    if provider is None:
        return None
    try:
        return provider.get_latest_price(ticker, market=market)
    except Exception as e:
        logger.error("Error fetching price for %s: %s", ticker, type(e).__name__)
        return None


def fetch_period_returns(ticker: str, market: Optional[str] = None) -> dict:
    provider = get_provider()
    if provider is None:
        return {}
    try:
        return provider.get_period_returns(ticker, market=market)
    except Exception as e:
        logger.error("Error fetching returns for %s: %s", ticker, type(e).__name__)
        return {}


def fetch_52w_high(ticker: str, market: Optional[str] = None) -> Optional[float]:
    provider = get_provider()
    if provider is None:
        return None
    try:
        return provider.get_52w_high(ticker, market=market)
    except Exception as e:
        logger.error("Error fetching 52w high for %s: %s", ticker, type(e).__name__)
        return None


def fetch_avg_volume_20d(ticker: str, market: Optional[str] = None) -> Optional[float]:
    provider = get_provider()
    if provider is None:
        return None
    try:
        return provider.get_avg_volume_20d(ticker, market=market)
    except Exception as e:
        logger.error("Error fetching avg volume for %s: %s", ticker, type(e).__name__)
        return None


def _fetch_twelve_data_fundamentals(symbol: str) -> dict:
    if not TWELVE_DATA_API_KEY:
        return {}
    try:
        import requests as _requests
        url = f"{TWELVE_DATA_BASE_URL}/statistics"
        params = {"symbol": symbol, "apikey": TWELVE_DATA_API_KEY}
        response = _requests.get(url, params=params, timeout=API_REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()

        if "status" in data and data["status"] == "error":
            msg = data.get("message", "")
            if "available exclusively with" in msg:
                logger.info("Twelve Data /statistics requires paid plan for %s, will use Yahoo fallback", symbol)
                return {"_needs_fallback": True}
            logger.warning("API error for %s: %s", symbol, msg)
            return {}

        if "statistics" not in data:
            logger.warning("No statistics for %s", symbol)
            return {}

        stats = data["statistics"]
        financials = stats.get("financials", {})
        valuations = stats.get("valuations_metrics", {})
        income = financials.get("income_statement", {})
        balance = financials.get("balance_sheet", {})

        revenue = safe_float(income.get("revenue_ttm"))
        net_income = safe_float(income.get("net_income_to_common_ttm"))
        gross_profit = safe_float(income.get("gross_profit_ttm"))
        ebitda_val = safe_float(income.get("ebitda")) or safe_float(financials.get("ebitda"))
        eps_val = safe_float(income.get("diluted_eps_ttm"))

        total_debt = safe_float(balance.get("total_debt_mrq"))
        total_cash = safe_float(balance.get("total_cash_mrq"))
        bvps = safe_float(balance.get("book_value_per_share_mrq"))

        shares = safe_float(stats.get("stock_statistics", {}).get("shares_outstanding"))
        equity_val = bvps * shares if bvps and shares else np.nan

        gross_margin = safe_float(financials.get("gross_margin"))
        profit_margin = safe_float(financials.get("profit_margin"))
        operating_margin = safe_float(financials.get("operating_margin"))
        roa = safe_float(financials.get("return_on_assets_ttm"))
        roe = safe_float(financials.get("return_on_equity_ttm"))

        net_margin_calc = np.nan
        if revenue and not np.isnan(revenue) and revenue != 0 and net_income and not np.isnan(net_income):
            net_margin_calc = net_income / revenue

        roic_calc = np.nan
        if net_income and not np.isnan(net_income) and equity_val and not np.isnan(equity_val) and equity_val != 0:
            roic_calc = net_income / equity_val

        operating_income = np.nan
        if operating_margin and not np.isnan(operating_margin) and revenue and not np.isnan(revenue):
            operating_income = operating_margin * revenue

        result = {
            "ticker": symbol,
            "company_name": data.get("meta", {}).get("name", symbol),
            "market_cap": safe_float(valuations.get("market_capitalization")),
            "pe": safe_float(valuations.get("trailing_pe")),
            "pb": safe_float(valuations.get("price_to_book_mrq")),
            "ev_ebitda": safe_float(valuations.get("enterprise_to_ebitda")),
            "peg": safe_float(valuations.get("peg_ratio")),
            "revenue": revenue,
            "net_income": net_income,
            "gross_profit": gross_profit,
            "operating_income": operating_income,
            "ebitda": ebitda_val,
            "total_assets": np.nan,
            "total_debt": total_debt,
            "equity": equity_val,
            "cash": total_cash,
            "eps": eps_val,
            "gross_margin": gross_margin,
            "net_margin": net_margin_calc if not np.isnan(net_margin_calc) else profit_margin,
            "operating_margin": operating_margin,
            "roe": roe,
            "roa": roa,
            "roic": roic_calc,
            "debt_to_equity": safe_float(balance.get("total_debt_to_equity_mrq")),
        }

        has_financials = any(
            result.get(f) is not None and not (isinstance(result.get(f), float) and np.isnan(result.get(f)))
            for f in ["revenue", "net_income", "equity"]
        )
        if has_financials:
            logger.info("Fundamentals OK for %s: revenue=%s, net_income=%s, equity=%s",
                        symbol, result.get("revenue"), result.get("net_income"), result.get("equity"))
        else:
            logger.info("No financial data in statistics for %s", symbol)

        return result

    except Exception as e:
        logger.error("Twelve Data fundamentals error for %s: %s — %s", symbol, type(e).__name__, e)
        return {}


_yahoo_fundamentals_mode = False


def fetch_fundamentals(symbol: str, market: Optional[str] = None) -> dict:
    global _yahoo_fundamentals_mode

    if not _yahoo_fundamentals_mode:
        result = _fetch_twelve_data_fundamentals(symbol)
        if result.get("_needs_fallback"):
            logger.info("Switching to Yahoo Finance for all fundamentals (Twelve Data requires paid plan)")
            _yahoo_fundamentals_mode = True
        elif result:
            return result

    if _yahoo_fundamentals_mode or not result:
        from yahoo_provider import fetch_yahoo_fundamentals
        return fetch_yahoo_fundamentals(symbol, market=market)

    return {}


def _check_row_completeness(record: dict, diag: FetchDiagnostics) -> None:
    ticker = record.get("ticker", "?")
    missing = []
    for f in REQUIRED_FIELDS_FOR_SCORING:
        val = record.get(f)
        if val is None or (isinstance(val, float) and np.isnan(val)):
            missing.append(f)
    if missing:
        diag.incomplete_rows += 1
        diag.incomplete_symbols.append(ticker)
        for f in missing:
            diag.missing_fields_summary[f] = diag.missing_fields_summary.get(f, 0) + 1
        logger.info("Incomplete data for %s: missing %s", ticker, ", ".join(missing))


def _enrich_via_yahoo(record: dict) -> dict:
    ticker = record.get("ticker", "")
    market = record.get("market")
    if not ticker:
        return record

    result = dict(record)
    history = _try_yahoo_fallback(ticker, market=market)
    result["price_data"] = history
    result["data_source"] = "yahoo"

    if history.empty:
        logger.warning("Yahoo: no price data for %s — skipping enrichment", ticker)
        return result

    closes = history["close"].values
    current = closes[-1]
    result["price"] = round(float(current), 2)

    periods = {"return_1m": 21, "return_3m": 63, "return_6m": 126, "return_12m": 252}
    for field_name, days in periods.items():
        if len(closes) >= days and closes[-days] != 0:
            result[field_name] = round((current / closes[-days] - 1) * 100, 2)

    if "volume" in history.columns and len(history) >= 20:
        result["avg_volume_20d"] = round(float(history["volume"].tail(20).mean()), 0)

    if "high" in history.columns and len(history) >= 21:
        high_52w = float(history["high"].tail(min(252, len(history))).max())
        if high_52w > 0:
            result["distance_to_52w_high"] = round((current / high_52w - 1) * 100, 2)

    return result


def fetch_market_data(market: str, skip_fundamentals: bool = False) -> pd.DataFrame:
    global _last_diagnostics

    if market not in SUPPORTED_MARKETS:
        raise ValueError(f"Unsupported market: {market}. Choose from {list(SUPPORTED_MARKETS.keys())}")

    from momentum_metrics import append_momentum_fields, get_benchmark_history

    start_time = time.time()
    diag = FetchDiagnostics(market=market, timestamp=start_time)
    symbols = SUPPORTED_MARKETS[market]["symbols"]
    diag.total_tickers = len(symbols)

    provider = get_provider()

    records = []
    skipped = []

    from symbol_mapper import resolve_twelve_symbol, canonical_ticker as _canonical

    for symbol in symbols:
        try:
            resolved_sym = resolve_twelve_symbol(symbol, market) if provider else symbol
            if skip_fundamentals:
                fundamentals = {}
            else:
                fundamentals = fetch_fundamentals(resolved_sym, market=market)
            canonical_sym = _canonical(symbol)
            if not fundamentals.get("ticker"):
                fundamentals["ticker"] = canonical_sym
            else:
                fundamentals["ticker"] = _canonical(fundamentals["ticker"])
            fundamentals["market"] = market
            fundamentals["sector"] = fundamentals.get("sector", "")
            fundamentals["industry"] = fundamentals.get("industry", "")

            if provider is not None:
                enriched = provider.enrich_record(fundamentals)
            else:
                enriched = _enrich_via_yahoo(fundamentals)

            _check_row_completeness(enriched, diag)
            records.append(enriched)
            diag.fetched_tickers += 1

            logger.info(
                "Fetched %s: price=%s, source=%s",
                symbol,
                enriched.get("price", "N/A"),
                enriched.get("data_source", "unknown"),
            )

        except Exception as e:
            logger.warning("Failed to fetch %s: %s — %s", symbol, type(e).__name__, e)
            diag.failed_tickers += 1
            diag.failed_symbols.append(symbol)
            diag.errors.append(f"{symbol}: {type(e).__name__}: {e}")
            skipped.append(symbol)

    if skipped:
        logger.warning("Skipped %d/%d tickers: %s", len(skipped), len(symbols), ", ".join(skipped))

    if not records:
        diag.duration_seconds = time.time() - start_time
        _last_diagnostics = diag
        raise RuntimeError(
            f"{market} piyasasi icin hicbir veri cekilemedi. "
            f"API anahtarinizi ve internet baglantinizi kontrol edin."
        )

    if len(records) < MIN_ROWS_FOR_SCORING:
        logger.warning(
            "Only %d/%d tickers fetched for %s — below minimum %d for reliable scoring",
            len(records), len(symbols), market, MIN_ROWS_FOR_SCORING,
        )

    df = pd.DataFrame(records)
    df = ensure_columns(df)
    df = coerce_numeric_columns(df)

    fin_count = 0
    for col in ["revenue", "net_income", "equity"]:
        if col in df.columns:
            valid = df[col].dropna()
            valid = valid[valid != 0]
            if len(valid) > fin_count:
                fin_count = len(valid)
    logger.info(
        "Financial data summary for %s: %d/%d tickers have fundamental data",
        market, fin_count, len(df),
    )

    benchmark = get_benchmark_history(market)
    df = append_momentum_fields(df, benchmark_history=benchmark)

    diag.duration_seconds = time.time() - start_time
    _last_diagnostics = diag
    return df


def _ensure_sorted(price_data: pd.DataFrame) -> pd.DataFrame:
    if price_data is not None and not price_data.empty and "datetime" in price_data.columns:
        return price_data.sort_values("datetime").reset_index(drop=True)
    return price_data


def get_historical_data(
    ticker: str,
    market: Optional[str] = None,
    outputsize: int = 252,
) -> pd.DataFrame:
    provider = get_provider()
    if provider is not None:
        try:
            history = provider.get_daily_history(ticker, outputsize=outputsize, market=market)
            if not history.empty:
                return _ensure_sorted(history)
        except Exception as e:
            logger.warning("get_historical_data failed for %s: %s", ticker, e)
    return _generate_placeholder_price_data(ticker, outputsize)


def calculate_returns(price_data: pd.DataFrame) -> Dict[str, Optional[float]]:
    if price_data is None or price_data.empty or "close" not in price_data.columns:
        return {"return_1m": None, "return_3m": None, "return_6m": None, "return_12m": None}
    closes = price_data["close"].values.astype(float)
    result: Dict[str, Optional[float]] = {}
    periods = {"return_1m": 21, "return_3m": 63, "return_6m": 126, "return_12m": 252}
    for key, days in periods.items():
        if len(closes) >= days + 1 and closes[-(days + 1)] != 0 and np.isfinite(closes[-(days + 1)]):
            result[key] = round((closes[-1] / closes[-(days + 1)] - 1) * 100, 2)
        else:
            result[key] = None
    return result


def calculate_moving_averages(price_data: pd.DataFrame) -> Dict[str, Optional[float]]:
    result: Dict[str, Optional[float]] = {
        "ma20": None, "ma50": None, "ma200": None,
        "ma20_ratio": None, "ma50_ratio": None, "ma200_ratio": None,
    }
    if price_data is None or price_data.empty or "close" not in price_data.columns:
        return result
    closes = price_data["close"].values.astype(float)
    current = closes[-1] if len(closes) > 0 and np.isfinite(closes[-1]) else None
    if current is None:
        return result
    for window, key in [(20, "ma20"), (50, "ma50"), (200, "ma200")]:
        if len(closes) >= window:
            ma = float(np.mean(closes[-window:]))
            if np.isfinite(ma) and ma > 0:
                result[key] = round(ma, 4)
                result[f"{key}_ratio"] = round(current / ma, 4)
    return result


def calculate_macd(price_data: pd.DataFrame) -> Dict[str, Optional[float]]:
    result: Dict[str, Optional[float]] = {"macd_line": None, "macd_signal": None, "macd_histogram": None}
    if price_data is None or price_data.empty or "close" not in price_data.columns:
        return result
    closes = price_data["close"].values.astype(float)
    if len(closes) < 35:
        return result
    alpha12 = 2.0 / 13
    alpha26 = 2.0 / 27
    ema12 = np.empty_like(closes)
    ema26 = np.empty_like(closes)
    ema12[0] = closes[0]
    ema26[0] = closes[0]
    for i in range(1, len(closes)):
        ema12[i] = alpha12 * closes[i] + (1 - alpha12) * ema12[i - 1]
        ema26[i] = alpha26 * closes[i] + (1 - alpha26) * ema26[i - 1]
    macd_line = ema12 - ema26
    alpha9 = 2.0 / 10
    signal = np.empty_like(macd_line)
    signal[0] = macd_line[0]
    for i in range(1, len(macd_line)):
        signal[i] = alpha9 * macd_line[i] + (1 - alpha9) * signal[i - 1]
    result["macd_line"] = round(float(macd_line[-1]), 4)
    result["macd_signal"] = round(float(signal[-1]), 4)
    result["macd_histogram"] = round(float(macd_line[-1] - signal[-1]), 4)
    return result


def calculate_atr(price_data: pd.DataFrame, period: int = 14) -> Optional[float]:
    if price_data is None or price_data.empty:
        return None
    if not all(c in price_data.columns for c in ["high", "low", "close"]):
        return None
    if len(price_data) < period + 1:
        return None
    high = price_data["high"].values.astype(float)
    low = price_data["low"].values.astype(float)
    close = price_data["close"].values.astype(float)
    tr_values = []
    for i in range(1, len(high)):
        tr = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
        tr_values.append(tr)
    if len(tr_values) < period:
        return None
    return round(float(np.mean(tr_values[-period:])), 4)


def calculate_rsi(price_data: pd.DataFrame, period: int = 14) -> Optional[float]:
    if price_data is None or price_data.empty or "close" not in price_data.columns:
        return None
    closes = price_data["close"].values.astype(float)
    if len(closes) < period + 1:
        return None
    deltas = np.diff(closes[-(period + 1):])
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = float(np.mean(gains))
    avg_loss = float(np.mean(losses))
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


def calculate_volume_ratio(price_data: pd.DataFrame, window: int = 20) -> Optional[float]:
    if price_data is None or price_data.empty or "volume" not in price_data.columns:
        return None
    volumes = price_data["volume"].values.astype(float)
    if len(volumes) < window:
        return None
    avg_vol = float(np.mean(volumes[-window:]))
    if avg_vol <= 0 or not np.isfinite(avg_vol):
        return None
    current_vol = volumes[-1]
    if not np.isfinite(current_vol):
        return None
    return round(float(current_vol / avg_vol), 4)


def calculate_obv(price_data: pd.DataFrame) -> Dict[str, Any]:
    result: Dict[str, Any] = {"obv_latest": None, "obv_trend_positive": None, "obv_slope": None}
    if price_data is None or price_data.empty:
        return result
    if "close" not in price_data.columns or "volume" not in price_data.columns:
        return result
    close = price_data["close"].values.astype(float)
    volume = price_data["volume"].values.astype(float)
    if len(close) < 5:
        return result
    obv = np.zeros(len(close))
    obv[0] = volume[0]
    for i in range(1, len(close)):
        if close[i] > close[i - 1]:
            obv[i] = obv[i - 1] + volume[i]
        elif close[i] < close[i - 1]:
            obv[i] = obv[i - 1] - volume[i]
        else:
            obv[i] = obv[i - 1]
    result["obv_latest"] = float(obv[-1])
    lookback = min(20, len(obv) - 1)
    if lookback >= 5:
        slope = obv[-1] - obv[-lookback]
        result["obv_slope"] = float(slope)
        result["obv_trend_positive"] = bool(slope > 0)
    return result


def calculate_mfi(price_data: pd.DataFrame, period: int = 14) -> Optional[float]:
    if price_data is None or price_data.empty:
        return None
    required = ["high", "low", "close", "volume"]
    if not all(c in price_data.columns for c in required):
        return None
    if len(price_data) < period + 1:
        return None
    data = price_data.tail(period + 1)
    high = data["high"].values.astype(float)
    low = data["low"].values.astype(float)
    close = data["close"].values.astype(float)
    volume = data["volume"].values.astype(float)
    typical_price = (high + low + close) / 3.0
    raw_money_flow = typical_price * volume
    pos_flow = 0.0
    neg_flow = 0.0
    for i in range(1, len(typical_price)):
        if typical_price[i] > typical_price[i - 1]:
            pos_flow += raw_money_flow[i]
        elif typical_price[i] < typical_price[i - 1]:
            neg_flow += raw_money_flow[i]
    if neg_flow == 0:
        return 100.0
    money_ratio = pos_flow / neg_flow
    return round(100.0 - (100.0 / (1.0 + money_ratio)), 2)


def build_technical_data(df: pd.DataFrame, market: Optional[str] = None) -> pd.DataFrame:
    result = df.copy()

    has_price_data = "price_data" in result.columns
    tickers = result["ticker"].tolist() if "ticker" in result.columns else []

    if not has_price_data and tickers:
        price_frames = []
        for ticker in tickers:
            try:
                hist = get_historical_data(ticker, market=market)
            except Exception as e:
                logger.warning("build_technical_data: failed to fetch %s: %s", ticker, e)
                hist = _generate_placeholder_price_data(ticker)
            price_frames.append(hist)
        result["price_data"] = price_frames

    tech_cols = {
        "return_1m": [], "return_3m": [], "return_6m": [], "return_12m": [],
        "ma20": [], "ma50": [], "ma200": [],
        "ma20_ratio": [], "ma50_ratio": [], "ma200_ratio": [],
        "rsi": [],
        "macd_line": [], "macd_signal": [], "macd_histogram": [],
        "atr": [],
        "volume_ratio": [],
        "mfi": [],
        "obv_latest": [], "obv_trend_positive": [], "obv_slope": [],
        "distance_to_52w_high": [],
    }

    for idx, row in result.iterrows():
        price_data = row.get("price_data")
        is_valid = isinstance(price_data, pd.DataFrame) and not price_data.empty

        if is_valid and "datetime" in price_data.columns:
            price_data = price_data.sort_values("datetime").reset_index(drop=True)
            result.at[idx, "price_data"] = price_data

        empty_rets = {"return_1m": None, "return_3m": None, "return_6m": None, "return_12m": None}
        rets = calculate_returns(price_data) if is_valid else empty_rets
        for k in empty_rets:
            tech_cols[k].append(rets.get(k))

        empty_mas = {"ma20": None, "ma50": None, "ma200": None, "ma20_ratio": None, "ma50_ratio": None, "ma200_ratio": None}
        mas = calculate_moving_averages(price_data) if is_valid else empty_mas
        for k in empty_mas:
            tech_cols[k].append(mas.get(k))

        tech_cols["rsi"].append(calculate_rsi(price_data) if is_valid else None)

        empty_macd = {"macd_line": None, "macd_signal": None, "macd_histogram": None}
        macd = calculate_macd(price_data) if is_valid else empty_macd
        for k in empty_macd:
            tech_cols[k].append(macd.get(k))

        tech_cols["atr"].append(calculate_atr(price_data) if is_valid else None)
        tech_cols["volume_ratio"].append(calculate_volume_ratio(price_data) if is_valid else None)
        tech_cols["mfi"].append(calculate_mfi(price_data) if is_valid else None)

        empty_obv = {"obv_latest": None, "obv_trend_positive": None, "obv_slope": None}
        obv = calculate_obv(price_data) if is_valid else empty_obv
        for k in empty_obv:
            tech_cols[k].append(obv.get(k))

        d52 = None
        if is_valid and "high" in price_data.columns and "close" in price_data.columns and len(price_data) >= 21:
            lookback = min(252, len(price_data))
            high_52w = float(price_data["high"].tail(lookback).max())
            current = float(price_data["close"].iloc[-1])
            if high_52w > 0 and np.isfinite(high_52w) and np.isfinite(current):
                d52 = round((current / high_52w - 1) * 100, 2)
        tech_cols["distance_to_52w_high"].append(d52)

    for col, values in tech_cols.items():
        result[col] = values

    numeric_cols = [
        "return_1m", "return_3m", "return_6m", "return_12m",
        "ma20", "ma50", "ma200", "ma20_ratio", "ma50_ratio", "ma200_ratio",
        "rsi", "macd_line", "macd_signal", "macd_histogram", "atr",
        "volume_ratio", "mfi", "obv_latest", "obv_slope", "distance_to_52w_high",
    ]
    for col in numeric_cols:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce")

    return result


@dataclass
class DataPrepStats:
    total_symbols: int = 0
    cache_hits: int = 0
    incremental_updates: int = 0
    full_fetches: int = 0
    failed: int = 0
    failed_symbols: List[str] = field(default_factory=list)
    placeholder_used: int = 0
    used_mock: bool = False
    duration_seconds: float = 0.0


def fetch_backtest_data(
    market: str,
    progress_callback=None,
    skip_momentum: bool = False,
) -> tuple:
    from momentum_metrics import append_momentum_fields
    from disk_cache import read_cache, needs_refresh, get_cached_or_fetch

    if market not in SUPPORTED_MARKETS:
        raise ValueError(f"Unsupported market: {market}. Choose from {list(SUPPORTED_MARKETS.keys())}")

    start_time = time.time()
    stats = DataPrepStats()
    symbols = SUPPORTED_MARKETS[market]["symbols"]
    stats.total_symbols = len(symbols)
    provider = get_provider()

    records = []
    has_any_cache = False

    for idx, symbol in enumerate(symbols):
        if progress_callback:
            progress_callback(
                (idx + 1) / len(symbols),
                f"Veri hazırlanıyor: {idx + 1}/{len(symbols)} ({symbol})"
            )

        try:
            from symbol_mapper import resolve_twelve_symbol
            resolved = resolve_twelve_symbol(symbol, market) if provider else symbol
            cached = read_cache(resolved)

            if cached is not None and not cached.empty:
                has_any_cache = True
                if not needs_refresh(resolved) or provider is None:
                    price_data = _ensure_sorted(cached)
                    stats.cache_hits += 1
                else:
                    def _disk_fetch(sym, outputsize=300, start_date=None):
                        return provider._fetch_from_api(sym, outputsize=outputsize, start_date=start_date)

                    fetched = get_cached_or_fetch(resolved, _disk_fetch, outputsize=300)
                    if fetched is not None and not fetched.empty:
                        price_data = _ensure_sorted(fetched)
                        stats.incremental_updates += 1
                    else:
                        price_data = _ensure_sorted(cached)
                        stats.cache_hits += 1
            elif provider is not None:
                def _disk_fetch(sym, outputsize=300, start_date=None):
                    return provider._fetch_from_api(sym, outputsize=outputsize, start_date=start_date)

                fetched = get_cached_or_fetch(resolved, _disk_fetch, outputsize=300)
                if fetched is not None and not fetched.empty:
                    price_data = _ensure_sorted(fetched)
                    stats.full_fetches += 1
                else:
                    yahoo_data = _try_yahoo_fallback(symbol, market=market)
                    if not yahoo_data.empty:
                        logger.info("Yahoo fallback for backtest: %s (%d rows)", symbol, len(yahoo_data))
                        price_data = _ensure_sorted(yahoo_data)
                        stats.full_fetches += 1
                    else:
                        logger.warning("No data for %s, using placeholder", symbol)
                        price_data = _generate_placeholder_price_data(symbol)
                        stats.failed += 1
                        stats.failed_symbols.append(symbol)
            else:
                yahoo_data = _try_yahoo_fallback(symbol, market=market)
                if not yahoo_data.empty:
                    logger.info("Yahoo fallback for backtest (no API key): %s (%d rows)", symbol, len(yahoo_data))
                    price_data = _ensure_sorted(yahoo_data)
                    stats.full_fetches += 1
                else:
                    price_data = _generate_placeholder_price_data(symbol)
                    stats.failed += 1
                    stats.failed_symbols.append(symbol)

            records.append({
                "ticker": symbol,
                "company_name": symbol,
                "market": market,
                "sector": "",
                "industry": "",
                "price_data": price_data,
            })

        except Exception as e:
            logger.error("Failed to load data for %s: %s — %s", symbol, type(e).__name__, e)
            stats.failed += 1
            stats.failed_symbols.append(symbol)
            records.append({
                "ticker": symbol,
                "company_name": symbol,
                "market": market,
                "sector": "",
                "industry": "",
                "price_data": _generate_placeholder_price_data(symbol),
            })

    df = pd.DataFrame(records)
    df = ensure_columns(df)
    df = coerce_numeric_columns(df)

    if not skip_momentum:
        benchmark = get_cached_benchmark(market)
        df = append_momentum_fields(df, benchmark_history=benchmark)

    stats.duration_seconds = time.time() - start_time
    logger.info(
        "Data prep complete for %s: %d symbols, %d cache hits, %d incremental, %d full fetch, %d failed in %.1fs",
        market, stats.total_symbols, stats.cache_hits, stats.incremental_updates,
        stats.full_fetches, stats.failed, stats.duration_seconds,
    )
    if stats.failed_symbols:
        logger.warning("Failed symbols: %s", ", ".join(stats.failed_symbols))

    return df, stats


def get_cached_benchmark(market: str) -> pd.DataFrame:
    from config import BENCHMARK_INDEX
    from disk_cache import read_cache, needs_refresh, get_cached_or_fetch

    index_ticker = BENCHMARK_INDEX.get(market)
    if not index_ticker:
        logger.warning("No benchmark configured for market %s", market)
        return _generate_placeholder_price_data("BENCH", days=300)

    provider = get_provider()
    from symbol_mapper import resolve_twelve_benchmark
    resolved = resolve_twelve_benchmark(index_ticker, market) if provider else index_ticker

    cached = read_cache(resolved)

    if cached is not None and not cached.empty:
        if not needs_refresh(resolved) or provider is None:
            return _ensure_sorted(cached)

    if provider is None:
        logger.info("No provider — trying Yahoo Finance for benchmark %s", index_ticker)
        try:
            from yahoo_provider import fetch_yahoo_benchmark
            yahoo_bench = fetch_yahoo_benchmark(index_ticker)
            if not yahoo_bench.empty:
                return _ensure_sorted(yahoo_bench)
        except Exception as e:
            logger.error("Yahoo benchmark fallback error: %s", e)
        return _generate_placeholder_price_data(index_ticker, days=300)

    def _disk_fetch(sym, outputsize=300, start_date=None):
        return provider._fetch_from_api(sym, outputsize=outputsize, start_date=start_date)

    fetched = get_cached_or_fetch(resolved, _disk_fetch, outputsize=300)
    if fetched is not None and not fetched.empty:
        return _ensure_sorted(fetched)

    if cached is not None and not cached.empty:
        return _ensure_sorted(cached)

    logger.info("Twelve Data benchmark fetch failed — trying Yahoo Finance for %s", index_ticker)
    try:
        from yahoo_provider import fetch_yahoo_benchmark
        yahoo_bench = fetch_yahoo_benchmark(index_ticker)
        if not yahoo_bench.empty:
            return _ensure_sorted(yahoo_bench)
    except Exception as e:
        logger.error("Yahoo benchmark fallback error: %s", e)

    return _generate_placeholder_price_data(index_ticker, days=300)


def _generate_placeholder_price_data(symbol: str, days: int = 260) -> pd.DataFrame:
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
