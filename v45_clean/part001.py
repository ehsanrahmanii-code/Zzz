from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import sqlite3
import statistics
import sys
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from logging.handlers import RotatingFileHandler

import numpy as np
import pandas as pd
import requests
from flask import Flask, jsonify, redirect, render_template_string, request, url_for
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    import websocket as _websocket_client
except Exception:
    _websocket_client = None

# ============================================================
# TITAN
# Technical layers: Fibonacci / Support-Resistance / Multi TF scoring integrated ENTERPRISE V32 Desktop edition
# Analysis only. No order execution.
# Persistent files remain under APP_HOME.
# ============================================================

# Android/Desktop production storage roots are deterministic and do not depend on
# the current working directory, executable location, profile directory, or a
# caller-supplied TITAN_HOME variable. TITAN data/cache/memory/logs/secrets are
# intentionally kept together under one user-visible folder.
# Android-first single-root storage. This build intentionally has NO desktop
# fallback: if shared storage is unavailable, TITAN stops instead of silently
# writing into the script directory, /tmp, the current working directory, or
# another application cache.
TITAN_ANDROID_HOME = Path("/storage/emulated/0/AI TAITAN AI")

def _select_app_home() -> Path:
    """Prefer Android shared storage; optional TITAN_HOME; safe desktop fallback for lab use.

    Production Android still hard-locks under /storage/emulated/0/AI TAITAN AI.
    On non-Android hosts (desktop/CI), TITAN_HOME or ./AI_TAITAN_AI is used so the
    engine can start without crashing, while never silently writing into /tmp.
    """
    if Path("/storage/emulated/0").exists():
        return TITAN_ANDROID_HOME
    env_home = (os.environ.get("TITAN_HOME") or "").strip()
    if env_home:
        return Path(env_home).expanduser().resolve()
    lab = Path(__file__).resolve().parent / "AI_TAITAN_AI"
    return lab

APP_HOME = _select_app_home()
DATA_DIR = APP_HOME / "data"
CACHE_DIR = APP_HOME / "cache"
MEMORY_DIR = APP_HOME / "memory"
SECRETS_DIR = APP_HOME / "secrets"
LOG_DIR = DATA_DIR

for directory in (APP_HOME, DATA_DIR, CACHE_DIR, MEMORY_DIR, SECRETS_DIR):
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as _mkdir_exc:
        print(f"TITAN mkdir warning: {directory} -> {_mkdir_exc}")

DB_PATH = DATA_DIR / "titan_enterprise.db"
LOG_PATH = LOG_DIR / "titan_engine.log"
AI_CACHE_PATH = CACHE_DIR / "ai_responses.json"
MARKET_CACHE_PATH = CACHE_DIR / "market_cache.json"
USER_SETTINGS_PATH = DATA_DIR / "user_settings.json"
MODEL_SETTINGS_PATH = DATA_DIR / "model_settings.json"
AI_SYMBOL_CACHE_PATH = CACHE_DIR / "ai_symbol_responses.json"


def _startup_storage_audit() -> dict[str, Any]:
    """Verify and enforce the single Android storage root before services start."""
    root = APP_HOME.resolve()
    required = (DATA_DIR, CACHE_DIR, MEMORY_DIR, SECRETS_DIR)
    root.mkdir(parents=True, exist_ok=True)
    for directory in required:
        directory.mkdir(parents=True, exist_ok=True)
        try:
            directory.resolve().relative_to(root)
        except ValueError:
            raise RuntimeError(f"TITAN storage escape: {directory}")
    probe = root / ".titan_storage_probe"
    try:
        probe.write_text("TITAN_STORAGE_OK", encoding="utf-8")
        if probe.read_text(encoding="utf-8") != "TITAN_STORAGE_OK":
            raise OSError("storage verification mismatch")
    finally:
        try:
            probe.unlink()
        except OSError:
            pass
    persistent = (DB_PATH, LOG_PATH, AI_CACHE_PATH, MARKET_CACHE_PATH,
                  USER_SETTINGS_PATH, MODEL_SETTINGS_PATH, AI_SYMBOL_CACHE_PATH)
    for path in persistent:
        try:
            path.resolve().relative_to(root)
        except ValueError:
            raise RuntimeError(f"Persistent path escaped TITAN root: {path}")
    return {"root": str(root), "writable": True, "persistent_paths_locked": True}


