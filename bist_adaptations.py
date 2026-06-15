"""
BIST Adaptations Module

BIST (Borsa İstanbul) piyasasına özgü skorlama düzeltmeleri.
USA ile BIST arasındaki yapısal farkları telafi eder:

  A. Reel büyüme filtresi  — nominal büyüme - TÜFE = reel büyüme
  B. Sektörel göreceli değerleme — PE/PB sabit eşik yerine sektör medyanı
  C. USD bazlı RS benchmark — XU100/TL yerine XU100/USD
  D. Bankacılık sektörü istisnası — D/E ve EV/EBITDA bank hisselerinde geçersiz
"""

import logging
import numpy as np
import pandas as pd
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# A. Türkiye Yıllık TÜFE Geçmişi (TÜİK / TCMB verileri)
# ---------------------------------------------------------------------------
# Yıl sonu enflasyon oranları (yıllık bazda, örn. 0.64 = %64)
TURKEY_CPI_ANNUAL = {
    2017: 0.1152,
    2018: 0.2030,
    2019: 0.1154,
    2020: 0.1436,
    2021: 0.1906,
    2022: 0.7224,
    2023: 0.6497,
    2024: 0.4461,
    2025: 0.3800,  # tahmin
    2026: 0.3200,  # tahmin
}

def _get_inflation(year: int) -> float:
    """Verilen yıl için TÜFE oranını döner. Bilinmiyorsa %40 varsayılan."""
    return TURKEY_CPI_ANNUAL.get(int(year), 0.40)


def _current_inflation() -> float:
    """Güncel yıl için tahmin edilen TÜFE."""
    from datetime import date
    return _get_inflation(date.today().year)


# ---------------------------------------------------------------------------
# A: Reel Büyüme Hesabı
# ---------------------------------------------------------------------------

def apply_real_growth(df: pd.DataFrame) -> pd.DataFrame:
    """
    Nominal büyüme oranlarını reel büyümeye çevirir.

    Formül: reel_büyüme = (1 + nominal) / (1 + enflasyon) - 1

    Etkilenen kolonlar:
      revenue_growth  → real_revenue_growth (ve üzerine yazar)
      earnings_growth → real_earnings_growth (ve üzerine yazar)
      revenue_cagr_3y → zaten birden fazla yılı kapsıyor, geometrik ortalama TÜFE kullanılır
    """
    inflation = _current_inflation()
    result = df.copy()

    for nom_col in ("revenue_growth", "earnings_growth"):
        if nom_col in result.columns:
            result[nom_col] = result[nom_col].apply(
                lambda x: _to_real(x, inflation)
            )
            logger.debug("BIST reel büyüme uygulandı: %s (enflasyon=%.1f%%)",
                         nom_col, inflation * 100)

    # 3 yıllık CAGR: ortalama 3 yıllık TÜFE ile düzelt
    from datetime import date
    yr = date.today().year
    avg_cpi_3y = np.mean([_get_inflation(yr - i) for i in range(3)])
    for cagr_col in ("revenue_cagr_3y", "eps_cagr_3y"):
        if cagr_col in result.columns:
            result[cagr_col] = result[cagr_col].apply(
                lambda x: _to_real(x, avg_cpi_3y)
            )

    return result


def _to_real(nominal, inflation: float):
    """(1+nominal)/(1+inflation)-1. NaN/None korumalı."""
    if nominal is None or (isinstance(nominal, float) and np.isnan(nominal)):
        return nominal
    try:
        return (1 + float(nominal)) / (1 + inflation) - 1
    except (TypeError, ValueError):
        return nominal


# ---------------------------------------------------------------------------
# B: Sektörel Göreceli Değerleme (BIST için sektör medyanları)
# ---------------------------------------------------------------------------

