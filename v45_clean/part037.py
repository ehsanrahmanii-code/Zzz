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
    quality = pack.get("participation", {}).get("quality_only_channels", {})
    v40 = quality.get("v40_precision") or {}
    v31 = quality.get("v31_edge_suite") or {}
    cal = quality.get("realized_calibration") or {}
    modifiers = []
    if v40:
        q = safe_float(v40.get("raw"), 50.0)
        modifiers.append({"module":"V40 precision", "score":q, "role":"quality-only"})
    if v31:
        q = safe_float(v31.get("raw"), 50.0)
        modifiers.append({"module":"V31 robustness", "score":q, "role":"quality-only"})
    if cal:
        modifiers.append({"module":"realized calibration", "score":safe_float(cal.get("raw"),50),
                          "samples":safe_float((x.get("probability_calibration") or {}).get("samples"),0),
                          "role":"probability calibration, not direction"})
    if isinstance(pack, dict):
        pack["quality_modifiers"] = modifiers
        pack["opportunity_policy"] = {
            "version": V44_VERSION,
            "edge_floor": _CENTRAL_MIN_EDGE,
            "margin_floor": _CENTRAL_MIN_MARGIN,
            "wait_is_not_a_target": True,
            "hard_safety_vetoes_preserved": True,
            "quality_channels_not_counted_as_direction": True,
        }
        x["unified_central"] = pack
        arch = x.get("decision_architecture") if isinstance(x.get("decision_architecture"),dict) else {}
        arch.update({"balanced_opportunity_policy": V44_VERSION,
                    "quality_channels_separate_from_direction": True,
                    "outcome_learning_required": True})
        x["decision_architecture"] = arch
        x["authority"] = V44_VERSION
    return x

# Detailed read-only evaluation endpoint. It reports observed history rather than
# claiming that a model has learned correctly merely because a loop is running.
@app.get("/api/decision-quality")
def api_decision_quality():
    try:
        with DB_LOCK, db_conn() as con:
            rows = con.execute("""SELECT outcome, confidence FROM central_predictions
                WHERE outcome IN ('WIN','LOSS') ORDER BY created_at DESC LIMIT 5000""").fetchall()
            total = int(con.execute("SELECT COUNT(*) FROM central_predictions").fetchone()[0])
            pending = int(con.execute("SELECT COUNT(*) FROM central_predictions WHERE outcome='PENDING'").fetchone()[0])
            # Optional trade metrics table is present in newer DB schemas.
            metrics = []
            try:
                metrics = con.execute("""SELECT m.r_multiple,m.net_return_pct,p.outcome
                    FROM central_trade_metrics m JOIN central_predictions p ON p.id=m.prediction_id
                    WHERE p.outcome IN ('WIN','LOSS') ORDER BY m.evaluated_at DESC LIMIT 5000""").fetchall()
            except Exception:
                metrics = []
        wins = sum(1 for r in rows if str(r[0]) == 'WIN')
        losses = sum(1 for r in rows if str(r[0]) == 'LOSS')
        confs = [safe_float(r[1], 0.0) for r in rows if r[1] is not None]
        rs = [safe_float(r[0], 0.0) for r in metrics if r[0] is not None]
        returns = [safe_float(r[1], 0.0) for r in metrics if r[1] is not None]
        return jsonify({"ok": True, "version": V44_VERSION,
            "history": {"recorded_predictions": total, "pending": pending,
                "resolved": len(rows), "wins": wins, "losses": losses,
                "observed_win_rate_pct": round(100*wins/max(1,wins+losses), 2) if rows else None,
                "mean_recorded_confidence": round(sum(confs)/len(confs),2) if confs else None,
                "mean_r_multiple": round(sum(rs)/len(rs),4) if rs else None,
                "mean_net_return_pct": round(sum(returns)/len(returns),4) if returns else None,
                "trade_metric_samples": len(metrics)},
            "learning_status": {"outcome_based": True,
                "insufficient_history": len(rows) < 30,
                "minimum_resolved_for_reliable_calibration": 30,
                "note": "این آمار گذشته است؛ به‌تنهایی تضمین‌کننده عملکرد آینده نیست."},
            "audit": {"last_5000_resolved_outcomes_used": len(rows),
                "confidence_is_not_win_probability": True,
                "win_rate_excludes_pending": True}})
    except Exception as exc:
        return jsonify({"ok": False, "version": V44_VERSION, "error": str(exc)[:240]}), 500


# ============================================================
# TITAN V44 — ADAPTIVE OPPORTUNITY + CONTINUOUS ERROR-LEARNING BRAIN
# ============================================================
# V44 does not promise zero errors.  Its job is to reduce avoidable errors,
# distinguish unsafe WAITs from merely weak-consensus WAITs, and adapt bounded
# thresholds from realized outcomes without allowing a short bad/good streak to
# destabilize the governor.
V44_VERSION = "TITAN-V44-ADAPTIVE-OPPORTUNITY-LEARNING"
V44_POLICY_MIN_SAMPLES = 12
V44_POLICY_WINDOW = 80
V44_BASE_EDGE = 0.135
V44_BASE_MARGIN = 0.075
V44_BASE_TRUST = 46.0
V44_MIN_EDGE = 0.105
V44_MAX_EDGE = 0.205
V44_MIN_MARGIN = 0.055
V44_MAX_MARGIN = 0.135
V44_MIN_TRUST = 42.0
V44_MAX_TRUST = 55.0
V44_MIN_CONFIDENCE = 58.0
V44_MAX_CONFIDENCE = 90.0


