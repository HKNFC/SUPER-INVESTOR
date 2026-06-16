"""
Historical Fundamentals Module

Backtest sırasında her rebalance tarihinde, o tarihe kadar mevcut olan
en son yıllık bilanço verilerini döndürür.

- USA hisseleri: FMP annual reports (5 yıl, 24s cache)
- BIST hisseleri: Yahoo Finance yıllık gelir/bilanço tabloları (4 yıl, 24s cache)
  Look-ahead bias önlemi: fiskal yıl bitiş tarihi + 90 gün geçmeden o yılın verisi kullanılmaz.
  (BIST şirketleri genellikle yıl sonu raporunu 2-3 ay içinde yayınlar.)
"""

import os
import json
import time
import logging
import numpy as np
import pandas as pd
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, Any

import requests

logger = logging.getLogger(__name__)

# FMP API
FMP_API_KEY = os.environ.get("FMP_API_KEY") or ""
FMP_BASE_URL = "https://financialmodelingprep.com/stable"

# Disk cache dizini
HIST_CACHE_DIR = Path(os.path.expanduser("~/.cache/fmp_hist"))
HIST_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 24 saatlik TTL
HIST_CACHE_TTL_HOURS = 24
_PARALLEL_WORKERS = 10

# ---------------------------------------------------------------------------
# RAM (in-memory) cache — disk'i yalnızca ilk yüklemede okur.
# Backtest döngüsünde 78 000+ disk JSON okuma → sıfıra iner.
# ---------------------------------------------------------------------------
_MEM_CACHE: Dict[str, dict] = {}      # USA FMP  → {symbol: data}
_MEM_BIST_CACHE: Dict[str, dict] = {} # BIST Yahoo → {symbol: data}


# ---------------------------------------------------------------------------
# Cache yardımcıları
# ---------------------------------------------------------------------------

def _cache_path(symbol: str) -> Path:
    safe = symbol.replace(".", "_").replace("/", "_").replace(":", "_")
    return HIST_CACHE_DIR / f"{safe}.json"


def _load_cache(symbol: str) -> Optional[dict]:
    # Önce RAM cache'e bak
    if symbol in _MEM_CACHE:
        return _MEM_CACHE[symbol]
    path = _cache_path(symbol)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        if time.time() - data.get("_ts", 0) < HIST_CACHE_TTL_HOURS * 3600:
            _MEM_CACHE[symbol] = data   # RAM'e al, bir daha diske gitme
            return data
    except Exception:
        pass
    return None


def _save_cache(symbol: str, data: dict) -> None:
    data["_ts"] = time.time()
    _MEM_CACHE[symbol] = data   # RAM'e de yaz
    try:
        with open(_cache_path(symbol), "w") as f:
            json.dump(data, f)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# FMP API
# ---------------------------------------------------------------------------