# BIST sektör kodlarına göre tipik PE ve PB aralıkları
# (Borsa İstanbul sektör sınıflandırması)
BIST_SECTOR_MEDIAN_PE = {
    "Bankacılık":          8.0,
    "Finans":              9.0,
    "Sigorta":             7.0,
    "Holding":             6.0,
    "Perakende":          12.0,
    "Gıda":               14.0,
    "Teknoloji":          20.0,
    "Sağlık":             16.0,
    "Enerji":             10.0,
    "Petrol & Gaz":        8.0,
    "Demir & Çelik":       7.0,
    "İnşaat":             10.0,
    "Tekstil":             8.0,
    "Kimya":              11.0,
    "Ulaştırma":          12.0,
    "Telekom":            13.0,
    "Çimento":             9.0,
    "DEFAULT":            10.0,
}

BIST_SECTOR_MEDIAN_PB = {
    "Bankacılık":          1.2,
    "Finans":              1.3,
    "Sigorta":             1.1,
    "Holding":             0.8,
    "Perakende":           2.5,
    "Gıda":                2.8,
    "Teknoloji":           4.0,
    "Sağlık":              3.0,
    "Enerji":              1.5,
    "Petrol & Gaz":        1.4,
    "Demir & Çelik":       1.0,
    "İnşaat":              1.2,
    "Tekstil":             1.0,
    "Kimya":               1.8,
    "Ulaştırma":           2.0,
    "Telekom":             2.2,
    "Çimento":             1.5,
    "DEFAULT":             1.5,
}


def _sector_key(sector_str: str) -> str:
    """Sektör stringinden eşleşme anahtarı bulur."""
    if not sector_str or not isinstance(sector_str, str):
        return "DEFAULT"
    s = sector_str.strip()
    for key in BIST_SECTOR_MEDIAN_PE:
        if key in s or s in key:
            return key
    return "DEFAULT"


def apply_sector_relative_valuation(df: pd.DataFrame) -> pd.DataFrame:
    """
    BIST'te PE ve PB'yi ham değer yerine sektör medyanına oranla normalize eder.

    Yeni kolonlar:
      pe_sector_ratio  = pe / sektör_medyan_pe
      pb_sector_ratio  = pb / sektör_medyan_pb

    Bunlar percentile hesabında PE/PB'nin yerini alır.
    (Düşük oran = ucuz = iyi puan)
    """
    result = df.copy()

    def _pe_ratio(row):
        val = row.get("pe")
        if val is None or (isinstance(val, float) and (np.isnan(val) or val <= 0)):
            return np.nan
        sector = _sector_key(str(row.get("sector", "")))
        median = BIST_SECTOR_MEDIAN_PE.get(sector, BIST_SECTOR_MEDIAN_PE["DEFAULT"])
        return float(val) / median  # < 1.0 = ucuz

    def _pb_ratio(row):
        val = row.get("pb")
        if val is None or (isinstance(val, float) and (np.isnan(val) or val <= 0)):
            return np.nan
        sector = _sector_key(str(row.get("sector", "")))
        median = BIST_SECTOR_MEDIAN_PB.get(sector, BIST_SECTOR_MEDIAN_PB["DEFAULT"])
        return float(val) / median

    if "pe" in result.columns:
        result["pe"] = result.apply(_pe_ratio, axis=1)
    if "pb" in result.columns:
        result["pb"] = result.apply(_pb_ratio, axis=1)

    # < 1.0 = sektöründen ucuz = daha iyi (düşük = iyi, percentile rank zaten invertiyor)
    return result


# ---------------------------------------------------------------------------
# C: USD Bazlı RS — XU100/USD
# ---------------------------------------------------------------------------

_usdtry_cache: Optional[pd.DataFrame] = None


def _fetch_usdtry() -> Optional[pd.DataFrame]:
    """USD/TRY kur geçmişini yfinance'ten çeker (cache'li)."""
    global _usdtry_cache
    if _usdtry_cache is not None and not _usdtry_cache.empty:
        return _usdtry_cache
    try:
        import yfinance as yf
        df = yf.download("USDTRY=X", period="2y", interval="1d",
                         auto_adjust=True, progress=False)
        if df.empty:
            return None
        df = df[["Close"]].copy()
        df.columns = ["usdtry"]
        df.index = pd.to_datetime(df.index).tz_localize(None)
        _usdtry_cache = df
        return df
    except Exception as e:
        logger.warning("USD/TRY çekilemedi: %s", e)
        return None


