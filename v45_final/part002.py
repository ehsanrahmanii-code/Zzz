        retry = Retry(
            total=3, connect=3, read=3, backoff_factor=0.6,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "HEAD", "OPTIONS"]),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=48, pool_maxsize=48)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        _HTTP_LOCAL.session = session
    return session

# ============================================================
# API KEYS - FILE ONLY
# ============================================================

OPENAI_API_KEY = ""
GEMINI_API_KEY = ""
GROK_API_KEY = ""
CLAUDE_API_KEY = ""
DEEPSEEK_API_KEY = ""
COINGLASS_API_KEY = ""

KEY_FILES = {
    "OPENAI_API_KEY": ["openai_api_key.txt", "chatgpt_api_key.txt", "titan_llm_key.txt"],
    "GEMINI_API_KEY": ["gemini_api_key.txt", "gemini_key.txt", "api gemini_key.txt"],
    "GROK_API_KEY": ["grok_api_key.txt", "xai_api_key.txt", "grok_key.txt"],
    "CLAUDE_API_KEY": ["claude_api_key.txt", "anthropic_api_key.txt", "claude_key.txt"],
    "DEEPSEEK_API_KEY": ["deepseek_api_key.txt", "deepseek_key.txt"],
    "COINGLASS_API_KEY": ["coinglass_api_key.txt", "coinglass_key.txt"],
}


def _clean_key(value: str) -> str:
    value = (value or "").lstrip("\ufeff").strip()
    if not value:
        return ""
    if "=" in value and "\n" not in value:
        left, right = value.split("=", 1)
        normalized = left.strip().upper().replace("_", "").replace("-", "")
        if normalized.endswith("APIKEY"):
            value = right.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1].strip()
    return value


def _read_key(name: str) -> str:
    for filename in KEY_FILES.get(name, []):
        for base in (SECRETS_DIR, APP_HOME, DATA_DIR):
            path = base / filename
            try:
                if path.is_file():
                    value = _clean_key(path.read_text(encoding="utf-8"))
                    if value:
                        return value
            except OSError as exc:
                LOGGER.warning("Key read failed for %s: %s", filename, exc)
    return ""


def reload_keys() -> None:
    global OPENAI_API_KEY, GEMINI_API_KEY, GROK_API_KEY, CLAUDE_API_KEY, DEEPSEEK_API_KEY, COINGLASS_API_KEY
    with KEY_LOCK:
        OPENAI_API_KEY = _read_key("OPENAI_API_KEY")
        GEMINI_API_KEY = _read_key("GEMINI_API_KEY")
        GROK_API_KEY = _read_key("GROK_API_KEY")
        CLAUDE_API_KEY = _read_key("CLAUDE_API_KEY")
        DEEPSEEK_API_KEY = _read_key("DEEPSEEK_API_KEY")
        COINGLASS_API_KEY = _read_key("COINGLASS_API_KEY")

reload_keys()

# ============================================================
# DEFAULTS / HELPERS
# ============================================================

DEFAULT_COINS = [
    "BTC/USDT",
    "ETH/USDT",
    "BNB/USDT",
    "XRP/USDT",
    "SOL/USDT",
    "ADA/USDT",
    "DOGE/USDT",
    "AVAX/USDT",
    "LINK/USDT",
    "NEAR/USDT",
    "SUI/USDT",
    "TAO/USDT",
    "AAVE/USDT",
    "BCH/USDT",
    "XLM/USDT",
    "TRX/USDT",
    "SHIB/USDT",
    "PEPE/USDT",
    "WIF/USDT",
    "FLOKI/USDT",
    "CAKE/USDT",
    "HYPE/USDT",
    "ZEC/USDT",
    "XAUT/USDT",
]
LIVE_PRICE_URL = "https://data-api.binance.vision/api/v3/ticker/price"
BINANCE_REST_HOSTS = [
    "https://data-api.binance.vision",
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
]
LIVE_PRICE_URLS = [f"{h}/api/v3/ticker/price" for h in BINANCE_REST_HOSTS]
KLINES_URLS = [f"{h}/api/v3/klines" for h in BINANCE_REST_HOSTS]


def _safe_startup_check():
    """Basic production startup validation."""
    try:
        APP_HOME.mkdir(parents=True, exist_ok=True)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        init_db()
        return True
    except Exception as exc:
        LOGGER.exception("Startup validation failed: %s", exc)
        return False
