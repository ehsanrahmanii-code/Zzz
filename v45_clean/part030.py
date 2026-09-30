        stoch = calc_stoch_rsi(df["close"])
        return jsonify({
            "ok": True,
            "symbol": symbol,
            "timeframe": tf,
            "rsi": round(float(rsi_s.iloc[-1]), 2) if len(rsi_s) else None,
            "macd": macd,
            "stoch_rsi": stoch,
            "patterns": patterns,
            "forecast": forecast,
            "guide_catalog": PATTERN_GUIDE,
        })
    except Exception as exc:
        LOGGER.warning("pattern-forecast failed %s: %s", symbol, exc)
        return jsonify({"ok": False, "error": str(exc)[:300], "symbol": symbol}), 500


@app.get("/api/klines")
def api_klines():
    """OHLCV for dashboard chart fallback (Binance)."""
    symbol = _normalize_symbol(request.args.get("symbol", "BTC/USDT"))
    tf = str(request.args.get("timeframe", "1h") or "1h")
    if tf not in {"15m", "1h", "4h", "1d"}:
        tf = "1h"
    limit = min(max(int(request.args.get("limit", 120)), 20), 300)
    try:
        df = fetch_klines(symbol, tf, limit)
        candles = []
        for _, row in df.iterrows():
            candles.append({
                "t": int(row["t"]),
                "o": float(row["open"]),
                "h": float(row["high"]),
                "l": float(row["low"]),
                "c": float(row["close"]),
                "v": float(row["vol"]),
            })
        return jsonify({"ok": True, "symbol": symbol, "timeframe": tf, "candles": candles})
    except Exception as exc:
        LOGGER.warning("api_klines failed %s: %s", symbol, exc)
        return jsonify({"ok": False, "error": str(exc)[:300], "symbol": symbol}), 500





@app.get("/api/scalp-window")
def api_scalp_window():
    """Short-horizon (30-60 min) leverage suitability from 15m/1h scores + live micro bias.

    Analysis-only. Designed for holding a position roughly 30 minutes, max ~60.
    """
    try:
        data, _, macro = _fast_market_snapshot()
        rows = []
        for item in data or []:
            sym = str(item.get("symbol") or "")
            tfs = item.get("tfs") or item.get("tf_scores") or {}
            s15 = safe_float(tfs.get("15m"), safe_float(item.get("score"), 50))
            s1h = safe_float(tfs.get("1h"), 50)
            rsi = safe_float(item.get("rsi"), 50)
            buy = safe_float((item.get("buy_sell") or {}).get("buy_pct"), item.get("taker_buy_pct", 50))
            sell = 100.0 - buy
            decision = str(item.get("decision_tag") or "WAIT").upper()
            score = safe_float(item.get("score"), 50)
            # Short-horizon edge: prefer 15m direction with 1h not strongly against
            success = safe_float(item.get("success_probability"), safe_float(item.get("signal_quality"), 50))
            long_edge = (s15 - 50) * 1.35 + (s1h - 50) * 0.55 + (buy - 50) * 0.30 + (success - 50) * 0.20
            short_edge = (50 - s15) * 1.35 + (50 - s1h) * 0.55 + (sell - 50) * 0.30 + (success - 50) * 0.20
            # RSI extremes: continuation bias for scalp window
            if rsi >= 70:
                short_edge += 5
                long_edge -= 4
            elif rsi <= 30:
                long_edge += 5
                short_edge -= 4
            side = "WAIT"
            edge = 0.0
            # Stricter gate: only clear 15m lean + non-conflicting 1h
            if long_edge >= 10 and long_edge > short_edge + 1.5 and s15 >= 55 and s1h >= 48:
                side = "LONG"
                edge = long_edge
            elif short_edge >= 10 and short_edge > long_edge + 1.5 and s15 <= 45 and s1h <= 52:
                side = "SHORT"
                edge = short_edge
            if side == decision and side in {"LONG", "SHORT"}:
                edge += 4
            conf = float(clamp(50 + edge * 2.0 + (success - 50) * 0.15, 0, 92))
            if side == "WAIT" or conf < 62:
                continue
            hold_min = 30 if conf >= 75 else 40 if conf >= 68 else 50
            rows.append({
                "symbol": sym,
                "base": sym.split("/")[0] if "/" in sym else sym,
                "side": side,
                "confidence": round(conf, 1),
                "success": round(success, 1),
                "hold_minutes": hold_min,
                "max_hold_minutes": 60,
                "score_15m": round(s15, 1),
                "score_1h": round(s1h, 1),
                "rsi": round(rsi, 1),
                "buy_pct": round(buy, 1),
                "reason": (
                    f"۱۵م={s15:.0f} · ۱س={s1h:.0f} · RSI={rsi:.0f} · موفقیت~{success:.0f} · "
                    f"{'خرید' if side=='LONG' else 'فروش'} {(buy if side=='LONG' else sell):.0f}% · "
                    f"نگهداری ~{hold_min}–۶۰ دقیقه"
                ),
            })
        rows.sort(key=lambda r: (
            -safe_float(r.get("confidence"), 0),
            -safe_float(r.get("success"), 0),
            -safe_float(r.get("score_15m"), 0),
        ))
        # Only the single best LONG and/or SHORT — hard cap 2 total
        top2 = rows[:2]
        return jsonify({
            "ok": True,
            "horizon": "30-60m",
            "count": len(top2),
            "rows": top2,
            "note": "ویژه معاملات اهرمی کوتاه‌مدت؛ خروج حداکثر تا ۶۰ دقیقه. تضمین سود نیست.",
            "macro": {"btc_trend": (macro or {}).get("btc_trend")},
        })
    except Exception as exc:
        LOGGER.exception("scalp-window failed: %s", exc)
        return jsonify({"ok": False, "error": str(exc)[:300]}), 500


