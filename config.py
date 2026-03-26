import os
from dotenv import load_dotenv

load_dotenv()

TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")
TWELVE_DATA_BASE_URL = "https://api.twelvedata.com"

CACHE_TTL_HISTORY = 600
CACHE_TTL_QUOTE = 120

SUPPORTED_MARKETS = {
    "BIST": {
        "label": "BIST (Türkiye)",
        "exchange": "BIST",
        "currency": "TRY",
        "symbols": [
            "THYAO", "GARAN", "AKBNK", "EREGL", "BIMAS",
            "KCHOL", "SAHOL", "SISE", "TUPRS", "ASELS",
            "TCELL", "PGSUS", "TOASO", "FROTO", "KOZAL",
            "HEKTS", "MGROS", "TAVHL", "VESTL", "ARCLK",
        ],
    },
    "USA": {
        "label": "ABD Hisseleri",
        "exchange": "NASDAQ/NYSE",
        "currency": "USD",
        "symbols": [
            "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
            "META", "TSLA", "BRK.B", "JPM", "V",
            "UNH", "XOM", "JNJ", "PG", "MA",
            "HD", "AVGO", "MRK", "COST", "PEP",
        ],
    },
}

BENCHMARK_INDEX = {
    "USA": "SPX",
    "BIST": "XU100",
}

BIST100_TICKERS = [
    "THYAO", "GARAN", "AKBNK", "EREGL", "BIMAS",
    "KCHOL", "SAHOL", "SISE", "TUPRS", "ASELS",
    "TCELL", "PGSUS", "TOASO", "FROTO", "KOZAL",
    "HEKTS", "MGROS", "TAVHL", "ARCLK", "SASA",
    "PETKM", "ISCTR", "YKBNK", "VAKBN", "HALKB",
    "TKFEN", "TTKOM", "EKGYO", "ENKAI", "GUBRF",
    "KRDMD", "OYAKC", "OTKAR", "DOHOL", "AEFES",
    "SOKM", "ALARK", "ECZYT", "CIMSA", "AKSEN",
    "GESAN", "KONTR", "BRYAT", "BTCIM", "ISGYO",
    "TSKB", "AGHOL", "CCOLA", "TTRAK", "ULKER",
]

BIST_SEGMENTS = {
    "BISTTUM": "BIST TÜM",
    "BIST100": "BIST 100",
    "BIST100_DISI": "BIST 100 Dışı",
}

SP500_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "META", "TSLA", "BRK.B", "JPM", "V",
    "UNH", "XOM", "JNJ", "PG", "MA",
    "HD", "AVGO", "MRK", "COST", "PEP",
]

NASDAQ100_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "META", "TSLA", "AVGO", "COST", "PEP",
]

USA_SEGMENTS = {
    "USA_ALL": "Tüm USA",
    "SP500": "S&P 500",
    "NASDAQ100": "NASDAQ 100",
}

SCORING_WEIGHTS = {
    "financial_strength": 0.25,
    "growth": 0.20,
    "margin_quality": 0.15,
    "valuation": 0.20,
    "momentum": 0.20,
}

FINANCIAL_STRENGTH_WEIGHTS = {
    "roic": 0.40,
    "debt_to_equity": 0.25,
    "equity_to_assets": 0.20,
    "net_income_to_assets": 0.15,
}

GROWTH_WEIGHTS = {
    "revenue_growth": 0.25,
    "earnings_growth": 0.30,
    "revenue_cagr_3y": 0.20,
    "eps_cagr_3y": 0.25,
}

MARGIN_QUALITY_WEIGHTS = {
    "gross_margin": 0.20,
    "operating_margin": 0.30,
    "net_margin": 0.30,
    "margin_trend": 0.20,
}

VALUATION_WEIGHTS = {
    "pe": 0.20,
    "pb": 0.15,
    "ev_ebitda": 0.25,
    "peg": 0.40,
}

MOMENTUM_WEIGHTS = {
    "return_3m": 0.20,
    "return_6m": 0.25,
    "return_12m": 0.25,
    "distance_to_52w_high": 0.10,
    "relative_return_vs_index": 0.20,
}

REVERSE_SCORED_METRICS = {
    "debt_to_equity",
    "pe",
    "pb",
    "ev_ebitda",
    "peg",
}

RS_CATEGORIES = [
    (85, 100, "Elit"),
    (70, 85, "Güçlü"),
    (55, 70, "İzleme"),
    (40, 55, "Zayıf"),
    (0, 40, "Kaçın"),
]

WINSORIZE_LOWER = 0.05
WINSORIZE_UPPER = 0.95

SCORE_CATEGORIES = list(SCORING_WEIGHTS.keys())

DEFAULT_TOP_N = 10

API_REQUEST_TIMEOUT = 20
API_MAX_RETRIES = 1
API_RETRY_DELAY = 10

CACHE_TTL_MARKET_DATA = 300

LOG_LEVEL = os.getenv("SCREENER_LOG_LEVEL", "INFO")

REQUIRED_FIELDS_FOR_SCORING = [
    "equity", "net_income", "revenue", "total_assets",
]

FALLBACK_TO_MOCK = True

MIN_ROWS_FOR_SCORING = 3
