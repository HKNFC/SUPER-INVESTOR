import streamlit as st
import pandas as pd
from config import SUPPORTED_MARKETS, SCORING_WEIGHTS, DEFAULT_TOP_N, TWELVE_DATA_API_KEY
from data_fetcher import fetch_market_data
from scoring_engine import compute_rs_scores, get_score_breakdown
from filters import filter_by_score, filter_by_category_score, filter_by_fundamentals
from utils import prepare_display_dataframe, format_market_cap, format_number, score_color

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

    with st.spinner("Computing RS Scores..."):
        scored_data = compute_rs_scores(raw_data)

    filtered_data = filter_by_score(scored_data, min_rs_score=min_rs_score, top_n=top_n)

    if category_filter != "None":
        filtered_data = filter_by_category_score(
            filtered_data,
            category=category_filter,
            min_score=category_min,
        )

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
                "symbol": st.column_config.TextColumn("Symbol", width="small"),
                "last_close": st.column_config.NumberColumn("Last Close", format="%.2f"),
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
            },
        )

        st.divider()
        st.subheader("Stock Details")

        selected_symbol = st.selectbox(
            "Select a stock for detailed breakdown",
            options=filtered_data["symbol"].tolist(),
        )

        if selected_symbol:
            stock_row = filtered_data[filtered_data["symbol"] == selected_symbol].iloc[0]
            breakdown = get_score_breakdown(stock_row)

            detail_cols = st.columns(3)
            with detail_cols[0]:
                st.metric("Symbol", breakdown["symbol"])
                st.metric("RS Score", f"{breakdown['rs_score']:.1f}")
            with detail_cols[1]:
                fs = breakdown["financial_strength"]
                g = breakdown["growth"]
                st.metric("Financial Strength", f"{fs:.1f}" if fs is not None else "N/A")
                st.metric("Growth", f"{g:.1f}" if g is not None else "N/A")
            with detail_cols[2]:
                mq = breakdown["margin_quality"]
                v = breakdown["valuation"]
                m = breakdown["momentum"]
                st.metric("Margin Quality", f"{mq:.1f}" if mq is not None else "N/A")
                st.metric("Valuation", f"{v:.1f}" if v is not None else "N/A")
                st.metric("Momentum", f"{m:.1f}" if m is not None else "N/A")

            if "price_data" in stock_row and isinstance(stock_row["price_data"], pd.DataFrame):
                price_df = stock_row["price_data"]
                if not price_df.empty:
                    st.subheader(f"Price Chart: {selected_symbol}")
                    chart_data = price_df.set_index("datetime")[["close"]].rename(
                        columns={"close": "Close Price"}
                    )
                    st.line_chart(chart_data)

else:
    st.info("Select a market from the sidebar and click **Run Screening** to begin.")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("How RS Score Works")
        st.markdown(
            """
            The RS (Relative Strength) Score ranks stocks on a 0-100 scale
            by combining five key dimensions:

            - **Financial Strength** — Balance sheet health (current ratio, D/E, ROE)
            - **Growth** — Revenue and earnings growth rates
            - **Margin Quality** — Gross, operating, and net margins
            - **Valuation** — P/E, P/B, EV/EBITDA multiples
            - **Momentum** — Price trends across multiple timeframes
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
