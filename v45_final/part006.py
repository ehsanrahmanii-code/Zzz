    if value.endswith("USDT"):
        return value
    if value.endswith("USD"):
        return value[:-3] + "USDT"
    return value + "USDT"


def _binance_symbol(symbol: str) -> str:
    return _normalize_symbol(symbol).replace("/", "")


def tf_to_ms(tf: str) -> int:
    units = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}
    if not tf or tf[-1] not in units:
        raise ValueError(f"Invalid timeframe: {tf}")
    n = int(tf[:-1])
    if n <= 0:
        raise ValueError(f"Invalid timeframe: {tf}")
    return n * units[tf[-1]]

# ============================================================
# JSON / SQLITE
# ============================================================


def _load_json(path: Path, default: Any) -> Any:
    with JSON_LOCK:
        try:
            path = _safe_app_path(path)
            if not path.is_file():
                return default
            text = path.read_text(encoding="utf-8")
            if not text.strip():
                return default
            return json.loads(text)
        except (OSError, json.JSONDecodeError, RuntimeError) as exc:
            LOGGER.warning("JSON read failed %s: %s", path, exc)
            return default


def _save_json(path: Path, data: Any) -> bool:
    with JSON_LOCK:
        try:
            path = _safe_app_path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(data, ensure_ascii=False, indent=2, default=str)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(path)
            return True
        except (OSError, TypeError, ValueError, RuntimeError) as exc:
            LOGGER.error("JSON write failed %s: %s", path, exc)
            return False


