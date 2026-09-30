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
