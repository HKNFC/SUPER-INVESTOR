import pandas as pd
import numpy as np
from typing import Optional
from data_model import safe_ratio


def calculate_financial_strength(row: pd.Series) -> Optional[float]:
    """
    Calculate a financial strength score (0-100) based on:
    - Debt-to-equity ratio (lower is better)
    - Return on equity (net_income / equity, higher is better)
    - Return on assets (net_income / total_assets, higher is better)
    - Cash coverage (cash / total_debt, higher is better)
    """
    scores = []

    de = safe_ratio(row.get("total_debt"), row.get("equity"))
    if np.isfinite(de) and de >= 0:
        de_score = max(0, (1 - de / 3.0)) * 100
        scores.append(de_score)

    roe = safe_ratio(row.get("net_income"), row.get("equity"))
    if np.isfinite(roe):
        roe_score = min(max(roe, 0) / 0.30, 1.0) * 100
        scores.append(roe_score)

    roa = safe_ratio(row.get("net_income"), row.get("total_assets"))
    if np.isfinite(roa):
        roa_score = min(max(roa, 0) / 0.15, 1.0) * 100
        scores.append(roa_score)

    cash_coverage = safe_ratio(row.get("cash"), row.get("total_debt"))
    if np.isfinite(cash_coverage):
        cc_score = min(cash_coverage / 1.0, 1.0) * 100
        scores.append(cc_score)

    if not scores:
        return None

    return round(np.mean(scores), 2)


def calculate_growth_score(row: pd.Series) -> Optional[float]:
    """
    Calculate a growth score (0-100) based on:
    - Revenue growth YoY (revenue vs revenue_prev_year)
    - Earnings growth YoY (net_income vs net_income_prev_year)
    - Revenue growth 3Y (revenue vs revenue_3y_ago)
    - EPS growth 3Y (eps vs eps_3y_ago)
    """
    scores = []

    rev_growth = _safe_growth(row.get("revenue"), row.get("revenue_prev_year"))
    if rev_growth is not None:
        rev_score = min(max(rev_growth + 0.10, 0) / 0.50, 1.0) * 100
        scores.append(rev_score)

    earn_growth = _safe_growth(row.get("net_income"), row.get("net_income_prev_year"))
    if earn_growth is not None:
        earn_score = min(max(earn_growth + 0.10, 0) / 0.60, 1.0) * 100
        scores.append(earn_score)

    rev_3y = _safe_growth(row.get("revenue"), row.get("revenue_3y_ago"))
    if rev_3y is not None:
        rev3_annualized = (1 + rev_3y) ** (1 / 3) - 1 if rev_3y > -1 else -1
        rev3_score = min(max(rev3_annualized + 0.05, 0) / 0.30, 1.0) * 100
        scores.append(rev3_score)

    eps_3y = _safe_growth(row.get("eps"), row.get("eps_3y_ago"))
    if eps_3y is not None:
        eps3_score = min(max(eps_3y + 0.10, 0) / 1.00, 1.0) * 100
        scores.append(eps3_score)

    if not scores:
        return None

    return round(np.mean(scores), 2)


def calculate_margin_quality(row: pd.Series) -> Optional[float]:
    """
    Calculate a margin quality score (0-100) based on:
    - Gross margin (gross_profit / revenue)
    - Operating margin (operating_income / revenue)
    - Net margin (net_income / revenue)
    - EBITDA margin (ebitda / revenue)
    """
    scores = []

    gm = safe_ratio(row.get("gross_profit"), row.get("revenue"))
    if np.isfinite(gm):
        gm_score = min(max(gm, 0) / 0.60, 1.0) * 100
        scores.append(gm_score)

    om = safe_ratio(row.get("operating_income"), row.get("revenue"))
    if np.isfinite(om):
        om_score = min(max(om, 0) / 0.30, 1.0) * 100
        scores.append(om_score)

    nm = safe_ratio(row.get("net_income"), row.get("revenue"))
    if np.isfinite(nm):
        nm_score = min(max(nm, 0) / 0.25, 1.0) * 100
        scores.append(nm_score)

    em = safe_ratio(row.get("ebitda"), row.get("revenue"))
    if np.isfinite(em):
        em_score = min(max(em, 0) / 0.40, 1.0) * 100
        scores.append(em_score)

    if not scores:
        return None

    return round(np.mean(scores), 2)


def calculate_valuation_score(row: pd.Series) -> Optional[float]:
    """
    Calculate a valuation score (0-100) based on:
    - P/E ratio (lower is better)
    - P/B ratio (lower is better)
    - EV/EBITDA (lower is better)
    - PEG ratio (lower is better, near 1.0 is ideal)

    Lower valuation multiples result in higher scores (value investing bias).
    """
    scores = []

    pe = row.get("pe")
    if pe is not None and np.isfinite(pe) and pe > 0:
        pe_score = max(0, (1 - pe / 50)) * 100
        scores.append(pe_score)

    pb = row.get("pb")
    if pb is not None and np.isfinite(pb) and pb > 0:
        pb_score = max(0, (1 - pb / 10)) * 100
        scores.append(pb_score)

    ev = row.get("ev_ebitda")
    if ev is not None and np.isfinite(ev) and ev > 0:
        ev_score = max(0, (1 - ev / 25)) * 100
        scores.append(ev_score)

    peg = row.get("peg")
    if peg is not None and np.isfinite(peg) and peg > 0:
        peg_score = max(0, (1 - abs(peg - 1.0) / 3.0)) * 100
        scores.append(peg_score)

    if not scores:
        return None

    return round(np.mean(scores), 2)


def _safe_growth(current, previous) -> Optional[float]:
    """Calculate growth rate safely, returning None if invalid."""
    try:
        if current is None or previous is None:
            return None
        c = float(current)
        p = float(previous)
        if p == 0 or not np.isfinite(c) or not np.isfinite(p):
            return None
        return (c - p) / abs(p)
    except (ValueError, TypeError):
        return None
