                out["source"] = (out.get("source") or "") + "+TopTrader"
    except Exception as exc:
        LOGGER.debug("Top trader ratio failed %s: %s", symbol, exc)
    return out


def fetch_binance_taker_buy_sell(symbol: str) -> dict[str, Any]:
    """Taker buy/sell volume ratio — real order-flow proxy."""
    pair = _binance_symbol(symbol)
    try:
        r = _http_session().get(
            "https://fapi.binance.com/futures/data/takerlongshortRatio",
            params={"symbol": pair, "period": "1h", "limit": 1},
            timeout=8,
        )
        if r.ok:
            data = r.json()
            if isinstance(data, list) and data:
                row = data[-1]
                buy = safe_float(row.get("buyVol"))
                sell = safe_float(row.get("sellVol"))
                ratio = safe_float(row.get("buySellRatio"))
                total = buy + sell
                return {
                    "buy_vol": buy, "sell_vol": sell,
                    "buy_sell_ratio": round(ratio, 4) if ratio else None,
                    "buy_pct": round(buy / total * 100, 1) if total > 0 else 50.0,
                    "sell_pct": round(sell / total * 100, 1) if total > 0 else 50.0,
                    "source": "Binance-Taker",
                }
    except Exception as exc:
        LOGGER.debug("Taker ratio failed %s: %s", symbol, exc)
    return {"buy_pct": 50.0, "sell_pct": 50.0, "buy_sell_ratio": None, "source": "N/A"}


def _ls_bias(ls: dict[str, Any], direction_wanted: int) -> tuple[float, str]:
    """Crowd positioning bias: extreme long crowding is short-friendly and vice versa."""
    ratio = safe_float(ls.get("long_short_ratio"), 1.0)
    if ratio <= 0:
        return 0.0, "فاقد داده L/S"
    if ratio >= 1.8:
        return (-5.0 if direction_wanted >= 0 else 4.0), "ازدحام شدید لانگ (ضدجمعیت نزولی)"
    if ratio >= 1.35:
        return (-2.5 if direction_wanted >= 0 else 2.0), "فشار لانگ بالا"
    if ratio <= 0.55:
        return (5.0 if direction_wanted <= 0 else -4.0), "ازدحام شدید شورت (ضدجمعیت صعودی)"
    if ratio <= 0.75:
        return (2.5 if direction_wanted <= 0 else -2.0), "فشار شورت بالا"
    return 0.0, "نسبت لانگ/شورت متعادل"



def clamp(value: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, value)))


# ============================================================
# TITAN V8 — CONFIDENCE ENGINE (Entry Ladder · DQ · Forecast Track · Portfolio)
# Analysis-only. Raises bar for LONG/SHORT; never invents edge.
# ============================================================

_FORECAST_TRACK_LOCK = threading.RLock()
_PORTFOLIO_SIGNAL_LOCK = threading.RLock()
_RECENT_DIRECTIONAL_SIGNALS: list[dict[str, Any]] = []


def _forecast_track_path() -> Path:
    return MEMORY_DIR / "forecast_path_accuracy.json"


def _load_forecast_track() -> dict[str, Any]:
    data = _load_json(_forecast_track_path(), {})
    return data if isinstance(data) else {}


def _save_forecast_track(data: dict[str, Any]) -> None:
    _save_json(_forecast_track_path(), data)