def convert_benchmark_to_usd(
    benchmark_history: Optional[pd.DataFrame],
) -> Optional[pd.DataFrame]:
    """
    XU100 TL bazlı geçmişini USD bazına çevirir.

    close_usd = close_tl / usdtry
    """
    if benchmark_history is None or benchmark_history.empty:
        return benchmark_history

    usdtry = _fetch_usdtry()
    if usdtry is None:
        logger.debug("USD/TRY alınamadı, TL bazlı benchmark kullanılıyor")
        return benchmark_history

    bh = benchmark_history.copy()
    bh["datetime"] = pd.to_datetime(bh["datetime"]).dt.tz_localize(None)

    merged = pd.merge_asof(
        bh.sort_values("datetime"),
        usdtry.reset_index().rename(columns={"Date": "datetime"}),
        on="datetime",
        direction="backward",
    )

    if "usdtry" in merged.columns and merged["usdtry"].notna().any():
        merged["close"] = merged["close"] / merged["usdtry"]
        merged.drop(columns=["usdtry"], inplace=True)
        logger.debug("XU100 USD bazına çevrildi")
        return merged

    return bh


def convert_stock_to_usd(price_df: pd.DataFrame) -> pd.DataFrame:
    """
    BIST hisse fiyatlarını TL'den USD'ye çevirir.
    close_usd = close_tl / usdtry
    """
    if price_df is None or price_df.empty:
        return price_df

    usdtry = _fetch_usdtry()
    if usdtry is None:
        return price_df

    df = price_df.copy()
    df["datetime"] = pd.to_datetime(df["datetime"]).dt.tz_localize(None)

    merged = pd.merge_asof(
        df.sort_values("datetime"),
        usdtry.reset_index().rename(columns={"Date": "datetime"}),
        on="datetime",
        direction="backward",
    )

    if "usdtry" in merged.columns and merged["usdtry"].notna().any():
        for col in ("open", "high", "low", "close"):
            if col in merged.columns:
                merged[col] = merged[col] / merged["usdtry"]
        merged.drop(columns=["usdtry"], inplace=True)
        return merged

    return df


# ---------------------------------------------------------------------------
# D: Bankacılık Sektörü İstisnası
# ---------------------------------------------------------------------------

BANKING_SECTOR_KEYWORDS = {
    "bankacılık", "bank", "finans", "financi", "sigorta", "insurance",
    "kalkınma", "yatırım bankası",
}


def _is_banking(sector_str: str) -> bool:
    if not sector_str or not isinstance(sector_str, str):
        return False
    s = sector_str.strip().lower()
    return any(kw in s for kw in BANKING_SECTOR_KEYWORDS)


def apply_banking_exception(df: pd.DataFrame) -> pd.DataFrame:
    """
    Bankacılık/finans sektörü hisseleri için yanıltıcı metrikleri NaN yap:
      - debt_to_equity: bankalar yapısal olarak yüksek kaldıraçlı → skor dışı
      - ev_ebitda: bankalar için anlamsız → skor dışı
      - equity_to_assets: banka regülasyonunda farklı normlar → skor dışı

    Bu NaN değerler _weighted_sub_score'da otomatik olarak ağırlık
    yeniden dağıtımına girer, bu da diğer metriklere daha fazla ağırlık verir.
    """
    result = df.copy()

    if "sector" not in result.columns:
        return result

    bank_mask = result["sector"].apply(
        lambda s: _is_banking(str(s) if s is not None else "")
    )

    if bank_mask.any():
        bank_count = bank_mask.sum()
        logger.debug("Bankacılık istisnası: %d hisse için D/E ve EV/EBITDA skor dışı", bank_count)
        for col in ("debt_to_equity", "ev_ebitda", "equity_to_assets"):
            if col in result.columns:
                result.loc[bank_mask, col] = np.nan

    return result


# ---------------------------------------------------------------------------
# Ana Entegrasyon Fonksiyonu
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# E: Free Float Filtresi
# ---------------------------------------------------------------------------
# BIST'te aile/holding kontrolündeki düşük free float hisseler
# fiyat manipülasyonuna açık ve kurumsal yatırımcı tarafından işlem görmez.
# FMP profile verisinde floatShares/sharesOutstanding yoksa
# bu statik liste devreye girer.

