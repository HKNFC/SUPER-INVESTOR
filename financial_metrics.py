"""
Financial Metrics Engine

Individual metric functions for computing derived financial ratios, margins,
growth rates, and return metrics from raw fundamental data.

Each function:
  - Handles division by zero safely (returns NaN)
  - Handles missing values explicitly (returns NaN)
  - Handles negative denominators where mathematically inappropriate (returns NaN)
  - Returns float (or NaN when metric is not meaningful)

The `append_all_derived_metrics` function appends every derived metric
as new columns to the master DataFrame.
"""

import pandas as pd
import numpy as np
from typing import Optional
from data_model import safe_ratio, safe_float


# ---------------------------------------------------------------------------
# Balance Sheet Ratios
# ---------------------------------------------------------------------------

def calc_debt_to_equity(total_debt, equity) -> float:
    """
    Debt-to-Equity = total_debt / equity

    Measures financial leverage. A higher ratio means more debt-financed operations.

    Returns NaN when:
      - Either input is missing or non-finite
      - Equity is zero (undefined ratio)
      - Equity is negative (ratio loses meaning as a leverage indicator)
    """
    td = safe_float(total_debt)
    eq = safe_float(equity)
    if np.isnan(td) or np.isnan(eq):
        return np.nan
    if eq <= 0:
        return np.nan
    return td / eq


def calc_equity_to_assets(equity, total_assets) -> float:
    """
    Equity-to-Assets = equity / total_assets

    Measures the proportion of assets financed by shareholders' equity.
    Higher values indicate less reliance on debt.

    Returns NaN when:
      - Either input is missing or non-finite
      - Total assets is zero or negative (not meaningful)
    """
    eq = safe_float(equity)
    ta = safe_float(total_assets)
    if np.isnan(eq) or np.isnan(ta):
        return np.nan
    if ta <= 0:
        return np.nan
    return eq / ta


def calc_net_income_to_assets(net_income, total_assets) -> float:
    """
    Net Income to Assets = net_income / total_assets

    A simplified return-on-assets measure using net income directly.

    Returns NaN when:
      - Either input is missing or non-finite
      - Total assets is zero or negative
    """
    ni = safe_float(net_income)
    ta = safe_float(total_assets)
    if np.isnan(ni) or np.isnan(ta):
        return np.nan
    if ta <= 0:
        return np.nan
    return ni / ta


# ---------------------------------------------------------------------------
# Return Metrics
# ---------------------------------------------------------------------------

def calc_roe(net_income, equity) -> float:
    """
    Return on Equity = net_income / equity

    Measures how efficiently equity capital generates profit.

    Returns NaN when:
      - Either input is missing or non-finite
      - Equity is zero (undefined)
      - Equity is negative (ROE sign becomes misleading)
    """
    ni = safe_float(net_income)
    eq = safe_float(equity)
    if np.isnan(ni) or np.isnan(eq):
        return np.nan
    if eq <= 0:
        return np.nan
    return ni / eq


def calc_roa(net_income, total_assets) -> float:
    """
    Return on Assets = net_income / total_assets

    Measures how efficiently total assets generate profit.

    Returns NaN when:
      - Either input is missing or non-finite
      - Total assets is zero or negative
    """
    return calc_net_income_to_assets(net_income, total_assets)


def calc_roic(operating_income, invested_capital, tax_rate: float = 0.25) -> float:
    """
    Return on Invested Capital = NOPAT / invested_capital

    Where NOPAT = operating_income * (1 - tax_rate).
    Measures how well a company generates returns on capital deployed.

    Args:
        operating_income: Operating income (EBIT)
        invested_capital: Total invested capital (equity + debt - cash, or as reported)
        tax_rate: Assumed effective tax rate for NOPAT calculation (default 25%)

    Returns NaN when:
      - Either input is missing or non-finite
      - Invested capital is zero or negative
      - Operating income is missing (NOPAT cannot be computed)
    """
    oi = safe_float(operating_income)
    ic = safe_float(invested_capital)
    if np.isnan(oi) or np.isnan(ic):
        return np.nan
    if ic <= 0:
        return np.nan
    nopat = oi * (1 - tax_rate)
    return nopat / ic