@app.get("/api/realtime-analysis")
def api_realtime_analysis():
    """Real-time snapshot: live prices, micro-moves, breadth, and per-symbol live bias."""
    try:
        coins = USER_SETTINGS.get("active_coins") or DEFAULT_COINS
        # Refresh a batch of live prices (non-blocking-ish, short timeout path)
        try:
            prices = _fetch_live_prices(list(coins)[:40])
            for sym, px in prices.items():
                if px and px > 0:
                    _register_live_price(sym, px, "REST-rt")
        except Exception as exc:
            LOGGER.debug("realtime price batch: %s", exc)

        live_status = _live_status()
        rows = []
        up = down = flat = 0
        with LIVE_LOCK:
            live_map = dict(LIVE_PRICES)

        # Merge with last cache decisions for context
        cached, _, macro = _fast_market_snapshot()
        by_sym = {str(x.get("symbol")): x for x in (cached or [])}

        for sym in coins:
            ns = _normalize_symbol(sym)
            bare = _normalize_symbol_for_binance(ns)
            info = live_map.get(ns) or live_map.get(bare) or live_map.get(bare.replace("USDT", "/USDT")) or {}
            # try alternate keys
            if not info:
                for k, v in live_map.items():
                    if k.replace("/", "") == bare:
                        info = v
                        break
            px = safe_float(info.get("price"), 0)
            ch = safe_float(info.get("change_pct"), 0)
            age = time.time() - safe_float(info.get("ts"), 0) if info.get("ts") else None
            item = by_sym.get(ns) or {}
            decision = str(item.get("decision_tag") or "WAIT")
            score = safe_float(item.get("score"), 50)
            buy = safe_float((item.get("buy_sell") or {}).get("buy_pct"), item.get("taker_buy_pct", 50))
            sell = safe_float((item.get("buy_sell") or {}).get("sell_pct"), 100 - buy)

            # Micro live bias from last tick change
            if ch > 0.08:
                micro = "صعودی"
                up += 1
            elif ch < -0.08:
                micro = "نزولی"
                down += 1
            else:
                micro = "خنثی"
                flat += 1

            # Build the realtime row from the same cached signal plus the newest
            # live snapshot so Entry/SL/TP shown by the UI cannot lag the price.
            live_item = dict(item)
            if px > 0:
                live_item = _v35_rebase_price_dependent_outputs(
                    live_item, {"price": px, "ts": safe_float(info.get("ts"), time.time()),
                                "source": info.get("source") or "Binance"}
                )
            rows.append({
                "symbol": ns,
                "price": px if px > 0 else safe_float(str(item.get("price") or "0").replace(",", ""), 0),
                "entry": safe_float(live_item.get("entry_raw"), px),
                "stop_loss": safe_float(live_item.get("stop_loss_raw"), 0),
                "tp1": safe_float(live_item.get("tp1_raw"), 0),
                "tp2": safe_float(live_item.get("tp2_raw"), 0),
                "rr_tp1": safe_float(live_item.get("rr_tp1"), 0),
                "rr_tp2": safe_float(live_item.get("rr_tp2"), 0),
                "change_pct": round(ch, 4),
                "age_sec": round(age, 2) if age is not None else None,
                "source": info.get("source") or "cache",
                "decision": str(live_item.get("decision_tag") or decision),
                "score": score,
                "buy_pct": round(buy, 1),
                "sell_pct": round(sell, 1),
                "micro_bias": micro,
                "fresh": bool(age is not None and age <= 8),
                "live_sync": bool(live_item.get("live_sync", False)),
            })

        rows.sort(key=lambda r: abs(safe_float(r.get("change_pct"), 0)), reverse=True)
        leaders = [r for r in rows if r.get("fresh") and abs(safe_float(r.get("change_pct"), 0)) >= 0.05][:5]
        return jsonify({
            "ok": True,
            "mode": "realtime",
            "server_time": int(time.time() * 1000),
            "live": live_status,
            "breadth": {"up": up, "down": down, "flat": flat},
            "leaders": leaders,
            "rows": rows,
            "macro": {
                "fear": (macro or {}).get("fear_greed_val"),
                "btc_dom": (macro or {}).get("dominance_btc"),
                "btc_trend": (macro or {}).get("btc_trend"),
            },
            "note": "تحلیل بلادرنگ بر اساس تیک زنده + آخرین سیگنال کش‌شده؛ سفارش اجرا نمی‌شود.",
        })
    except Exception as exc:
        LOGGER.exception("realtime-analysis failed: %s", exc)
        return jsonify({"ok": False, "error": str(exc)[:300]}), 500


