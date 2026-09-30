    if df is None or df.empty or entry <= 0:
        return "PENDING", 0.0, 0.0, 0.0
    close = pd.to_numeric(df.get("close"), errors="coerce").dropna()
    high = pd.to_numeric(df.get("high"), errors="coerce").dropna()
    low = pd.to_numeric(df.get("low"), errors="coerce").dropna()
    if close.empty:
        return "PENDING", 0.0, 0.0, 0.0
    final_px = float(close.iloc[-1])
    ret = (final_px / entry - 1.0) if entry else 0.0
    if decision == "SHORT":
        ret = -ret
        favorable = max(0.0, (entry - float(low.min())) / entry) if not low.empty else max(0.0, ret)
        adverse = max(0.0, (float(high.max()) - entry) / entry) if not high.empty else 0.0
    elif decision == "LONG":
        favorable = max(0.0, (float(high.max()) - entry) / entry) if not high.empty else max(0.0, ret)
        adverse = max(0.0, (entry - float(low.min())) / entry) if not low.empty else 0.0
    else:
        favorable = adverse = abs(ret)
    # A directional forecast is correct only if price moved beyond a friction/
    # noise band in the predicted direction. Small moves are NEUTRAL, not wins.
    if decision in {"LONG", "SHORT"}:
        if ret > V32_WAIT_MOVE_THRESHOLD:
            outcome = "WIN"
        elif ret < -V32_WAIT_MOVE_THRESHOLD:
            outcome = "LOSS"
        else:
            outcome = "NEUTRAL"
    else:
        outcome = "WAIT_CORRECT" if abs(ret) <= V32_WAIT_MOVE_THRESHOLD else "WAIT_MISSED"
    return outcome, ret * 100.0, favorable * 100.0, adverse * 100.0


def v32_record_scan_predictions(market_data: list[dict[str, Any]]) -> None:
    """Record one *timeframe-specific* prediction per symbol.

    The previous implementation wrote the same canonical decision into all four
    timeframe rows. That made the performance matrix look like 15m/1h/4h/1d
    were independently tested when they were not. Here each row is derived from
    that timeframe's own score; the canonical multi-TF decision remains separate.
    """
    now = time.time()
    if not market_data:
        return
    with DB_LOCK, db_conn() as con:
        for item in market_data:
            symbol = _normalize_symbol(item.get("symbol", ""))
            price = safe_float(str(item.get("live_price") or item.get("price") or "0").replace(",", ""), 0.0)
            tf_scores = item.get("tf_scores") or {}
            if not symbol or price <= 0:
                continue
            for tf in V32_TFS:
                score = safe_float(tf_scores.get(tf), 50.0)
                if score >= 55.0:
                    decision = "LONG"
                elif score <= 45.0:
                    decision = "SHORT"
                else:
                    decision = "WAIT"
                confidence = clamp(50.0 + abs(score - 50.0) * 2.0, 50.0, 90.0)
                cooldown = V32_COOLDOWN_MIN[tf] * 60
                recent = con.execute(
                    "SELECT 1 FROM v32_forecast_audit WHERE symbol=? AND timeframe=? AND created_at>=? LIMIT 1",
                    (symbol, tf, now - cooldown),
                ).fetchone()
                if recent:
                    continue
                con.execute(
                    """INSERT OR IGNORE INTO v32_forecast_audit(
                        symbol,timeframe,created_at,decision,confidence,price,horizon_minutes,outcome
                    ) VALUES(?,?,?,?,?,?,?,'PENDING')""",
                    (symbol, tf, now, decision, confidence, price, V32_HORIZON_MIN[tf]),
                )


def v32_evaluate_pending() -> int:
    """Resolve historical predictions from actual Binance OHLC, never from later model output."""
    now = time.time(); learned = 0
    with DB_LOCK, db_conn() as con:
        rows = con.execute("SELECT * FROM v32_forecast_audit WHERE outcome='PENDING' AND created_at <= ? ORDER BY created_at LIMIT 250", (now,)).fetchall()
    for row in rows:
        end = float(row["created_at"]) + int(row["horizon_minutes"]) * 60
        if now < end:
            continue
        try:
            tf = str(row["timeframe"]); symbol = str(row["symbol"]); decision = str(row["decision"])
            start_ms = int(float(row["created_at"]) * 1000); end_ms = int(end * 1000)
            # Small bounded pull: enough bars for the horizon, with no look-ahead
            # beyond the evaluation endpoint.
            bars = max(12, min(1000, int(math.ceil(row["horizon_minutes"] / max(1, _tf_minutes(tf)))) + 4))
            df = fetch_klines(symbol, tf, bars, start_ms=start_ms, end_ms=end_ms)
            window = df[(df["t"] >= start_ms) & (df["t"] <= end_ms)] if df is not None and not df.empty else pd.DataFrame()
            outcome, ret, fav, adv = _v32_tf_price_direction(window, decision, safe_float(row["price"], 0.0))
            if outcome == "PENDING":
                continue
            with DB_LOCK, db_conn() as con:
                con.execute("UPDATE v32_forecast_audit SET outcome=?,return_pct=?,max_favorable_pct=?,max_adverse_pct=?,evaluated_at=? WHERE id=?",
                            (outcome, ret, fav, adv, now, row["id"]))
            if outcome in {"WIN", "LOSS"}:
                learned += 1
        except Exception as exc:
            LOGGER.debug("V32 forecast evaluation failed #%s: %s", row["id"], exc)
    return learned