# ---------------------------------------------------------------------------
# Margin Metrics
# ---------------------------------------------------------------------------

def calc_gross_margin(gross_profit, revenue) -> float:
    """
    Gross Margin = gross_profit / revenue

    Measures the percentage of revenue retained after cost of goods sold.

    Returns NaN when:
      - Either input is missing or non-finite
      - Revenue is zero (undefined)
      - Revenue is negative (not meaningful)
    """
    gp = safe_float(gross_profit)
    rev = safe_float(revenue)
    if np.isnan(gp) or np.isnan(rev):
        return np.nan
    if rev <= 0:
        return np.nan
    return gp / rev


def calc_operating_margin(operating_income, revenue) -> float:
    """
    Operating Margin = operating_income / revenue

    Measures operational efficiency after operating expenses.

    Returns NaN when:
      - Either input is missing or non-finite
      - Revenue is zero or negative
    """
    oi = safe_float(operating_income)
    rev = safe_float(revenue)
    if np.isnan(oi) or np.isnan(rev):
        return np.nan
    if rev <= 0:
        return np.nan
    return oi / rev


def calc_net_margin(net_income, revenue) -> float:
    """
    Net Margin = net_income / revenue

    Measures the percentage of revenue that becomes profit after all expenses.

    Returns NaN when:
      - Either input is missing or non-finite
      - Revenue is zero or negative
    """
    ni = safe_float(net_income)
    rev = safe_float(revenue)
    if np.isnan(ni) or np.isnan(rev):
        return np.nan
    if rev <= 0:
        return np.nan
    return ni / rev


def calc_ebitda_margin(ebitda, revenue) -> float:
    """
    EBITDA Margin = ebitda / revenue

    Measures operating profitability before depreciation, amortization, interest, and taxes.

    Returns NaN when:
      - Either input is missing or non-finite
      - Revenue is zero or negative
    """
    eb = safe_float(ebitda)
    rev = safe_float(revenue)
    if np.isnan(eb) or np.isnan(rev):
        return np.nan
    if rev <= 0:
        return np.nan
    return eb / rev


# ---------------------------------------------------------------------------
# Growth Metrics
# ---------------------------------------------------------------------------

def calc_yoy_growth(current, previous) -> float:
    """
    Year-over-Year Growth = (current - previous) / abs(previous)

    Computes percentage change from previous period to current.
    Uses abs(previous) so that growth from a negative base is directionally correct.

    Returns NaN when:
      - Either input is missing or non-finite
      - Previous value is zero (growth from zero is undefined)
    """
    c = safe_float(current)
    p = safe_float(previous)
    if np.isnan(c) or np.isnan(p):
        return np.nan
    if p == 0:
        return np.nan
    return (c - p) / abs(p)


def calc_revenue_growth_yoy(revenue, revenue_prev_year) -> float:
    """
    Revenue Growth YoY = (revenue - revenue_prev_year) / abs(revenue_prev_year)

    Returns NaN if either value is missing/zero.
    """
    return calc_yoy_growth(revenue, revenue_prev_year)


def calc_net_income_growth_yoy(net_income, net_income_prev_year) -> float:
    """
    Net Income Growth YoY = (net_income - net_income_prev_year) / abs(net_income_prev_year)

    Returns NaN if either value is missing/zero.
    """
    return calc_yoy_growth(net_income, net_income_prev_year)


