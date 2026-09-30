@app.route("/api/tf-gauge")
def api_tf_gauge():
    symbol = _normalize_symbol(request.args.get("symbol", "") or (USER_SETTINGS.get("active_coins") or DEFAULT_COINS)[0])
    frames = ["15m", "1h", "4h", "1d"]
    out = []
    try:
        data, _, _ = _fast_market_snapshot()
        if not data:
            _background_market_refresh(False)
        item = next((x for x in (data or []) if x.get("symbol") == symbol), None)
        if not item:
            bare = symbol.replace("/", "")
            item = next((x for x in (data or []) if str(x.get("tv_symbol", "")).replace("/", "") == bare), {}) or {}
        tf_scores = (item or {}).get("tf_scores") or {}
        base = float((item or {}).get("score") or 50)
        alignment_all = float((item or {}).get("alignment") or 50)
        vol_spike = bool((item or {}).get("volume_spike"))
    except Exception as exc:
        LOGGER.warning("TF gauge snapshot failed for %s: %s", symbol, exc)
        tf_scores, base, alignment_all, vol_spike = {}, 50.0, 50.0, False
    # The gauge must be independently reliable even when the dashboard cache is cold.
    # Build missing timeframe scores directly from closed Binance candles.
    if not tf_scores:
        try:
            fresh_scores = {}
            for f in frames:
                df = fetch_klines(symbol, f, 140 if f in ("15m", "1h") else 100)
                if df is not None and len(df) >= 55:
                    _d, _sc, _m = _tf_forecast(df)
                    fresh_scores[f] = float(_sc)
            tf_scores = fresh_scores
        except Exception as exc:
            LOGGER.debug("fresh TF gauge fallback failed: %s", exc)
    if not tf_scores and not data:
        return jsonify({"ok": False, "ready": False, "symbol": symbol, "error": "داده تایم‌فریم هنوز آماده نشده است"}), 202
    for f in frames:
        score = float(tf_scores.get(f, base))
        trend = int(clamp(score, 0, 100))
        momentum = int(clamp(score * 0.92 + (5 if score >= 60 else -5 if score <= 40 else 0), 0, 100))
        volume = int(clamp((75 if vol_spike else 45) + (score - 50) * 0.35, 0, 100))
        alignment = int(clamp(alignment_all * 0.7 + score * 0.3, 0, 100))
        final = int(round(trend * 0.35 + momentum * 0.25 + volume * 0.15 + alignment * 0.25))
        out.append({"name": f, "trend": trend, "momentum": momentum, "volume": volume, "alignment": alignment, "score": final})
    return jsonify({"ok": True, "symbol": symbol, "timeframes": out})

@app.route("/rescan")
def rescan():
    global CACHE
    with CACHE_LOCK:
        CACHE = {"timestamp": 0.0, "data": [], "gemini_summary": "", "macro": {}}
    _scan_progress_update(status="queued",phase="در صف اسکن",started_at=0.0,finished_at=0.0,completed=0,total=len(USER_SETTINGS.get("active_coins") or DEFAULT_COINS),percent=0,message="اسکن جدید درخواست شد…",fresh=False)
    return redirect(url_for("index"))

@app.route("/update_settings", methods=["POST"])
def update_settings():
    global USER_SETTINGS, CACHE
    risk = clamp(safe_float(request.form.get("risk_multiplier"), 1.2), 0.2, 5.0)
    coins: list[str] = []
    for raw in request.form.get("active_coins", "").split(","):
        symbol = _normalize_symbol(raw)
        if symbol and symbol not in coins:
            coins.append(symbol)
    USER_SETTINGS = {"risk_multiplier": risk, "active_coins": coins or DEFAULT_COINS.copy()}
    save_settings()
    with CACHE_LOCK:
        CACHE = {"timestamp": 0.0, "data": [], "gemini_summary": "", "macro": {}}
    return redirect(url_for("index"))






@app.get("/api/depth")
def api_depth():
    symbol = _normalize_symbol(request.args.get("symbol", "BTC/USDT"))
    return jsonify({"ok": True, "depth": get_depth_snapshot(symbol), "watchlist": DEPTH_WATCHLIST})

@app.get("/api/calibration")
def api_calibration():
    symbol = _normalize_symbol(request.args.get("symbol", ""))
    direction = str(request.args.get("direction", "") or "")
    raw = safe_float(request.args.get("raw", 55), 55)
    return jsonify({"ok": True, "calibration": calibrate_success_probability(symbol, direction, raw)})


@app.get("/api/pattern-forecast")
def api_pattern_forecast():
    """Pattern detection + probabilistic future candle path for one symbol."""
    symbol = _normalize_symbol(request.args.get("symbol", "BTC/USDT"))
    tf = str(request.args.get("timeframe", "1h") or "1h")
    if tf not in {"15m", "1h", "4h", "1d"}:
        tf = "1h"
    horizon = min(max(int(request.args.get("horizon", 12)), 3), 12)
    try:
        df = fetch_klines(symbol, tf, 200 if tf in ("15m", "1h") else 150)
        rsi_s = wilder_rsi(df["close"])
        patterns = detect_chart_patterns(df, rsi_s)
        forecast = forecast_future_candles(df, horizon=horizon, patterns=patterns)
        macd = calc_macd(df["close"])
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