def _v44_learning_schema() -> None:
    try:
        with DB_LOCK, db_conn() as con:
            con.execute("""CREATE TABLE IF NOT EXISTS central_learning_events(
                prediction_id INTEGER PRIMARY KEY,
                created_at REAL,
                symbol TEXT,
                direction TEXT,
                outcome TEXT,
                return_pct REAL,
                error_class TEXT,
                lesson TEXT,
                regime TEXT,
                confidence REAL,
                edge REAL,
                margin REAL,
                policy_edge REAL,
                policy_margin REAL,
                policy_trust REAL,
                learned_at REAL
            )""")
            con.execute("""CREATE TABLE IF NOT EXISTS central_policy_state(
                scope TEXT PRIMARY KEY,
                samples INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                time_exits INTEGER DEFAULT 0,
                avg_return REAL DEFAULT 0,
                win_rate REAL DEFAULT 50,
                edge_threshold REAL DEFAULT 0.135,
                margin_threshold REAL DEFAULT 0.075,
                trust_threshold REAL DEFAULT 46,
                last_update REAL,
                lesson TEXT
            )""")
            con.execute("CREATE INDEX IF NOT EXISTS idx_learning_symbol ON central_learning_events(symbol,learned_at)")
            con.commit()
    except Exception as exc:
        LOGGER.debug("V44 learning schema: %s", exc)


_v44_learning_schema()


def _v44_policy_stats(symbol: str = "", direction: str = "") -> dict[str, Any]:
    """Read realized outcomes; never treat PENDING/AMBIGUOUS as wins/losses."""
    try:
        clauses = ["outcome IN ('WIN','LOSS','TIME_EXIT')"]
        args: list[Any] = []
        if symbol:
            clauses.append("symbol=?")
            args.append(_normalize_symbol(symbol))
        if direction in {"LONG", "SHORT"}:
            clauses.append("decision=?")
            args.append(direction)
        where = " AND ".join(clauses)
        with DB_LOCK, db_conn() as con:
            rows = con.execute(
                f"SELECT outcome,return_pct,confidence,created_at FROM central_predictions WHERE {where} ORDER BY created_at DESC LIMIT ?",
                (*args, V44_POLICY_WINDOW),
            ).fetchall()
        if not rows:
            return {"samples": 0, "wins": 0, "losses": 0, "time_exits": 0, "win_rate": 50.0,
                    "avg_return": 0.0, "thresholds": {"edge": V44_BASE_EDGE, "margin": V44_BASE_MARGIN, "trust": V44_BASE_TRUST}}
        usable = [r for r in rows if str(r[0]) in {"WIN", "LOSS", "TIME_EXIT"}]
        wins = sum(str(r[0]) == "WIN" for r in usable)
        losses = sum(str(r[0]) == "LOSS" for r in usable)
        exits = sum(str(r[0]) == "TIME_EXIT" for r in usable)
        n_bin = wins + losses
        wr = 100.0 * wins / n_bin if n_bin else 50.0
        returns = [safe_float(r[1], 0.0) for r in usable]
        avg_ret = sum(returns) / len(returns) if returns else 0.0
        # Bounded adaptation: good realized edge opens the gate slightly;
        # weak realized edge tightens it.  The adjustment is deliberately small.
        edge = V44_BASE_EDGE
        margin = V44_BASE_MARGIN
        trust = V44_BASE_TRUST
        if len(usable) >= V44_POLICY_MIN_SAMPLES:
            if wr >= 62.0 and avg_ret > 0:
                edge -= 0.018; margin -= 0.012; trust -= 1.5
            elif wr >= 56.0 and avg_ret >= 0:
                edge -= 0.010; margin -= 0.007; trust -= 0.8
            elif wr <= 42.0 or avg_ret < -0.10:
                edge += 0.028; margin += 0.018; trust += 2.5
            elif wr <= 47.0:
                edge += 0.015; margin += 0.010; trust += 1.2
        return {
            "samples": len(usable), "wins": wins, "losses": losses, "time_exits": exits,
            "win_rate": round(wr, 2), "avg_return": round(avg_ret, 5),
            "thresholds": {"edge": clamp(edge, V44_MIN_EDGE, V44_MAX_EDGE),
                           "margin": clamp(margin, V44_MIN_MARGIN, V44_MAX_MARGIN),
                           "trust": clamp(trust, V44_MIN_TRUST, V44_MAX_TRUST)},
        }
    except Exception as exc:
        return {"samples": 0, "wins": 0, "losses": 0, "time_exits": 0, "win_rate": 50.0,
                "avg_return": 0.0, "thresholds": {"edge": V44_BASE_EDGE, "margin": V44_BASE_MARGIN, "trust": V44_BASE_TRUST},
                "error": str(exc)[:160]}


def _v44_hard_safety_reasons(item: dict[str, Any]) -> list[str]:
    """Reasons that must never be overridden merely to capture opportunity."""