def calc_cagr(ending_value, beginning_value, years: float = 3.0) -> float:
    """
    Compound Annual Growth Rate = (ending / beginning)^(1/years) - 1

    Computes the annualized growth rate over the specified number of years.

    Returns NaN when:
      - Either input is missing or non-finite
      - Beginning value is zero (division by zero)
      - The ratio ending/beginning is negative (cannot take fractional root of negative)
      - Years is zero or negative
    """
    end = safe_float(ending_value)
    beg = safe_float(beginning_value)
    if np.isnan(end) or np.isnan(beg):
        return np.nan
    if beg == 0 or years <= 0:
        return np.nan

    ratio = end / beg

    # CAGR is undefined for negative ratios (e.g., profit turned to loss)
    # because we cannot raise a negative number to a fractional power
    if ratio <= 0:
        return np.nan

    return ratio ** (1.0 / years) - 1.0


def calc_revenue_cagr_3y(revenue, revenue_3y_ago) -> float:
    """
    Revenue 3-Year CAGR = (revenue / revenue_3y_ago)^(1/3) - 1

    Annualized revenue growth rate over a 3-year period.

    Returns NaN when:
      - Either value is missing or zero
      - The ratio is negative (e.g., revenue turned negative)
    """
    return calc_cagr(revenue, revenue_3y_ago, years=3.0)


def calc_eps_cagr_3y(eps, eps_3y_ago) -> float:
    """
    EPS 3-Year CAGR = (eps / eps_3y_ago)^(1/3) - 1

    Annualized earnings-per-share growth rate over a 3-year period.

    Returns NaN when:
      - Either value is missing or zero
      - The ratio is negative (e.g., EPS went from positive to negative)
    """
    return calc_cagr(eps, eps_3y_ago, years=3.0)


# ---------------------------------------------------------------------------
# Master DataFrame Enrichment
# ---------------------------------------------------------------------------

DERIVED_METRIC_COLUMNS = [
    "debt_to_equity",
    "equity_to_assets",
    "net_income_to_assets",
    "roe",
    "roa",
    "roic",
    "gross_margin",
    "operating_margin",
    "net_margin",
    "ebitda_margin",
    "revenue_growth",
    "earnings_growth",
    "revenue_cagr_3y",
    "eps_cagr_3y",
]