def _v32_beta_rate(wins: int, losses: int, prior: float = 0.5) -> float:
    # Conservative Beta prior. It avoids turning 1/1 into an apparent 50% oracle.
    a = 6.0 * prior + max(0, wins); b = 6.0 * (1.0-prior) + max(0, losses)
    return a / max(a + b, 1e-9)


def v32_performance_matrix(symbol: str | None = None) -> dict[str, Any]:
    """Detailed correctness by symbol/timeframe/direction with sample sufficiency."""
    where=[]; args=[]
    if symbol:
        where.append("symbol=?"); args.append(_normalize_symbol(symbol))
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    with DB_LOCK, db_conn() as con:
        rows = con.execute(f"SELECT * FROM v32_forecast_audit {clause} ORDER BY created_at DESC LIMIT 5000", args).fetchall()
    groups={}
    for r in rows:
        key=(str(r["symbol"]),str(r["timeframe"]),str(r["decision"]))
        g=groups.setdefault(key,{"symbol":key[0],"timeframe":key[1],"decision":key[2],"samples":0,"wins":0,"losses":0,"neutral":0,"wait_correct":0,"wait_missed":0,"returns":[]})
        outcome=str(r["outcome"])
        if outcome == "PENDING": continue
        g["samples"] += 1
        if outcome == "WIN": g["wins"] += 1
        elif outcome == "LOSS": g["losses"] += 1
        elif outcome == "NEUTRAL": g["neutral"] += 1
        elif outcome == "WAIT_CORRECT": g["wait_correct"] += 1
        elif outcome == "WAIT_MISSED": g["wait_missed"] += 1
        if r["return_pct"] is not None: g["returns"].append(float(r["return_pct"]))
    items=[]
    for g in groups.values():
        decisive=g["wins"]+g["losses"]
        g["win_rate"]=round(g["wins"]/decisive*100,1) if decisive else None
        total_group = sum(
            1 for r in rows
            if str(r["symbol"]) == g["symbol"] and str(r["timeframe"]) == g["timeframe"]
        )
        g["coverage"] = round(g["samples"] / max(1, total_group) * 100, 1)
        g["avg_return_pct"]=round(float(np.mean(g["returns"])),4) if g["returns"] else 0.0
        g["reliability"]=round(_v32_beta_rate(g["wins"],g["losses"])*100,1) if decisive else 50.0
        g["sample_status"]="ROBUST" if decisive>=30 else "DEVELOPING" if decisive>=V32_MIN_LEARN_SAMPLES else "INSUFFICIENT"
        g.pop("returns",None)
        items.append(g)
    items.sort(key=lambda x:(x["symbol"], V32_TFS.index(x["timeframe"]) if x["timeframe"] in V32_TFS else 99, x["decision"]))
    return {"version":V32_VERSION,"items":items,"count":len(items)}


def v32_learning_profile(symbol: str) -> dict[str, Any]:
    """Return conservative per-timeframe reliability used as one evidence adjustment."""
    matrix=v32_performance_matrix(symbol).get("items",[])
    profile={"symbol":symbol,"timeframes":{},"aggregate":50.0,"samples":0}
    weighted=[]
    for tf in V32_TFS:
        rows=[x for x in matrix if x["timeframe"]==tf and x["decision"] in {"LONG","SHORT"}]
        wins=sum(int(x["wins"]) for x in rows); losses=sum(int(x["losses"]) for x in rows); n=wins+losses
        rel=_v32_beta_rate(wins,losses)*100 if n else 50.0
        recent_score=rel
        if rows:
            recent_score=float(np.mean([x["reliability"] for x in rows]))
        weight=1.0 + (clamp(recent_score,35,65)-50)/50.0 * V32_LEARN_CAP if n>=V32_MIN_LEARN_SAMPLES else 1.0
        profile["timeframes"][tf]={"samples":n,"wins":wins,"losses":losses,"reliability":round(rel,1),"weight":round(weight,4),"status":"LEARNED" if n>=V32_MIN_LEARN_SAMPLES else "WARMING"}
        if n: weighted.append((rel,n))
        profile["samples"] += n
    profile["aggregate"]=round(sum(r*n for r,n in weighted)/sum(n for _,n in weighted),1) if weighted else 50.0
    return profile


