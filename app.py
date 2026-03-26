import streamlit as st
import pandas as pd
import numpy as np
from config import SUPPORTED_MARKETS, SCORING_WEIGHTS, DEFAULT_TOP_N, TWELVE_DATA_API_KEY
from data_model import validate_dataframe
from data_fetcher import fetch_market_data
from scoring_engine import compute_rs_scores, get_score_breakdown
from filters import filter_by_score, filter_by_category_score, filter_by_fundamentals, filter_by_sector
from utils import (
    prepare_display_dataframe, format_market_cap, format_number,
    format_percentage, format_pct_value, format_large_number, score_color,
)

st.set_page_config(
    page_title="Stock Screener - RS Score",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Stock Screener")
st.caption("Rank stocks using a custom RS Score across multiple dimensions")

with st.sidebar:
    st.header("Settings")

    market = st.selectbox(
        "Select Market",
        options=list(SUPPORTED_MARKETS.keys()),
        format_func=lambda x: SUPPORTED_MARKETS[x]["label"],
    )

    st.divider()
    st.subheader("Filters")

    min_rs_score = st.slider(
        "Minimum RS Score",
        min_value=0,
        max_value=100,
        value=0,
        step=5,
    )

    top_n = st.number_input(
        "Show Top N Stocks",
        min_value=1,
        max_value=50,
        value=DEFAULT_TOP_N,
    )

    st.divider()
    st.subheader("Category Filters")
    category_filter = st.selectbox(
        "Filter by Category",
        options=["None"] + list(SCORING_WEIGHTS.keys()),
        format_func=lambda x: x.replace("_", " ").title(),
    )

    category_min = 50
    if category_filter != "None":
        category_min = st.slider(
            f"Min {category_filter.replace('_', ' ').title()} Score",
            min_value=0,
            max_value=100,
            value=50,
            step=5,
        )

    st.divider()
    st.subheader("Fundamental Filters")

    max_pe = st.number_input("Max P/E Ratio", min_value=0.0, value=0.0, step=5.0,
                             help="Set to 0 to disable")
    max_pe = max_pe if max_pe > 0 else None

    min_market_cap_input = st.selectbox(
        "Min Market Cap",
        options=["Any", "$1B+", "$10B+", "$100B+", "$1T+"],
    )
    min_market_cap_map = {"Any": None, "$1B+": 1e9, "$10B+": 10e9, "$100B+": 100e9, "$1T+": 1e12}
    min_market_cap = min_market_cap_map[min_market_cap_input]

    st.divider()
    st.subheader("Scoring Weights")
    st.caption("Current weights used for RS Score calculation")
    for cat, weight in SCORING_WEIGHTS.items():
        st.text(f"{cat.replace('_', ' ').title()}: {weight:.0%}")

    st.divider()
    api_status = "Connected" if TWELVE_DATA_API_KEY else "Not configured (using demo data)"
    st.caption(f"API Status: {api_status}")

run_screening = st.button("Run Screening", type="primary", use_container_width=True)

if run_screening:
    market_info = SUPPORTED_MARKETS[market]

    with st.spinner(f"Fetching data for {market_info['label']}..."):
        raw_data = fetch_market_data(market)

    validation = validate_dataframe(raw_data)
    if not validation["valid"]:
        st.warning(f"Data validation: missing columns {validation['missing_columns']}")

    with st.spinner("Computing RS Scores..."):
        scored_data = compute_rs_scores(raw_data)

    filtered_data = filter_by_score(scored_data, min_rs_score=min_rs_score, top_n=None)

    if category_filter != "None":
        filtered_data = filter_by_category_score(
            filtered_data,
            category=category_filter,
            min_score=category_min,
        )

    filtered_data = filter_by_fundamentals(
        filtered_data,
        max_pe=max_pe,
        min_market_cap=min_market_cap,
    )

    if top_n and top_n > 0:
        filtered_data = filtered_data.head(top_n).reset_index(drop=True)

    st.header(f"Results: {market_info['label']}")
    st.caption(f"{market_info['exchange']} | Currency: {market_info['currency']}")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Stocks Screened", len(scored_data))
    with col2:
        st.metric("Showing", len(filtered_data))
    with col3:
        if not filtered_data.empty:
            st.metric("Top RS Score", f"{filtered_data['rs_score'].max():.1f}")
    with col4:
        if not filtered_data.empty:
            st.metric("Avg RS Score", f"{filtered_data['rs_score'].mean():.1f}")

    st.divider()

    if filtered_data.empty:
        st.warning("No stocks match the current filter criteria. Try adjusting the filters.")
    else:
        display_df = prepare_display_dataframe(filtered_data)
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "rank": st.column_config.NumberColumn("Rank", width="small"),
                "ticker": st.column_config.TextColumn("Ticker", width="small"),
                "company_name": st.column_config.TextColumn("Company"),
                "sector": st.column_config.TextColumn("Sector"),
                "price": st.column_config.NumberColumn("Price", format="%.2f"),
                "market_cap": st.column_config.NumberColumn("Mkt Cap", format="%.0f"),
                "rs_score": st.column_config.ProgressColumn(
                    "RS Score", min_value=0, max_value=100, format="%.1f",
                ),
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
                "return_1m": st.column_config.NumberColumn("1M Ret%", format="%.1f%%"),
                "return_3m": st.column_config.NumberColumn("3M Ret%", format="%.1f%%"),
                "return_6m": st.column_config.NumberColumn("6M Ret%", format="%.1f%%"),
                "return_12m": st.column_config.NumberColumn("12M Ret%", format="%.1f%%"),
            },
        )

        st.divider()

        tab_details, tab_fundamentals = st.tabs(["Score Details", "Fundamentals"])

        with tab_details:
            selected_symbol = st.selectbox(
                "Select a stock for detailed breakdown",
                options=filtered_data["ticker"].tolist(),
                key="detail_select",
            )

            if selected_symbol:
                stock_row = filtered_data[filtered_data["ticker"] == selected_symbol].iloc[0]
                breakdown = get_score_breakdown(stock_row)

                st.subheader(f"{breakdown['ticker']} — {breakdown['company_name']}")

                score_cols = st.columns(6)
                labels = ["RS Score", "Financial Strength", "Growth", "Margin Quality", "Valuation", "Momentum"]
                keys = ["rs_score", "financial_strength", "growth", "margin_quality", "valuation", "momentum"]

                for col, label, key in zip(score_cols, labels, keys):
                    with col:
                        val = breakdown[key]
                        st.metric(label, f"{val:.1f}" if val is not None else "N/A")

                st.divider()

                metric_cols = st.columns(4)
                with metric_cols[0]:
                    st.markdown("**Margins**")
                    gm = breakdown.get("gross_margin")
                    om = breakdown.get("operating_margin")
                    nm = breakdown.get("net_margin")
                    st.text(f"Gross:      {format_percentage(gm)}")
                    st.text(f"Operating:  {format_percentage(om)}")
                    st.text(f"Net:        {format_percentage(nm)}")

                with metric_cols[1]:
                    st.markdown("**Returns on Capital**")
                    roe = breakdown.get("roe")
                    roa = breakdown.get("roa")
                    st.text(f"ROE:  {format_percentage(roe)}")
                    st.text(f"ROA:  {format_percentage(roa)}")

                with metric_cols[2]:
                    st.markdown("**Growth**")
                    rg = breakdown.get("revenue_growth")
                    eg = breakdown.get("earnings_growth")
                    st.text(f"Revenue:   {format_percentage(rg)}")
                    st.text(f"Earnings:  {format_percentage(eg)}")

                with metric_cols[3]:
                    st.markdown("**Leverage**")
                    de = breakdown.get("debt_to_equity")
                    st.text(f"D/E Ratio:  {format_number(de) if de is not None else 'N/A'}")

                if "price_data" in stock_row and isinstance(stock_row["price_data"], pd.DataFrame):
                    price_df = stock_row["price_data"]
                    if not price_df.empty:
                        st.subheader(f"Price Chart: {selected_symbol}")
                        chart_data = price_df.set_index("datetime")[["close"]].rename(
                            columns={"close": "Close Price"}
                        )
                        st.line_chart(chart_data)

        with tab_fundamentals:
            fund_symbol = st.selectbox(
                "Select a stock",
                options=filtered_data["ticker"].tolist(),
                key="fund_select",
            )

            if fund_symbol:
                stock = filtered_data[filtered_data["ticker"] == fund_symbol].iloc[0]

                st.subheader(f"{stock.get('ticker')} — {stock.get('company_name', 'N/A')}")
                st.caption(f"{stock.get('sector', 'N/A')} | {stock.get('industry', 'N/A')}")

                fc1, fc2, fc3 = st.columns(3)

                with fc1:
                    st.markdown("**Income Statement**")
                    st.text(f"Revenue:         {format_large_number(stock.get('revenue'))}")
                    st.text(f"Rev Prev Year:   {format_large_number(stock.get('revenue_prev_year'))}")
                    st.text(f"Rev 3Y Ago:      {format_large_number(stock.get('revenue_3y_ago'))}")
                    st.text(f"Gross Profit:    {format_large_number(stock.get('gross_profit'))}")
                    st.text(f"Operating Inc:   {format_large_number(stock.get('operating_income'))}")
                    st.text(f"EBITDA:          {format_large_number(stock.get('ebitda'))}")
                    st.text(f"Net Income:      {format_large_number(stock.get('net_income'))}")
                    st.text(f"Net Inc Prev Yr: {format_large_number(stock.get('net_income_prev_year'))}")

                with fc2:
                    st.markdown("**Balance Sheet**")
                    st.text(f"Total Assets:    {format_large_number(stock.get('total_assets'))}")
                    st.text(f"Total Debt:      {format_large_number(stock.get('total_debt'))}")
                    st.text(f"Equity:          {format_large_number(stock.get('equity'))}")
                    st.text(f"Cash:            {format_large_number(stock.get('cash'))}")
                    st.text(f"Invested Cap:    {format_large_number(stock.get('invested_capital'))}")
                    st.text(f"EPS:             {format_number(stock.get('eps'))}")
                    st.text(f"EPS 3Y Ago:      {format_number(stock.get('eps_3y_ago'))}")

                with fc3:
                    st.markdown("**Valuation & Market**")
                    st.text(f"Market Cap:      {format_market_cap(stock.get('market_cap'))}")
                    st.text(f"Price:           {format_number(stock.get('price'))}")
                    st.text(f"P/E:             {format_number(stock.get('pe'))}")
                    st.text(f"P/B:             {format_number(stock.get('pb'))}")
                    st.text(f"EV/EBITDA:       {format_number(stock.get('ev_ebitda'))}")
                    st.text(f"PEG:             {format_number(stock.get('peg'))}")
                    st.text(f"Avg Vol (20d):   {format_number(stock.get('avg_volume_20d'), decimals=0)}")

                st.divider()
                st.markdown("**Price Returns**")
                ret_cols = st.columns(4)
                ret_labels = ["1 Month", "3 Months", "6 Months", "12 Months"]
                ret_keys = ["return_1m", "return_3m", "return_6m", "return_12m"]
                for col, label, key in zip(ret_cols, ret_labels, ret_keys):
                    with col:
                        val = stock.get(key)
                        st.metric(label, format_pct_value(val))