TF_CFG = {
    "15m": {"horizon": 60, "weight": 0.15},
    "1h": {"horizon": 240, "weight": 0.25},
    "4h": {"horizon": 720, "weight": 0.30},
    "1d": {"horizon": 2880, "weight": 0.30},
}

USER_SETTINGS = {"risk_multiplier": 1.2, "active_coins": DEFAULT_COINS.copy()}
CACHE = {"timestamp": 0.0, "data": [], "gemini_summary": "", "macro": {}}
OI_HISTORY: dict[str, tuple[float, float, str]] = {}
LIVE_PRICES: dict[str, dict[str, Any]] = {}
LIVE_LOCK = threading.RLock()
LIVE_STOP = threading.Event()
LIVE_THREADS: list[threading.Thread] = []

COIN_META = {
    "BTC": ("Bitcoin", "₿"), "ETH": ("Ethereum", "Ξ"), "XRP": ("XRP", "✕"),
    "SOL": ("Solana", "◎"), "SHIB": ("Shiba Inu", "🐕"), "BNB": ("BNB", "◆"),
    "ZEC": ("Zcash", "ⓩ"), "ADA": ("Cardano", "₳"), "TRX": ("TRON", "⚡"),
    "HYPE": ("Hyperliquid", "🌊"), "DOGE": ("Dogecoin", "Ð"), "WIF": ("dogwifhat", "🐶"),
    "PEPE": ("Pepe", "🐸"), "AVAX": ("Avalanche", "🔺"), "FLOKI": ("Floki", "🐺"),
    "CAKE": ("PancakeSwap", "🥞"), "BCH": ("Bitcoin Cash", "Ƀ"), "XLM": ("Stellar", "✦"),
    "AAVE": ("Aave", "👻"), "SUI": ("Sui", "💧"), "TAO": ("Bittensor", "🧠"),
    "LINK": ("Chainlink", "⬡"), "NEAR": ("NEAR", "Ⓝ"), "XAUT": ("Tether Gold", "🥇"),
}


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default




# === TITAN ULTRA TECHNICAL LAYER ===

def calculate_auto_fibonacci(high, low):
    diff=float(high)-float(low)
    return {
        "0.236": round(float(high)-diff*0.236,8),
        "0.382": round(float(high)-diff*0.382,8),
        "0.500": round(float(high)-diff*0.500,8),
        "0.618": round(float(high)-diff*0.618,8),
        "0.786": round(float(high)-diff*0.786,8),
    }

def calculate_support_resistance(closes, window=20):
    vals=list(map(float, closes[-window:])) if closes else []
    if not vals:
        return {"support":None,"resistance":None}
    return {"support":min(vals),"resistance":max(vals)}

def technical_layers(df):
    close=df["close"].astype(float)
    mid=close.rolling(20).mean()
    std=close.rolling(20).std()
    high=float(df["high"].max()); low=float(df["low"].min())
    return {
        "bollinger": {"upper":float((mid+2*std).iloc[-1]), "middle":float(mid.iloc[-1]), "lower":float((mid-2*std).iloc[-1])},
        "fibonacci": calculate_auto_fibonacci(high,low),
        "support_resistance": calculate_support_resistance(close.tolist())
    }

# === TITAN V6 ADVANCED TECHNICAL SUITE ===
def calc_macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, float]:
    """MACD line, signal, histogram — fail-safe."""
    try:
        c = close.astype(float)
        if len(c) < slow + signal:
            return {"macd": 0.0, "signal": 0.0, "hist": 0.0, "cross": "none"}
        ema_f = c.ewm(span=fast, adjust=False).mean()
        ema_s = c.ewm(span=slow, adjust=False).mean()
        macd = ema_f - ema_s
        sig = macd.ewm(span=signal, adjust=False).mean()
        hist = macd - sig
        h0, h1 = float(hist.iloc[-1]), float(hist.iloc[-2]) if len(hist) > 1 else 0.0
        cross = "bull" if h1 <= 0 < h0 else "bear" if h1 >= 0 > h0 else "none"
        return {"macd": round(float(macd.iloc[-1]), 8), "signal": round(float(sig.iloc[-1]), 8),
                "hist": round(h0, 8), "cross": cross}
    except Exception:
        return {"macd": 0.0, "signal": 0.0, "hist": 0.0, "cross": "none"}


