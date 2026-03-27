# Workspace

## Overview

pnpm workspace monorepo using TypeScript, plus a Python Streamlit stock screening application. Each package manages its own dependencies.

## Stock Screener (Python / Streamlit)

A production-ready stock screening web app that ranks stocks using a custom RS Score based on five dimensions: Financial Strength, Growth, Margin Quality, Valuation, and Momentum. Supports BIST (Turkey) and US stock markets.

### Python Files

- `app.py` — Streamlit UI entry point with sidebar market selector, filters, results table, and detail tabs
- `config.py` — Market definitions, scoring weights, API configuration (uses `TWELVE_DATA_API_KEY` env var)
- `data_model.py` — Unified DataFrame schema with validation helpers, type coercion, derived field computation, and mock data (10 stocks per market). META_COLUMNS includes `data_source` (price provider) and `data_provider` (fundamentals provider: yahoo/twelve_profile/none)
- `price_provider.py` — Abstract base class (PriceProvider) defining the provider-agnostic interface for market data
- `twelve_data_provider.py` — Twelve Data API implementation with in-memory TTL caching, rate-limit tracking, BIST ticker resolution, and Yahoo Finance fallback when API fails
- `symbol_mapper.py` — Centralized provider-agnostic symbol mapping. Canonical tickers (ASELS, AAPL) are resolved per-provider: `resolve_twelve_symbol` adds `:BIST`, `resolve_yahoo_symbol` adds `.IS`. Includes benchmark maps, `map_symbol_for_provider` dispatch, `canonical_ticker` normalizer, and JSON-backed cache (`data/cache/symbol_map.json`) via `load_symbol_cache`/`save_symbol_cache`
- `disk_cache.py` — Parquet-based disk cache layer for OHLCV data. Stores each symbol's history as `data/cache/{symbol}.parquet`. Features: daily refresh (20h TTL), incremental date-based updates (only fetches missing dates), atomic writes via temp-file rename, per-symbol thread locking, corrupted file auto-removal, outputsize-aware tail slicing
- `data_fetcher.py` — Orchestration layer: selects provider or mock data, exposes reusable functions (latest price, history, returns, 52w high, avg volume). `fetch_fundamentals(symbol, market)` uses hybrid approach: Twelve Data `/profile` for company name/sector/industry + Yahoo Finance for financial data (revenue, net_income, equity, margins, ratios). Grow plan doesn't support `/statistics` or `/income_statement` for most BIST stocks, so Yahoo Finance is the reliable source for financials. Supports `skip_fundamentals` parameter to bypass all fundamentals when quality filter is off. Provides all standalone technical indicator functions (`calculate_moving_averages` (MA20/MA50/MA200 + ratios), `calculate_rsi`, `calculate_macd` (line/signal/histogram), `calculate_atr`, `calculate_volume_ratio`, `calculate_obv`, `calculate_mfi`). The `build_technical_data` pipeline computes all 21 indicator columns from OHLCV in one pass and attaches them to the master DataFrame
- `yahoo_provider.py` — Yahoo Finance provider using yfinance. `fetch_yahoo_history` for OHLCV price data, `fetch_yahoo_fundamentals` for financial data including revenue, revenue_prev_year, net_income, net_income_prev_year (from `stock.income_stmt`), equity, total_debt, total_assets, margins, ROE, ROA, ROIC, PE, PB, EV/EBITDA, sector, industry. debtToEquity divided by 100 for ratio normalization. Primary source for fundamentals since Twelve Data Grow plan restricts financial statements for most BIST stocks
- `financial_metrics.py` — Individual financial metric functions (margins, growth, returns) and `append_all_derived_metrics` for bulk DataFrame enrichment. All derived metrics computed from normalize base columns (revenue, net_income, equity, total_debt, total_assets). Includes `roic_approx` (net_income / invested capital approximation) and quality flags (quality_profitable, quality_growing, quality_solvent). Uses `_prefer_existing()` to preserve API-provided values over recalculated ones
- `momentum_metrics.py` — Momentum engine: period returns, 52W high distance, relative return vs benchmark (SPX/XU100), MA signals, volume
- `scoring_engine.py` — Percentile-based RS Score engine with true 0-100 scaling, 5th/95th winsorization, reverse-scoring for lower-is-better metrics, NaN-aware weight redistribution, RS Category assignment (Elite/Strong/Watchlist/Weak/Avoid). Integrates technical_signals after RS computation.
- `technical_signals.py` — Technical Signal Score engine (0-100): Trend (30%, MA50/MA200/golden cross), Momentum (20%, RSI/MACD), Breakout (20%, 52w high proximity, volume ratio), Volume Flow (20%, MFI scoring + OBV trend/divergence), Risk/Stability (10%, ATR volatility penalty). Uses pre-computed indicator columns from `build_technical_data` when available; falls back to legacy price_data calculation when columns are missing. Computes combined_score (0.65*RS + 0.35*tech), setup_label, and stores volume indicators for scan mode filtering.
- `filters.py` — Pre-ranking quality filter engine with presets (None/Basic/Strict), configurable min volume, top-N results, sort by rs_score or combined_score
- `backtest_engine.py` — Backtest engine: replays screening strategy using disk-cached OHLCV data (no API fundamentals calls). Uses `fetch_backtest_data` for cache-first symbol loading with progress callback, failure logging, and `DataPrepStats` tracking (cache hits, incremental updates, failures). Uses `get_cached_benchmark` for cached benchmark index. Skips redundant momentum pre-computation (recomputes per-period). Point-in-time truncation (no look-ahead bias), supports 1w/15d/1m rebalance, computes equity curve, drawdown, Sharpe, alpha, volatility. UI shows data prep stats after results.
- `watchlist.py` — Local JSON-backed watchlist: add/remove/clear stocks, export CSV, auto-update scores on screening runs
- `utils.py` — Formatting helpers for numbers, percentages, market cap, large numbers, and `is_na` utility
- `requirements.txt` — Python dependencies (streamlit, pandas, numpy, requests, python-dotenv, pyarrow, yfinance)
- `.streamlit/config.toml` — Streamlit server configuration (port 5000, headless)

