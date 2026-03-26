import pandas as pd
import numpy as np
from typing import Optional


def calculate_financial_strength(row: pd.Series) -> Optional[float]:
    """
    Calculate a financial strength score (0-100) based on:
    - Current ratio (higher is better, up to ~2.5)
    - Debt-to-equity ratio (lower is better)
    - Return on equity (higher is better)
    """
    scores = []

    cr = row.get("current_ratio")
    if cr is not None and np.isfinite(cr):
        cr_score = min(cr / 2.5, 1.0) * 100
        scores.append(cr_score)

    de = row.get("debt_to_equity")
    if de is not None and np.isfinite(de):
        de_score = max(0, (1 - de / 3.0)) * 100
        scores.append(de_score)

    roe = row.get("return_on_equity")
    if roe is not None and np.isfinite(roe):
        roe_score = min(max(roe, 0) / 0.30, 1.0) * 100
        scores.append(roe_score)

    if not scores:
        return None

    return round(np.mean(scores), 2)


def calculate_growth_score(row: pd.Series) -> Optional[float]:
    """
    Calculate a growth score (0-100) based on:
    - Revenue growth (YoY)
    - Earnings growth (YoY)
    """
    scores = []

    rev_g = row.get("revenue_growth")
    if rev_g is not None and np.isfinite(rev_g):
        rev_score = min(max(rev_g + 0.10, 0) / 0.50, 1.0) * 100
        scores.append(rev_score)

    earn_g = row.get("earnings_growth")
    if earn_g is not None and np.isfinite(earn_g):
        earn_score = min(max(earn_g + 0.10, 0) / 0.60, 1.0) * 100
        scores.append(earn_score)

    if not scores:
        return None

    return round(np.mean(scores), 2)


def calculate_margin_quality(row: pd.Series) -> Optional[float]:
    """
    Calculate a margin quality score (0-100) based on:
    - Gross margin
    - Operating margin
    - Net margin
    """
    scores = []

    gm = row.get("gross_margin")
    if gm is not None and np.isfinite(gm):
        gm_score = min(max(gm, 0) / 0.60, 1.0) * 100
        scores.append(gm_score)

    om = row.get("operating_margin")
    if om is not None and np.isfinite(om):
        om_score = min(max(om, 0) / 0.30, 1.0) * 100
        scores.append(om_score)

    nm = row.get("net_margin")
    if nm is not None and np.isfinite(nm):
        nm_score = min(max(nm, 0) / 0.25, 1.0) * 100
        scores.append(nm_score)

    if not scores:
        return None

    return round(np.mean(scores), 2)


def calculate_valuation_score(row: pd.Series) -> Optional[float]:
    """
    Calculate a valuation score (0-100) based on:
    - P/E ratio (lower is better)
    - P/B ratio (lower is better)
    - EV/EBITDA (lower is better)

    Lower valuation multiples result in higher scores (value investing bias).
    """
    scores = []

    pe = row.get("pe_ratio")
    if pe is not None and np.isfinite(pe) and pe > 0:
        pe_score = max(0, (1 - pe / 50)) * 100
        scores.append(pe_score)

    pb = row.get("pb_ratio")
    if pb is not None and np.isfinite(pb) and pb > 0:
        pb_score = max(0, (1 - pb / 10)) * 100
        scores.append(pb_score)

    ev_ebitda = row.get("ev_to_ebitda")
    if ev_ebitda is not None and np.isfinite(ev_ebitda) and ev_ebitda > 0:
        ev_score = max(0, (1 - ev_ebitda / 25)) * 100
        scores.append(ev_score)

    if not scores:
        return None

    return round(np.mean(scores), 2)