# Bilinen düşük free float BIST hisseleri (< %25 serbest dolaşım)
_LOW_FREE_FLOAT_BIST = {
    # Aile/holding kontrolü ile bilinen hisseler
    "ATATR", "ATYHO", "AVHOL", "AVPGY",
    "BEGYO", "CGCAM", "DENGE",
    "EKGYO",  # GYO - düşük serbest dolaşım dönemleri oldu
    "GLYHO", "GLCVY",
    "HEKTS",
    "ISYHO",
    "KOZAA", "KOZAL",  # Koza grubu düşük free float dönemleri
    "MRSHL",
    "PRKAB",
    "SARKY",
    "ULUFA",
    "YKGYO",
}

_MIN_FREE_FLOAT_PCT = 0.25  # %25 minimum serbest dolaşım oranı


def apply_free_float_filter(df: pd.DataFrame) -> pd.DataFrame:
    """
    Düşük serbest dolaşım oranlı BIST hisselerini filtreler.

    İki katmanlı yaklaşım:
    1. Eğer veri modelinde free_float_pct kolonu varsa: %25 altındakileri eliyor.
    2. Yoksa: bilinen düşük free float statik listesini kullanıyor.
    """
    if df.empty:
        return df

    result = df.copy()

    # Katman 1: free_float_pct kolonu mevcut ise hesapla
    if "free_float_pct" in result.columns:
        before = len(result)
        result = result[
            result["free_float_pct"].isna() |  # veri yoksa geçir
            (result["free_float_pct"] >= _MIN_FREE_FLOAT_PCT)
        ].reset_index(drop=True)
        removed = before - len(result)
        if removed > 0:
            logger.debug("Free float filtresi: %d hisse elendi (< %%.0f%%)",
                         removed, _MIN_FREE_FLOAT_PCT * 100)
        return result

    # Katman 2: Statik liste — ticker kolonunu kontrol et
    if "ticker" not in result.columns:
        return result

    def _base_ticker(t: str) -> str:
        """THYAO.IS → THYAO"""
        return t.split(".")[0].upper() if isinstance(t, str) else t

    before = len(result)
    result = result[
        ~result["ticker"].apply(_base_ticker).isin(_LOW_FREE_FLOAT_BIST)
    ].reset_index(drop=True)
    removed = before - len(result)
    if removed > 0:
        logger.debug("Free float statik liste: %d hisse elendi", removed)

    return result


# ---------------------------------------------------------------------------
# F: BIST Pure Momentum Score (fundamentals yoksa kullanılır — backtest)
# ---------------------------------------------------------------------------
# Mark Minervini yaklaşımı: RS vs benchmark + Stage2 trend + price momentum
# compute_rs_scores() içinde financial sub-scorelerin büyük bölümü NaN ise
# bu skor rs_score'un yerine geçer.

