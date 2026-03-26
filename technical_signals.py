"""
Technical Signal Score Engine

Computes a 0-100 Technical Signal Score from price/volume data
using five sub-components:

  1) Trend Score (30%) — MA50, MA200, golden cross
  2) Momentum Score (20%) — RSI(14), MACD signals
  3) Breakout Score (20%) — proximity to highs, volume ratio
  4) Volume Flow Score (20%) — MFI, OBV trend/divergence
  5) Risk / Stability Penalty (10%) — ATR-based volatility penalty

All indicators are computed from the 'price_data' DataFrame stored
in each row of the master DataFrame. Missing data is handled safely.
"""

import numpy as np
import pandas as pd
from typing import Optional


COMBINED_WEIGHT_RS = 0.65
COMBINED_WEIGHT_TECH = 0.35

TREND_WEIGHT = 0.30
MOMENTUM_WEIGHT = 0.20
BREAKOUT_WEIGHT = 0.20
VOLUME_FLOW_WEIGHT = 0.20
RISK_WEIGHT = 0.10

SETUP_LABELS = {
    "strong_buy": "Güçlü Alım Adayı",
    "watchlist": "İzleme",
    "early_setup": "Erken Kurulum",
    "avoid": "Kaçın",
}


def _safe_float(val) -> float:
    if val is None:
        return np.nan
    try:
        f = float(val)
        return f if np.isfinite(f) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _get_closes(price_data: pd.DataFrame) -> Optional[np.ndarray]:
    if price_data is None or not isinstance(price_data, pd.DataFrame):
        return None
    if price_data.empty or "close" not in price_data.columns:
        return None
    arr = price_data["close"].values.astype(float)
    if len(arr) < 5:
        return None
    return arr


def _calc_sma(closes: np.ndarray, window: int) -> Optional[float]:
    if len(closes) < window:
        return None
    return float(np.mean(closes[-window:]))


def _calc_ema(closes: np.ndarray, span: int) -> np.ndarray:
    alpha = 2.0 / (span + 1)
    ema = np.empty_like(closes)
    ema[0] = closes[0]
    for i in range(1, len(closes)):
        ema[i] = alpha * closes[i] + (1 - alpha) * ema[i - 1]
    return ema