def calc_stoch_rsi(close: pd.Series, rsi_period: int = 14, stoch_period: int = 14, k: int = 3, d: int = 3) -> dict[str, float]:
    """Stochastic RSI for timing entries on oversold/overbought extremes."""
    try:
        rsi = wilder_rsi(close, rsi_period)
        if len(rsi) < stoch_period + d:
            return {"k": 50.0, "d": 50.0, "zone": "mid"}
        rmin = rsi.rolling(stoch_period).min()
        rmax = rsi.rolling(stoch_period).max()
        stoch = 100 * (rsi - rmin) / (rmax - rmin).replace(0, np.nan)
        k_line = stoch.rolling(k).mean().fillna(50)
        d_line = k_line.rolling(d).mean().fillna(50)
        kv, dv = float(k_line.iloc[-1]), float(d_line.iloc[-1])
        zone = "oversold" if kv < 20 else "overbought" if kv > 80 else "mid"
        return {"k": round(kv, 2), "d": round(dv, 2), "zone": zone}
    except Exception:
        return {"k": 50.0, "d": 50.0, "zone": "mid"}


def calc_pivot_points(df: pd.DataFrame) -> dict[str, float]:
    """Classic daily pivots from last closed candle high/low/close."""
    try:
        if df is None or len(df) < 2:
            return {}
        row = df.iloc[-1]
        h, l, c = float(row["high"]), float(row["low"]), float(row["close"])
        pp = (h + l + c) / 3.0
        r1 = 2 * pp - l
        s1 = 2 * pp - h
        r2 = pp + (h - l)
        s2 = pp - (h - l)
        r3 = h + 2 * (pp - l)
        s3 = l - 2 * (h - pp)
        return {k: round(v, 8) for k, v in (("pp", pp), ("r1", r1), ("r2", r2), ("r3", r3), ("s1", s1), ("s2", s2), ("s3", s3))}
    except Exception:
        return {}


def calc_volume_delta(df: pd.DataFrame, lookback: int = 24) -> dict[str, float]:
    """Proxy CVD from candle body direction * volume (no tick data required)."""
    try:
        x = df.tail(lookback).copy()
        if x.empty:
            return {"delta": 0.0, "buy_vol": 0.0, "sell_vol": 0.0, "delta_pct": 0.0}
        body_up = (x["close"] >= x["open"]).astype(float)
        buy_v = float((x["vol"] * body_up).sum())
        sell_v = float((x["vol"] * (1 - body_up)).sum())
        total = buy_v + sell_v
        delta = buy_v - sell_v
        return {
            "delta": round(delta, 4),
            "buy_vol": round(buy_v, 4),
            "sell_vol": round(sell_v, 4),
            "delta_pct": round((delta / total * 100) if total > 0 else 0.0, 2),
        }
    except Exception:
        return {"delta": 0.0, "buy_vol": 0.0, "sell_vol": 0.0, "delta_pct": 0.0}


def market_session_utc() -> dict[str, Any]:
    """Current major session and overlap (analysis-only context)."""
    hour = datetime.now(timezone.utc).hour
    if 0 <= hour < 8:
        name, risk_mult = "Asia", 0.95
    elif 8 <= hour < 13:
        name, risk_mult = "London", 1.05
    elif 13 <= hour < 17:
        name, risk_mult = "London-NY Overlap", 1.12
    elif 17 <= hour < 21:
        name, risk_mult = "New York", 1.05
    else:
        name, risk_mult = "Off-hours", 0.88
    return {"session": name, "hour_utc": hour, "liquidity_boost": risk_mult}




# === TITAN PATTERN + FUTURE CANDLE FORECAST ENGINE ===
PATTERN_GUIDE = {
    "سرشانه": {
        "name_en": "Head & Shoulders",
        "meaning": "الگوی بازگشتی نزولی: سه قله که قله میانی (سر) بالاتر از دو شانه است. خط گردن اتصال کف‌های بین شانه و سر است.",
        "expect": "با شکست معتبر خط گردن به سمت پایین، انتظار ادامه نزول تا اندازه ارتفاع سر تا خط گردن وجود دارد. حد ضرر بالای شانه راست.",
        "bias": "نزولی",
    },
    "سرشانه معکوس": {
        "name_en": "Inverse Head & Shoulders",
        "meaning": "الگوی بازگشتی صعودی: سه کف که کف میانی (سر) پایین‌تر از دو شانه است.",
        "expect": "با شکست خط گردن به بالا، انتظار رشد تا اندازه ارتفاع الگو. حد ضرر زیر شانه راست.",
        "bias": "صعودی",
    },