### Data Model (data_model.py)

Unified DataFrame structure:
- **Identity (5)**: ticker, company_name, market, sector, industry
- **Price & Market (9)**: price, market_cap, avg_volume_20d, return_1m/3m/6m/12m, distance_to_52w_high, relative_return_vs_index
- **Fundamentals (19)**: revenue (current/prev/3y), net_income (current/prev), eps (current/3y), gross_profit, operating_income, ebitda, total_assets, total_debt, equity, cash, invested_capital, pe, pb, ev_ebitda, peg
- **Meta (2)**: data_source (price provider), data_provider (fundamentals: yahoo/twelve_profile/none)

Normalize base columns (provider-agnostic): revenue, revenue_prev_year, net_income, net_income_prev_year, equity, total_debt, total_assets, pe, pb, peg

Derived fields computed by `compute_derived_fields()`: debt_to_equity, equity_to_assets, net_income_to_assets, roe, roa, roic, roic_approx, gross_margin, operating_margin, net_margin, ebitda_margin, revenue_growth, earnings_growth, revenue_cagr_3y, eps_cagr_3y, quality_profitable, quality_growing, quality_solvent

### RS Score Engine (scoring_engine.py)

- **Percentile ranking**: True 0-100 scaling via `(rank-1)/(n-1)*100`; NaN-safe
- **Reverse scoring**: D/E, PE, PB, EV/EBITDA, PEG (lower raw value = higher score)
- **Negative valuation filter**: Non-positive PE/PB/EV_EBITDA/PEG treated as NaN
- **Winsorization**: 5th/95th percentile clipping before ranking
- **Sub-scores**: Financial Strength (25%), Growth (20%), Margin Quality (15%), Valuation (20%), Momentum (20%)
- **NaN redistribution**: Missing metrics' weights redistributed to available metrics within each sub-score
- **RS Categories**: Elite (85-100), Strong (70-85), Watchlist (55-70), Weak (40-55), Avoid (0-40)
- **Margin trend**: `net_margin - prev_year_net_margin` added as scoring metric

Helper functions: `validate_dataframe()`, `coerce_numeric_columns()`, `ensure_columns()`, `safe_float()`, `safe_ratio()`

### Running

- Artifact: `artifacts/stock-screener` (kind: web, previewPath: `/`)
- Workflow: `artifacts/stock-screener: web` — runs `streamlit run app.py --server.port 5000`
- Port: 5000
- The Streamlit app lives at the project root (app.py, config.py, etc.) but is registered as an artifact for preview proxy routing

### API Integration

Set the `TWELVE_DATA_API_KEY` environment variable to connect to real market data. Without it, the app uses realistic placeholder data for demonstration.

## TypeScript Stack

- **Monorepo tool**: pnpm workspaces
- **Node.js version**: 24
- **Package manager**: pnpm
- **TypeScript version**: 5.9
- **API framework**: Express 5
- **Database**: PostgreSQL + Drizzle ORM
- **Validation**: Zod (`zod/v4`), `drizzle-zod`
- **API codegen**: Orval (from OpenAPI spec)
- **Build**: esbuild (CJS bundle)