def v32_adaptive_evidence(item: dict[str, Any]) -> dict[str, Any]:
    """Create one historical-calibration evidence channel for the V31 brain."""
    symbol=_normalize_symbol(item.get("symbol", "")); profile=v32_learning_profile(symbol)
    tf_scores=(item.get("tf_scores") or {})
    # If the live item does not expose tf scores, derive a neutral profile only;
    # never invent direction from history.
    long_boost=short_boost=0.0; used=[]
    for tf in V32_TFS:
        p=profile["timeframes"].get(tf,{})
        if p.get("samples",0) < V32_MIN_LEARN_SAMPLES: continue
        sc=safe_float(tf_scores.get(tf),50.0)
        direction="LONG" if sc>=55 else "SHORT" if sc<=45 else "WAIT"
        delta=(safe_float(p.get("reliability"),50)-50)/100.0
        if direction=="LONG": long_boost += delta * 0.025; used.append(tf)
        elif direction=="SHORT": short_boost += delta * 0.025; used.append(tf)
    return {"symbol":symbol,"long_adjustment":round(long_boost,4),"short_adjustment":round(short_boost,4),"profile":profile,"used_timeframes":used}


def v32_register_learning_maintenance() -> None:
    try:
        v32_evaluate_pending()
        # Rebuild the authoritative adaptive state from outcomes only. Existing
        # engines remain intact; V32 adds a small measured calibration signal.
        with DB_LOCK, db_conn() as con:
            state={"updated_at":time.time(),"symbols":{}}
            syms=[r[0] for r in con.execute("SELECT DISTINCT symbol FROM v32_forecast_audit").fetchall()]
        for sym in syms:
            state["symbols"][sym]=v32_learning_profile(sym)
        with DB_LOCK, db_conn() as con:
            con.execute("INSERT OR REPLACE INTO v32_learning_state(key,updated_at,payload) VALUES('global',?,?)",(time.time(),json.dumps(state,ensure_ascii=False)))
    except Exception as exc:
        LOGGER.debug("V32 maintenance failed: %s", exc)


# Extend the single V31 brain with one conservative historical-calibration channel.
_v32_analyze_asset_v31 = analyze_asset

def analyze_asset(symbol: str, btc_trend: str) -> Optional[dict[str, Any]]:
    item=_v32_analyze_asset_v31(symbol,btc_trend)
    if not item: return None
    try:
        # The prediction being learned is always the canonical V31 output from
        # this same scan. Learning never gets to create an independent signal.
        learning=v32_adaptive_evidence(item)
        debate=dict(item.get("deep_consensus_v30") or {})
        for side, adj in (("long",learning["long_adjustment"]),("short",learning["short_adjustment"])):
            if isinstance(debate.get(side),dict):
                debate[side]=dict(debate[side]); debate[side]["score"]=float(debate[side].get("score",0) or 0)+adj
        canonical=TITAN_CANONICAL_V31.decide(item,debate)
        decision=canonical["decision"]
        item["decision_tag"]=decision
        item["bias"]="صعودی" if decision=="LONG" else "نزولی" if decision=="SHORT" else "خنثی"
        item["entry_mode"]="EARLY" if decision in {"LONG","SHORT"} else "WAIT"
        item["decision_confidence"]=canonical["confidence"]
        item["decision_state"]=canonical["state"]
        item["signal_tag"]=f"V32 LEARNED CANONICAL — {decision}"
        item["v32_learning"]=learning
        item["canonical_decision"]={**(item.get("canonical_decision") or {}),"decision":decision,"bias":item["bias"],"confidence":canonical["confidence"],"state":canonical["state"],"version":V32_VERSION,"authoritative":True}
        item["decision_audit_v32"]={"version":V32_VERSION,"decision":decision,"learning":learning,"canonical":canonical,"authoritative":True}
        item["decision_architecture"]={"type":"ONE_BRAIN_MANY_EVIDENCE_CHANNELS","authoritative_source":V32_VERSION,"upstream_are_evidence_only":True,"learning_is_evidence_only":True,"final_decision":decision}
        return item
    except Exception as exc:
        LOGGER.exception("V32 learned canonical failed for %s: %s",symbol,exc)
        return item


