import os
from dotenv import load_dotenv

load_dotenv()

TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")
TWELVE_DATA_BASE_URL = "https://api.twelvedata.com"

CACHE_TTL_HISTORY = 600
CACHE_TTL_QUOTE = 120

BIST_ALL_TICKERS = [
    "A1CAP", "A1YEN", "ACSEL", "ADEL", "ADESE", "ADGYO", "AEFES", "AFYON", "AGESA", "AGHOL",
    "AGROT", "AGYO", "AHGAZ", "AHSGY", "AKBNK", "AKCNS", "AKENR", "AKFGY", "AKFIS", "AKFYE",
    "AKGRT", "AKHAN", "AKMGY", "AKSA", "AKSEN", "AKSGY", "AKSUE", "AKYHO", "ALARK", "ALBRK",
    "ALCAR", "ALCTL", "ALFAS", "ALGYO", "ALKA", "ALKIM", "ALKLC", "ALTNY", "ALVES",
    "ANELE", "ANGEN", "ANHYT", "ANSGR", "ARASE", "ARCLK", "ARDYZ", "ARENA", "ARFYE", "ARMGD",
    "ARSAN", "ARTMS", "ARZUM", "ASELS", "ASGYO", "ASTOR", "ASUZU", "ATAGY", "ATAKP", "ATATP",
    "ATATR", "ATEKS", "ATLAS", "ATSYH", "AVGYO", "AVHOL", "AVOD", "AVPGY", "AVTUR", "AYCES",
    "AYDEM", "AYEN", "AYES", "AYGAZ", "AZTEK", "BAGFS", "BAHKM", "BAKAB", "BALAT", "BALSU",
    "BANVT", "BARMA", "BASCM", "BASGZ", "BAYRK", "BEGYO", "BERA", "BESLR", "BESTE", "BEYAZ",
    "BFREN", "BIENY", "BIGCH", "BIGEN", "BIGTK", "BIMAS", "BINBN", "BINHO", "BIOEN", "BIZIM",
    "BJKAS", "BLCYT", "BLUME", "BMSCH", "BMSTL", "BNTAS", "BOBET", "BORLS", "BORSK", "BOSSA",
    "BRISA", "BRKO", "BRKSN", "BRKVY", "BRLSM", "BRMEN", "BRSAN", "BRYAT", "BSOKE", "BTCIM",
    "BUCIM", "BULGS", "BURCE", "BURVA", "BVSAN", "BYDNR", "CANTE", "CASA", "CATES", "CCOLA",
    "CELHA", "CEMAS", "CEMTS", "CEMZY", "CEOEM", "CGCAM", "CIMSA", "CLEBI", "CMBTN", "CMENT",
    "CONSE", "COSMO", "CRDFA", "CRFSA", "CUSAN", "CVKMD", "CWENE", "DAGI", "DAPGM", "DARDL",
    "DCTTR", "DENGE", "DERHL", "DERIM", "DESA", "DESPC", "DEVA", "DGATE", "DGGYO", "DGNMO",
    "DIRIT", "DITAS", "DMRGD", "DMSAS", "DNISI", "DOAS", "DOCO", "DOFER", "DOFRB",
    "DOGUB", "DOHOL", "DOKTA", "DSTKF", "DUNYH", "DURDO", "DURKN", "DYOBY", "DZGYO", "EBEBK",
    "ECILC", "ECOGR", "ECZYT", "EDATA", "EDIP", "EFOR", "EGEEN", "EGEGY", "EGEPO", "EGGUB",
    "EGPRO", "EGSER", "EKGYO", "EKIZ", "EKOS", "EKSUN", "ELITE", "EMKEL", "EMNIS", "EMPAE",
    "ENDAE", "ENERY", "ENJSA", "ENKAI", "ENSRI", "ENTRA", "EPLAS", "ERBOS", "ERCB", "EREGL",
    "ERSU", "ESCAR", "ESCOM", "ESEN", "ETILR", "ETYAT", "EUHOL", "EUKYO", "EUPWR", "EUREN",
    "EUYO", "EYGYO", "FADE", "FENER", "FLAP", "FMIZP", "FONET", "FORMT", "FORTE", "FRIGO",
    "FRMPL", "FROTO", "FZLGY", "GARAN", "GARFA", "GATEG", "GEDIK", "GEDZA", "GENIL", "GENKM",
    "GENTS", "GEREL", "GESAN", "GIPTA", "GLBMD", "GLCVY", "GLRMK", "GLRYH", "GLYHO", "GMTAS",
    "GOKNR", "GOLTS", "GOODY", "GOZDE", "GRNYO", "GRSEL", "GRTHO", "GSDDE", "GSDHO", "GSRAY",
    "GUBRF", "GUNDG", "GWIND", "GZNMI", "HALKB", "HATEK", "HATSN", "HDFGS", "HEDEF", "HEKTS",
    "HKTM", "HLGYO", "HOROZ", "HRKET", "HTTBT", "HUBVC", "HUNER", "HURGZ", "ICBCT", "ICUGS",
    "IDGYO", "IEYHO", "IHAAS", "IHEVA", "IHGZT", "IHLAS", "IHLGM", "IHYAY", "IMASM", "INDES",
    "INFO", "INGRM", "INTEK", "INTEM", "INVEO", "INVES", "ISATR", "ISBIR", "ISBTR", "ISCTR",
    "ISDMR", "ISFIN", "ISGSY", "ISGYO", "ISKPL", "ISKUR", "ISMEN", "ISSEN", "ISYAT", "IZENR",
    "IZFAS", "IZINV", "IZMDC", "JANTS", "KAPLM", "KAREL", "KARSN", "KARTN", "KATMR", "KAYSE",
    "KBORU", "KCAER", "KCHOL", "KENT", "KERVN", "KERVT", "KFEIN", "KGYO", "KIMMR", "KLGYO", "KLKIM",
    "KLMSN", "KLNMA", "KLRHO", "KLSER", "KLSYN", "KLYPV", "KMPUR", "KNFRT", "KOCMT", "KONKA",
    "KONTR", "KONYA", "KOPOL", "KORDS", "KOTON", "KRDMA", "KRDMB", "KRDMD", "KRGYO", "KRONT",
    "KRPLS", "KRSTL", "KRTEK", "KRVGD", "KSTUR", "KTLEV", "KTSKR", "KUTPO", "KUVVA", "KUYAS",
    "KOZAL", "KZBGY", "KZGYO", "LIDER", "LIDFA", "LILAK", "LINK", "LKMNH", "LMKDC", "LOGO", "LRSHO",
    "LUKSK", "LXGYO", "LYDHO", "LYDYE", "MAALT", "MACKO", "MAGEN", "MAKIM", "MAKTK", "MANAS",
    "MARBL", "MARKA", "MARMR", "MARTI", "MAVI", "MCARD", "MEDTR", "MEGAP", "MEGMT", "MEKAG",
    "MEPET", "MERCN", "MERIT", "MERKO", "METRO", "MEYSU", "MGROS", "MHRGY", "MIATK", "MMCAS",
    "MNDRS", "MNDTR", "MOBTL", "MOGAN", "MOPAS", "MPARK", "MRGYO", "MRSHL", "MSGYO", "MTRKS",
    "MTRYO", "MZHLD", "NATEN", "NETAS", "NETCD", "NIBAS", "NTGAZ", "NTHOL", "NUGYO", "NUHCM",
    "OBAMS", "OBASE", "ODAS", "ODINE", "OFSYM", "ONCSM", "ONRYT", "ORCAY", "ORGE", "ORMA",
    "OSMEN", "OSTIM", "OTKAR", "OTTO", "OYAKC", "OYAYO", "OYLUM", "OYYAT", "OZATD", "OZGYO",
    "OZKGY", "OZRDN", "OZSUB", "OZYSR", "PAGYO", "PAHOL", "PAMEL", "PAPIL", "PARSN", "PASEU",
    "PATEK", "PCILT", "PEKGY", "PENGD", "PENTA", "PETKM", "PETUN", "PGSUS", "PINSU", "PKART",
    "PKENT", "PLTUR", "PNLSN", "PNSUT", "POLHO", "POLTK", "PRDGS", "PRKAB", "PRKME", "PRZMA",
    "PSDTC", "PSGYO", "QNBFK", "QNBTR", "QUAGR", "RALYH", "RAYSG", "REEDR", "RGYAS", "RNPOL",
    "RODRG", "RTALB", "RUBNS", "RUZYE", "RYGYO", "RYSAS", "SAFKR", "SAHOL", "SAMAT", "SANEL",
    "SANFM", "SANKO", "SARKY", "SASA", "SAYAS", "SDTTR", "SEGMN", "SEGYO", "SEKFK", "SEKUR",
    "SELEC", "SELVA", "SERNT", "SEYKM", "SILVR", "SISE", "SKBNK", "SKTAS", "SKYLP", "SKYMD",
    "SMART", "SMRTG", "SMRVA", "SNGYO", "SNICA", "SNPAM", "SODSN", "SOKE", "SOKM", "SONME",
    "SRVGY", "SUMAS", "SUNTK", "SURGY", "SUWEN", "SVGYO", "TABGD", "TARKM", "TATEN", "TATGD",
    "TAVHL", "TBORG", "TCELL", "TCKRC", "TDGYO", "TEHOL", "TEKTU", "TERA", "TEZOL", "TGSAS",
    "THYAO", "TKFEN", "TKNSA", "TLMAN", "TMPOL", "TMSN", "TNZTP", "TOASO", "TRALT", "TRCAS",
    "TRENJ", "TRGYO", "TRHOL", "TRILC", "TRMET", "TSGYO", "TSKB", "TSPOR", "TTKOM", "TTRAK",
    "TUCLK", "TUKAS", "TUPRS", "TUREX", "TURGG", "TURSG", "UCAYM", "UFUK", "ULAS", "ULKER",
    "ULUFA", "ULUSE", "ULUUN", "UMPAS", "UNLU", "USAK", "VAKBN", "VAKFA", "VAKFN", "VAKKO",
    "VANGD", "VBTYZ", "VERTU", "VERUS", "VESBE", "VESTL", "VKFYO", "VKGYO", "VKING", "VRGYO",
    "VSNMD", "YAPRK", "YATAS", "YAYLA", "YBTAS", "YEOTK", "YESIL", "YGGYO", "YGYO", "YIGIT",
    "YKBNK", "YKSLN", "YONGA", "YUNSA", "YYAPI", "YYLGD", "ZEDUR", "ZERGY", "ZGYO", "ZOREN",
    "ZRGYO",
]

