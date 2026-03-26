import logging
import time
import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from config import (
    TWELVE_DATA_API_KEY, TWELVE_DATA_BASE_URL, SUPPORTED_MARKETS,
    API_REQUEST_TIMEOUT, FALLBACK_TO_MOCK, LOG_LEVEL,
    REQUIRED_FIELDS_FOR_SCORING, MIN_ROWS_FOR_SCORING,
)
from data_model import (
    ensure_columns, coerce_numeric_columns, get_mock_data,
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


def fetch_price_history(
    ticker: str,
    outputsize: int = 252,
    market: Optional[str] = None,
) -> pd.DataFrame:
    provider = get_provider()
    if provider is None:
        return _generate_placeholder_price_data(ticker, outputsize)
    try:
        history = provider.get_daily_history(ticker, outputsize=outputsize, market=market)
        if history.empty:
            logger.warning("Empty history for %s — using placeholder", ticker)
            return _generate_placeholder_price_data(ticker, outputsize)
        return history
    except Exception as e:
        logger.error("Error fetching history for %s: %s — %s", ticker, type(e).__name__, e)
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


def fetch_fundamentals(symbol: str) -> dict:
    if not TWELVE_DATA_API_KEY:
        return {}
    try:
        import requests
        url = f"{TWELVE_DATA_BASE_URL}/statistics"
        params = {"symbol": symbol, "apikey": TWELVE_DATA_API_KEY}
        response = requests.get(url, params=params, timeout=API_REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()

        if "status" in data and data["status"] == "error":
            logger.warning("API error for %s: %s", symbol, data.get("message", ""))
            return {}

        if "statistics" not in data:
            logger.warning("No statistics for %s", symbol)
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

    except requests.Timeout:
        logger.error("Timeout fetching fundamentals for %s (limit=%ds)", symbol, API_REQUEST_TIMEOUT)
        return {}
    except requests.ConnectionError:
        logger.error("Connection error fetching fundamentals for %s", symbol)
        return {}
    except Exception as e:
        logger.error("Unexpected error fetching fundamentals for %s: %s — %s", symbol, type(e).__name__, e)
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


def fetch_market_data(market: str) -> pd.DataFrame:
    global _last_diagnostics

    if market not in SUPPORTED_MARKETS:
        raise ValueError(f"Unsupported market: {market}. Choose from {list(SUPPORTED_MARKETS.keys())}")

    from momentum_metrics import append_momentum_fields, get_benchmark_history

    start_time = time.time()
    diag = FetchDiagnostics(market=market, timestamp=start_time)
    symbols = SUPPORTED_MARKETS[market]["symbols"]
    diag.total_tickers = len(symbols)

    provider = get_provider()

    if provider is None:
        logger.info("No API key — using mock data for %s", market)
        diag.used_mock = True
        df = get_mock_data(market)
        df["price_data"] = df["ticker"].apply(
            lambda t: _generate_placeholder_price_data(t)
        )
        benchmark = get_benchmark_history(market)
        df = append_momentum_fields(df, benchmark_history=benchmark)
        diag.fetched_tickers = len(df)
        for _, row in df.iterrows():
            _check_row_completeness(row.to_dict(), diag)
        diag.duration_seconds = time.time() - start_time
        _last_diagnostics = diag
        return df

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
            _check_row_completeness(enriched, diag)
            records.append(enriched)
            diag.fetched_tickers += 1

            logger.info(
                "Fetched %s: price=%s, rs_fields=%d/%d",
                symbol,
                enriched.get("price", "N/A"),
                len(REQUIRED_FIELDS_FOR_SCORING) - sum(
                    1 for f in REQUIRED_FIELDS_FOR_SCORING
                    if enriched.get(f) is None or (isinstance(enriched.get(f), float) and np.isnan(enriched.get(f)))
                ),
                len(REQUIRED_FIELDS_FOR_SCORING),
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
        if FALLBACK_TO_MOCK:
            logger.error("No data fetched for %s — falling back to mock data", market)
            diag.fallback_triggered = True
            diag.used_mock = True
            df = get_mock_data(market)
            df["price_data"] = df["ticker"].apply(
                lambda t: _generate_placeholder_price_data(t)
            )
            benchmark = get_benchmark_history(market)
            df = append_momentum_fields(df, benchmark_history=benchmark)
            diag.fetched_tickers = len(df)
            diag.duration_seconds = time.time() - start_time
            _last_diagnostics = diag
            return df
        else:
            diag.duration_seconds = time.time() - start_time
            _last_diagnostics = diag
            raise RuntimeError(f"No data could be fetched for market {market} and fallback is disabled")

    if len(records) < MIN_ROWS_FOR_SCORING:
        logger.warning(
            "Only %d/%d tickers fetched for %s — below minimum %d for reliable scoring",
            len(records), len(symbols), market, MIN_ROWS_FOR_SCORING,
        )

    df = pd.DataFrame(records)
    df = ensure_columns(df)
    df = coerce_numeric_columns(df)

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
    result: Dict[str, Optional[float]] = {"ma50": None, "ma200": None, "ma50_ratio": None, "ma200_ratio": None}
    if price_data is None or price_data.empty or "close" not in price_data.columns:
        return result
    closes = price_data["close"].values.astype(float)
    current = closes[-1] if len(closes) > 0 and np.isfinite(closes[-1]) else None
    if current is None:
        return result
    if len(closes) >= 50:
        ma50 = float(np.mean(closes[-50:]))
        if np.isfinite(ma50) and ma50 > 0:
            result["ma50"] = round(ma50, 4)
            result["ma50_ratio"] = round(current / ma50, 4)
    if len(closes) >= 200:
        ma200 = float(np.mean(closes[-200:]))
        if np.isfinite(ma200) and ma200 > 0:
            result["ma200"] = round(ma200, 4)
            result["ma200_ratio"] = round(current / ma200, 4)
    return result


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
        "ma50": [], "ma200": [], "ma50_ratio": [], "ma200_ratio": [],
        "rsi": [],
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

        rets = calculate_returns(price_data) if is_valid else {"return_1m": None, "return_3m": None, "return_6m": None, "return_12m": None}
        tech_cols["return_1m"].append(rets.get("return_1m"))
        tech_cols["return_3m"].append(rets.get("return_3m"))
        tech_cols["return_6m"].append(rets.get("return_6m"))
        tech_cols["return_12m"].append(rets.get("return_12m"))

        mas = calculate_moving_averages(price_data) if is_valid else {"ma50": None, "ma200": None, "ma50_ratio": None, "ma200_ratio": None}
        tech_cols["ma50"].append(mas.get("ma50"))
        tech_cols["ma200"].append(mas.get("ma200"))
        tech_cols["ma50_ratio"].append(mas.get("ma50_ratio"))
        tech_cols["ma200_ratio"].append(mas.get("ma200_ratio"))

        tech_cols["rsi"].append(calculate_rsi(price_data) if is_valid else None)
        tech_cols["volume_ratio"].append(calculate_volume_ratio(price_data) if is_valid else None)
        tech_cols["mfi"].append(calculate_mfi(price_data) if is_valid else None)

        obv = calculate_obv(price_data) if is_valid else {"obv_latest": None, "obv_trend_positive": None, "obv_slope": None}
        tech_cols["obv_latest"].append(obv.get("obv_latest"))
        tech_cols["obv_trend_positive"].append(obv.get("obv_trend_positive"))
        tech_cols["obv_slope"].append(obv.get("obv_slope"))

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

    for col in ["return_1m", "return_3m", "return_6m", "return_12m",
                "ma50", "ma200", "ma50_ratio", "ma200_ratio",
                "rsi", "volume_ratio", "mfi",
                "obv_latest", "obv_slope", "distance_to_52w_high"]:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce")

    return result


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
