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


def _td_get_json(endpoint: str, symbol: str) -> Optional[dict]:
    import requests as _requests
    url = f"{TWELVE_DATA_BASE_URL}{endpoint}"
    params = {"symbol": symbol, "apikey": TWELVE_DATA_API_KEY}
    resp = _requests.get(url, params=params, timeout=API_REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and data.get("status") == "error":
        logger.warning("Twelve Data %s error for %s: %s", endpoint, symbol, data.get("message", ""))
        return None
    return data


_FUNDAMENTALS_CACHE: Dict[str, dict] = {}
_FUNDAMENTALS_CACHE_TTL: Dict[str, float] = {}
FUNDAMENTALS_CACHE_HOURS = 20


def _get_cached_fundamentals(symbol: str) -> Optional[dict]:
    if symbol in _FUNDAMENTALS_CACHE:
        if time.time() - _FUNDAMENTALS_CACHE_TTL.get(symbol, 0) < FUNDAMENTALS_CACHE_HOURS * 3600:
            return dict(_FUNDAMENTALS_CACHE[symbol])
        else:
            del _FUNDAMENTALS_CACHE[symbol]
            _FUNDAMENTALS_CACHE_TTL.pop(symbol, None)
    return None


def _set_cached_fundamentals(symbol: str, data: dict) -> None:
    _FUNDAMENTALS_CACHE[symbol] = dict(data)
    _FUNDAMENTALS_CACHE_TTL[symbol] = time.time()


def fetch_fundamentals(symbol: str, market: Optional[str] = None) -> dict:
    cached = _get_cached_fundamentals(symbol)
    if cached is not None:
        return cached

    try:
        from yahoo_provider import fetch_yahoo_fundamentals
        yahoo_data = fetch_yahoo_fundamentals(symbol, market=market)

        if yahoo_data:
            yahoo_data["data_provider"] = "yahoo"
            _set_cached_fundamentals(symbol, yahoo_data)
            return yahoo_data

        result = {
            "ticker": symbol,
            "data_provider": "none",
        }
        return result

    except Exception as e:
        logger.error("Fundamentals error for %s: %s — %s", symbol, type(e).__name__, e)
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


_PARALLEL_WORKERS = 4


def _fetch_single_ticker(args: tuple) -> tuple:
    symbol, market, skip_fundamentals, provider = args
    from symbol_mapper import resolve_twelve_symbol, canonical_ticker as _canonical
    try:
        resolved_sym = resolve_twelve_symbol(symbol, market) if provider else symbol
        if skip_fundamentals:
            fundamentals = {"data_provider": "none"}
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
        if "data_provider" not in fundamentals:
            fundamentals["data_provider"] = "unknown"

        if provider is not None:
            enriched = provider.enrich_record(fundamentals)
        else:
            enriched = _enrich_via_yahoo(fundamentals)

        logger.info(
            "Fetched %s: price=%s, source=%s",
            symbol,
            enriched.get("price", "N/A"),
            enriched.get("data_source", "unknown"),
        )
        return ("ok", symbol, enriched)

    except Exception as e:
        logger.warning("Failed to fetch %s: %s — %s", symbol, type(e).__name__, e)
        return ("error", symbol, f"{type(e).__name__}: {e}")


def fetch_market_data(market: str, skip_fundamentals: bool = False) -> pd.DataFrame:
    global _last_diagnostics
    from concurrent.futures import ThreadPoolExecutor, as_completed

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

    tasks = [(sym, market, skip_fundamentals, provider) for sym in symbols]

    with ThreadPoolExecutor(max_workers=_PARALLEL_WORKERS) as executor:
        futures = {executor.submit(_fetch_single_ticker, t): t[0] for t in tasks}
        for future in as_completed(futures):
            sym = futures[future]
            try:
                status, symbol, result = future.result()
                if status == "ok":
                    _check_row_completeness(result, diag)
                    records.append(result)
                    diag.fetched_tickers += 1
                else:
                    diag.failed_tickers += 1
                    diag.failed_symbols.append(symbol)
                    diag.errors.append(f"{symbol}: {result}")
                    skipped.append(symbol)
            except Exception as e:
                diag.failed_tickers += 1
                diag.failed_symbols.append(sym)
                diag.errors.append(f"{sym}: {type(e).__name__}: {e}")
                skipped.append(sym)

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


def refresh_eod_cache(market: str, progress_callback=None) -> Dict[str, int]:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from disk_cache import read_cache, needs_refresh, get_cached_or_fetch, write_cache

    if market not in SUPPORTED_MARKETS:
        raise ValueError(f"Unsupported market: {market}")

    symbols = SUPPORTED_MARKETS[market]["symbols"]
    provider = get_provider()

    from symbol_mapper import resolve_twelve_symbol
    result = {"total": len(symbols), "fresh": 0, "updated": 0, "failed": 0}

    def _refresh_one(symbol: str) -> tuple:
        resolved = resolve_twelve_symbol(symbol, market) if provider else symbol
        try:
            if not needs_refresh(resolved):
                return ("fresh", symbol)

            if provider is not None:
                def _disk_fetch(sym, outputsize=500, start_date=None):
                    return provider._fetch_from_api(sym, outputsize=outputsize, start_date=start_date)
                fetched = get_cached_or_fetch(resolved, _disk_fetch, outputsize=500)
                if fetched is not None and not fetched.empty:
                    return ("updated", symbol)
                return ("failed", symbol)
            else:
                yahoo_data = _try_yahoo_fallback(symbol, market=market, outputsize=500)
                if not yahoo_data.empty:
                    from disk_cache import merge_cache as _merge
                    _merge(resolved, yahoo_data)
                    return ("updated", symbol)
                cached = read_cache(resolved)
                if cached is not None and not cached.empty:
                    return ("fresh", symbol)
                return ("failed", symbol)
        except Exception as e:
            logger.warning("Cache refresh failed for %s: %s", symbol, e)
            return ("failed", symbol)

    with ThreadPoolExecutor(max_workers=_PARALLEL_WORKERS) as executor:
        futures = {executor.submit(_refresh_one, sym): sym for sym in symbols}
        done_count = 0
        for future in as_completed(futures):
            done_count += 1
            if progress_callback:
                progress_callback(done_count / len(symbols), f"Cache güncelleniyor: {done_count}/{len(symbols)}")
            try:
                status, sym = future.result()
                result[status] = result.get(status, 0) + 1
            except Exception:
                result["failed"] += 1

    logger.info("EOD cache refresh for %s: %s", market, result)
    return result


def fetch_backtest_data(
    market: str,
    progress_callback=None,
    skip_momentum: bool = False,
) -> tuple:
    from momentum_metrics import append_momentum_fields
    from disk_cache import read_cache

    if market not in SUPPORTED_MARKETS:
        raise ValueError(f"Unsupported market: {market}. Choose from {list(SUPPORTED_MARKETS.keys())}")

    start_time = time.time()
    stats = DataPrepStats()
    symbols = SUPPORTED_MARKETS[market]["symbols"]
    stats.total_symbols = len(symbols)
    provider = get_provider()

    records = []

    from symbol_mapper import resolve_twelve_symbol

    for idx, symbol in enumerate(symbols):
        if progress_callback:
            progress_callback(
                (idx + 1) / len(symbols),
                f"Veri hazırlanıyor: {idx + 1}/{len(symbols)} ({symbol})"
            )

        try:
            resolved = resolve_twelve_symbol(symbol, market) if provider else symbol
            cached = read_cache(resolved)

            if cached is not None and not cached.empty:
                price_data = _ensure_sorted(cached)
                stats.cache_hits += 1
            else:
                logger.info("Backtest: no cache for %s — skipping (cache-only mode)", symbol)
                stats.failed += 1
                stats.failed_symbols.append(symbol)
                continue

            records.append({
                "ticker": symbol,
                "company_name": symbol,
                "market": market,
                "sector": "",
                "industry": "",
                "price_data": price_data,
            })

        except Exception as e:
            logger.error("Failed to load cache for %s: %s — %s", symbol, type(e).__name__, e)
            stats.failed += 1
            stats.failed_symbols.append(symbol)

    if not records:
        logger.warning("Backtest: no cached data found for %s — run a screener scan first to populate cache", market)
        df = pd.DataFrame(columns=["ticker", "company_name", "market", "sector", "industry", "price_data"])
        df = ensure_columns(df)
        stats.duration_seconds = time.time() - start_time
        return df, stats

    df = pd.DataFrame(records)
    df = ensure_columns(df)
    df = coerce_numeric_columns(df)

    if not skip_momentum:
        benchmark = get_cached_benchmark(market, cache_only=True)
        df = append_momentum_fields(df, benchmark_history=benchmark)

    stats.duration_seconds = time.time() - start_time
    logger.info(
        "Backtest data (cache-only) for %s: %d symbols, %d cache hits, %d missing in %.1fs",
        market, stats.total_symbols, stats.cache_hits, stats.failed, stats.duration_seconds,
    )
    if stats.failed_symbols:
        logger.warning("No cache for: %s", ", ".join(stats.failed_symbols[:20]))

    return df, stats


def get_cached_benchmark(market: str, cache_only: bool = False) -> pd.DataFrame:
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

    if cache_only:
        if cached is not None and not cached.empty:
            return _ensure_sorted(cached)
        logger.info("Benchmark cache-only: no cache for %s", index_ticker)
        return _generate_placeholder_price_data(index_ticker, days=300)

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
