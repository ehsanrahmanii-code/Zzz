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