STARTUP_STORAGE_AUDIT = _startup_storage_audit()

# V29 autonomous loop:
# - live prices are streamed/polled continuously;
# - the expensive multi-timeframe scan runs automatically in the background;
# - outcome/performance learning is maintained independently of page requests;
# - Gemini enrichment is asynchronous and is fed back into the next scan.
AUTO_SCAN_INTERVAL_SECONDS = 45
AUTO_MAINTENANCE_INTERVAL_SECONDS = 20
AUTO_AI_TOP_N = 6
AUTO_AI_REFRESH_SECONDS = 180

MARKET_CACHE_TTL = 40
# Fast dashboard scan: skip external LLM calls during bulk market refresh (biggest latency win).
# Detail endpoints can still request AI on demand.
DASHBOARD_FAST_SCAN = True
RENDER_PERF_LOG = True
AI_CACHE_TTL = 180
LIVE_PRICE_POLL_SECONDS = 2
MAX_BACKTEST_CANDLES = 5000
SIGNAL_COOLDOWN_SECONDS = 2700
MIN_DIRECTIONAL_QUALITY = 50
MIN_PRECISION_SCORE = 48
MIN_TREND_STABILITY = 0.38
MAX_STRETCH_ATR = 2.8
MIN_EFFECTIVE_RR = 1.10
HTTP_TIMEOUT = 15
FEE_RATE = 0.0004
SPREAD_RATE = 0.0002
SLIPPAGE_RATE = 0.0002
TOTAL_ENTRY_BUFFER = FEE_RATE + SPREAD_RATE + SLIPPAGE_RATE

# --- V8 Professional confidence gates ---
# V28.5: deep audit — residual WAIT kills softened, hero board fixed,
# refine_bias balanced, neural demotion only on real conflict.
TITAN_PARAM_VERSION = "V41.0-ANDROID-BALANCED-OPPORTUNITY"
MAX_LIVE_PRICE_AGE_SEC = 12.0
MIN_CLOSED_CANDLES_1H = 48
MIN_CLOSED_CANDLES_15M = 35
MIN_DATA_QUALITY_SCORE = 52
ENTRY_LADDER_MIN_HTF_SCORE = 50
ENTRY_LADDER_MIN_MTF_SCORE = 50
ENTRY_LADDER_MIN_LTF_ALIGN = 0.0  # soft; hard check is direction match
MAX_PORTFOLIO_SAME_SIDE = 3
FORECAST_TRACK_PATH = None  # set after APP_HOME exists
CALIB_MIN_SAMPLES_FULL = 20
CALIB_CAP_LOW_N = 62.0
CALIB_CAP_MID_N = 72.0
CALIB_CAP_HIGH_N = 86.0

sys.dont_write_bytecode = True

# ============================================================
# LOGGING / SAFETY
# ============================================================