## Structure

```text
artifacts-monorepo/
├── app.py                 # Streamlit stock screener entry point
├── config.py              # Stock screener configuration
├── data_model.py          # Unified DataFrame schema, validation, mock data
├── price_provider.py      # Abstract market data provider interface
├── twelve_data_provider.py # Twelve Data API provider implementation
├── symbol_mapper.py       # Centralized symbol resolution & caching
├── data_fetcher.py        # Market data orchestration layer
├── financial_metrics.py   # Financial sub-score calculations
├── momentum_metrics.py    # Momentum sub-score calculations
├── scoring_engine.py      # Composite RS Score engine
├── technical_signals.py   # Technical Signal Score engine
├── backtest_engine.py     # Historical backtest engine
├── filters.py             # Stock filtering logic
├── watchlist.py           # JSON-backed watchlist storage
├── utils.py               # Display formatting utilities
├── requirements.txt       # Python dependencies
├── .streamlit/            # Streamlit configuration
├── artifacts/             # Deployable applications
│   └── api-server/        # Express API server
├── lib/                   # Shared libraries
│   ├── api-spec/          # OpenAPI spec + Orval codegen config
│   ├── api-client-react/  # Generated React Query hooks
│   ├── api-zod/           # Generated Zod schemas from OpenAPI
│   └── db/                # Drizzle ORM schema + DB connection
├── scripts/               # Utility scripts (single workspace package)
├── pnpm-workspace.yaml    # pnpm workspace config
├── tsconfig.base.json     # Shared TS options
├── tsconfig.json          # Root TS project references
└── package.json           # Root package with hoisted devDeps
```

## TypeScript & Composite Projects

Every package extends `tsconfig.base.json` which sets `composite: true`. The root `tsconfig.json` lists all packages as project references. This means:

- **Always typecheck from the root** — run `pnpm run typecheck` (which runs `tsc --build --emitDeclarationOnly`). This builds the full dependency graph so that cross-package imports resolve correctly. Running `tsc` inside a single package will fail if its dependencies haven't been built yet.
- **`emitDeclarationOnly`** — we only emit `.d.ts` files during typecheck; actual JS bundling is handled by esbuild/tsx/vite...etc, not `tsc`.
- **Project references** — when package A depends on package B, A's `tsconfig.json` must list B in its `references` array. `tsc --build` uses this to determine build order and skip up-to-date packages.

## Root Scripts

- `pnpm run build` — runs `typecheck` first, then recursively runs `build` in all packages that define it
- `pnpm run typecheck` — runs `tsc --build --emitDeclarationOnly` using project references

## Packages

### `artifacts/api-server` (`@workspace/api-server`)

Express 5 API server. Routes live in `src/routes/` and use `@workspace/api-zod` for request and response validation and `@workspace/db` for persistence.

- Entry: `src/index.ts` — reads `PORT`, starts Express
- App setup: `src/app.ts` — mounts CORS, JSON/urlencoded parsing, routes at `/api`
- Routes: `src/routes/index.ts` mounts sub-routers; `src/routes/health.ts` exposes `GET /health` (full path: `/api/health`)
- Depends on: `@workspace/db`, `@workspace/api-zod`
- `pnpm --filter @workspace/api-server run dev` — run the dev server
- `pnpm --filter @workspace/api-server run build` — production esbuild bundle (`dist/index.cjs`)
- Build bundles an allowlist of deps (express, cors, pg, drizzle-orm, zod, etc.) and externalizes the rest

### `lib/db` (`@workspace/db`)

Database layer using Drizzle ORM with PostgreSQL. Exports a Drizzle client instance and schema models.

### `lib/api-spec` (`@workspace/api-spec`)

Owns the OpenAPI 3.1 spec (`openapi.yaml`) and the Orval config (`orval.config.ts`). Running codegen produces output into two sibling packages:

1. `lib/api-client-react/src/generated/` — React Query hooks + fetch client
2. `lib/api-zod/src/generated/` — Zod schemas

Run codegen: `pnpm --filter @workspace/api-spec run codegen`

### `lib/api-zod` (`@workspace/api-zod`)

Generated Zod schemas from the OpenAPI spec. Used by `api-server` for response validation.

### `lib/api-client-react` (`@workspace/api-client-react`)

Generated React Query hooks and fetch client from the OpenAPI spec.

### `scripts` (`@workspace/scripts`)

Utility scripts package. Each script is a `.ts` file in `src/` with a corresponding npm script in `package.json`. Run scripts via `pnpm --filter @workspace/scripts run <script>`.