def assess_data_quality(
    *,
    symbol: str,
    price: float,
    live_age_sec: Optional[float],
    df15: Optional[pd.DataFrame],
    df1h: Optional[pd.DataFrame],
    derivatives: dict[str, Any],
    frames: Optional[dict] = None,
) -> dict[str, Any]:
    """Hard data-quality score + veto reasons. Low quality forces WAIT."""
    reasons: list[str] = []
    score = 100.0
    n15 = len(df15) if df15 is not None else 0
    n1h = len(df1h) if df1h is not None else 0
    if price <= 0:
        reasons.append("invalid_price")
        score -= 40
    if live_age_sec is None:
        score -= 8
        reasons.append("no_live_ts")
    elif live_age_sec > MAX_LIVE_PRICE_AGE_SEC:
        score -= min(25.0, 8 + (live_age_sec - MAX_LIVE_PRICE_AGE_SEC) * 0.8)
        reasons.append(f"stale_live_{live_age_sec:.0f}s")
    if n1h < MIN_CLOSED_CANDLES_1H:
        score -= 20
        reasons.append(f"thin_1h_{n1h}")
    if n15 < MIN_CLOSED_CANDLES_15M:
        score -= 12
        reasons.append(f"thin_15m_{n15}")
    if frames:
        missing = [tf for tf in ("15m", "1h", "4h", "1d") if tf not in frames or frames[tf] is None or len(frames[tf]) < 30]
        if missing:
            score -= 6 * len(missing)
            reasons.append("missing_tf:" + ",".join(missing))
    fund = derivatives.get("funding_value")
    if fund is None and str(derivatives.get("funding", "N/A")) == "N/A":
        score -= 6
        reasons.append("no_funding")
    if safe_float(derivatives.get("raw_oi"), 0) <= 0 and str(derivatives.get("oi", "N/A")) == "N/A":
        score -= 5
        reasons.append("no_oi")
    score = float(clamp(score, 0, 100))
    # Hard veto only for truly unusable data — borderline quality is soft penalty.
    hard_veto = (
        "invalid_price" in reasons
        or n1h < 25
        or score < 32
    )
    return {
        "score": round(score, 1),
        "hard_veto": hard_veto,
        "reasons": reasons,
        "live_age_sec": live_age_sec,
        "candles_1h": n1h,
        "candles_15m": n15,
        "param_version": TITAN_PARAM_VERSION,
    }


def entry_ladder_gate(
    tf_scores: dict[str, float],
    tf_results: dict[str, str],
    decision_tag: str,
    bias: str,
) -> dict[str, Any]:
    """Mandatory HTF→MTF→LTF alignment before directional signal.

    4h/1d = macro direction, 1h = setup, 15m = trigger lean.
    """
    s15 = safe_float(tf_scores.get("15m"), 50)
    s1h = safe_float(tf_scores.get("1h"), 50)
    s4h = safe_float(tf_scores.get("4h"), 50)
    s1d = safe_float(tf_scores.get("1d"), 50)
    htf = 0.55 * s4h + 0.45 * s1d
    mtf = s1h
    ltf = s15

    def _side(sc: float) -> str:
        if sc >= 54:
            return "LONG"
        if sc <= 46:
            return "SHORT"
        return "WAIT"

    htf_side, mtf_side, ltf_side = _side(htf), _side(mtf), _side(ltf)
    wanted = decision_tag if decision_tag in {"LONG", "SHORT"} else (
        "LONG" if bias == "صعودی" else "SHORT" if bias == "نزولی" else "WAIT"
    )
    passed = True
    reasons: list[str] = []
    if wanted == "LONG":
        if htf < ENTRY_LADDER_MIN_HTF_SCORE:
            passed = False
            reasons.append(f"HTF_weak_{htf:.0f}")
        if mtf < ENTRY_LADDER_MIN_MTF_SCORE:
            passed = False
            reasons.append(f"MTF_weak_{mtf:.0f}")
        if htf_side == "SHORT" or mtf_side == "SHORT":
            passed = False
            reasons.append("HTF/MTF_against_long")
        # LTF should not be strongly opposite
        if ltf <= 40:
            passed = False
            reasons.append(f"LTF_against_{ltf:.0f}")
    elif wanted == "SHORT":
        if htf > (100 - ENTRY_LADDER_MIN_HTF_SCORE):
            passed = False
            reasons.append(f"HTF_weak_short_{htf:.0f}")
        if mtf > (100 - ENTRY_LADDER_MIN_MTF_SCORE):
            passed = False
            reasons.append(f"MTF_weak_short_{mtf:.0f}")
        if htf_side == "LONG" or mtf_side == "LONG":
            passed = False
            reasons.append("HTF/MTF_against_short")
        if ltf >= 60:
            passed = False
            reasons.append(f"LTF_against_{ltf:.0f}")
    else:
        reasons.append("no_directional_want")

    strength = float(clamp(
        (abs(htf - 50) * 0.4 + abs(mtf - 50) * 0.4 + abs(ltf - 50) * 0.2),
        0, 50,
    ))
    return {
        "passed": passed if wanted in {"LONG", "SHORT"} else True,
        "wanted": wanted,
        "htf_score": round(htf, 1),
        "mtf_score": round(mtf, 1),
        "ltf_score": round(ltf, 1),
        "htf_side": htf_side,
        "mtf_side": mtf_side,
        "ltf_side": ltf_side,
        "strength": round(strength, 1),
        "reasons": reasons,
        "tf_results": tf_results,
    }


