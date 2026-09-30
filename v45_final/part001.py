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