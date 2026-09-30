                            CACHE["timestamp"] = time.time()
                    _scan_progress_update(
                        status="running", phase="قیمت زنده موقت", percent=8,
                        message=f"{len(emergency)} ارز · تحلیل کامل در صف",
                        completed=0, total=len(USER_SETTINGS.get("active_coins") or DEFAULT_COINS),
                        started_at=time.time(), fresh=False,
                    )
            except Exception as exc:
                LOGGER.warning("index emergency: %s", exc)
            try:
                threading.Thread(target=lambda: _background_market_refresh(True), name="titan-force-scan", daemon=True).start()
            except Exception:
                pass
        return _CENTRAL_PREV_INDEX()
    except Exception as exc:
        LOGGER.exception("index wrapper: %s", exc)
        return _CENTRAL_PREV_INDEX()


@app.get("/api/system-audit")
def api_system_audit():
    """Runtime integrity contract: components, DB schema, and final seal."""
    try:
        return jsonify(titan_system_audit())
    except Exception as exc:
        return jsonify({"passed": False, "version": V42_VERSION, "error": str(exc)[:240]}), 500


@app.get("/api/central-brain")
def api_central_brain():
    try:
        with DB_LOCK, db_conn() as con:
            pending = int(con.execute("SELECT COUNT(*) FROM central_predictions WHERE outcome='PENDING'").fetchone()[0])
            done = con.execute(
                "SELECT outcome,COUNT(*) FROM central_predictions WHERE outcome!='PENDING' GROUP BY outcome"
            ).fetchall()
            comps = con.execute(
                "SELECT component,samples,wins,losses,reward_sum,penalty_sum,weight FROM central_component_stats ORDER BY component"
            ).fetchall()
        return jsonify({
            "ok": True,
            "version": TITAN_CENTRAL_VERSION,
            "pending": pending,
            "outcomes": {str(r[0]): int(r[1]) for r in done},
            "components": [
                {"component": r[0], "samples": r[1], "wins": r[2], "losses": r[3],
                 "reward": r[4], "penalty": r[5], "weight": r[6]}
                for r in comps
            ],
            "live_weights": dict(_CENTRAL_WEIGHTS),
            "mode": "CENTRAL_GOVERNOR_ONLY",
            "note": "سیگنال‌ها احتمالی هستند و تضمین سود نیست.",
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)[:240]}), 500


@app.get("/api/v31-edge")
def api_v31_edge():
    """Expose the 21-module Edge Suite without changing the existing dashboard contract."""
    try:
        with CACHE_LOCK:
            rows=list(CACHE.get("data") or [])
        suite=[]
        for item in rows:
            e=item.get("v31_edge_suite") or {}
            suite.append({"symbol":item.get("symbol"),"decision":item.get("decision_tag") or item.get("decision"),
                          "safety_wait":e.get("safety_wait",False),"uncertainty":(e.get("uncertainty") or {}).get("uncertainty"),
                          "robustness":(e.get("adversarial") or {}).get("robustness"),
                          "entry_stability":(e.get("entry_stability") or {}).get("score"),
                          "data_quality":(e.get("data_quality") or {}).get("score"),
                          "explainability":e.get("explainability") or {}})
        return jsonify({"ok":True,"version":V31_EDGE_VERSION,"count":len(suite),"items":suite})
    except Exception as exc:
        return jsonify({"ok":False,"error":str(exc)[:240]}),500