def forecast_path_accuracy_stats(symbol: str = "") -> dict[str, Any]:
    """Recent directional accuracy of 12-candle path from tracked outcomes."""
    try:
        with _FORECAST_TRACK_LOCK:
            data = _load_forecast_track()
        rows = data.get("events") or []
        if symbol:
            rows = [r for r in rows if r.get("symbol") == symbol]
        rows = rows[-200:]
        if len(rows) < 5:
            return {"samples": len(rows), "dir_acc": 0.5, "weight_scale": 0.35, "mae_pct": None}
        hits = sum(1 for r in rows if r.get("dir_hit"))
        acc = hits / max(1, len(rows))
        # Weight scale: only trust path when accuracy clearly above coin-flip
        if len(rows) < 12:
            scale = 0.40
        elif acc >= 0.58:
            scale = min(1.15, 0.7 + (acc - 0.5) * 2.0)
        elif acc >= 0.52:
            scale = 0.55
        else:
            scale = 0.20
        maes = [safe_float(r.get("mae_pct"), 0) for r in rows if r.get("mae_pct") is not None]
        return {
            "samples": len(rows),
            "dir_acc": round(acc, 3),
            "weight_scale": round(scale, 3),
            "mae_pct": round(float(sum(maes) / len(maes)), 3) if maes else None,
        }
    except Exception as exc:
        LOGGER.debug("forecast track stats: %s", exc)
        return {"samples": 0, "dir_acc": 0.5, "weight_scale": 0.35, "mae_pct": None}


def record_forecast_path_outcome(
    symbol: str,
    predicted_bias: str,
    predicted_move_pct: float,
    actual_move_pct: float,
) -> None:
    """Append path accuracy event for self-weighting of forecast layer."""
    try:
        pred_sign = 1 if predicted_bias == "صعودی" else -1 if predicted_bias == "نزولی" else 0
        act_sign = 1 if actual_move_pct > 0.05 else -1 if actual_move_pct < -0.05 else 0
        dir_hit = bool(pred_sign and act_sign and pred_sign == act_sign)
        mae = abs(predicted_move_pct - actual_move_pct)
        with _FORECAST_TRACK_LOCK:
            data = _load_forecast_track()
            ev = data.setdefault("events", [])
            ev.append({
                "ts": time.time(),
                "symbol": symbol,
                "predicted_bias": predicted_bias,
                "pred_move_pct": round(predicted_move_pct, 4),
                "actual_move_pct": round(actual_move_pct, 4),
                "dir_hit": dir_hit,
                "mae_pct": round(mae, 4),
                "version": TITAN_PARAM_VERSION,
            })
            data["events"] = ev[-500:]
            _save_forecast_track(data)
    except Exception as exc:
        LOGGER.debug("record forecast path: %s", exc)


def calibrate_success_probability_v8(
    symbol: str = "",
    direction: str = "",
    raw_prob: float = 50.0,
    regime: str = "",
) -> dict[str, Any]:
    """Regime- and side-aware calibration with honest sample caps."""
    base = calibrate_success_probability(symbol=symbol, direction=direction, raw_prob=raw_prob)
    n = int(base.get("samples") or 0)
    cal = safe_float(base.get("calibrated"), raw_prob)
    # Conservative certainty caps by sample size
    if n < 8:
        cap = CALIB_CAP_LOW_N
        method = "prior_capped"
    elif n < CALIB_MIN_SAMPLES_FULL:
        cap = CALIB_CAP_MID_N
        method = str(base.get("method") or "mid_n") + "+cap"
    else:
        cap = CALIB_CAP_HIGH_N
        method = str(base.get("method") or "full")
    # Mild regime shrink when high-vol (harder to be sure)
    reg = str(regime or "").lower()
    if "high_vol" in reg or "high_volatility" in reg:
        cal = 50.0 + (cal - 50.0) * 0.85
        cap = min(cap, 70.0)
    cal = float(clamp(cal, 5.0, cap))
    base["calibrated"] = round(cal, 1)
    base["cap"] = cap
    base["method"] = method
    base["regime"] = regime or "unknown"
    base["direction"] = direction
    base["param_version"] = TITAN_PARAM_VERSION
    base["honest_label"] = (
        f"کالیبره {cal:.0f}% · n={n} · سقف {cap:.0f}% · {method}"
    )
    return base