def compute_bist_pure_momentum_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    BIST için geliştirilmiş saf momentum/teknik skoru.

    Ağırlıklar:
      RS vs XU100      35%  — benchmark göreceli getiri
      Price Momentum   25%  — ağırlıklı return (1m/3m/6m) + ivme bonusu
      Stage2 Trend     20%  — MA50/MA200 hizalaması + eğim gücü
      RSI Sinyali      10%  — 50-70 güçlü, >70 hala pozitif (BIST dinamiğine uygun)
      52w Yakınlığı    10%  — DÜZELTİLDİ: dist yüzde cinsinden
    """
    result = df.copy()
    n = len(result)
    if n == 0:
        return result

    def _pct_rank(arr):
        s = pd.Series(arr, dtype=float)
        return s.rank(pct=True, na_option="keep").mul(100).fillna(50.0).values

    # ── 1. RS vs XU100 (35%) ─────────────────────────────────────────
    rel_col = "relative_return_vs_index"
    rs_raw = pd.to_numeric(
        result[rel_col] if rel_col in result.columns else pd.Series([np.nan] * n),
        errors="coerce"
    )
    rs_pct = _pct_rank(rs_raw.values)

    # ── 2. Price Momentum (25%) + ivme bonusu ────────────────────────
    def _get_col(col):
        if col in result.columns:
            return pd.to_numeric(result[col], errors="coerce").fillna(0).values
        return np.zeros(n)

    r1m = _get_col("return_1m")
    r3m = _get_col("return_3m")
    r6m = _get_col("return_6m")

    mom_raw = r1m * 0.25 + r3m * 0.50 + r6m * 0.25
    mom_pct = _pct_rank(mom_raw)

    # İvme bonusu: 1 aylık hız > 3 aylık ortalama hız → trend hızlanıyor
    r3m_monthly = r3m / 3.0
    accel_bonus = np.where(r1m > r3m_monthly, 8.0, 0.0)
    mom_pct = np.minimum(mom_pct + accel_bonus, 100.0)

    # ── 3. Stage2 Trend (20%) ────────────────────────────────────────
    def _stage2(row):
        try:
            p    = float(row.get("price") or row.get("close") or 0)
            m50  = float(row.get("ma50")  or row.get("sma50")  or 0)
            m200 = float(row.get("ma200") or row.get("sma200") or 0)
            if p <= 0 or m50 <= 0 or m200 <= 0:
                return 50.0
            if p > m50 and m50 > m200:
                # Full Stage2: eğim ne kadar dik?
                slope_bonus = min((m50 / m200 - 1.0) * 1500, 15.0)
                return min(80.0 + slope_bonus, 100.0)
            elif p > m200 and p > m50 * 0.97:  # MA50'ye yakın, MA200 üstü
                return 65.0
            elif p > m200:
                return 40.0
            elif p > m50:
                return 30.0
            else:
                return 15.0
        except Exception:
            return 50.0

    stage2_scores = result.apply(_stage2, axis=1).values

    # ── 4. RSI Sinyali (10%) ─────────────────────────────────────────
    rsi_raw = pd.to_numeric(
        result["rsi"] if "rsi" in result.columns else pd.Series([np.nan] * n),
        errors="coerce"
    )

    def _rsi_to_score(r):
        if np.isnan(r): return 50.0
        if 50 <= r <= 70:  return 100.0   # En güçlü momentum
        if 70 < r <= 80:   return 85.0    # Hala güçlü (BIST'te normal)
        if r > 80:         return 65.0    # Climax uyarısı
        if 45 <= r < 50:   return 55.0    # Zayıflıyor
        if 35 <= r < 45:   return 25.0    # Zayıf
        return 10.0

    rsi_scores = rsi_raw.apply(_rsi_to_score).values

    # ── 5. 52w Yakınlığı (10%) — DÜZELTİLMİŞ ───────────────────────
    # distance_to_52w_high YÜZDE cinsinden: 0 = tam yüksekte, -5.0 = %5 aşağıda
    # Önceki kod ondalık bekliyordu → -5.0 için (1+(-5))*100 = -400 → 0! (BUG)
    if "distance_to_52w_high" in result.columns:
        dist = pd.to_numeric(result["distance_to_52w_high"], errors="coerce")
        prox = (100.0 + dist.fillna(-50.0)).clip(0, 100).values
    else:
        prox = np.full(n, 50.0)

    # ── 6. Birleştir ─────────────────────────────────────────────────
    bist_mom = (
        rs_pct        * 0.35
        + mom_pct     * 0.25
        + stage2_scores * 0.20
        + rsi_scores  * 0.10
        + prox        * 0.10
    ).clip(0, 100).round(1)

    result["bist_momentum_rs"] = bist_mom
    return result

def apply_all(df: pd.DataFrame, market: str) -> pd.DataFrame:
    """
    BIST piyasasına özgü tüm adaptasyonları sırayla uygular.
    market != "BIST" ise hiçbir şey yapmaz.
    """
    if not df.empty and (market or "").upper() == "BIST":
        df = apply_real_growth(df)                # A: Reel büyüme
        df = apply_sector_relative_valuation(df)  # B: Sektörel değerleme
        df = apply_banking_exception(df)          # D: Bankacılık istisnası
        df = apply_free_float_filter(df)          # E: Free float filtresi
        # C (USD benchmark) momentum_metrics.py'de ayrıca uygulanır
    return df