LOGGER = logging.getLogger("TITAN")
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False
if not LOGGER.handlers:
    _file_handler = RotatingFileHandler(
        LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    _file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    LOGGER.addHandler(_file_handler)


def _now_iso() -> str:
    """Return a timezone-aware UTC timestamp for dashboard/cache metadata."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

CACHE_LOCK = threading.RLock()
DB_LOCK = threading.RLock()
JSON_LOCK = threading.RLock()
_HTTP_LOCAL = threading.local()
KEY_LOCK = threading.RLock()
OI_LOCK = threading.RLock()
UPDATE_LOCK = threading.Lock()

# --- V9 Performance: shared pools + short-TTL kline/derivative memory cache ---
KLINE_CACHE: dict[str, tuple[float, "pd.DataFrame"]] = {}
KLINE_CACHE_LOCK = threading.RLock()
KLINE_CACHE_TTL = 28.0          # seconds — closed candles change slowly
KLINE_CACHE_MAX = 240           # hard cap entries (symbols × TFs)
DERIV_CACHE: dict[str, tuple[float, dict]] = {}
DERIV_CACHE_TTL = 30.0
_ANALYSIS_POOL: Optional[ThreadPoolExecutor] = None
_ANALYSIS_POOL_LOCK = threading.Lock()
_KLINE_POOL: Optional[ThreadPoolExecutor] = None
_KLINE_POOL_LOCK = threading.Lock()


def _get_analysis_pool(size: int = 6) -> ThreadPoolExecutor:
    global _ANALYSIS_POOL
    with _ANALYSIS_POOL_LOCK:
        if _ANALYSIS_POOL is None:
            # Cap workers: network-bound; too many just fight DNS/SSL on mobile.
            n = max(3, min(int(size), 6))
            _ANALYSIS_POOL = ThreadPoolExecutor(max_workers=n, thread_name_prefix="titan-an")
        return _ANALYSIS_POOL


def _get_kline_pool(size: int = 4) -> ThreadPoolExecutor:
    global _KLINE_POOL
    with _KLINE_POOL_LOCK:
        if _KLINE_POOL is None:
            _KLINE_POOL = ThreadPoolExecutor(max_workers=max(2, min(int(size), 4)), thread_name_prefix="titan-kl")
        return _KLINE_POOL


_AI_POOL: Optional[ThreadPoolExecutor] = None
_AI_POOL_LOCK = threading.Lock()
DERIV_CACHE_MAX = 80


def _append_capped(target: list, value: Any, max_items: int = 256) -> None:
    """Append to an in-memory history without allowing unbounded growth."""
    target.append(value)
    overflow = len(target) - int(max_items)
    if overflow > 0:
        del target[:overflow]


def _get_ai_pool(size: int = 2) -> ThreadPoolExecutor:
    """Reuse one AI thread pool across symbols (avoids create/destroy per coin)."""
    global _AI_POOL
    with _AI_POOL_LOCK:
        if _AI_POOL is None:
            _AI_POOL = ThreadPoolExecutor(max_workers=size, thread_name_prefix="titan-ai")
        return _AI_POOL


def _kline_cache_key(symbol: str, tf: str, limit: int, start_ms: Optional[int], end_ms: Optional[int]) -> str:
    return f"{_binance_symbol(symbol)}|{tf}|{limit}|{start_ms or 0}|{end_ms or 0}"


def _kline_cache_get(key: str) -> Optional["pd.DataFrame"]:
    with KLINE_CACHE_LOCK:
        row = KLINE_CACHE.get(key)
        if not row:
            return None
        ts, df = row
        if time.time() - ts > KLINE_CACHE_TTL:
            KLINE_CACHE.pop(key, None)
            return None
        # Never hand out the mutable cached frame itself; one consumer must not
        # be able to corrupt another concurrent analysis.
        return df.copy(deep=False)


def _kline_cache_put(key: str, df: "pd.DataFrame") -> None:
    with KLINE_CACHE_LOCK:
        # Keep a private immutable-by-convention snapshot. Consumers receive a
        # shallow copy on read, preventing accidental index/column mutations.
        KLINE_CACHE[key] = (time.time(), df.copy(deep=False))
        if len(KLINE_CACHE) > KLINE_CACHE_MAX:
            # drop oldest ~20%
            items = sorted(KLINE_CACHE.items(), key=lambda x: x[1][0])
            for k, _ in items[: max(1, len(items) // 5)]:
                KLINE_CACHE.pop(k, None)



def _safe_app_path(path: Path) -> Path:
    candidate = Path(path).resolve()
    root = APP_HOME.resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise RuntimeError(f"TITAN path escaped APP_HOME: {candidate}")
    return candidate


def _http_session() -> requests.Session:
    """Return one requests.Session per worker thread.

    requests.Session is not guaranteed to be safely mutable across concurrent
    workers; TITAN performs many parallel market/API calls. Thread-local sessions
    preserve connection pooling without sharing mutable session state.
    """
    session = getattr(_HTTP_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update({"User-Agent": "TITAN-ENTERPRISE/3.0", "Accept": "application/json"})
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