def portfolio_side_pressure(decision_tag: str, symbol: str) -> dict[str, Any]:
    """Limit clustered same-side alt signals (correlation risk proxy)."""
    if decision_tag not in {"LONG", "SHORT"}:
        return {"ok": True, "same_side": 0, "penalty": 0.0, "reason": ""}
    now = time.time()
    with _PORTFOLIO_SIGNAL_LOCK:
        global _RECENT_DIRECTIONAL_SIGNALS
        _RECENT_DIRECTIONAL_SIGNALS = [
            s for s in _RECENT_DIRECTIONAL_SIGNALS
            if now - safe_float(s.get("ts"), 0) < 3600 and s.get("symbol") != symbol
        ]
        same = [s for s in _RECENT_DIRECTIONAL_SIGNALS if s.get("side") == decision_tag]
        count = len(same)
        penalty = 0.0
        ok = True
        reason = ""
        if count >= MAX_PORTFOLIO_SAME_SIDE:
            ok = False
            penalty = 15.0
            reason = f"سبد اشباع {decision_tag}: {count}+ سیگنال هم‌جهت در ۱ ساعت"
        elif count >= MAX_PORTFOLIO_SAME_SIDE - 1:
            penalty = 8.0
            reason = f"فشار سبد {decision_tag}: {count} سیگنال هم‌جهت"
        return {"ok": ok, "same_side": count, "penalty": penalty, "reason": reason}


def register_portfolio_signal(symbol: str, decision_tag: str) -> None:
    if decision_tag not in {"LONG", "SHORT"}:
        return
    with _PORTFOLIO_SIGNAL_LOCK:
        _RECENT_DIRECTIONAL_SIGNALS.append({
            "symbol": symbol, "side": decision_tag, "ts": time.time(), "v": TITAN_PARAM_VERSION,
        })
        if len(_RECENT_DIRECTIONAL_SIGNALS) > 80:
            del _RECENT_DIRECTIONAL_SIGNALS[:-60]


