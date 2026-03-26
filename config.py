import os
from dotenv import load_dotenv

load_dotenv()

TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")
TWELVE_DATA_BASE_URL = "https://api.twelvedata.com"

CACHE_TTL_HISTORY = 600
CACHE_TTL_QUOTE = 120

SUPPORTED_MARKETS = {
    "BIST": {
        "label": "BIST (Turkey)",
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
        "label": "US Stocks",
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

SCORING_WEIGHTS = {
    "financial_strength": 0.20,
    "growth": 0.25,
    "margin_quality": 0.20,
    "valuation": 0.15,
    "momentum": 0.20,
}

SCORE_CATEGORIES = list(SCORING_WEIGHTS.keys())

DEFAULT_TOP_N = 10