@app.get("/api/live-prices")
def api_live_prices():
    symbols = [_normalize_symbol(x) for x in request.args.get("symbols", "").split(",") if x.strip()][:100]
    return jsonify({"ok": True, "source": "Binance Spot Ticker", "prices": _fetch_live_prices(symbols), "server_time": int(time.time() * 1000)})

@app.get("/api/market-pulse")
def api_market_pulse():
    data, _summary, macro = update_cache(False)
    return jsonify({"ok": True, "pulse": _market_pulse_snapshot(data, macro)})

@app.get("/api/advanced-metrics")
def api_advanced_metrics():
    evaluate_paper_trades()
    return jsonify({"ok": True, "metrics": get_advanced_metrics()})

@app.get("/api/backtest")
def api_backtest():
    symbol = _normalize_symbol(request.args.get("symbol", "BTC/USDT")); tf = _query_timeframe(); limit = _query_int("limit", 1000, 100, MAX_BACKTEST_CANDLES)
    return jsonify(backtest_signal_logic(symbol, tf, limit))

@app.get("/api/walk-forward")
def api_walk_forward():
    symbol = _normalize_symbol(request.args.get("symbol", "BTC/USDT")); tf = _query_timeframe(); limit = _query_int("limit", 1000, 200, MAX_BACKTEST_CANDLES)
    train = _query_int("train", 300, 100, MAX_BACKTEST_CANDLES); test = _query_int("test", 100, 20, MAX_BACKTEST_CANDLES)
    return jsonify(walk_forward_backtest(symbol, tf, limit, train, test))