# ============================================================
# ROUTES
# ============================================================

def _query_int(name: str, default: int, lo: int, hi: int) -> int:
    """Parse bounded integer query parameters without turning bad URLs into 500s."""
    try:
        value = int(request.args.get(name, default))
    except (TypeError, ValueError):
        value = int(default)
    return max(int(lo), min(int(value), int(hi)))


def _query_timeframe(name: str = "timeframe", default: str = "1h") -> str:
    value = str(request.args.get(name, default) or default).strip()
    # Binance-supported TITAN analysis frames. Reject arbitrary strings early.
    return value if value in {"15m", "1h", "4h", "1d"} else default

_MAINTENANCE_LOCK = threading.Lock()

def _safe_background_forecast_maintenance():
    if not _MAINTENANCE_LOCK.acquire(blocking=False):
        return
    try:
        v32_evaluate_pending()
        v32_register_learning_maintenance()
    except Exception as exc:
        LOGGER.warning("V32 learning maintenance failed: %s", exc)
    try:
        evaluate_pending_forecasts()
    except Exception as exc:
        LOGGER.warning("Background forecast maintenance failed: %s", exc)
    try:
        evaluate_paper_trades()
    except Exception as exc:
        LOGGER.warning("Background paper-trade maintenance failed: %s", exc)
    try:
        autonomous_performance_maintenance(False)
    except Exception as exc:
        LOGGER.debug("Autonomous performance maintenance failed: %s", exc)
    finally:
        _MAINTENANCE_LOCK.release()

# --- Render speed: compile the huge dashboard template once ---
_DASHBOARD_TEMPLATE = None

def _get_dashboard_template():
    """Compile the large dashboard HTML once; reuse Flask's Jinja env (filters/globals)."""
    global _DASHBOARD_TEMPLATE
    if _DASHBOARD_TEMPLATE is None:
        try:
            _DASHBOARD_TEMPLATE = app.jinja_env.from_string(HTML)
        except Exception as exc:
            LOGGER.warning("dashboard template compile failed: %s", exc)
            return None
    return _DASHBOARD_TEMPLATE


@app.route("/")
def index():
    # Fast-but-complete bootstrap: if a usable snapshot exists, render it immediately.
    # On a cold start, wait for the market engine ONCE so the user receives the full coin
    # dashboard exactly like the original build. The engine itself is parallelized and
    # Gemini is non-blocking, making the cold start substantially faster without a blank UI.
    try:
        t0 = time.perf_counter()
        market_data, gemini_summary, macro = _fast_market_snapshot()
        with CACHE_LOCK:
            cache_age = time.time() - float(CACHE.get("timestamp") or 0) if CACHE.get("timestamp") else 1e9
        # Never block the first paint on a full multi-coin analyze when any snapshot exists.
        # Cold start without disk cache: kick background refresh and render lightweight empty shell.
        if not market_data:
            # One fast blocking scan (LLM skipped via DASHBOARD_FAST_SCAN) so first paint has coins.
            try:
                market_data, gemini_summary, macro = update_cache(False)
            except Exception as _uc_exc:
                LOGGER.warning("cold update_cache: %s", _uc_exc)
                _background_market_refresh(False)
        elif cache_age >= MARKET_CACHE_TTL:
            _background_market_refresh(False)
        if RENDER_PERF_LOG:
            LOGGER.info("index snapshot ready in %.0fms coins=%s age=%.1fs",
                        (time.perf_counter() - t0) * 1000, len(market_data or []), cache_age if market_data else -1)
    except Exception as exc:
        LOGGER.exception("Index market bootstrap error: %s", exc)
        market_data, gemini_summary, macro = _fast_market_snapshot()
        if not market_data:
            _background_market_refresh(False)
    # Historical evaluation is maintenance work; never hold up dashboard rendering.
    threading.Thread(target=lambda: _safe_background_forecast_maintenance(), name="titan-forecast-maint", daemon=True).start()
    try:
        audit = get_audit_stats()
    except Exception as exc:
        LOGGER.exception("Audit stats failed on index: %s", exc)
        audit = {"evaluated": 0, "wins": 0, "losses": 0, "neutral": 0, "ambiguous": 0, "win_rate": 0.0, "tp_hits": 0, "sl_hits": 0, "label": "در حال آماده‌سازی"}
    try:
        tpl = _get_dashboard_template()
        ctx = dict(market_data=market_data or [], gemini_summary=gemini_summary or "", gemini_status=_gemini_dashboard_status(gemini_summary or ""), macro=macro or {}, settings=USER_SETTINGS, audit=audit)
        if tpl is not None:
            return tpl.render(**ctx)
        return render_template_string(HTML, **ctx)
    except Exception as exc:
        # Last-resort visible page so the dashboard never degenerates into a blank JSON response.
        LOGGER.exception("Dashboard render failed: %s", exc)
        safe_detail = str(exc).replace("<", "&lt;").replace(">", "&gt;")
        return (
            "<!doctype html><html lang='fa' dir='rtl'><meta charset='utf-8'>"
            "<title>TITAN Enterprise</title>"
            "<body style='background:#050812;color:#eef2ff;font-family:Tahoma;padding:24px'>"
            "<h1 style='color:#38bdf8'>⚡ TITAN ENTERPRISE</h1>"
            "<p>موتور داده فعال است، ولی رندر یکی از بخش‌های داشبورد خطا داده است.</p>"
            f"<pre style='white-space:pre-wrap;background:#0b1220;padding:16px;border-radius:12px'>{safe_detail}</pre>"
            "<p>این خطا در لاگ TITAN نیز ثبت شده است.</p></body></html>", 500, {"Content-Type": "text/html; charset=utf-8"}
        )


