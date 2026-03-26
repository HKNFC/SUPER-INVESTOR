# Workspace

## Overview

pnpm workspace monorepo using TypeScript, plus a Python Streamlit stock screening application. Each package manages its own dependencies.

## Stock Screener (Python / Streamlit)

A production-ready stock screening web app that ranks stocks using a custom RS Score based on five dimensions: Financial Strength, Growth, Margin Quality, Valuation, and Momentum. Supports BIST (Turkey) and US stock markets.

### Python Files

- `app.py` — Streamlit UI entry point with sidebar market selector, filters, and results table
- `config.py` — Market definitions, scoring weights, API configuration (uses `TWELVE_DATA_API_KEY` env var)
- `data_fetcher.py` — Fetches price history and fundamentals from Twelve Data API (placeholder data when API key not set)
- `financial_metrics.py` — Calculates financial strength, growth, margin quality, and valuation sub-scores
- `momentum_metrics.py` — Calculates momentum sub-scores from price history (multi-timeframe returns + MA signals)
- `scoring_engine.py` — Computes weighted composite RS Score and ranks stocks
- `filters.py` — Applies score-based, category-based, and fundamental filters
- `utils.py` — Formatting helpers for numbers, percentages, market cap, and display DataFrames
- `requirements.txt` — Python dependencies (streamlit, pandas, numpy, requests, python-dotenv)
- `.streamlit/config.toml` — Streamlit server configuration (port 5000, headless)

### Running

- Workflow: `streamlit run app.py --server.port 5000`
- Port: 5000

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
├── data_fetcher.py        # Market data fetching
├── financial_metrics.py   # Financial sub-score calculations
├── momentum_metrics.py    # Momentum sub-score calculations
├── scoring_engine.py      # Composite RS Score engine
├── filters.py             # Stock filtering logic
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
