import streamlit as st
import pandas as pd
import numpy as np
from config import (
    SUPPORTED_MARKETS, DEFAULT_TOP_N,
    TWELVE_DATA_API_KEY, BENCHMARK_INDEX,
)
from data_model import validate_dataframe
from data_fetcher import fetch_market_data
from scoring_engine import compute_rs_scores, get_score_breakdown
from filters import (
    apply_preset_filter, rank_and_limit,
    get_preset_names, get_preset_info,
)
from utils import format_number, format_percentage

st.set_page_config(
    page_title="Stock Screener",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _fmt_rule(rule_key: str, threshold: float) -> str:
    _pct_keys = {"roic_gt", "revenue_growth_gt", "net_margin_gt", "return_12m_gt"}
    labels = {
        "equity_gt": "Equity > {:.0f}",
        "net_income_gt": "Net Income > {:.0f}",
        "roic_gt": "ROIC > {:.0f}%",
        "revenue_growth_gt": "Rev Growth > {:.0f}%",
        "net_margin_gt": "Net Margin > {:.0f}%",
        "debt_to_equity_lt": "D/E < {:.1f}",
        "peg_gt": "PEG > {:.0f}",
        "pe_gt": "P/E > {:.0f}",
        "return_12m_gt": "12M Return > {:.0f}%",
        "avg_volume_20d_gte": "Avg Vol >= {:.0f}",
    }
    if rule_key in labels:
        fmt = labels[rule_key]
        val = threshold * 100 if rule_key in _pct_keys else threshold
        return fmt.format(val)
    return f"{rule_key}: {threshold}"


def _render_detail(stock_row: pd.Series) -> None:
    bd = get_score_breakdown(stock_row)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("RS Score", f"{bd['rs_score']:.1f}" if bd["rs_score"] is not None else "N/A")
    c2.metric("Financial", f"{bd['financial_strength']:.1f}" if bd["financial_strength"] is not None else "N/A")
    c3.metric("Growth", f"{bd['growth']:.1f}" if bd["growth"] is not None else "N/A")
    c4.metric("Margins", f"{bd['margin_quality']:.1f}" if bd["margin_quality"] is not None else "N/A")
    c5.metric("Valuation", f"{bd['valuation']:.1f}" if bd["valuation"] is not None else "N/A")
    c6.metric("Momentum", f"{bd['momentum']:.1f}" if bd["momentum"] is not None else "N/A")

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown("**Margins**")
        st.text(f"Gross:      {format_percentage(bd.get('gross_margin'))}")
        st.text(f"Operating:  {format_percentage(bd.get('operating_margin'))}")
        st.text(f"Net:        {format_percentage(bd.get('net_margin'))}")
        st.text(f"EBITDA:     {format_percentage(bd.get('ebitda_margin'))}")
    with m2:
        st.markdown("**Returns on Capital**")
        st.text(f"ROE:   {format_percentage(bd.get('roe'))}")
        st.text(f"ROA:   {format_percentage(bd.get('roa'))}")
        st.text(f"ROIC:  {format_percentage(bd.get('roic'))}")
    with m3:
        st.markdown("**Growth**")
        st.text(f"Revenue YoY:  {format_percentage(bd.get('revenue_growth'))}")
        st.text(f"Earnings YoY: {format_percentage(bd.get('earnings_growth'))}")
        st.text(f"Rev CAGR 3Y:  {format_percentage(bd.get('revenue_cagr_3y'))}")
        st.text(f"EPS CAGR 3Y:  {format_percentage(bd.get('eps_cagr_3y'))}")
    with m4:
        st.markdown("**Valuation & Leverage**")
        st.text(f"P/E:        {format_number(stock_row.get('pe'))}")
        st.text(f"P/B:        {format_number(stock_row.get('pb'))}")
        st.text(f"EV/EBITDA:  {format_number(stock_row.get('ev_ebitda'))}")
        st.text(f"PEG:        {format_number(stock_row.get('peg'))}")
        de = bd.get("debt_to_equity")
        st.text(f"D/E:        {format_number(de) if de is not None else 'N/A'}")

    if "price_data" in stock_row and isinstance(stock_row["price_data"], pd.DataFrame):
        price_df = stock_row["price_data"]
        if not price_df.empty:
            chart_data = price_df.set_index("datetime")[["close"]].rename(columns={"close": "Close"})
            st.line_chart(chart_data, height=200)


with st.sidebar:
    st.header("Stock Screener")

    market = st.selectbox(
        "Market",
        options=list(SUPPORTED_MARKETS.keys()),
        format_func=lambda x: SUPPORTED_MARKETS[x]["label"],
    )

    benchmark = BENCHMARK_INDEX.get(market, "SPX")
    st.caption(f"Benchmark: {benchmark}")

    st.divider()

    preset_options = get_preset_names()
    preset_labels = {k: get_preset_info(k)["label"] for k in preset_options}
    selected_preset = st.radio(
        "Quality Filter",
        options=preset_options,
        format_func=lambda x: preset_labels[x],
        index=0,
    )
    preset_info = get_preset_info(selected_preset)
    st.caption(preset_info["description"])

    if selected_preset != "none" and preset_info["rules"]:
        with st.expander("Filter rules", expanded=False):
            for rule_key, threshold in preset_info["rules"].items():
                st.text(_fmt_rule(rule_key, threshold))

    st.divider()

    min_avg_volume = st.number_input(
        "Min Avg Volume (20d)",
        min_value=0,
        value=0,
        step=100000,
        help="Set to 0 to disable",
    )
    min_avg_volume = min_avg_volume if min_avg_volume > 0 else None

    top_n = st.number_input(
        "Results to Display",
        min_value=1,
        max_value=100,
        value=DEFAULT_TOP_N,
    )

    st.divider()
    api_status = "Live Data" if TWELVE_DATA_API_KEY else "Demo Data"
    st.caption(f"Data: {api_status}")

run_screening = st.button("Run Screening", type="primary", use_container_width=True)

if run_screening:
    market_info = SUPPORTED_MARKETS[market]

    with st.spinner(f"Fetching {market_info['label']} data..."):
        raw_data = fetch_market_data(market)

    validation = validate_dataframe(raw_data)
    if not validation["valid"]:
        st.warning(f"Data quality notice: missing columns {validation['missing_columns']}")

    with st.spinner("Scoring..."):
        scored_data = compute_rs_scores(raw_data)

    filtered_data = apply_preset_filter(
        scored_data, preset=selected_preset, min_avg_volume=min_avg_volume,
    )
    passed_count = len(filtered_data)
    filtered_data = rank_and_limit(filtered_data, top_n=top_n)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Stocks Scanned", len(scored_data))
    c2.metric("Passed Filter", passed_count)
    if not filtered_data.empty:
        c3.metric("Highest RS", f"{filtered_data['rs_score'].max():.1f}")
        c4.metric("Avg RS", f"{filtered_data['rs_score'].mean():.1f}")
    else:
        c3.metric("Highest RS", "—")
        c4.metric("Avg RS", "—")

    st.divider()

    if filtered_data.empty:
        st.warning("No stocks match the current filters. Try relaxing the quality preset or lowering the volume threshold.")
    else:
        display_cols = [
            "ticker", "sector", "price",
            "rs_score", "rs_category",
            "financial_strength", "growth", "margin_quality",
            "valuation", "momentum",
        ]
        display_df = filtered_data[[c for c in display_cols if c in filtered_data.columns]].copy()

        for col in ["rs_score", "financial_strength", "growth", "margin_quality", "valuation", "momentum"]:
            if col in display_df.columns:
                display_df[col] = display_df[col].apply(
                    lambda x: round(x, 1) if x is not None and np.isfinite(x) else None
                )
        if "price" in display_df.columns:
            display_df["price"] = display_df["price"].apply(
                lambda x: round(x, 2) if x is not None and np.isfinite(x) else None
            )

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "ticker": st.column_config.TextColumn("Ticker", width="small"),
                "sector": st.column_config.TextColumn("Sector"),
                "price": st.column_config.NumberColumn("Price", format="%.2f"),
                "rs_score": st.column_config.ProgressColumn(
                    "RS Score", min_value=0, max_value=100, format="%.1f",
                ),
                "rs_category": st.column_config.TextColumn("Category", width="small"),
                "financial_strength": st.column_config.ProgressColumn(
                    "Financial", min_value=0, max_value=100, format="%.1f",
                ),
                "growth": st.column_config.ProgressColumn(
                    "Growth", min_value=0, max_value=100, format="%.1f",
                ),
                "margin_quality": st.column_config.ProgressColumn(
                    "Margins", min_value=0, max_value=100, format="%.1f",
                ),
                "valuation": st.column_config.ProgressColumn(
                    "Valuation", min_value=0, max_value=100, format="%.1f",
                ),
                "momentum": st.column_config.ProgressColumn(
                    "Momentum", min_value=0, max_value=100, format="%.1f",
                ),
            },
        )

        csv_cols = [
            "rank", "ticker", "company_name", "sector", "price", "market_cap",
            "rs_score", "rs_category",
            "financial_strength", "growth", "margin_quality", "valuation", "momentum",
            "return_1m", "return_3m", "return_6m", "return_12m",
        ]
        csv_df = filtered_data[[c for c in csv_cols if c in filtered_data.columns]].copy()
        csv_data = csv_df.to_csv(index=False)

        st.download_button(
            label="Download CSV",
            data=csv_data,
            file_name=f"screener_{market}_{selected_preset}.csv",
            mime="text/csv",
        )

        st.divider()
        st.subheader("Stock Details")

        for _, row in filtered_data.iterrows():
            ticker = row.get("ticker", "?")
            name = row.get("company_name", "")
            cat = row.get("rs_category", "N/A")
            rs = row.get("rs_score", 0)
            label = f"{ticker}  —  {name}  |  RS {rs:.1f}  ({cat})"

            with st.expander(label, expanded=False):
                _render_detail(row)

else:
    st.markdown("### Stock Screener")
    st.markdown("Select a market and click **Run Screening** to rank stocks by RS Score.")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            """
**RS Score** ranks stocks 0–100 across five dimensions:

- **Financial Strength** — ROIC, leverage, asset quality
- **Growth** — Revenue & earnings growth (YoY + 3Y CAGR)
- **Margin Quality** — Gross, operating, net, EBITDA margins + trend
- **Valuation** — P/E, P/B, EV/EBITDA, PEG
- **Momentum** — Multi-period returns, 52W high, relative strength
            """
        )
    with col2:
        st.markdown("**Available Markets**")
        for key, info in SUPPORTED_MARKETS.items():
            bench = BENCHMARK_INDEX.get(key, "—")
            st.markdown(f"- **{info['label']}** — {len(info['symbols'])} stocks, benchmark: {bench}")

        st.markdown(
            """
**Quality Presets** pre-screen stocks before ranking:
- **No Filter** — full universe
- **Basic** — profitable, positive equity, reasonable leverage
- **Strict** — high ROIC, strong margins, positive momentum
            """
        )