USA_ALL_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "META", "TSLA", "BRK.B", "JPM", "V",
    "UNH", "XOM", "JNJ", "PG", "MA",
    "HD", "AVGO", "MRK", "COST", "PEP",
]

SUPPORTED_MARKETS = {
    "BIST": {
        "label": "BIST (Türkiye)",
        "exchange": "BIST",
        "currency": "TRY",
        "symbols": BIST_ALL_TICKERS,
    },
    "USA": {
        "label": "ABD Hisseleri",
        "exchange": "NASDAQ/NYSE",
        "currency": "USD",
        "symbols": USA_ALL_TICKERS,
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
    "MPARK", "INDES", "LOGO", "QUAGR", "BERA",
    "VERUS", "EUPWR", "KLSER", "PAPIL", "ARDYZ",
    "CWENE", "TURSG", "ISMEN", "ZOREN", "SARKY",
    "AYDEM", "ODAS", "BRSAN", "VESBE", "PENTA",
    "MAVI", "DOAS", "TMSN", "NETAS", "GLYHO",
    "ANHYT", "ANELE", "KERVT", "KCAER", "AHGAZ",
    "BIOEN", "EGEEN", "GEDZA", "GOODY", "KARTN",
    "KLRHO", "KUYAS", "MAGEN", "OZKGY", "SILVR",
    "TMPOL", "TUKAS", "YATAS", "ADEL", "VESTL",
    "AKFGY", "ALBRK", "ALFAS", "ANSGR", "ARSAN",
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

FALLBACK_TO_MOCK = False

MIN_ROWS_FOR_SCORING = 3