def extract_structured_ai_vote(text: str) -> dict[str, Any]:
    """Parse free-text or JSON-ish AI reply into side + confidence."""
    t = str(text or "").strip()
    if not t:
        return {"side": "WAIT", "confidence": 0, "raw": ""}
    # Try JSON fragment
    try:
        if "{" in t and "}" in t:
            frag = t[t.find("{"): t.rfind("}") + 1]
            obj = json.loads(frag)
            side = str(obj.get("side") or obj.get("decision") or obj.get("bias") or "WAIT").upper()
            if side in {"صعودی", "LONG", "BUY"}:
                side = "LONG"
            elif side in {"نزولی", "SHORT", "SELL"}:
                side = "SHORT"
            else:
                side = "WAIT"
            conf = safe_float(obj.get("confidence", obj.get("prob", 50)), 50)
            return {"side": side, "confidence": float(clamp(conf, 0, 100)), "raw": t[:200]}
    except Exception:
        pass
    low = t.lower()
    # Prefer an explicit final decision over incidental words such as
    # "کاهش ریسک" or "رشد هزینه" that are not a market-direction vote.
    final_markers = (
        ("نتیجه نهایی", "fa"), ("final result", "en"),
        ("decision", "en"), ("تصمیم", "fa"),
    )
    final_chunk = ""
    for marker, _ in final_markers:
        pos = low.rfind(marker.lower()) if marker.isascii() else t.rfind(marker)
        if pos >= 0:
            final_chunk = t[pos:pos + 140]
            break
    final_low = final_chunk.lower()
    if final_chunk:
        if any(k in final_low or k in final_chunk for k in ("نزولی", "فروش", "short", "sell")):
            side = "SHORT"
        elif any(k in final_low or k in final_chunk for k in ("صعودی", "خرید", "long", "buy")):
            side = "LONG"
        elif any(k in final_low or k in final_chunk for k in ("انتظار", "wait", "خنثی", "neutral", "no trade")):
            side = "WAIT"
        else:
            side = "WAIT"
    else:
        # Fallback lexical parser. Keep phrases with explicit direction rather
        # than generic words like "کاهش" which frequently describe risk/volatility.
        short_keys = ("short", "sell", "نزولی", "فروش", "ریزش", "نزول")
        long_keys = ("long", "buy", "صعودی", "خرید", "رشد", "صعود")
        wait_keys = ("wait", "خنثی", "انتظار", "no trade", "حاشیه‌نشین")
        side = "WAIT"
        if any(k in low or k in t for k in short_keys):
            side = "SHORT"
        elif any(k in low or k in t for k in long_keys):
            side = "LONG"
        if any(k in low or k in t for k in wait_keys) and side != "WAIT":
            if t.count("انتظار") + low.count("wait") >= 1 and ("اما" in t or "but" in low):
                side = "WAIT"
    conf = 55.0
    for token in ("90", "85", "80", "75", "70", "65", "60"):
        if token in t:
            conf = float(token)
            break
    if side == "WAIT":
        conf = min(conf, 50)
    return {"side": side, "confidence": conf, "raw": t[:200]}


def meta_label_v8(
    *,
    confluence_score: float,
    precision_score: float,
    alignment: float,
    success_prob: float,
    ai_conflict: bool,
    stretch_atr: float,
    ladder_passed: bool,
    data_quality: float,
    hist_wr: float,
) -> dict[str, Any]:
    """Second-stage accept/reject: only ACCEPT enables high-conviction tags."""
    score = (
        0.22 * safe_float(confluence_score, 50)
        + 0.20 * safe_float(precision_score, 50)
        + 0.15 * safe_float(alignment, 50)
        + 0.18 * safe_float(success_prob, 50)
        + 0.12 * safe_float(data_quality, 50)
        + 0.08 * safe_float(hist_wr, 50)
        + 0.05 * (70 if ladder_passed else 30)
    )
    if ai_conflict:
        score -= 5
    if stretch_atr > 3.4:
        score -= min(12.0, (stretch_atr - 3.4) * 4)
    score = float(clamp(score, 0, 100))
    if score >= 62 and data_quality >= (MIN_DATA_QUALITY_SCORE - 4) and not ai_conflict:
        label = "ACCEPT"
    elif score < 42 or data_quality < 42:
        label = "REJECT"
    else:
        label = "WATCH"
    return {
        "label": label,
        "probability": round(score, 1),
        "param_version": TITAN_PARAM_VERSION,
        "gates": {
            "ladder": ladder_passed,
            "dq": data_quality >= MIN_DATA_QUALITY_SCORE,
            "ai_conflict": ai_conflict,
        },
    }



def smart_format(value: Any) -> str:
    try:
        number = float(value)
        if not math.isfinite(number):
            return "N/A"
    except (TypeError, ValueError):
        return "N/A"
    if abs(number) >= 100:
        return f"{number:,.2f}"
    if abs(number) >= 1:
        return f"{number:,.4f}"
    if abs(number) >= 0.0001:
        return f"{number:,.6f}"
    return f"{number:.8f}"


def _normalize_symbol(symbol: str) -> str:
    value = str(symbol or "").upper().replace("-", "/").replace(" ", "")
    if not value:
        return ""
    if "/" not in value:
        value += "/USDT"
    return value


def _normalize_symbol_for_binance(symbol: str) -> str:
    value = str(symbol or "").upper().replace("/", "").replace("-", "")
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
        now_ms = int(time.time() * 1000)
        df = df[df["T"] < now_ms].sort_values("t").drop_duplicates(subset=["t"], keep="last").reset_index(drop=True)

    if len(df) < 10:
        raise RuntimeError(f"Insufficient closed candles for {symbol} {tf}")
    if cacheable:
        _kline_cache_put(ckey, df)
    return df