else:
    st.info("Select a market from the sidebar and click **Run Screening** to begin.")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("How RS Score Works")
        st.markdown(
            """
            The RS (Relative Strength) Score ranks stocks on a 0-100 scale
            by combining five key dimensions:

            - **Financial Strength** — D/E ratio, ROE, ROA, cash coverage
            - **Growth** — Revenue & earnings growth (YoY and 3Y)
            - **Margin Quality** — Gross, operating, net, and EBITDA margins
            - **Valuation** — P/E, P/B, EV/EBITDA, PEG ratio
            - **Momentum** — Multi-timeframe returns, 52W high distance, relative strength
            """
        )

        st.subheader("Data Model")
        st.markdown(
            """
            Each stock row includes:
            - **Identity** — ticker, company name, market, sector, industry
            - **Price** — price, market cap, volume, multi-period returns
            - **Fundamentals** — revenue, income, margins, balance sheet, valuation ratios
            """
        )

    with col2:
        st.subheader("Available Markets")
        for key, info in SUPPORTED_MARKETS.items():
            st.markdown(f"**{info['label']}** — {len(info['symbols'])} stocks ({info['exchange']})")

        st.subheader("Getting Started")
        st.markdown(
            """
            1. Choose a market from the sidebar
            2. Adjust filters as needed
            3. Click **Run Screening**
            4. Explore results and drill into individual stocks
            """
        )