@app.get("/api/v36-resonance")
def api_v36_resonance():
    """Dashboard summary of Quantum Resonance Edge state per symbol."""
    try:
        with CACHE_LOCK:
            rows = list(CACHE.get("data") or [])
        items = []
        killed = boosted = 0
        for item in rows:
            r = item.get("v36_resonance") or {}
            ha = r.get("horizon_agreement") or {}
            pd_ = r.get("price_drift") or {}
            ca = r.get("cross_asset") or {}
            if r.get("killed"):
                killed += 1
            if r.get("boosted"):
                boosted += 1
            items.append({
                "symbol": item.get("symbol"),
                "decision": item.get("decision_tag") or item.get("decision"),
                "confidence": item.get("decision_confidence"),
                "agreement": ha.get("agreement"),
                "horizon_direction": ha.get("direction"),
                "aligned": ha.get("aligned_with_decision"),
                "drift_pct": pd_.get("drift_pct"),
                "drift_kill": pd_.get("kill"),
                "same_side_cluster": ca.get("same_side"),
                "cluster_penalty": ca.get("penalty"),
                "killed": bool(r.get("killed")),
                "boosted": bool(r.get("boosted")),
                "notes": r.get("notes") or [],
                "live_sync": item.get("live_sync"),
                "live_age_sec": item.get("live_price_age_sec"),
                "v34": (item.get("v34_opportunity") or {}).get("state"),
            })
        return jsonify({
            "ok": True,
            "version": globals().get("V36_VERSION", "V36"),
            "param_version": TITAN_PARAM_VERSION,
            "count": len(items),
            "killed": killed,
            "boosted": boosted,
            "items": items,
            "note": "رزونانس کوانتومی فقط کیفیت/ایمنی سیگنال را تنظیم می‌کند؛ احتمال برد تضمینی نیست.",
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)[:240]}), 500



@app.get("/api/v40-precision")
def api_v40_precision():
    """History bans, live precision status, self-heal report endpoint."""
    try:
        hist = _v40_refresh_hist(force=True)
        with CACHE_LOCK:
            rows = list(CACHE.get("data") or [])
        live = []
        for item in rows:
            p = item.get("v40_precision") or {}
            live.append({
                "symbol": item.get("symbol"),
                "decision": item.get("decision_tag") or item.get("decision"),
                "confidence": item.get("decision_confidence"),
                "passed": p.get("passed"),
                "demoted": item.get("v40_demoted"),
                "code": item.get("v40_demote_code"),
                "horizon": (p.get("horizon") or {}).get("agreement"),
                "history_wr": (p.get("history") or {}).get("wr"),
                "history_n": (p.get("history") or {}).get("samples"),
            })
        by_key = hist.get("by_key") or {}
        banned = [k for k, st in by_key.items()
                  if st.get("samples", 0) >= V40_BAN_N and st.get("wr", 50) < V40_BAN_WR]
        with DB_LOCK, db_conn() as con:
            totals = {r[0]: r[1] for r in con.execute(
                "SELECT outcome, COUNT(*) FROM central_predictions GROUP BY outcome").fetchall()}
        w, l = int(totals.get("WIN", 0) or 0), int(totals.get("LOSS", 0) or 0)
        return jsonify({
            "ok": True,
            "version": V40_VERSION,
            "param_version": TITAN_PARAM_VERSION,
            "decided_win_rate": round(100.0 * w / (w + l), 1) if (w + l) else None,
            "central_totals": totals,
            "global_short": hist.get("g_short"),
            "global_long": hist.get("g_long"),
            "banned_keys": banned,
            "live": live,
            "note": "V40 فقط سیگنال با اجماع، RR قوی، سابقه قابل قبول و رژیم سازگار را منتشر می‌کند.",
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)[:240]}), 500


@app.get("/api/edge-lab")
def api_edge_lab():
    try:
        return jsonify(_edge_api_report())
    except Exception as exc:
        return jsonify({"ok":False,"error":str(exc)[:240]}),500


def _central_learner_loop():
    while not LIVE_STOP.is_set():
        try:
            _central_evaluate_pending()
            _central_load_weights()
        except Exception as exc:
            LOGGER.debug("central learner: %s", exc)
        LIVE_STOP.wait(40)


def _shutdown_runtime() -> None:
    """Stop background loops and close reusable worker pools on process exit."""
    LIVE_STOP.set()
    for pool_name in ("_ANALYSIS_POOL", "_KLINE_POOL", "_AI_POOL"):
        pool = globals().get(pool_name)
        if pool is not None:
            try:
                pool.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                try:
                    pool.shutdown(wait=False)
                except Exception:
                    pass
            except Exception:
                pass