def _binance_futures_funding(symbol: str) -> Optional[float]:
    try:
        r = _http_session().get(
            "https://fapi.binance.com/fapi/v1/premiumIndex",
            params={"symbol": _binance_symbol(symbol)}, timeout=8,
        )
        if not r.ok:
            return None
        payload = r.json()
        if not isinstance(payload, dict):
            return None
        return safe_float(payload.get("lastFundingRate")) * 100
    except Exception:
        return None


def _binance_futures_oi(symbol: str) -> Optional[float]:
    try:
        r = _http_session().get(
            "https://fapi.binance.com/fapi/v1/openInterest",
            params={"symbol": _binance_symbol(symbol)}, timeout=8,
        )
        if not r.ok:
            return None
        payload = r.json()
        if not isinstance(payload, dict):
            return None
        value = safe_float(payload.get("openInterest"))
        return value if value > 0 else None
    except Exception:
        return None


def fetch_derivatives(symbol: str) -> dict[str, Any]:
    # Short TTL cache — funding/OI rarely need sub-20s refresh during one scan
    _sym_key = _normalize_symbol(symbol)
    with KLINE_CACHE_LOCK:
        _hit = DERIV_CACHE.get(_sym_key)
        if _hit and (time.time() - _hit[0]) < DERIV_CACHE_TTL:
            return _hit[1]
    clean = _binance_symbol(symbol)
    base = clean.replace("USDT", "")
    raw_oi = 0.0
    oi_kind = "unknown"
    funding: Optional[float] = None
    cg_usd = cg_qty = cg_delta = None
    source_parts: list[str] = []

    if COINGLASS_API_KEY:
        headers = {"CG-API-KEY": COINGLASS_API_KEY}
        try:
            res = _http_session().get(
                "https://open-api-v4.coinglass.com/api/futures/open-interest/exchange-list",
                params={"symbol": base}, headers=headers, timeout=10,
            ).json()
            if str(res.get("code")) in {"0", "200"}:
                rows = res.get("data") or []
                row = next((r for r in rows if str(r.get("exchange", "")).lower() == "all"), rows[0] if rows else None)
                if row:
                    cg_qty = safe_float(row.get("open_interest_quantity"), 0)
                    cg_usd = safe_float(row.get("open_interest_usd"), 0)
                    cg_delta = safe_float(row.get("open_interest_change_percent_5m"), 0)
                    if cg_usd and cg_usd > 0:
                        raw_oi, oi_kind = cg_usd, "usd"
                    elif cg_qty and cg_qty > 0:
                        raw_oi, oi_kind = cg_qty, "base"
                    if raw_oi > 0:
                        source_parts.append("CoinGlass-OI")
        except Exception as exc:
            LOGGER.warning("CoinGlass OI failed for %s: %s", symbol, exc)
        try:
            res = _http_session().get(
                "https://open-api-v4.coinglass.com/api/futures/funding-rate/exchange-list",
                params={"symbol": base}, headers=headers, timeout=10,
            ).json()
            if str(res.get("code")) in {"0", "200"}:
                rows = res.get("data") or []
                row = next((r for r in rows if str(r.get("symbol", "")).upper() == base), rows[0] if rows else None)
                if row:
                    vals = [safe_float(x.get("funding_rate"), np.nan) for x in (row.get("stablecoin_margin_list") or [])]
                    vals = [x for x in vals if np.isfinite(x)]
                    if vals:
                        funding = float(np.mean(vals)) * 100
                        source_parts.append("CoinGlass-Funding")
        except Exception as exc:
            LOGGER.warning("CoinGlass funding failed for %s: %s", symbol, exc)

    if funding is None:
        funding = _binance_futures_funding(symbol)
        if funding is not None:
            source_parts.append("Binance-Funding")
    if raw_oi <= 0:
        fallback_oi = _binance_futures_oi(symbol)
        if fallback_oi is not None:
            raw_oi, oi_kind = fallback_oi, "base"
            source_parts.append("Binance-OI")

    now = time.time()
    delta = cg_delta if cg_delta is not None else 0.0
    with OI_LOCK:
        previous = OI_HISTORY.get(symbol)
        if cg_delta is None and previous and previous[2] == oi_kind:
            prev_oi, prev_ts, _ = previous
            if prev_oi > 0 and raw_oi > 0 and now - prev_ts <= 900:
                delta = ((raw_oi - prev_oi) / prev_oi) * 100
        if raw_oi > 0:
            OI_HISTORY[symbol] = (raw_oi, now, oi_kind)

    if cg_usd and cg_usd > 0:
        oi_disp = f"${smart_format(cg_usd)}"
    elif cg_qty and cg_qty > 0:
        oi_disp = f"{smart_format(cg_qty)} {base}"
    elif raw_oi > 0:
        oi_disp = f"{smart_format(raw_oi)} {base}"
    else:
        oi_disp = "N/A"
    ls = fetch_binance_long_short_ratio(symbol)
    taker = fetch_binance_taker_buy_sell(symbol)
    if ls.get("source") and ls.get("source") != "N/A":
        source_parts.append(str(ls.get("source")))
    if taker.get("source") and taker.get("source") != "N/A":
        source_parts.append(str(taker.get("source")))
    out = {
        "oi": oi_disp,
        "raw_oi": raw_oi,
        "oi_delta": delta,
        "funding_value": funding,
        "funding": f"{funding:+.4f}%" if funding is not None else "N/A",
        "source": " + ".join(dict.fromkeys(source_parts)) if source_parts else "N/A",
        "long_short": ls,
        "taker": taker,
        "long_ratio": ls.get("long_ratio"),
        "short_ratio": ls.get("short_ratio"),
        "long_short_ratio": ls.get("long_short_ratio"),
        "top_long_ratio": ls.get("top_long_ratio"),
        "taker_buy_pct": taker.get("buy_pct", 50),
        "taker_sell_pct": taker.get("sell_pct", 50),
    }
    with KLINE_CACHE_LOCK:
        DERIV_CACHE[_normalize_symbol(symbol)] = (time.time(), out)
        if len(DERIV_CACHE) > 80:
            for k, _ in sorted(DERIV_CACHE.items(), key=lambda x: x[1][0])[:20]:
                DERIV_CACHE.pop(k, None)
    return out