@app.get("/api/dashboard-status")
def api_dashboard_status():
    """Tiny non-blocking status endpoint used by the fast dashboard bootstrap."""
    with CACHE_LOCK:
        data = CACHE.get("data") or []
        ts = float(CACHE.get("timestamp") or 0)
    return jsonify({"ok": True, "ready": bool(data), "count": len(data), "age": round(max(0.0, time.time()-ts), 1) if ts else None, "refreshing": bool(_BACKGROUND_REFRESH_RUNNING), "scan": _scan_progress_snapshot()})

@app.get("/api/scan-progress")
def api_scan_progress():
    p=_scan_progress_snapshot()
    with CACHE_LOCK:
        ts=float(CACHE.get("timestamp") or 0)
    if not p.get("last_success_at") and ts:
        p["last_success_at"]=ts
        p["finished_at"]=ts
    p["cache_age_sec"]=round(max(0.0,time.time()-ts),1) if ts else None
    p["server_now"]=time.time()
    return jsonify({"ok":True,"progress":p})

@app.get("/api/performance-learning")
def api_performance_learning():
    try:
        symbol=request.args.get("symbol","").strip() or None
        v32_evaluate_pending()
        matrix=v32_performance_matrix(symbol)
        learning=v32_learning_profile(_normalize_symbol(symbol)) if symbol else None
        with DB_LOCK, db_conn() as con:
            total=con.execute("SELECT COUNT(*) FROM v32_forecast_audit").fetchone()[0]
            pending=con.execute("SELECT COUNT(*) FROM v32_forecast_audit WHERE outcome='PENDING'").fetchone()[0]
            wins=con.execute("SELECT COUNT(*) FROM v32_forecast_audit WHERE outcome='WIN'").fetchone()[0]
            losses=con.execute("SELECT COUNT(*) FROM v32_forecast_audit WHERE outcome='LOSS'").fetchone()[0]
            wait_ok=con.execute("SELECT COUNT(*) FROM v32_forecast_audit WHERE outcome='WAIT_CORRECT'").fetchone()[0]
            wait_missed=con.execute("SELECT COUNT(*) FROM v32_forecast_audit WHERE outcome='WAIT_MISSED'").fetchone()[0]
        dec=wins+losses
        return jsonify({"ok":True,"version":V32_VERSION,"matrix":matrix,"learning":learning,"summary":{"total":total,"pending":pending,"wins":wins,"losses":losses,"directional_win_rate":round(wins/dec*100,1) if dec else None,"wait_correct":wait_ok,"wait_missed":wait_missed}})
    except Exception as exc:
        LOGGER.exception("V32 performance endpoint failed")
        return jsonify({"ok":False,"error":str(exc)}),500

@app.get("/api/forecast-audit")
def api_forecast_audit():
    symbol=request.args.get("symbol","").strip()
    limit=_query_int("limit",100,10,500)
    where="WHERE symbol=?" if symbol else ""; args=[_normalize_symbol(symbol)] if symbol else []
    with DB_LOCK, db_conn() as con:
        rows=con.execute(f"SELECT * FROM v32_forecast_audit {where} ORDER BY created_at DESC LIMIT ?",args+[limit]).fetchall()
    return jsonify({"ok":True,"items":[dict(r) for r in rows]})

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