import atexit
atexit.register(_shutdown_runtime)


def _open_dashboard_browser() -> None:
    """Open the local dashboard after the HTTP server becomes reachable."""
    try:
        import webbrowser
        url = f"http://127.0.0.1:{PORT}/"
        for _ in range(30):
            try:
                with socket.create_connection(("127.0.0.1", PORT), timeout=0.25):
                    webbrowser.open(url, new=1, autoraise=True)
                    return
            except OSError:
                LIVE_STOP.wait(0.5)
                if LIVE_STOP.is_set():
                    return
    except Exception as exc:
        LOGGER.debug("Dashboard browser launch skipped: %s", exc)


# continuous learner started with main
_CENTRAL_LEARNER_STARTED = False


def _ensure_central_learner():
    global _CENTRAL_LEARNER_STARTED
    if _CENTRAL_LEARNER_STARTED:
        return
    try:
        threading.Thread(target=_central_learner_loop, name="titan-central-learner", daemon=True).start()
        _CENTRAL_LEARNER_STARTED = True
    except Exception:
        pass




# ============================================================
# TITAN V44 — BALANCED OPPORTUNITY + HONEST OUTCOME LEARNING
# ============================================================
V44_VERSION = "TITAN-V44-BALANCED-LEARNING"
# A modestly more opportunity-aware operating point. V42 hard safety checks
# remain authoritative; these values never override stale/bad data or invalid levels.
_CENTRAL_MIN_EDGE = 0.12
_CENTRAL_MIN_MARGIN = 0.055
_CENTRAL_MIN_TRUST = 48.0

_V44_PREV_EVIDENCE = _v43_unified_evidence

def _v43_unified_evidence(item: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Keep directional evidence separate from quality/reliability evidence.

    Precision, robustness, opportunity, calibration and forecast magnitude are
    not direction votes. Counting them as LONG/SHORT was a source of bias.
    They remain visible in the audit registry and are applied as quality context.
    """
    votes, participation = _V44_PREV_EVIDENCE(item)
    quality_only = {"precision_engine", "v31_edge_suite", "v34_opportunity",
                    "v40_precision", "realized_calibration", "forecast_engine"}
    quality = {}
    for name in list(votes):
        if name in quality_only:
            quality[name] = votes.pop(name)
    # Re-add forecast only when its direction is explicit; never infer direction
    # from a positive expected move alone (which can be an unsigned magnitude).
    fc = item.get("candle_forecast") or item.get("forecast") or {}
    if isinstance(fc, dict):
        bias = str(fc.get("overall_bias") or "").strip().lower()
        if bias in {"صعودی", "bullish", "up", "long"}:
            _v43_add_vote(votes, "forecast_direction", 68.0, "جهت پیش‌بینی", "FORECAST", True, 0.40)
        elif bias in {"نزولی", "bearish", "down", "short"}:
            _v43_add_vote(votes, "forecast_direction", 32.0, "جهت پیش‌بینی", "FORECAST", True, 0.40)
    directional = [v for v in votes.values() if v.get("side") in {"LONG", "SHORT"}
                   and safe_float(v.get("confidence"), 0.0) >= 0.08]
    groups = {str(v.get("group") or "CORE") for v in directional}
    required_components, required_groups = 5, 3
    sufficient = len(directional) >= required_components and len(groups) >= required_groups
    participation.update({
        "active_components": len(directional), "active_groups": len(groups),
        "required_components": required_components, "required_groups": required_groups,
        "sufficient": sufficient,
        "directional_components": [k for k,v in votes.items() if v in directional],
        "quality_only_channels": quality,
        "policy": "direction votes are separated from quality/calibration channels",
    })
    return votes, participation

_V44_PREV_DECIDE = _v43_unified_decide

def _v43_unified_decide(item: dict[str, Any]) -> dict[str, Any]:
    x = _V44_PREV_DECIDE(item)
    pack = x.get("unified_central") if isinstance(x.get("unified_central"), dict) else {}
    # Transparent quality modifiers; do not manufacture direction or bypass hard vetoes.