def db_conn() -> sqlite3.Connection:
    con = sqlite3.connect(str(DB_PATH), timeout=60, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA temp_store=MEMORY")
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=10000")
    return con


def init_db() -> None:
    with DB_LOCK, db_conn() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS forecasts(
            id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
            created_at REAL NOT NULL, direction TEXT NOT NULL, score REAL NOT NULL,
            alignment REAL NOT NULL DEFAULT 0, price REAL NOT NULL, sl REAL, tp1 REAL, tp2 REAL,
            horizon_minutes INTEGER NOT NULL, outcome TEXT DEFAULT 'PENDING', evaluated_at REAL,
            hit_type TEXT, source TEXT DEFAULT 'quant', ai_majority TEXT DEFAULT '',
            ai_agreement REAL DEFAULT 0, fused_score REAL DEFAULT 0, success_prob REAL DEFAULT 0,
            predicted_move_pct REAL DEFAULT 0)""")
        for _col, _typ in (
            ("ai_majority", "TEXT DEFAULT ''"),
            ("ai_agreement", "REAL DEFAULT 0"),
            ("fused_score", "REAL DEFAULT 0"),
            ("success_prob", "REAL DEFAULT 0"),
            ("predicted_move_pct", "REAL DEFAULT 0"),
        ):
            try:
                con.execute(f"ALTER TABLE forecasts ADD COLUMN {_col} {_typ}")
            except Exception:
                pass
        con.execute("CREATE INDEX IF NOT EXISTS idx_forecasts_pending ON forecasts(outcome, created_at)")
        con.execute("""CREATE TABLE IF NOT EXISTS paper_trades(
            id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
            created_at REAL NOT NULL, decision TEXT NOT NULL, entry REAL NOT NULL, sl REAL, tp1 REAL,
            tp2 REAL, quantity REAL DEFAULT 0, risk_pct REAL DEFAULT 0, status TEXT DEFAULT 'OPEN',
            exit_price REAL, pnl_pct REAL, r_multiple REAL, closed_at REAL, reason TEXT DEFAULT 'signal',
            success_prob REAL DEFAULT 0)""")
        try:
            con.execute("ALTER TABLE paper_trades ADD COLUMN success_prob REAL DEFAULT 0")
        except Exception:
            pass
        con.execute("CREATE INDEX IF NOT EXISTS idx_paper_open ON paper_trades(status, created_at)")
        con.execute("""CREATE TABLE IF NOT EXISTS data_quality(
            id INTEGER PRIMARY KEY AUTOINCREMENT, created_at REAL NOT NULL, symbol TEXT, source TEXT,
            latency_ms REAL, candles_ok INTEGER, volume_ok INTEGER, funding_ok INTEGER, oi_ok INTEGER,
            macro_ok INTEGER, overall_ok INTEGER, details TEXT)""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_quality_time ON data_quality(created_at)")
        con.execute("""CREATE TABLE IF NOT EXISTS ai_votes(
            id INTEGER PRIMARY KEY AUTOINCREMENT, created_at REAL NOT NULL, symbol TEXT NOT NULL,
            provider TEXT NOT NULL, direction TEXT, titan_direction TEXT, aligned INTEGER, latency_ms REAL)""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_ai_votes_symbol ON ai_votes(symbol, created_at)")
        con.execute("""CREATE TABLE IF NOT EXISTS alerts(
            id INTEGER PRIMARY KEY AUTOINCREMENT, created_at REAL NOT NULL, severity TEXT,
            symbol TEXT, category TEXT, message TEXT, acknowledged INTEGER DEFAULT 0)""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_alerts_time ON alerts(created_at)")
        con.execute("""CREATE TABLE IF NOT EXISTS performance_snapshots(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            created_at REAL NOT NULL,
            trades INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            win_rate REAL DEFAULT 0,
            expectancy REAL DEFAULT 0,
            profit_factor REAL,
            max_drawdown REAL DEFAULT 0,
            sharpe REAL DEFAULT 0,
            sortino REAL DEFAULT 0,
            oos_status TEXT DEFAULT '',
            metrics_json TEXT DEFAULT ''
        )""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_perf_snap ON performance_snapshots(symbol,timeframe,created_at)")
        con.execute("""CREATE TABLE IF NOT EXISTS setup_stats(
            setup_key TEXT PRIMARY KEY, trades INTEGER DEFAULT 0, wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0, pnl_r REAL DEFAULT 0, updated_at REAL DEFAULT 0)""")

init_db()


def load_settings() -> None:
    global USER_SETTINGS
    data = _load_json(USER_SETTINGS_PATH, {})
    if not isinstance(data, dict):
        return
    risk = clamp(safe_float(data.get("risk_multiplier"), 1.2), 0.2, 5.0)
    normalized: list[str] = []
    for coin in data.get("active_coins", []) if isinstance(data.get("active_coins"), list) else []:
        symbol = _normalize_symbol(coin)
        if symbol and symbol not in normalized:
            normalized.append(symbol)
    USER_SETTINGS = {"risk_multiplier": risk, "active_coins": normalized or DEFAULT_COINS.copy()}


def save_settings() -> bool:
    return _save_json(USER_SETTINGS_PATH, USER_SETTINGS)

load_settings()

# ============================================================
# HTTP / MARKET DATA
# ============================================================


def _request_json(method: str, url: str, **kwargs) -> Optional[Any]:
    try:
        response = _http_session().request(method, url, **kwargs)
        if not response.ok:
            LOGGER.warning("HTTP %s %s -> %s", method, url, response.status_code)
            return None
        payload = response.json()
        # Binance and other APIs can legitimately return either an object or a
        # list. Keep the transport layer lossless and let callers validate shape.
        return payload
    except (requests.RequestException, ValueError) as exc:
        LOGGER.warning("HTTP request failed %s: %s", url, exc)
        return None


def _fetch_live_prices(symbols: list[str]) -> dict[str, float]:
    """Fetch all requested Binance spot prices in one batch call.

    The old implementation made one HTTP request per symbol every polling cycle.
    That created avoidable latency/rate-limit pressure and could leave cards on
    different timestamps.  Batch ticker data gives one coherent market snapshot.
    """
    requested = {_normalize_symbol(s): _normalize_symbol_for_binance(s) for s in symbols if s}
    if not requested:
        return {}
    wanted_pairs = set(requested.values())
    hosts = LIVE_PRICE_URLS if "LIVE_PRICE_URLS" in globals() else [LIVE_PRICE_URL]
    last_error = None
    for url in hosts:
        try:
            response = _http_session().get(url, timeout=5)
            if not response.ok:
                last_error = RuntimeError(f"HTTP {response.status_code} from {url}")
                continue
            payload = response.json()
            if not isinstance(payload, list):
                last_error = RuntimeError("Invalid Binance ticker payload")
                continue
            by_pair = {}
            for row in payload:
                if not isinstance(row, dict):
                    continue
                pair = str(row.get("symbol") or "").upper()
                if pair not in wanted_pairs:
                    continue
                px = safe_float(row.get("price"), 0.0)
                if px > 0:
                    by_pair[pair] = px
            result = {}
            for sym, pair in requested.items():
                px = by_pair.get(pair)
                if px is not None and px > 0:
                    result[sym] = px
            if result:
                return result
        except Exception as exc:
            last_error = exc
            LOGGER.debug("Batch live price unavailable via %s: %s", url, exc)
    if last_error:
        LOGGER.debug("All batch live price hosts failed: %s", last_error)
    return {}


def fetch_klines(symbol: str, tf: str, limit: int = 150, start_ms: Optional[int] = None, end_ms: Optional[int] = None) -> pd.DataFrame:
    """Fetch closed OHLCV with short TTL memory cache + fast numeric path.

    Cache key includes symbol/tf/limit/range so historical backtests stay uncached
    when start/end are set; live dashboard hits are almost free within TTL.
    """
    limit = min(max(int(limit), 1), 1000)
    cacheable = start_ms is None and end_ms is None
    ckey = _kline_cache_key(symbol, tf, limit, start_ms, end_ms) if cacheable else ""
    if cacheable:
        hit = _kline_cache_get(ckey)
        if hit is not None and len(hit) >= 10:
            return hit

    params: dict[str, Any] = {"symbol": _binance_symbol(symbol), "interval": tf, "limit": limit}
    if start_ms is not None:
        params["startTime"] = int(start_ms)
    if end_ms is not None:
        params["endTime"] = int(end_ms)
    raw = None
    last_err = None
    # Prefer data-api first; shorter timeout on failover hosts for snappy mobile UX
    hosts = KLINES_URLS if "KLINES_URLS" in globals() else ["https://data-api.binance.vision/api/v3/klines"]
    for i, kurl in enumerate(hosts):
        try:
            to = 5 if i == 0 else 3
            response = _http_session().get(kurl, params=params, timeout=to)
            if not response.ok:
                last_err = RuntimeError(f"HTTP {response.status_code} from {kurl}")
                continue
            raw = response.json()
            break
        except Exception as exc:
            last_err = exc
            LOGGER.debug("klines fail %s: %s", kurl, exc)
    if raw is None:
        raise RuntimeError(f"All kline hosts failed: {last_err}")
    if not isinstance(raw, list) or not raw:
        raise RuntimeError("Invalid Binance kline response")

    # Fast path: build from list-of-lists without per-column to_numeric loops
    # Columns: 0=t 1=o 2=h 3=l 4=c 5=v 6=T
    try:
        arr = np.asarray(raw, dtype=object)
        t = arr[:, 0].astype(np.float64)
        o = arr[:, 1].astype(np.float64)
        h = arr[:, 2].astype(np.float64)
        l = arr[:, 3].astype(np.float64)
        c = arr[:, 4].astype(np.float64)
        v = arr[:, 5].astype(np.float64)
        T = arr[:, 6].astype(np.float64)
        now_ms = time.time() * 1000.0
        mask = (T < now_ms) & np.isfinite(o) & np.isfinite(h) & np.isfinite(l) & np.isfinite(c) & np.isfinite(v)
        t, o, h, l, c, v, T = t[mask], o[mask], h[mask], l[mask], c[mask], v[mask], T[mask]
        # sort + dedupe by t (keep last)
        order = np.argsort(t, kind="mergesort")
        t, o, h, l, c, v, T = t[order], o[order], h[order], l[order], c[order], v[order], T[order]
        if len(t) > 1:
            uniq = np.empty(len(t), dtype=bool)
            uniq[:-1] = t[:-1] != t[1:]
            uniq[-1] = True
            # keep last of each duplicate group: reverse mark
            rev = np.empty(len(t), dtype=bool)
            rev[0] = True
            rev[1:] = t[1:] != t[:-1]
            # actually keep last: mark where next differs or last
            keep = np.ones(len(t), dtype=bool)
            keep[:-1] = t[:-1] != t[1:]
            t, o, h, l, c, v, T = t[keep], o[keep], h[keep], l[keep], c[keep], v[keep], T[keep]
        df = pd.DataFrame({"t": t, "open": o, "high": h, "low": l, "close": c, "vol": v, "T": T})
    except Exception:
        columns = ["t", "open", "high", "low", "close", "vol", "T", "qav", "n", "tbb", "tbq", "ign"]
        df = pd.DataFrame(raw, columns=columns)
        for col in ["open", "high", "low", "close", "vol", "t", "T"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["t", "open", "high", "low", "close", "vol"])