def fetch_btc_trend() -> str:
    try:
        df = fetch_klines("BTC/USDT", "1h", 60)
        ema = df["close"].ewm(span=20, adjust=False).mean().iloc[-1]
        return "صعودی" if float(df["close"].iloc[-1]) >= float(ema) else "نزولی"
    except Exception as exc:
        LOGGER.warning("BTC trend failed: %s", exc)
        return "خنثی"


def fetch_macro() -> dict[str, Any]:
    fear_value = "N/A"
    fear_text = "داده نیست"
    dominance = "N/A"
    sources: list[str] = []
    try:
        payload = _http_session().get("https://api.alternative.me/fng/", params={"limit": 1}, timeout=8).json()
        data = payload.get("data") or []
        if data:
            fear_value = data[0].get("value", "N/A")
            fear_text = data[0].get("value_classification", "N/A")
            sources.append("Alternative.me")
    except Exception as exc:
        LOGGER.warning("Fear & Greed failed: %s", exc)
    try:
        payload = _http_session().get("https://api.coingecko.com/api/v3/global", timeout=8).json()
        btc_dom = safe_float((payload.get("data") or {}).get("market_cap_percentage", {}).get("btc"), np.nan)
        if np.isfinite(btc_dom):
            dominance = f"{btc_dom:.2f}%"
            sources.append("CoinGecko")
    except Exception as exc:
        LOGGER.warning("CoinGecko macro failed: %s", exc)
    return {"fear_greed_val": fear_value, "fear_greed_text": fear_text, "global_status": " / ".join(sources) or "N/A", "dominance_btc": dominance}

# ============================================================
# TECHNICALS / DECISION CORE
# ============================================================




# === TITAN V6.2 PROFESSIONAL MODULES ===
# 1) Platt + Isotonic calibration from paper trades
# 2) BTC correlation filter for alts in high-vol