def _fmp_get(endpoint: str, params: dict = None):
    """FMP stable API'den veri çeker."""
    if not FMP_API_KEY:
        return None
    p = dict(params or {})
    p["apikey"] = FMP_API_KEY
    try:
        r = requests.get(f"{FMP_BASE_URL}/{endpoint}", params=p, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.debug("FMP request failed (%s): %s", endpoint, e)
    return None


# ---------------------------------------------------------------------------
# Veri çekme ve hazırlama
# ---------------------------------------------------------------------------

def _fetch_symbol_data(symbol: str) -> dict:
    """FMP'den bir sembolün 5 yıllık yıllık verilerini çekip cache'e yazar."""
    cached = _load_cache(symbol)
    if cached:
        return cached

    income_raw = _fmp_get("income-statement", {"symbol": symbol, "period": "annual", "limit": 6}) or []
    balance_raw = _fmp_get("balance-sheet-statement", {"symbol": symbol, "period": "annual", "limit": 6}) or []
    metrics_raw = _fmp_get("key-metrics", {"symbol": symbol, "period": "annual", "limit": 6}) or []

    if not income_raw:
        empty = {"reports": []}
        _save_cache(symbol, empty)
        return empty

    # Tarih bazlı lookup
    income_by_date = {r["date"]: r for r in income_raw if r.get("date")}
    balance_by_date = {r["date"]: r for r in balance_raw if r.get("date")}
    metrics_by_date = {r["date"]: r for r in metrics_raw if r.get("date")}

    all_dates = sorted(income_by_date.keys(), reverse=True)

    reports = []
    for i, d in enumerate(all_dates):
        inc = income_by_date.get(d, {})
        bal = balance_by_date.get(d, {})
        met = metrics_by_date.get(d, {})
        prev_inc = income_by_date.get(all_dates[i + 1]) if i + 1 < len(all_dates) else None

        revenue = _safe(inc.get("revenue"))
        net_income = _safe(inc.get("netIncome"))
        prev_revenue = _safe(prev_inc.get("revenue")) if prev_inc else None
        prev_net_income = _safe(prev_inc.get("netIncome")) if prev_inc else None
        eps = _safe(inc.get("eps"))
        prev_eps = _safe(prev_inc.get("eps")) if prev_inc else None

        revenue_growth = None
        if revenue is not None and prev_revenue and prev_revenue != 0:
            revenue_growth = (revenue - prev_revenue) / abs(prev_revenue)

        earnings_growth = None
        if net_income is not None and prev_net_income and prev_net_income != 0:
            earnings_growth = (net_income - prev_net_income) / abs(prev_net_income)

        gross_profit = _safe(inc.get("grossProfit"))
        operating_income = _safe(inc.get("operatingIncome"))
        ebitda = _safe(inc.get("ebitda"))
        equity = _safe(bal.get("totalEquity") or bal.get("stockholdersEquity"))
        total_debt = _safe(bal.get("totalDebt"))
        total_assets = _safe(bal.get("totalAssets"))

        report = {
            "date": d,
            # Gelir tablosu ham
            "revenue": revenue,
            "net_income": net_income,
            "gross_profit": gross_profit,
            "operating_income": operating_income,
            "ebitda": ebitda,
            "eps": eps,
            # Bilanço ham
            "equity": equity,
            "total_debt": total_debt,
            "total_assets": total_assets,
            # Geçen yıl (büyüme için)
            "revenue_prev_year": prev_revenue,
            "net_income_prev_year": prev_net_income,
            # Büyüme oranları (YoY)
            "revenue_growth": revenue_growth,
            "earnings_growth": earnings_growth,
            # FMP key metrics (önceden hesaplanmış)
            "roe": _safe(met.get("roe")),
            "roic": _safe(met.get("roic")),
            "pe": _safe(met.get("peRatio")),
            "pb": _safe(met.get("priceToBookRatio")),
            "ev_ebitda": _safe(met.get("evToEbitda") or met.get("enterpriseValueOverEBITDA")),
            "peg": _safe(met.get("pegRatio")),
            "gross_margin": _safe(met.get("grossProfitMargin")),
            "net_margin": _safe(met.get("netProfitMargin")),
            "debt_to_equity": _safe(met.get("debtToEquity")),
            "current_ratio": _safe(met.get("currentRatio")),
        }
        reports.append(report)

    # 3 yıllık CAGR hesapla (4 rapor gerekli)
    for i, r in enumerate(reports):
        if i + 3 < len(reports):
            old = reports[i + 3]
            rev_now = r.get("revenue")
            rev_old = old.get("revenue")
            eps_now = r.get("eps")
            eps_old = old.get("eps")
            if rev_now and rev_old and rev_old > 0:
                r["revenue_cagr_3y"] = (rev_now / rev_old) ** (1 / 3) - 1
            if eps_now and eps_old and eps_old > 0:
                r["eps_cagr_3y"] = (eps_now / eps_old) ** (1 / 3) - 1

    result = {"reports": reports}
    _save_cache(symbol, result)
    return result


def _safe(val):
    """None/NaN/sonsuz olmayan float döner, yoksa None."""
    if val is None:
        return None
    try:
        f = float(val)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# BIST — Yahoo Finance tarihsel temel veri
# ---------------------------------------------------------------------------

# BIST için ayrı cache dizini
BIST_HIST_CACHE_DIR = Path(os.path.expanduser("~/.cache/bist_hist"))
BIST_HIST_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Look-ahead bias koruma süresi (gün)
# BIST şirketleri yıl sonu raporunu genellikle 60-90 gün içinde açıklar.
BIST_FILING_LAG_DAYS = 90


def _bist_cache_path(symbol: str) -> Path:
    safe = symbol.replace(".", "_").replace("/", "_").replace(":", "_")
    return BIST_HIST_CACHE_DIR / f"{safe}.json"


def _load_bist_cache(symbol: str) -> Optional[dict]:
    # Önce RAM cache'e bak
    if symbol in _MEM_BIST_CACHE:
        return _MEM_BIST_CACHE[symbol]
    path = _bist_cache_path(symbol)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        if time.time() - data.get("_ts", 0) < HIST_CACHE_TTL_HOURS * 3600:
            _MEM_BIST_CACHE[symbol] = data  # RAM'e al
            return data
    except Exception:
        pass
    return None


def _save_bist_cache(symbol: str, data: dict) -> None:
    data["_ts"] = time.time()
    _MEM_BIST_CACHE[symbol] = data  # RAM'e de yaz
    try:
        with open(_bist_cache_path(symbol), "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def _fetch_bist_symbol_data(symbol: str) -> dict:
    """
    Yahoo Finance'ten bir BIST hissesinin yıllık gelir/bilanço geçmişini çeker.
    symbol: 'THYAO' veya 'THYAO.IS' formatında kabul eder.
    Çıktı: {'reports': [{date, revenue, net_income, ...}, ...]} — azalan tarih sırası
    """
    cached = _load_bist_cache(symbol)
    if cached:
        return cached

    # Yahoo sembolü: THYAO → THYAO.IS
    yahoo_sym = symbol if symbol.endswith(".IS") else f"{symbol}.IS"

    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance not installed — BIST historical fundamentals unavailable")
        empty = {"reports": []}
        _save_bist_cache(symbol, empty)
        return empty

    try:
        ticker_obj = yf.Ticker(yahoo_sym)
        inc_stmt = ticker_obj.income_stmt   # sütunlar = fiscal year end Timestamps
        bs_stmt = ticker_obj.balance_sheet  # sütunlar = fiscal year end Timestamps
        info = ticker_obj.info or {}

        if inc_stmt is None or inc_stmt.empty:
            empty = {"reports": []}
            _save_bist_cache(symbol, empty)
            return empty

        # Ortak tarihleri bul (income & balance sheet kesişimi)
        inc_dates = sorted(inc_stmt.columns.tolist(), reverse=True)
        bs_dates  = set(bs_stmt.columns.tolist()) if bs_stmt is not None and not bs_stmt.empty else set()

        # Yalnızca geçmiş tarihleri tut (bugünden sonrası forward estimate olabilir)
        today_ts = pd.Timestamp.now().normalize()
        inc_dates = [d for d in inc_dates if pd.Timestamp(d) <= today_ts]

        def _row(stmt, label_candidates, col):
            for label in label_candidates:
                if label in stmt.index:
                    val = stmt.at[label, col]
                    return _safe(val)
            return None

        reports = []
        for i, col in enumerate(inc_dates):
            col_ts = pd.Timestamp(col)

            # Gelir tablosu
            revenue        = _row(inc_stmt, ["Total Revenue", "TotalRevenue"], col)
            net_income     = _row(inc_stmt, ["Net Income", "Net Income Common Stockholders", "NetIncome"], col)
            gross_profit   = _row(inc_stmt, ["Gross Profit", "GrossProfit"], col)
            operating_inc  = _row(inc_stmt, ["Operating Income", "OperatingIncome", "EBIT"], col)
            ebitda         = _row(inc_stmt, ["EBITDA", "Normalized EBITDA"], col)
            eps_basic      = _row(inc_stmt, ["Basic EPS", "Diluted EPS", "EPS"], col)

            # Bilanço
            total_assets = total_debt = equity = None
            if col in bs_dates:
                total_assets = _row(bs_stmt, ["Total Assets", "TotalAssets"], col)
                total_debt   = _row(bs_stmt, ["Total Debt", "Long Term Debt And Capital Lease Obligation",
                                               "Long Term Debt"], col)
                equity       = _row(bs_stmt, ["Total Equity Gross Minority Interest",
                                               "Stockholders Equity", "Total Stockholders Equity",
                                               "Common Stock Equity"], col)

            # Önceki yıl büyüme (bir sonraki tarih = eski yıl)
            prev_col = inc_dates[i + 1] if i + 1 < len(inc_dates) else None
            revenue_prev = net_income_prev = None
            if prev_col is not None:
                revenue_prev    = _row(inc_stmt, ["Total Revenue", "TotalRevenue"], prev_col)
                net_income_prev = _row(inc_stmt, ["Net Income", "Net Income Common Stockholders", "NetIncome"], prev_col)

            revenue_growth = earnings_growth = None
            if revenue is not None and revenue_prev and revenue_prev != 0:
                revenue_growth = (revenue - revenue_prev) / abs(revenue_prev)
            if net_income is not None and net_income_prev and net_income_prev != 0:
                earnings_growth = (net_income - net_income_prev) / abs(net_income_prev)

            # Temel oranlar (bilanço bazlı)
            roe = roic = gross_margin = net_margin = operating_margin = None
            debt_to_equity = None
            if equity and equity != 0 and net_income is not None:
                roe  = net_income / equity
                roic = net_income / equity  # basit proxy (invested_capital yok)
            if revenue and revenue != 0:
                if gross_profit is not None:
                    gross_margin = gross_profit / revenue
                if net_income is not None:
                    net_margin = net_income / revenue
                if operating_inc is not None:
                    operating_margin = operating_inc / revenue
            if equity and equity != 0 and total_debt is not None:
                debt_to_equity = total_debt / abs(equity)

            report = {
                "date": col_ts.strftime("%Y-%m-%d"),
                "revenue": revenue,
                "net_income": net_income,
                "gross_profit": gross_profit,
                "operating_income": operating_inc,
                "ebitda": ebitda,
                "eps": eps_basic,
                "equity": equity,
                "total_debt": total_debt,
                "total_assets": total_assets,
                "revenue_prev_year": revenue_prev,
                "net_income_prev_year": net_income_prev,
                "revenue_growth": revenue_growth,
                "earnings_growth": earnings_growth,
                "roe": roe,
                "roic": roic,
                "gross_margin": gross_margin,
                "net_margin": net_margin,
                "operating_margin": operating_margin,
                "debt_to_equity": debt_to_equity,
                # PE/PB/EV_EBITDA: static info'dan (fiyat bağımlı, tarihsel değil → None bırak)
                "pe": None,
                "pb": None,
                "ev_ebitda": None,
                "peg": None,
                "current_ratio": None,
            }
            reports.append(report)

        # 3 yıllık CAGR
        for i, r in enumerate(reports):
            if i + 3 < len(reports):
                old = reports[i + 3]
                rev_now = r.get("revenue"); rev_old = old.get("revenue")
                eps_now = r.get("eps");     eps_old = old.get("eps")
                if rev_now and rev_old and rev_old > 0:
                    r["revenue_cagr_3y"] = (rev_now / rev_old) ** (1 / 3) - 1
                if eps_now and eps_old and eps_old > 0:
                    r["eps_cagr_3y"] = (eps_now / eps_old) ** (1 / 3) - 1

        result = {"reports": reports, "source": "yahoo_bist"}
        _save_bist_cache(symbol, result)
        logger.info("BIST historical fundamentals cached for %s (%d reports)", symbol, len(reports))
        return result

    except Exception as e:
        logger.warning("BIST historical fundamentals failed for %s: %s", symbol, e)
        empty = {"reports": []}
        _save_bist_cache(symbol, empty)
        return empty


def get_bist_snapshot(symbol: str, as_of_date) -> dict:
    """
    as_of_date tarihinde BIST hissesi için mevcut olan en son yıllık bilanço verisini döner.

    Look-ahead bias önlemi:
      Bir rapor yalnızca fiskal yıl bitiş tarihi + BIST_FILING_LAG_DAYS (90 gün) geçtikten
      sonra "bilinen veri" sayılır.
      Örnek: FY2023 bitiş=2023-12-31 → en erken 2024-03-31'de kullanılabilir.
    """
    as_of_ts = pd.Timestamp(as_of_date)
    data = _fetch_bist_symbol_data(symbol)
    reports = data.get("reports", [])

    for report in reports:
        rep_date_str = report.get("date")
        if not rep_date_str:
            continue
        try:
            fiscal_end = pd.Timestamp(rep_date_str)
            available_date = fiscal_end + pd.Timedelta(days=BIST_FILING_LAG_DAYS)
            if available_date <= as_of_ts:
                return {k: v for k, v in report.items() if k not in ("date", "source")}
        except Exception:
            continue

    return {}


# ---------------------------------------------------------------------------
# Dışa açık API
# ---------------------------------------------------------------------------

def get_snapshot(symbol: str, market: str, as_of_date) -> dict:
    """
    as_of_date tarihinde mevcut olan en son yıllık temel veri snapshotını döner.

    - USA: FMP annual reports (FMP_API_KEY gerekli)
    - BIST: Yahoo Finance yıllık tablolar (90 gün filing-lag ile look-ahead bias önlemi)
    """
    is_bist = (market or "").upper() == "BIST"

    if is_bist:
        return get_bist_snapshot(symbol, as_of_date)

    # USA — FMP
    if not FMP_API_KEY:
        return {}

    as_of_ts = pd.Timestamp(as_of_date)
    data = _fetch_symbol_data(symbol)
    reports = data.get("reports", [])

    for report in reports:
        rep_date_str = report.get("date")
        if not rep_date_str:
            continue
        try:
            rep_ts = pd.Timestamp(rep_date_str)
            if rep_ts <= as_of_ts:
                return {k: v for k, v in report.items() if k != "date"}
        except Exception:
            continue

    return {}


def batch_prefetch(symbols: list, market: str, progress_callback=None) -> None:
    """
    Tüm sembollerin tarihsel temel verilerini paralel olarak önceden çeker ve cache'ler.
    - USA: FMP API (paralel, _PARALLEL_WORKERS thread)
    - BIST: Yahoo Finance (paralel, maksimum 5 thread — rate limit önlemi)
    """
    is_bist = (market or "").upper() == "BIST"

    if is_bist:
        # BIST: Yahoo Finance'ten yıllık tablolar
        to_fetch = [s for s in symbols if _load_bist_cache(s) is None]
        if not to_fetch:
            logger.info("BIST historical fundamentals: all %d symbols already cached", len(symbols))
            return
        total = len(to_fetch)
        logger.info("BIST historical fundamentals: prefetching %d/%d symbols...", total, len(symbols))
        done = 0
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(_fetch_bist_symbol_data, s): s for s in to_fetch}
            for future in as_completed(futures):
                done += 1
                sym = futures[future]
                if progress_callback:
                    progress_callback(done / total, f"BIST tarihsel temel veri: {done}/{total}")
                try:
                    future.result()
                except Exception as e:
                    logger.warning("BIST historical fundamentals failed for %s: %s", sym, e)
        logger.info("BIST historical fundamentals: prefetch complete (%d symbols)", total)
        return

    # USA — FMP
    if not FMP_API_KEY:
        return

    to_fetch = [s for s in symbols if _load_cache(s) is None]
    if not to_fetch:
        logger.info("Historical fundamentals: all %d symbols already cached", len(symbols))
        return

    total = len(to_fetch)
    logger.info("Historical fundamentals: prefetching %d/%d symbols...", total, len(symbols))
    done = 0

    with ThreadPoolExecutor(max_workers=_PARALLEL_WORKERS) as executor:
        futures = {executor.submit(_fetch_symbol_data, s): s for s in to_fetch}
        for future in as_completed(futures):
            done += 1
            sym = futures[future]
            if progress_callback:
                progress_callback(done / total, f"Tarihsel temel veri: {done}/{total}")
            try:
                future.result()
            except Exception as e:
                logger.warning("Historical fundamentals failed for %s: %s", sym, e)

    logger.info("Historical fundamentals: prefetch complete (%d symbols)", total)


def inject_fundamentals_at_date(
    df: pd.DataFrame,
    as_of_date,
    market: str,
) -> pd.DataFrame:
    """
    Her satır (hisse) için as_of_date tarihindeki tarihsel temel veriyi
    DataFrame'e enjekte eder.

    - USA: FMP historical data
    - BIST: Yahoo Finance historical data (90 gün filing-lag)
    - Mevcut NaN olmayan sütunlara dokunmaz.
    - Sadece NaN olan sütunları doldurur.
    """
    is_bist = (market or "").upper() == "BIST"

    # USA FMP key yoksa ve BIST değilse çık
    if not is_bist and not FMP_API_KEY:
        return df

    FUND_FIELDS = [
        "revenue", "net_income", "gross_profit", "operating_income", "ebitda",
        "equity", "total_debt", "total_assets",
        "revenue_prev_year", "net_income_prev_year",
        "revenue_growth", "earnings_growth",
        "roe", "roic", "pe", "pb", "ev_ebitda", "peg",
        "gross_margin", "net_margin", "debt_to_equity", "current_ratio",
    ]

    result = df.copy()

    # Eksik sütunları NaN olarak ekle
    for field in FUND_FIELDS:
        if field not in result.columns:
            result[field] = np.nan

    for idx, row in result.iterrows():
        ticker = row.get("ticker")
        if not ticker:
            continue

        snapshot = get_snapshot(ticker, market, as_of_date)
        if not snapshot:
            continue

        for field in FUND_FIELDS:
            val = snapshot.get(field)
            if val is None:
                continue
            current = row.get(field)
            is_nan = current is None or (isinstance(current, float) and np.isnan(current))
            if is_nan:
                try:
                    result.at[idx, field] = float(val)
                except (TypeError, ValueError):
                    pass

    return result