@app.get("/api/titan-terminal")
def api_titan_terminal():
    symbol = _normalize_symbol(request.args.get("symbol", USER_SETTINGS.get("active_coins", DEFAULT_COINS)[0]))
    data, _summary, _macro = update_cache(False)
    item = next((x for x in data if x.get("symbol") == symbol), None)
    if not item:
        return jsonify({"ok": False, "error": "نماد در کش فعلی موجود نیست"}), 404
    return jsonify({"ok": True, "terminal": item.get("decision_terminal", TITAN_EDGE_SUITE.decision_terminal(item))})


@app.get("/api/all-performance")
def api_all_performance():
    symbols = USER_SETTINGS.get("active_coins") or DEFAULT_COINS
    out = []
    audit = get_audit_stats()
    for symbol in symbols:
        try:
            sym = _normalize_symbol(symbol)
            result = backtest_signal_logic(sym, "1h", 800)
            m = result.get("metrics", {}) if isinstance(result, dict) and result.get("ok") else {}
            out.append({
                "symbol": sym,
                "win_rate": m.get("win_rate", audit.get("win_rate", 0)),
                "wins": m.get("wins", audit.get("wins", 0)),
                "losses": m.get("losses", audit.get("losses", 0)),
                "expectancy": m.get("expectancy", 0),
                "profit_factor": m.get("profit_factor", 0),
            })
        except Exception as e:
            out.append({"symbol": symbol, "error": str(e)})
    return jsonify({"ok": True, "items": out})

@app.get("/api/performance-history")
def api_performance_history():
    symbol = _normalize_symbol(request.args.get("symbol", "")) if request.args.get("symbol") else ""
    tf = request.args.get("timeframe", "")
    limit = _query_int("limit", 120, 1, 500)
    return jsonify(get_performance_history(symbol, tf, limit))


