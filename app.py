import streamlit as st
import pandas as pd
import numpy as np
import time
from config import (
    SUPPORTED_MARKETS, DEFAULT_TOP_N,
    TWELVE_DATA_API_KEY, BENCHMARK_INDEX,
    CACHE_TTL_MARKET_DATA, REQUIRED_FIELDS_FOR_SCORING,
)
from data_model import validate_dataframe
from data_fetcher import fetch_market_data, get_last_diagnostics
from scoring_engine import compute_rs_scores, get_score_breakdown
from filters import (
    apply_preset_filter, rank_and_limit,
    get_preset_names, get_preset_info,
)
from utils import format_number, format_percentage, format_large_number, format_market_cap, format_pct_value
from watchlist import (
    get_watchlist, get_watchlist_tickers, is_in_watchlist,
    add_to_watchlist, remove_from_watchlist, clear_watchlist,
    update_watchlist_scores, export_watchlist_csv,
)

st.set_page_config(
    page_title="Stock Screener",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(ttl=CACHE_TTL_MARKET_DATA, show_spinner=False)
def _cached_fetch(market: str, _cache_bust: int) -> pd.DataFrame:
    return fetch_market_data(market)


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


def _score_fmt(val) -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/A"
    return f"{val:.1f}"


def _missing_metric_warnings(stock_row: pd.Series) -> list:
    warnings = []
    for f in REQUIRED_FIELDS_FOR_SCORING:
        val = stock_row.get(f)
        if val is None or (isinstance(val, float) and np.isnan(val)):
            warnings.append(f)
    return warnings


def _render_detail(stock_row: pd.Series) -> None:
    bd = get_score_breakdown(stock_row)

    missing = _missing_metric_warnings(stock_row)
    if missing:
        readable = [f.replace("_", " ").title() for f in missing]
        st.warning(f"Missing data: {', '.join(readable)} — scores may be less reliable")

    st.markdown(
        f"**{stock_row.get('company_name', '')}** · "
        f"{stock_row.get('sector', '')} · "
        f"{stock_row.get('industry', '')} · "
        f"Market Cap: {format_market_cap(stock_row.get('market_cap'))}"
    )

    price_val = stock_row.get("price")
    price_str = f"${price_val:,.2f}" if price_val is not None and np.isfinite(price_val) else "N/A"
    rs_val = bd.get("rs_score")
    cat_val = bd.get("rs_category", "N/A")

    h1, h2, h3 = st.columns(3)
    h1.metric("Price", price_str)
    h2.metric("RS Score", _score_fmt(rs_val))
    h3.metric("Category", cat_val)

    st.markdown("---")

    s1, s2, s3, s4, s5 = st.columns(5)
    s1.metric("Financial Strength", _score_fmt(bd.get("financial_strength")))
    s2.metric("Growth", _score_fmt(bd.get("growth")))
    s3.metric("Margin Quality", _score_fmt(bd.get("margin_quality")))
    s4.metric("Valuation", _score_fmt(bd.get("valuation")))
    s5.metric("Momentum", _score_fmt(bd.get("momentum")))

    st.markdown("---")

    raw_col, derived_col = st.columns(2)

    with raw_col:
        st.markdown("**Raw Metrics**")
        st.text(f"Equity:        {format_large_number(stock_row.get('equity'))}")
        st.text(f"Total Debt:    {format_large_number(stock_row.get('total_debt'))}")
        st.text(f"Total Assets:  {format_large_number(stock_row.get('total_assets'))}")
        st.text(f"Revenue:       {format_large_number(stock_row.get('revenue'))}")
        st.text(f"Net Income:    {format_large_number(stock_row.get('net_income'))}")
        st.text(f"P/E:           {format_number(stock_row.get('pe'))}")
        st.text(f"P/B:           {format_number(stock_row.get('pb'))}")
        st.text(f"EV/EBITDA:     {format_number(stock_row.get('ev_ebitda'))}")
        st.text(f"PEG:           {format_number(stock_row.get('peg'))}")

    with derived_col:
        st.markdown("**Derived Metrics**")
        st.text(f"D/E Ratio:      {format_number(bd.get('debt_to_equity'))}")
        st.text(f"Equity/Assets:  {format_percentage(bd.get('equity_to_assets'))}")
        st.text(f"ROIC:           {format_percentage(bd.get('roic'))}")
        st.text(f"Gross Margin:   {format_percentage(bd.get('gross_margin'))}")
        st.text(f"Op Margin:      {format_percentage(bd.get('operating_margin'))}")
        st.text(f"Net Margin:     {format_percentage(bd.get('net_margin'))}")
        st.text(f"Rev Growth YoY: {format_percentage(bd.get('revenue_growth'))}")
        st.text(f"NI Growth YoY:  {format_percentage(bd.get('earnings_growth'))}")
        st.text(f"Rev CAGR 3Y:    {format_percentage(bd.get('revenue_cagr_3y'))}")
        st.text(f"EPS CAGR 3Y:    {format_percentage(bd.get('eps_cagr_3y'))}")

    st.markdown("---")

    r1, r2, r3 = st.columns(3)
    ret_3m = stock_row.get("return_3m")
    ret_6m = stock_row.get("return_6m")
    ret_12m = stock_row.get("return_12m")
    r1.metric("3M Return", format_pct_value(ret_3m))
    r2.metric("6M Return", format_pct_value(ret_6m))
    r3.metric("12M Return", format_pct_value(ret_12m))

    if "price_data" in stock_row and isinstance(stock_row["price_data"], pd.DataFrame):
        price_df = stock_row["price_data"]
        if not price_df.empty:
            st.markdown("**Price History**")
            chart_data = price_df.set_index("datetime")[["close"]].rename(columns={"close": "Close"})
            st.line_chart(chart_data, height=250)


def _render_diagnostics() -> None:
    diag = get_last_diagnostics()
    if diag is None:
        return

    with st.expander("Diagnostics", expanded=False):
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Fetched", f"{diag.fetched_tickers}/{diag.total_tickers}")
        d2.metric("Failed", str(diag.failed_tickers))
        d3.metric("Incomplete Data", str(diag.incomplete_rows))
        d4.metric("Last Refresh", diag.timestamp_str)

        info_parts = []
        if diag.used_mock:
            info_parts.append("Using demo/mock data")
        if diag.fallback_triggered:
            info_parts.append("Fallback triggered — API returned no data")
        info_parts.append(f"Fetch duration: {diag.duration_seconds:.1f}s")
        st.caption(" · ".join(info_parts))

        if diag.failed_symbols:
            st.error(f"Failed tickers: {', '.join(diag.failed_symbols)}")

        if diag.missing_fields_summary:
            missing_lines = [f"{k.replace('_', ' ').title()}: {v} stocks" for k, v in sorted(diag.missing_fields_summary.items(), key=lambda x: -x[1])]
            st.warning("Missing fields across universe: " + " · ".join(missing_lines))

        if diag.errors:
            with st.expander("Error details", expanded=False):
                for err in diag.errors[:20]:
                    st.text(err)


with st.sidebar:
    st.header("Stock Screener")

    watchlist_count = len(get_watchlist_tickers())
    page = st.radio(
        "View",
        options=["Screener", "Watchlist"],
        format_func=lambda x: f"{x} ({watchlist_count})" if x == "Watchlist" else x,
        horizontal=True,
    )

    st.divider()

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

if page == "Watchlist":
    st.markdown("### Watchlist")

    wl_items = get_watchlist()

    if not wl_items:
        st.info("Your watchlist is empty. Run the screener and add stocks to track them here.")
    else:
        wl_df = pd.DataFrame(wl_items)
        display_wl_cols = ["ticker", "company_name", "rs_score", "rs_category", "price", "market"]
        display_wl = wl_df[[c for c in display_wl_cols if c in wl_df.columns]].copy()

        if "rs_score" in display_wl.columns:
            display_wl["rs_score"] = display_wl["rs_score"].apply(
                lambda x: round(x, 1) if x is not None and not (isinstance(x, float) and np.isnan(x)) else None
            )
        if "price" in display_wl.columns:
            display_wl["price"] = display_wl["price"].apply(
                lambda x: round(x, 2) if x is not None and not (isinstance(x, float) and np.isnan(x)) else None
            )

        st.dataframe(
            display_wl,
            use_container_width=True,
            hide_index=True,
            column_config={
                "ticker": st.column_config.TextColumn("Ticker", width="small"),
                "company_name": st.column_config.TextColumn("Company"),
                "rs_score": st.column_config.ProgressColumn(
                    "RS Score", min_value=0, max_value=100, format="%.1f",
                ),
                "rs_category": st.column_config.TextColumn("Category", width="small"),
                "price": st.column_config.NumberColumn("Price", format="%.2f"),
                "market": st.column_config.TextColumn("Market", width="small"),
            },
        )

        col_csv, col_clear = st.columns([1, 1])
        with col_csv:
            csv_wl = export_watchlist_csv()
            st.download_button(
                label="Export Watchlist CSV",
                data=csv_wl,
                file_name="watchlist.csv",
                mime="text/csv",
            )
        with col_clear:
            if st.button("Clear Watchlist", type="secondary"):
                cleared = clear_watchlist()
                st.success(f"Removed {cleared} stocks from watchlist.")
                st.rerun()

        st.divider()
        st.markdown("**Remove individual stocks**")
        for item in wl_items:
            t = item["ticker"]
            col_t, col_btn = st.columns([3, 1])
            col_t.text(f"{t} — {item.get('company_name', '')} | RS {_score_fmt(item.get('rs_score'))}")
            if col_btn.button("Remove", key=f"wl_remove_{t}"):
                remove_from_watchlist(t)
                st.rerun()

elif page == "Screener":
    run_screening = st.button("Run Screening", type="primary", use_container_width=True)

    if run_screening:
        market_info = SUPPORTED_MARKETS[market]

        try:
            with st.spinner(f"Fetching {market_info['label']} data..."):
                cache_bust = int(time.time() // CACHE_TTL_MARKET_DATA)
                raw_data = _cached_fetch(market, cache_bust)

            validation = validate_dataframe(raw_data)
            if not validation["valid"]:
                st.warning(f"Data quality notice: missing columns {validation['missing_columns']}")

            with st.spinner("Scoring..."):
                scored_data = compute_rs_scores(raw_data)

            scored_rows = scored_data.to_dict("records")
            updated = update_watchlist_scores(scored_rows)
            if updated > 0:
                st.toast(f"Updated scores for {updated} watchlist stock(s)")

            filtered_data = apply_preset_filter(
                scored_data, preset=selected_preset, min_avg_volume=min_avg_volume,
            )
            passed_count = len(filtered_data)
            filtered_data = rank_and_limit(filtered_data, top_n=top_n)

            st.session_state["screener_scored"] = scored_data
            st.session_state["screener_filtered"] = filtered_data
            st.session_state["screener_passed_count"] = passed_count
            st.session_state["screener_market"] = market
            st.session_state["screener_preset"] = selected_preset

        except Exception as e:
            st.error(f"An error occurred during screening: {e}")
            _render_diagnostics()

    if "screener_filtered" in st.session_state:
        scored_data = st.session_state["screener_scored"]
        filtered_data = st.session_state["screener_filtered"]
        passed_count = st.session_state["screener_passed_count"]
        stored_market = st.session_state["screener_market"]
        stored_preset = st.session_state["screener_preset"]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Stocks Scanned", len(scored_data))
        c2.metric("Passed Filter", passed_count)
        if not filtered_data.empty:
            c3.metric("Highest RS", f"{filtered_data['rs_score'].max():.1f}")
            c4.metric("Avg RS", f"{filtered_data['rs_score'].mean():.1f}")
        else:
            c3.metric("Highest RS", "—")
            c4.metric("Avg RS", "—")

        _render_diagnostics()

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
                file_name=f"screener_{stored_market}_{stored_preset}.csv",
                mime="text/csv",
            )

            st.divider()
            st.subheader("Stock Details")

            for _, row in filtered_data.iterrows():
                ticker = row.get("ticker", "?")
                name = row.get("company_name", "")
                cat = row.get("rs_category", "N/A")
                rs = row.get("rs_score", 0)
                in_wl = is_in_watchlist(ticker)
                wl_icon = " [W]" if in_wl else ""
                label = f"{ticker}  —  {name}  |  RS {rs:.1f}  ({cat}){wl_icon}"

                with st.expander(label, expanded=False):
                    if not in_wl:
                        if st.button(f"Add {ticker} to Watchlist", key=f"wl_add_{ticker}"):
                            ok = add_to_watchlist(
                                ticker=ticker,
                                rs_score=rs,
                                rs_category=cat,
                                price=row.get("price"),
                                company_name=name,
                                market=stored_market,
                            )
                            if ok:
                                st.success(f"Added {ticker} to watchlist")
                            else:
                                st.error(f"Failed to save {ticker} to watchlist")
                            st.rerun()
                    else:
                        st.caption(f"{ticker} is in your watchlist")
                        if st.button(f"Remove {ticker} from Watchlist", key=f"wl_rem_{ticker}"):
                            remove_from_watchlist(ticker)
                            st.rerun()

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