def _calc_rsi(closes: np.ndarray, period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    deltas = np.diff(closes[-(period + 1):])
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains)
    avg_loss = np.mean(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


def _calc_macd(closes: np.ndarray):
    if len(closes) < 35:
        return None, None, None
    ema12 = _calc_ema(closes, 12)
    ema26 = _calc_ema(closes, 26)
    macd_line = ema12 - ema26
    signal_line = _calc_ema(macd_line, 9)
    histogram = macd_line - signal_line
    return float(macd_line[-1]), float(signal_line[-1]), float(histogram[-1])


def _calc_atr(price_data: pd.DataFrame, period: int = 14) -> Optional[float]:
    if price_data is None or len(price_data) < period + 1:
        return None
    if not all(c in price_data.columns for c in ["high", "low", "close"]):
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
    return float(np.mean(tr_values[-period:]))


def compute_trend_score(closes: np.ndarray) -> float:
    score = 0.0
    n_signals = 0
    current = closes[-1]

    ma50 = _calc_sma(closes, 50)
    if ma50 is not None:
        n_signals += 1
        if current > ma50:
            score += 25
            proximity = min((current / ma50 - 1) * 100, 10)
            score += proximity
    
    ma200 = _calc_sma(closes, 200)
    if ma200 is not None:
        n_signals += 1
        if current > ma200:
            score += 25
            proximity = min((current / ma200 - 1) * 100, 10)
            score += proximity

    if ma50 is not None and ma200 is not None:
        n_signals += 1
        if ma50 > ma200:
            score += 20

    if n_signals == 0:
        return 50.0
    return min(score, 100.0)


def compute_momentum_score(closes: np.ndarray) -> float:
    components = []

    rsi = _calc_rsi(closes, 14)
    if rsi is not None:
        if 40 <= rsi <= 70:
            rsi_score = 60 + (rsi - 40) * (40.0 / 30.0)
        elif rsi > 70:
            rsi_score = max(100 - (rsi - 70) * 2, 50)
        elif rsi < 30:
            rsi_score = rsi
        else:
            rsi_score = 30 + (rsi - 30) * (30.0 / 10.0)
        components.append(rsi_score)

    macd_line, signal_line, histogram = _calc_macd(closes)
    if macd_line is not None:
        macd_score = 0.0
        if macd_line > signal_line:
            macd_score += 50
        if histogram is not None and histogram > 0:
            macd_score += 30
        if macd_line > 0:
            macd_score += 20
        components.append(macd_score)

    if not components:
        return 50.0
    return min(np.mean(components), 100.0)


def compute_breakout_volume_score(
    closes: np.ndarray,
    price_data: pd.DataFrame,
) -> float:
    components = []

    if len(closes) >= 20:
        high_20d = float(np.max(closes[-20:]))
        if high_20d > 0:
            proximity_20d = (closes[-1] / high_20d) * 100
            components.append(min(proximity_20d, 100.0))

    if len(closes) >= 252:
        high_52w = float(np.max(closes[-252:]))
    elif len(closes) >= 126:
        high_52w = float(np.max(closes))
    else:
        high_52w = None

    if high_52w is not None and high_52w > 0:
        proximity_52w = (closes[-1] / high_52w) * 100
        components.append(min(proximity_52w, 100.0))

    if (price_data is not None and "volume" in price_data.columns
            and len(price_data) >= 20):
        volumes = price_data["volume"].values.astype(float)
        avg_vol = np.mean(volumes[-20:])
        if avg_vol > 0 and np.isfinite(avg_vol):
            current_vol = volumes[-1]
            vol_ratio = current_vol / avg_vol
            vol_score = min(vol_ratio * 50, 100.0)
            components.append(vol_score)

    if not components:
        return 50.0
    return min(np.mean(components), 100.0)


def _calc_mfi(price_data: pd.DataFrame, period: int = 14) -> Optional[float]:
    if price_data is None or len(price_data) < period + 1:
        return None
    required = ["high", "low", "close", "volume"]
    if not all(c in price_data.columns for c in required):
        return None
    data = price_data.tail(period + 1).copy()
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
    mfi = 100.0 - (100.0 / (1.0 + money_ratio))
    return round(mfi, 2)


def _calc_obv(price_data: pd.DataFrame) -> Optional[np.ndarray]:
    if price_data is None or len(price_data) < 5:
        return None
    if "close" not in price_data.columns or "volume" not in price_data.columns:
        return None
    close = price_data["close"].values.astype(float)
    volume = price_data["volume"].values.astype(float)
    obv = np.zeros(len(close))
    obv[0] = volume[0]
    for i in range(1, len(close)):
        if close[i] > close[i - 1]:
            obv[i] = obv[i - 1] + volume[i]
        elif close[i] < close[i - 1]:
            obv[i] = obv[i - 1] - volume[i]
        else:
            obv[i] = obv[i - 1]
    return obv


def _score_mfi(mfi: float) -> float:
    if 55 <= mfi <= 75:
        return 85 + (mfi - 55) * (15.0 / 20.0)
    elif 50 <= mfi < 55:
        return 60 + (mfi - 50) * (25.0 / 5.0)
    elif 45 <= mfi < 50:
        return 40 + (mfi - 45) * (20.0 / 5.0)
    elif mfi > 80:
        return max(50 - (mfi - 80) * 3, 10)
    elif mfi > 75:
        return max(85 - (mfi - 75) * 7, 50)
    elif mfi < 30:
        return max(mfi, 5)
    elif mfi < 45:
        return 20 + (mfi - 30) * (20.0 / 15.0)
    return 50.0


def _score_obv(obv: np.ndarray, closes: np.ndarray) -> tuple:
    lookback = min(20, len(obv) - 1)
    if lookback < 5:
        return 50.0, 0.0

    obv_recent = obv[-lookback:]
    closes_recent = closes[-lookback:]

    obv_slope = (obv_recent[-1] - obv_recent[0])
    obv_mean = np.mean(np.abs(obv_recent))
    if obv_mean > 0:
        obv_trend_pct = obv_slope / obv_mean
    else:
        obv_trend_pct = 0.0

    price_change_pct = 0.0
    if closes_recent[0] > 0:
        price_change_pct = (closes_recent[-1] - closes_recent[0]) / closes_recent[0]

    obv_score = 50.0
    if obv_trend_pct > 0.1:
        obv_score = 70 + min(obv_trend_pct * 100, 30)
    elif obv_trend_pct > 0:
        obv_score = 50 + obv_trend_pct * 200
    elif obv_trend_pct < -0.1:
        obv_score = max(30 - abs(obv_trend_pct) * 100, 5)
    else:
        obv_score = 50 + obv_trend_pct * 200

    divergence_bonus = 0.0

    if price_change_pct > 0.02 and obv_trend_pct < -0.05:
        divergence_bonus = -15.0

    if abs(price_change_pct) < 0.02 and obv_trend_pct > 0.1:
        divergence_bonus = 10.0

    return min(max(obv_score, 0.0), 100.0), divergence_bonus


def compute_volume_flow_score(
    closes: np.ndarray,
    price_data: pd.DataFrame,
) -> tuple:
    components = []
    divergence_bonus = 0.0

    mfi = _calc_mfi(price_data)
    if mfi is not None:
        components.append(_score_mfi(mfi))

    obv = _calc_obv(price_data)
    if obv is not None and len(closes) >= 5:
        obv_s, div_b = _score_obv(obv, closes)
        components.append(obv_s)
        divergence_bonus = div_b

    if not components:
        return 50.0, 0.0

    base_score = min(np.mean(components), 100.0)
    return max(min(base_score, 100.0), 0.0), divergence_bonus


def compute_risk_stability_score(
    closes: np.ndarray,
    price_data: pd.DataFrame,
) -> float:
    atr = _calc_atr(price_data)
    if atr is None or closes[-1] <= 0:
        return 50.0

    atr_pct = (atr / closes[-1]) * 100

    if atr_pct <= 1.0:
        score = 100.0
    elif atr_pct <= 2.0:
        score = 90.0
    elif atr_pct <= 3.0:
        score = 75.0
    elif atr_pct <= 5.0:
        score = 60.0
    elif atr_pct <= 8.0:
        score = 40.0
    else:
        score = max(20.0 - (atr_pct - 8.0) * 2, 0.0)

    return score


def compute_technical_score_for_row(price_data) -> float:
    closes = _get_closes(price_data)
    if closes is None:
        return np.nan

    trend = compute_trend_score(closes)
    momentum = compute_momentum_score(closes)
    breakout = compute_breakout_volume_score(closes, price_data)
    volume_flow, divergence_bonus = compute_volume_flow_score(closes, price_data)
    risk = compute_risk_stability_score(closes, price_data)

    raw = (
        trend * TREND_WEIGHT
        + momentum * MOMENTUM_WEIGHT
        + breakout * BREAKOUT_WEIGHT
        + volume_flow * VOLUME_FLOW_WEIGHT
        + risk * RISK_WEIGHT
        + divergence_bonus
    )
    return round(min(max(raw, 0.0), 100.0), 2)


def assign_setup_label(rs_score: float, tech_score: float) -> str:
    rs = _safe_float(rs_score)
    tech = _safe_float(tech_score)
    if np.isnan(rs) or np.isnan(tech):
        return "N/A"
    if rs >= 75 and tech >= 70:
        return SETUP_LABELS["strong_buy"]
    if rs >= 70 and 50 <= tech < 70:
        return SETUP_LABELS["watchlist"]
    if rs >= 70 and tech < 50:
        return SETUP_LABELS["early_setup"]
    return SETUP_LABELS["avoid"]


def append_technical_scores(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()

    tech_scores = []
    for _, row in result.iterrows():
        price_data = row.get("price_data")
        tech_scores.append(compute_technical_score_for_row(price_data))

    result["technical_score"] = tech_scores

    rs_scores = result["rs_score"].values if "rs_score" in result.columns else np.full(len(result), np.nan)
    tech_arr = np.array(tech_scores)

    combined = np.where(
        np.isnan(rs_scores) | np.isnan(tech_arr),
        np.where(np.isnan(rs_scores), tech_arr, rs_scores),
        rs_scores * COMBINED_WEIGHT_RS + tech_arr * COMBINED_WEIGHT_TECH,
    )
    result["combined_score"] = np.round(combined, 2)

    result["setup_label"] = [
        assign_setup_label(rs, tech)
        for rs, tech in zip(rs_scores, tech_arr)
    ]

    return result