@app.get("/api/performance")
def api_performance():
    symbol = _normalize_symbol(request.args.get("symbol", USER_SETTINGS.get("active_coins", DEFAULT_COINS)[0]))
    tf = _query_timeframe(); limit = _query_int("limit", 1200, 200, MAX_BACKTEST_CANDLES)
    result = backtest_signal_logic(symbol, tf, limit)
    wf = walk_forward_backtest(symbol, tf, limit, max(200, min(300, limit//3)), max(50, min(100, limit//8))) if result.get("ok") else {"ok": False}
    audit = get_audit_stats()
    strategies = result.get("professional", {}).get("strategy_lab", {}) if result.get("ok") else {}
    return jsonify({"ok": bool(result.get("ok")), "symbol": symbol, "timeframe": tf, "backtest": result, "walk_forward": wf, "historical": audit, "strategies": strategies})

@app.get("/api/pro-lab")
def api_pro_lab():
    symbol = _normalize_symbol(request.args.get("symbol", USER_SETTINGS.get("active_coins", DEFAULT_COINS)[0]))
    tf = _query_timeframe()
    limit = _query_int("limit", 1000, 200, MAX_BACKTEST_CANDLES)
    result = backtest_signal_logic(symbol, tf, limit)
    return jsonify({"ok": bool(result.get("ok")), "suite": {"modules": 12, "status": "ACTIVE"}, "result": result})

@app.get("/api/ai-votes")
def api_ai_votes():
    """Aggregate AI model votes across active symbols for dashboard AI tab."""
    data, _summary, _macro = _fast_market_snapshot()
    if not data:
        _background_market_refresh(False)
    board = []
    tally = {"LONG": 0, "SHORT": 0, "WAIT": 0, "providers": {}}
    for item in data or []:
        ai = item.get("ai_opinions") or {}
        ens = (item.get("edge") or {}).get("ai") or TITAN_EDGE_SUITE.ai_ensemble(ai, item.get("bias", "خنثی"))
        votes = ens.get("votes") or {}
        details = ens.get("details") or {}
        row = {
            "symbol": item.get("symbol"),
            "bias": item.get("bias"),
            "decision_tag": item.get("decision_tag") or "WAIT",
            "score": item.get("score"),
            "titan": "LONG" if item.get("bias") == "صعودی" else "SHORT" if item.get("bias") == "نزولی" else "WAIT",
            "majority": ens.get("majority", "WAIT"),
            "agreement": ens.get("agreement", 0),
            "status": ens.get("status", "NO_AI_DATA"),
            "votes": votes,
            "details": details,
            "gemini": ai.get("gemini") or "",
            "openai": ai.get("openai") or "",
            "grok": ai.get("grok") or "",
            "claude": ai.get("claude") or "",
            "deepseek": ai.get("deepseek") or "",
        }
        board.append(row)
        maj = row["majority"]
        if maj in tally:
            tally[maj] += 1
        for p, v in votes.items():
            bucket = tally["providers"].setdefault(p, {"LONG": 0, "SHORT": 0, "WAIT": 0})
            if v in bucket:
                bucket[v] += 1
    return jsonify({"ok": True, "board": board, "tally": tally, "count": len(board)})


@app.get("/api/gemini-analysis")
def api_gemini_analysis():
    """Return fresh Gemini global analysis instead of only reading the cache.

    This endpoint is intentionally fail-safe: cached market data is reused when
    available, and a fresh Gemini request is attempted whenever the caller asks
    for a refresh or the cached summary is empty.
    """
    reload_keys()
    data, summary, macro = _load_market_cache()
    force = str(request.args.get("refresh", "0")).lower() in {"1", "true", "yes", "on"}
    if not data:
        try:
            data, summary, macro = update_cache(False)
        except Exception as exc:
            LOGGER.exception("Gemini endpoint cache update failed: %s", exc)
    if GEMINI_API_KEY and data and (force or not str(summary or "").strip()):
        try:
            fresh = _global_ai_summary(data, macro)
            if fresh:
                summary = fresh
                _save_json(MARKET_CACHE_PATH, {"timestamp": time.time(), "data": data, "gemini_summary": summary, "macro": macro})
                with CACHE_LOCK:
                    CACHE.update(timestamp=time.time(), data=data, gemini_summary=summary, macro=macro)
        except Exception as exc:
            LOGGER.exception("Gemini global refresh failed: %s", exc)
    return jsonify({
        "ok": True,
        "provider": "Gemini",
        "available": bool(GEMINI_API_KEY),
        "ready": bool(str(summary or "").strip()),
        "analysis": summary or "",
        "macro": macro,
        "error": (GEMINI_LAST_ERROR if not str(summary or '').strip() else ""),
    })

@app.get("/api/gemini-debug")
def api_gemini_debug():
    reload_keys()
    models = _gemini_available_models() if GEMINI_API_KEY else []
    return jsonify({
        "ok": True,
        "available": bool(GEMINI_API_KEY),
        "models": models[:20],
        "last_error": GEMINI_LAST_ERROR,
        "storage": str(APP_HOME),
    })

@app.route("/health")
def health():
    with CACHE_LOCK:
        age = time.time() - CACHE["timestamp"] if CACHE.get("timestamp") else None
    return jsonify({"status": "ok", "home": str(APP_HOME), "gemini": bool(GEMINI_API_KEY), "openai": bool(OPENAI_API_KEY), "grok": bool(GROK_API_KEY), "claude": bool(CLAUDE_API_KEY), "deepseek": bool(DEEPSEEK_API_KEY), "coinglass": bool(COINGLASS_API_KEY), "cache_age_seconds": round(age, 2) if age is not None else None, "assets": len(CACHE.get("data") or []), "live": _live_status(), "storage_enforced": True})

# ============================================================
# STARTUP
# ============================================================



# =============================================================================
# TITAN V29.3 — CENTRAL GOVERNOR (single decision authority)
# - All upstream engines (V29..V32, CNS, patterns, AI) = evidence only
# - Central Governor = sole LONG / SHORT / WAIT publisher
# - Timestamped predictions + automatic outcome audit + component reward/penalty
# - Auto scan / learn / score — no manual button required
# - Emergency live-price cards so Android dashboard is never blank
# - Analysis only. No order execution. Signals are probabilistic, not guarantees.
# =============================================================================

TITAN_CENTRAL_VERSION = "TITAN-CENTRAL-GOVERNOR-V29.5-EDGE"
TITAN_PARAM_VERSION = "V41.0-ANDROID-BALANCED-OPPORTUNITY"
TITAN_PUBLIC_AUTHORITY = TITAN_CENTRAL_VERSION
TITAN_ENGINE_MODE = "CENTRAL_GOVERNOR_ONLY"
TITAN_LEGACY_ENGINES_ARE_EVIDENCE_ONLY = True

_CENTRAL_WEIGHT_LOCK = threading.RLock()
# Reweighted from realized phone-DB component stats (htf best; ltf/forecast weak)
_CENTRAL_WEIGHTS_DEFAULT = {
    "htf_trend": 1.55,
    "mtf_setup": 1.05,
    "ltf_trigger": 0.55,
    "momentum": 0.90,
    "structure": 1.25,
    "volume_flow": 0.55,
    "derivatives": 0.85,
    "pattern": 0.70,
    "forecast_path": 0.45,
    "ai_vote": 0.60,
    "data_trust": 1.35,
    "learning_v32": 0.70,
}
_CENTRAL_WEIGHTS: dict[str, float] = dict(_CENTRAL_WEIGHTS_DEFAULT)
_CENTRAL_MIN_EDGE = 0.15
_CENTRAL_MIN_MARGIN = 0.09
_CENTRAL_MIN_TRUST = 48.0
_CENTRAL_MIN_EDGE_SHORT = 0.18
_CENTRAL_MIN_MARGIN_SHORT = 0.12


# ============================================================
# TITAN V29.5 EDGE LAB — ten hardened decision-quality layers
# 1) honest online probability calibration
# 2) MAE/MFE + time-to-event telemetry
# 3) regime-conditioned performance
# 4) overlapping-signal suppression
# 5) Monte-Carlo risk analysis
# 6) friction-aware expectancy / profit factor
# 7) champion / challenger governance
# 8) immutable parameter/version provenance
# 9) purged walk-forward style validation on realized central outcomes
# 10) entry-quality vs directional-bias separation + component attribution
# ============================================================

EDGE_LAB_VERSION = "V30-REAL-EDGE-22X"
EDGE_MAX_PENDING_PER_SYMBOL = 1
EDGE_MAX_PENDING_SAME_SIDE = 4
EDGE_MC_RUNS = 2000


def _edge_lab_init_schema() -> None:
    """Create additive analytics tables; never destroys legacy data."""
    try:
        with DB_LOCK, db_conn() as con:
            con.execute("""CREATE TABLE IF NOT EXISTS central_trade_metrics(
                prediction_id INTEGER PRIMARY KEY,
                regime TEXT,
                volatility_pct REAL,
                trend_strength REAL,
                mae_pct REAL,
                mfe_pct REAL,
                time_to_event_min REAL,
                exit_price REAL,
                net_return_pct REAL,
                r_multiple REAL,
                entry_quality REAL,
                directional_bias REAL,
                ambiguity INTEGER DEFAULT 0,
                friction_pct REAL,
                evaluated_at REAL,
                param_version TEXT,