def append_all_derived_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Append all derived financial metrics as new columns to the master DataFrame.

    Computes each metric row-by-row from the raw fundamental columns.
    Existing derived columns are overwritten with freshly computed values.

    Input columns used:
      total_debt, equity, total_assets, net_income, net_income_prev_year,
      operating_income, invested_capital, gross_profit, revenue,
      revenue_prev_year, revenue_3y_ago, ebitda, eps, eps_3y_ago

    Output columns added:
      debt_to_equity, equity_to_assets, net_income_to_assets,
      roe, roa, roic,
      gross_margin, operating_margin, net_margin, ebitda_margin,
      revenue_growth, earnings_growth, revenue_cagr_3y, eps_cagr_3y
    """
    result = df.copy()

    # Balance sheet ratios
    result["debt_to_equity"] = result.apply(
        lambda r: calc_debt_to_equity(r.get("total_debt"), r.get("equity")),
        axis=1,
    )
    result["equity_to_assets"] = result.apply(
        lambda r: calc_equity_to_assets(r.get("equity"), r.get("total_assets")),
        axis=1,
    )
    result["net_income_to_assets"] = result.apply(
        lambda r: calc_net_income_to_assets(r.get("net_income"), r.get("total_assets")),
        axis=1,
    )

    # Return metrics
    result["roe"] = result.apply(
        lambda r: calc_roe(r.get("net_income"), r.get("equity")),
        axis=1,
    )
    result["roa"] = result.apply(
        lambda r: calc_roa(r.get("net_income"), r.get("total_assets")),
        axis=1,
    )
    result["roic"] = result.apply(
        lambda r: calc_roic(r.get("operating_income"), r.get("invested_capital")),
        axis=1,
    )

    # Margin metrics
    result["gross_margin"] = result.apply(
        lambda r: calc_gross_margin(r.get("gross_profit"), r.get("revenue")),
        axis=1,
    )
    result["operating_margin"] = result.apply(
        lambda r: calc_operating_margin(r.get("operating_income"), r.get("revenue")),
        axis=1,
    )
    result["net_margin"] = result.apply(
        lambda r: calc_net_margin(r.get("net_income"), r.get("revenue")),
        axis=1,
    )
    result["ebitda_margin"] = result.apply(
        lambda r: calc_ebitda_margin(r.get("ebitda"), r.get("revenue")),
        axis=1,
    )

    # Growth metrics
    result["revenue_growth"] = result.apply(
        lambda r: calc_revenue_growth_yoy(r.get("revenue"), r.get("revenue_prev_year")),
        axis=1,
    )
    result["earnings_growth"] = result.apply(
        lambda r: calc_net_income_growth_yoy(r.get("net_income"), r.get("net_income_prev_year")),
        axis=1,
    )
    result["revenue_cagr_3y"] = result.apply(
        lambda r: calc_revenue_cagr_3y(r.get("revenue"), r.get("revenue_3y_ago")),
        axis=1,
    )
    result["eps_cagr_3y"] = result.apply(
        lambda r: calc_eps_cagr_3y(r.get("eps"), r.get("eps_3y_ago")),
        axis=1,
    )

    return result


# ---------------------------------------------------------------------------
# Sub-Score Functions (used by scoring_engine.py)
# ---------------------------------------------------------------------------

def calculate_financial_strength(row: pd.Series) -> Optional[float]:
    """
    Calculate a financial strength score (0-100) based on:
      - Debt-to-equity ratio (lower is better, capped at 3.0)
      - ROE (higher is better, capped at 30%)
      - ROA (higher is better, capped at 15%)
      - Cash coverage: cash / total_debt (higher is better, capped at 1.0)

    Returns None if no sub-metric could be computed.
    """
    scores = []

    de = calc_debt_to_equity(row.get("total_debt"), row.get("equity"))
    if np.isfinite(de):
        # D/E of 0 scores 100, D/E of 3+ scores 0
        de_score = max(0, (1 - de / 3.0)) * 100
        scores.append(de_score)

    roe = calc_roe(row.get("net_income"), row.get("equity"))
    if np.isfinite(roe):
        # ROE of 30%+ scores 100, negative ROE scores 0
        roe_score = min(max(roe, 0) / 0.30, 1.0) * 100
        scores.append(roe_score)

    roa = calc_roa(row.get("net_income"), row.get("total_assets"))
    if np.isfinite(roa):
        # ROA of 15%+ scores 100, negative ROA scores 0
        roa_score = min(max(roa, 0) / 0.15, 1.0) * 100
        scores.append(roa_score)

    cash_coverage = safe_ratio(row.get("cash"), row.get("total_debt"))
    if np.isfinite(cash_coverage):
        # Cash coverage of 1.0+ scores 100
        cc_score = min(max(cash_coverage, 0) / 1.0, 1.0) * 100
        scores.append(cc_score)

    if not scores:
        return None

    return round(np.mean(scores), 2)


def calculate_growth_score(row: pd.Series) -> Optional[float]:
    """
    Calculate a growth score (0-100) based on:
      - Revenue growth YoY (shifted +10% so flat growth still scores some)
      - Net income growth YoY (shifted +10%)
      - Revenue 3Y CAGR (shifted +5%, capped at 30%)
      - EPS 3Y CAGR (shifted +10%, capped at 100%)

    Returns None if no sub-metric could be computed.
    """
    scores = []

    rev_growth = calc_revenue_growth_yoy(row.get("revenue"), row.get("revenue_prev_year"))
    if np.isfinite(rev_growth):
        # -10% growth scores 0, +40% growth scores 100
        rev_score = min(max(rev_growth + 0.10, 0) / 0.50, 1.0) * 100
        scores.append(rev_score)

    earn_growth = calc_net_income_growth_yoy(row.get("net_income"), row.get("net_income_prev_year"))
    if np.isfinite(earn_growth):
        # -10% growth scores 0, +50% growth scores 100
        earn_score = min(max(earn_growth + 0.10, 0) / 0.60, 1.0) * 100
        scores.append(earn_score)

    rev_cagr = calc_revenue_cagr_3y(row.get("revenue"), row.get("revenue_3y_ago"))
    if np.isfinite(rev_cagr):
        # -5% CAGR scores 0, +25% CAGR scores 100
        rev3_score = min(max(rev_cagr + 0.05, 0) / 0.30, 1.0) * 100
        scores.append(rev3_score)

    eps_cagr = calc_eps_cagr_3y(row.get("eps"), row.get("eps_3y_ago"))
    if np.isfinite(eps_cagr):
        # -10% CAGR scores 0, +90% CAGR scores 100
        eps3_score = min(max(eps_cagr + 0.10, 0) / 1.00, 1.0) * 100
        scores.append(eps3_score)

    if not scores:
        return None

    return round(np.mean(scores), 2)


def calculate_margin_quality(row: pd.Series) -> Optional[float]:
    """
    Calculate a margin quality score (0-100) based on:
      - Gross margin (higher is better, capped at 60%)
      - Operating margin (higher is better, capped at 30%)
      - Net margin (higher is better, capped at 25%)
      - EBITDA margin (higher is better, capped at 40%)

    Returns None if no sub-metric could be computed.
    """
    scores = []

    gm = calc_gross_margin(row.get("gross_profit"), row.get("revenue"))
    if np.isfinite(gm):
        # 60%+ gross margin scores 100, negative scores 0
        gm_score = min(max(gm, 0) / 0.60, 1.0) * 100
        scores.append(gm_score)

    om = calc_operating_margin(row.get("operating_income"), row.get("revenue"))
    if np.isfinite(om):
        # 30%+ operating margin scores 100
        om_score = min(max(om, 0) / 0.30, 1.0) * 100
        scores.append(om_score)

    nm = calc_net_margin(row.get("net_income"), row.get("revenue"))
    if np.isfinite(nm):
        # 25%+ net margin scores 100
        nm_score = min(max(nm, 0) / 0.25, 1.0) * 100
        scores.append(nm_score)

    em = calc_ebitda_margin(row.get("ebitda"), row.get("revenue"))
    if np.isfinite(em):
        # 40%+ EBITDA margin scores 100
        em_score = min(max(em, 0) / 0.40, 1.0) * 100
        scores.append(em_score)

    if not scores:
        return None

    return round(np.mean(scores), 2)


def calculate_valuation_score(row: pd.Series) -> Optional[float]:
    """
    Calculate a valuation score (0-100) based on:
      - P/E ratio (lower is better, 50+ scores 0)
      - P/B ratio (lower is better, 10+ scores 0)
      - EV/EBITDA (lower is better, 25+ scores 0)
      - PEG ratio (closer to 1.0 is ideal)

    Only positive multiples are scored (negative P/E means losses).
    Returns None if no sub-metric could be computed.
    """
    scores = []

    pe = safe_float(row.get("pe"))
    if np.isfinite(pe) and pe > 0:
        # P/E of 0 scores 100, P/E of 50+ scores 0
        pe_score = max(0, (1 - pe / 50)) * 100
        scores.append(pe_score)

    pb = safe_float(row.get("pb"))
    if np.isfinite(pb) and pb > 0:
        # P/B of 0 scores 100, P/B of 10+ scores 0
        pb_score = max(0, (1 - pb / 10)) * 100
        scores.append(pb_score)

    ev = safe_float(row.get("ev_ebitda"))
    if np.isfinite(ev) and ev > 0:
        # EV/EBITDA of 0 scores 100, 25+ scores 0
        ev_score = max(0, (1 - ev / 25)) * 100
        scores.append(ev_score)

    peg = safe_float(row.get("peg"))
    if np.isfinite(peg) and peg > 0:
        # PEG of 1.0 scores 100, deviation of 3+ from 1.0 scores 0
        peg_score = max(0, (1 - abs(peg - 1.0) / 3.0)) * 100
        scores.append(peg_score)

    if not scores:
        return None

    return round(np.mean(scores), 2)
