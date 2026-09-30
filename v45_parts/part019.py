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
    hard: list[str] = []
    u = item.get("unified_central") or {}
    for r in u.get("participation", {}).get("hard_vetoes", []) if isinstance(u, dict) else []:
        hard.append(str(r))
    v40 = item.get("v40_precision") or {}
    if isinstance(v40, dict):
        hard.extend(str(x) for x in (v40.get("hard_blocks") or []) if x)
        if bool(v40.get("veto")) or bool(v40.get("hard_block")):
            hard.append("V40_HARD_VETO")
    real = (item.get("central_decision") or {}).get("real_edge") or item.get("real_edge") or {}
    if isinstance(real, dict):
        for r in real.get("no_trade_reasons") or []:
            # quality-only reasons are soft; structural/risk violations remain hard.
            rs = str(r)
            if rs in {"invalid_levels", "weak_rr", "correlation_risk", "regime_conflict", "structure_not_confirmed",
                      "liquidity_flow_conflict", "late_entry"}:
                hard.append(rs)
    integ = item.get("v42_integrity") or {}
    if isinstance(integ, dict) and not integ.get("passed", True):
        for r in integ.get("reasons") or []:
            hard.append(str(r))
    return list(dict.fromkeys(hard))


def _v44_should_promote(item: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """Turn only *soft* WAITs into opportunities when evidence is strong enough."""
    x = item or {}
    u = x.get("unified_central") or {}
    candidate = str(u.get("candidate") or "WAIT").upper()
    if candidate not in {"LONG", "SHORT"}:
        return False, {"reason": "no_directional_candidate"}
    hard = _v44_hard_safety_reasons(x)
    if hard:
        return False, {"reason": "hard_safety", "hard_reasons": hard}
    stats = _v44_policy_stats(str(x.get("symbol") or ""), candidate)
    th = stats.get("thresholds") or {}
    edge = safe_float(u.get("edge"), 0.0)
    margin = safe_float(u.get("margin"), 0.0)
    trust = safe_float(u.get("trust"), 0.0)
    conf = safe_float(u.get("confidence"), safe_float(x.get("decision_confidence"), 0.0))
    # Require two independent dimensions above gate plus usable confidence.
    ok = edge >= safe_float(th.get("edge"), V44_BASE_EDGE) and \
         margin >= safe_float(th.get("margin"), V44_BASE_MARGIN) and \
         trust >= safe_float(th.get("trust"), V44_BASE_TRUST) and \
         conf >= V44_MIN_CONFIDENCE
    return ok, {
        "candidate": candidate, "edge": round(edge, 5), "margin": round(margin, 5), "trust": round(trust, 2),
        "confidence": round(conf, 2), "thresholds": th, "policy_stats": stats,
        "hard_reasons": hard, "promoted": bool(ok),
    }


def _v44_apply_opportunity_policy(item: dict[str, Any]) -> dict[str, Any]:
    """Adaptive final policy: preserve V42 safety, recover only quality WAITs."""
    x = dict(item or {})
    before = str(x.get("decision_tag") or x.get("decision") or "WAIT").upper()
    if before != "WAIT":
        x["v44_opportunity"] = {"version": V44_VERSION, "promoted": False, "reason": "already_directional"}
        return x
    ok, audit = _v44_should_promote(x)
    if not ok:
        x["v44_opportunity"] = {"version": V44_VERSION, **audit}
        return x

    candidate = audit["candidate"]
    # Re-run the integrity contract on the candidate before publishing it.
    trial = dict(x)
    trial["decision"] = candidate
    trial["decision_tag"] = candidate
    trial["bias"] = "صعودی" if candidate == "LONG" else "نزولی"
    trial["entry_mode"] = "EARLY"
    trial["signal_tag"] = f"ADAPTIVE-CENTRAL — {candidate}"
    trial["decision_state"] = f"ADAPTIVE_CENTRAL_{candidate}"
    trial = _v42_integrity_seal(trial)
    if str(trial.get("decision_tag") or "WAIT") != candidate:
        audit["promoted"] = False
        audit["reason"] = "integrity_recheck_failed"
        audit["integrity"] = trial.get("v42_integrity") or {}
        x["v44_opportunity"] = audit
        return x

    x.update({
        "decision": candidate, "decision_tag": candidate,
        "bias": "صعودی" if candidate == "LONG" else "نزولی",
        "entry_mode": "EARLY",
        "signal_tag": f"ADAPTIVE-CENTRAL — {candidate}",
        "decision_state": f"ADAPTIVE_CENTRAL_{candidate}",
        "decision_confidence": round(clamp(safe_float((x.get("unified_central") or {}).get("confidence"), 0.0), V44_MIN_CONFIDENCE, V44_MAX_CONFIDENCE), 2),
        "v44_opportunity": {"version": V44_VERSION, **audit},
    })
    arch = dict(x.get("decision_architecture") or {})
    arch.update({"adaptive_opportunity_policy": V44_VERSION, "final_decision": candidate,
                 "soft_wait_recovered": True, "hard_safety_overridable": False})
    x["decision_architecture"] = arch
    x["authority"] = V44_VERSION
    return x


def _v44_learn_realized_outcomes() -> int:
    """Create explicit error/lesson records and persistent policy state."""
    done = 0
    try:
        with DB_LOCK, db_conn() as con:
            rows = con.execute(
                """SELECT p.id,p.created_at,p.symbol,p.decision,p.outcome,p.return_pct,p.confidence,p.margin,p.reasons_json,
                          m.regime
                   FROM central_predictions p LEFT JOIN central_trade_metrics m ON m.prediction_id=p.id
                   WHERE p.outcome IN ('WIN','LOSS','TIME_EXIT','AMBIGUOUS')
                     AND NOT EXISTS (SELECT 1 FROM central_learning_events e WHERE e.prediction_id=p.id)
                   ORDER BY p.evaluated_at LIMIT 250"""
            ).fetchall()
        for row in rows:
            rid, created, symbol, direction, outcome, ret, conf, margin, reasons_json, regime = row
            try:
                reasons = json.loads(reasons_json or "[]")
            except Exception:
                reasons = []
            if outcome == "WIN":
                error_class = "NONE"
                lesson = "تصمیم تحقق‌یافته موفق بود؛ وزن شواهد هم‌جهت حفظ و فقط در صورت تکرار تقویت شود."
            elif outcome == "LOSS":
                error_class = "FALSE_DIRECTION"
                lesson = "تصمیم اشتباه بود؛ عوامل هم‌جهت با تصمیم باید در نمونه‌های بعدی وزن کمتری بگیرند و شرایط شکست بررسی شود."
            elif outcome == "TIME_EXIT":
                error_class = "NO_RESOLUTION"
                lesson = "حرکت کافی برای تحقق هدف/حدضرر رخ نداد؛ این نمونه برای کالیبراسیون باینری ضعیف است و نباید برد محسوب شود."
            else:
                error_class = "AMBIGUOUS_PATH"
                lesson = "ترتیب لمس سطوح نامشخص بود؛ نمونه از یادگیری برد/باخت حذف می‌شود."
            with DB_LOCK, db_conn() as con:
                con.execute(
                    """INSERT OR IGNORE INTO central_learning_events(
                       prediction_id,created_at,symbol,direction,outcome,return_pct,error_class,lesson,regime,confidence,edge,margin,policy_edge,policy_margin,policy_trust,learned_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (rid,created, symbol,direction,outcome,safe_float(ret,0),error_class,lesson,regime,
                     safe_float(conf,0),0.0,safe_float(margin,0),V44_BASE_EDGE,V44_BASE_MARGIN,V44_BASE_TRUST,time.time())
                )
                con.commit()
            done += 1
        # Persist current bounded policy for global/LONG/SHORT and symbols with data.
        scopes = [("GLOBAL", ""), ("LONG", "LONG"), ("SHORT", "SHORT")]
        try:
            with DB_LOCK, db_conn() as con:
                syms = [r[0] for r in con.execute("SELECT DISTINCT symbol FROM central_predictions WHERE symbol IS NOT NULL LIMIT 200").fetchall()]
        except Exception:
            syms = []
        for scope, direction in scopes + [(f"SYMBOL:{s}", "") for s in syms]:
            sym = scope.split(":",1)[1] if scope.startswith("SYMBOL:") else ""
            st = _v44_policy_stats(sym, direction)
            th = st.get("thresholds") or {}
            with DB_LOCK, db_conn() as con:
                con.execute(
                    """INSERT INTO central_policy_state(scope,samples,wins,losses,time_exits,avg_return,win_rate,edge_threshold,margin_threshold,trust_threshold,last_update,lesson)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(scope) DO UPDATE SET samples=excluded.samples,wins=excluded.wins,losses=excluded.losses,time_exits=excluded.time_exits,
                       avg_return=excluded.avg_return,win_rate=excluded.win_rate,edge_threshold=excluded.edge_threshold,margin_threshold=excluded.margin_threshold,
                       trust_threshold=excluded.trust_threshold,last_update=excluded.last_update,lesson=excluded.lesson""",
                    (scope,st.get("samples",0),st.get("wins",0),st.get("losses",0),st.get("time_exits",0),st.get("avg_return",0),st.get("win_rate",50),
                     safe_float(th.get("edge"),V44_BASE_EDGE),safe_float(th.get("margin"),V44_BASE_MARGIN),safe_float(th.get("trust"),V44_BASE_TRUST),time.time(),
                     "bounded adaptive policy from realized outcomes"),
                )
                con.commit()
        return done
    except Exception as exc:
        LOGGER.debug("V44 learner: %s", exc)
        return done


# Wrap the existing evaluator so realized outcomes automatically feed the
# adaptive policy without changing its careful chronological first-touch logic.
_V44_PREV_EVALUATE_PENDING = _central_evaluate_pending

def _central_evaluate_pending() -> dict[str, Any]:
    result = _V44_PREV_EVALUATE_PENDING()
    try:
        learned = _v44_learn_realized_outcomes()
        if isinstance(result, dict):
            result = dict(result)
            result["v44_learning_events"] = learned
    except Exception:
        pass
    return result


# Final public gateway: V43 remains the one-brain evidence arbiter; V44 only
# recovers high-quality soft WAITs and can never bypass V42 hard integrity.
_V44_PREV_ANALYZE = analyze_asset

def analyze_asset(symbol: str, btc_trend: str) -> Optional[dict[str, Any]]:
    x = _V44_PREV_ANALYZE(symbol, btc_trend)
    if not x:
        return x
    out = _v44_apply_opportunity_policy(x)
    try:
        _central_record_prediction(out)
    except Exception:
        pass
    return out


@app.get("/api/adaptive-learning")
def api_adaptive_learning():
    try:
        global_stats = _v44_policy_stats()
        long_stats = _v44_policy_stats(direction="LONG")
        short_stats = _v44_policy_stats(direction="SHORT")
        with DB_LOCK, db_conn() as con:
            lessons = con.execute(
                "SELECT symbol,direction,outcome,error_class,lesson,confidence,created_at,learned_at FROM central_learning_events ORDER BY learned_at DESC LIMIT 100"
            ).fetchall()
        return jsonify({
            "ok": True, "version": V44_VERSION,
            "global": global_stats, "long": long_stats, "short": short_stats,
            "lessons": [dict(symbol=r[0],direction=r[1],outcome=r[2],error_class=r[3],lesson=r[4],confidence=r[5],created_at=r[6],learned_at=r[7]) for r in lessons],
            "policy": {"soft_wait_recovery": True, "hard_safety_override": False,
                       "bounded_adaptation": True, "zero_error_claim": False},
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)[:240]}), 500


# ============================================================
# TITAN V45 — COHERENT VALIDATED DECISIONS · HONEST BACKTEST · SHADOW LEARNING
# ------------------------------------------------------------
# Root causes fixed here (found by auditing V44 against the live WAL log):
#  1. WAIT candidates were judged with NEUTRAL symmetric SL/TP (RR≈1.0, and
#     inverted levels for SHORT), so `weak_rr` / `invalid_levels` fired on every
#     candidate and V44 promotion could never succeed.  V45 rebuilds levels
#     for the candidate side before judging it.
#  2. Learning deadlock: WAIT never produced samples, so policy stayed at
#     0 samples / default 50 %.  V45 records every directional candidate as a
#     SHADOW sample (no capital), evaluates it with chronological first-touch,
#     and feeds the result back into the gate.
#  3. Backtest held 1 bar with no SL/TP and ignored that costs (0.16 %) eat
#     more than half of a 1h move.  V45 simulates the SAME ATR levels the live
#     system publishes, reports gross vs net, one-trade-at-a-time, a random-entry
#     baseline and train-only walk-forward with abstention.
#  4. Duplicate arbiter/overlap log rows (same symbol, same second).
# Nothing here can guarantee profit.  V45 only publishes a directional signal
# when evidence, costs, levels and learned outcomes are mutually consistent.
# ============================================================
V45_VERSION = "TITAN-V45-COHERENT-VALIDATED-LEARNING"
V45_FRICTION_PCT = TOTAL_ENTRY_BUFFER * 2.0 * 100.0     # round-trip fee+spread+slippage, in %
V45_SL_ATR = 1.5
V45_RR1 = 1.6
V45_RR2 = 2.8
V45_MIN_RISK_ATR = 1.0
V45_MAX_RISK_ATR = 2.4
V45_MAX_COST_R = 0.35            # cost must stay below 0.35R, otherwise the trade is not worth its friction
V45_TF_MAX_HOLD = {"1m": 60, "5m": 48, "15m": 32, "30m": 24, "1h": 16, "4h": 10, "1d": 7}
V45_SHADOW_HORIZON_MIN = 240
V45_SHADOW_COOLDOWN = 2700
V45_MIN_VALIDATED_N = 20
V45_PRIOR_P = 0.45               # deliberately below a coin flip: no edge is assumed
V45_PRIOR_STRENGTH = 12.0
V45_TIER_A_MAX_SOFT = 0.5
V45_TIER_B_MAX_SOFT = 1.5
V45_EXPLORE_MAX_SOFT = 1.0
V45_EXPLORE_MAX_PER_HOUR = 6
V45_SIDE_SHARE_MAX = 0.70
V45_SOFT_WEIGHTS = {
    "regime_conflict": 1.0, "structure_not_confirmed": 1.0, "structure_confidence_low": 0.5,
    "regime_confidence_low": 0.5, "mtf_alignment_low": 0.75, "liquidity_flow_conflict": 1.0,
    "entry_quality_low": 0.75,
}
V45_LEVEL_REASONS = {"weak_rr", "invalid_levels", "rr1_below_floor", "rr2_below_floor",
                     "invalid_directional_levels", "stop_distance_extreme"}
V45_META_REASONS = {"REAL_EDGE_FINAL_GATE"}

_V45_EXPLORE_LOCK = threading.Lock()
_V45_EXPLORE_LOG: list[tuple[float, str]] = []
_V45_PUBLISHED: dict[tuple[str, str], float] = {}
_V45_EVAL_STATE = {"last": 0.0}


# ---------------------------------------------------------------- levels / simulation
def _v45_rr_levels(price: float, atr: float, side: str, anchor: Optional[float] = None,
                   rr1: float = V45_RR1, rr2: float = V45_RR2) -> Optional[dict[str, float]]:
    """Oriented ATR levels for the candidate side (pure price levels; costs are charged separately)."""
    try:
        price = float(price); atr = float(atr)
    except (TypeError, ValueError):
        return None
    if side not in {"LONG", "SHORT"} or not (price > 0 and atr > 0 and math.isfinite(price) and math.isfinite(atr)):
        return None
    risk = V45_SL_ATR * atr
    if anchor and anchor > 0:
        dist = (price - anchor) if side == "LONG" else (anchor - price)
        if dist > 0:
            risk = clamp(dist + 0.25 * atr, V45_MIN_RISK_ATR * atr, V45_MAX_RISK_ATR * atr)
    sgn = 1.0 if side == "LONG" else -1.0
    sl = price - sgn * risk
    tp1 = price + sgn * rr1 * risk
    tp2 = price + sgn * rr2 * risk
    if sl <= 0:
        return None
    risk_pct = risk / price * 100.0
    return {"sl": sl, "tp1": tp1, "tp2": tp2, "risk": risk, "risk_pct": risk_pct,
            "rr1": rr1, "rr2": rr2, "cost_r": V45_FRICTION_PCT / max(risk_pct, 1e-9)}


def _v45_sim_trade(arr: dict[str, Any], i: int, side: str, max_hold: int,
                   anchor: Optional[float] = None) -> Optional[dict[str, Any]]:
    """Signal at close of bar i -> enter at OPEN of bar i+1; SL/TP1 on high/low; same-bar tie = SL (conservative)."""
    o, h, l, c, atr = arr["o"], arr["h"], arr["l"], arr["c"], arr["atr"]
    n = len(c)
    if i + 1 >= n:
        return None
    entry = float(o[i + 1])
    lv = _v45_rr_levels(entry, float(atr[i]), side, anchor)
    if not lv:
        return None
    sl, tp1 = lv["sl"], lv["tp1"]
    last = min(n - 1, i + max_hold)
    exit_px, outcome, exit_idx = float(c[last]), "TIME", last
    for j in range(i + 1, last + 1):
        hi, lo, op = float(h[j]), float(l[j]), float(o[j])
        if side == "LONG":
            if op <= sl:
                exit_px, outcome, exit_idx = op, "SL", j; break
            sl_hit, tp_hit = lo <= sl, hi >= tp1
        else:
            if op >= sl:
                exit_px, outcome, exit_idx = op, "SL", j; break
            sl_hit, tp_hit = hi >= sl, lo <= tp1
        if sl_hit:
            exit_px, outcome, exit_idx = sl, "SL", j; break
        if tp_hit:
            exit_px, outcome, exit_idx = tp1, "TP1", j; break
    gross = ((exit_px - entry) / entry * 100.0) if side == "LONG" else ((entry - exit_px) / entry * 100.0)
    net = gross - V45_FRICTION_PCT
    return {"i": int(i), "side": side, "entry": entry, "exit": exit_px, "outcome": outcome,
            "gross_pct": gross, "net_pct": net, "r_net": net / max(lv["risk_pct"], 1e-9),
            "risk_pct": lv["risk_pct"], "cost_r": lv["cost_r"], "exit_idx": int(exit_idx),
            "bars": int(exit_idx - i)}


def _v45_arrays(df: "pd.DataFrame") -> dict[str, Any]:
    return {"o": df["open"].astype(float).to_numpy(), "h": df["high"].astype(float).to_numpy(),
            "l": df["low"].astype(float).to_numpy(), "c": df["close"].astype(float).to_numpy(),
            "atr": calc_atr(df).astype(float).to_numpy()}


def _v45_signal_table(df: "pd.DataFrame", warmup: int = 60, window: int = 200) -> list[tuple]:
    """Causal per-bar forecast table computed once and reused across the whole parameter grid."""
    rows: list[tuple] = []
    for i in range(warmup, len(df) - 2):
        sample = df.iloc[max(0, i + 1 - window): i + 1]
        direction, score, meta = _tf_forecast(sample)
        m = meta or {}
        rows.append((i, direction, float(score), safe_float(m.get("rsi"), 50.0), safe_float(m.get("ema_gap"), 0.0),
                     safe_float(m.get("momentum"), 0.0), safe_float(m.get("adx"), 20.0)))
    return rows


def _v45_pick_side(row: tuple, p: dict[str, float]) -> Optional[str]:
    _, direction, score, rsi_v, gap, mom, adx = row
    if adx < p.get("adx_min", 0):
        return None
    if direction == "صعودی" and score >= p["long_thr"] and gap >= -0.15:
        return "LONG"
    if (direction == "نزولی" and score <= p["short_thr"] and gap <= 0.10 and mom <= 0.15
            and not (rsi_v < 22 and mom > -0.5)):
        return "SHORT"
    return None


def _v45_run_sim(arr: dict[str, Any], table: list[tuple], p: dict[str, float], start: int, end: int,
                 max_hold: int) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    busy = -1
    for row in table:
        i = row[0]
        if i < start or i >= end or i <= busy:
            continue
        side = _v45_pick_side(row, p)
        if not side:
            continue
        t = _v45_sim_trade(arr, i, side, max_hold)
        if t:
            trades.append(t); busy = t["exit_idx"]
    return trades


def _v45_random_baseline(arr: dict[str, Any], n_trades: int, long_frac: float, max_hold: int,
                         start: int, end: int, iters: int = 300, seed: int = 11) -> list[float]:
    rng = np.random.default_rng(seed)
    means: list[float] = []
    if n_trades < 5 or end - start < 20:
        return means
    for _ in range(iters):
        idx = np.sort(rng.integers(start, end, size=n_trades * 3))
        busy = -1; rs: list[float] = []
        for i in idx:
            if i <= busy:
                continue
            t = _v45_sim_trade(arr, int(i), "LONG" if rng.random() < long_frac else "SHORT", max_hold)
            if t:
                rs.append(t["r_net"]); busy = t["exit_idx"]
            if len(rs) >= n_trades:
                break
        if rs:
            means.append(float(np.mean(rs)))
    return means


def _v45_trade_metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    net = [t["net_pct"] for t in trades]
    m = _safe_return_series(net, return_unit="pct")
    rs = np.asarray([t["r_net"] for t in trades], dtype=float) if trades else np.asarray([], dtype=float)
    gw = sum(1 for t in trades if t["gross_pct"] > 0)
    m["gross_win_rate"] = round(gw / len(trades) * 100, 2) if trades else 0.0
    m["expectancy_r"] = round(float(rs.mean()), 4) if rs.size else 0.0
    m["expectancy_r_se"] = round(float(rs.std(ddof=1) / math.sqrt(rs.size)), 4) if rs.size > 1 else None
    m["avg_cost_r"] = round(float(np.mean([t["cost_r"] for t in trades])), 3) if trades else 0.0
    m["avg_bars_held"] = round(float(np.mean([t["bars"] for t in trades])), 2) if trades else 0.0
    m["tp1_hits"] = sum(1 for t in trades if t["outcome"] == "TP1")
    m["sl_hits"] = sum(1 for t in trades if t["outcome"] == "SL")
    m["time_exits"] = sum(1 for t in trades if t["outcome"] == "TIME")
    return m


def _v45_verdict(metrics: dict[str, Any], rnd_pct: Optional[float], oos: dict[str, Any]) -> str:
    """EDGE_SUPPORTED needs: >=30 trades, PF>=1.1, positive OOS expectancy, expectancy lower bound (1.64 SE) > 0
    and, when a random-entry baseline exists, >=90th percentile of it. Anything weaker is never called an edge."""
    n = int(metrics.get("trades") or 0)
    if n < 30:
        return "INSUFFICIENT_SAMPLE"
    exp_r = safe_float(metrics.get("expectancy_r"), 0.0)
    se = metrics.get("expectancy_r_se")
    lcb = exp_r - 1.64 * safe_float(se, 9.0)
    pf = safe_float(metrics.get("profit_factor"), 0.0)
    oos_e = safe_float((oos or {}).get("oos_expectancy"), 0.0)
    rnd_ok = True if rnd_pct is None else rnd_pct >= 90
    if exp_r > 0 and lcb > 0 and pf >= 1.1 and oos_e > 0 and rnd_ok:
        return "EDGE_SUPPORTED"
    if exp_r > 0 and (rnd_pct is None or rnd_pct >= 75):
        return "WEAK_POSITIVE_UNPROVEN"
    return "NO_EDGE_PROVEN"


def backtest_signal_logic(symbol: str, tf: str = "1h", limit: int = 1000) -> dict[str, Any]:  # noqa: F811 (V45 override)
    """Honest proxy backtest: the SAME ATR SL/TP1 levels V45 publishes, first-touch on OHLC, entry at next open,
    one trade at a time, costs charged once, gross vs net, random-entry baseline. Still technical-only
    (no historical AI/derivatives) — that limitation is stated in the output."""
    limit = min(max(int(limit), 100), MAX_BACKTEST_CANDLES)
    try:
        df = fetch_klines(symbol, tf, limit)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "symbol": symbol, "timeframe": tf}
    if df is None or len(df) < 120:
        return {"ok": False, "error": "داده تاریخی کافی نیست", "symbol": symbol, "timeframe": tf}
    df = df.reset_index(drop=True)
    max_hold = V45_TF_MAX_HOLD.get(str(tf), 12)
    arr = _v45_arrays(df)
    table = _v45_signal_table(df)
    params = {"long_thr": 58.0, "short_thr": 40.0, "adx_min": 0.0}
    trades = _v45_run_sim(arr, table, params, 60, len(df) - 2, max_hold)
    longs = [t for t in trades if t["side"] == "LONG"]
    shorts = [t for t in trades if t["side"] == "SHORT"]
    m = _v45_trade_metrics(trades)
    long_m, short_m = _v45_trade_metrics(longs), _v45_trade_metrics(shorts)
    returns = [t["net_pct"] for t in trades]
    oos = TITAN_EDGE_SUITE.out_of_sample_check(returns, return_unit="pct")
    governor = TITAN_EDGE_SUITE.drawdown_governor(returns, unit="pct")
    strategies = TITAN_EDGE_SUITE.strategy_lab(df)
    rnd = _v45_random_baseline(arr, len(trades), (len(longs) / len(trades)) if trades else 0.5, max_hold, 60, len(df) - 2)
    actual_r = m["expectancy_r"]
    rnd_pct = round(100.0 * sum(1 for x in rnd if x < actual_r) / len(rnd), 1) if rnd else None
    verdict = _v45_verdict(m, rnd_pct, oos)
    paths = {"TP1": m["tp1_hits"], "TP2": 0, "SL": m["sl_hits"], "NONE": m["time_exits"]}
    bh = round((float(arr["c"][-1]) / float(arr["c"][0]) - 1.0) * 100.0, 2)
    return {
        "ok": True, "symbol": symbol, "timeframe": tf, "candles": len(df), "metrics": m,
        "validation_scope": "technical_proxy_only_no_historical_ai_or_derivatives",
        "long_metrics": long_m, "short_metrics": short_m,
        "long_signals": len(longs), "short_signals": len(shorts), "directional_signals": len(trades),
        "from": float(df["t"].iloc[0]), "to": float(df["t"].iloc[-1]),
        "return_series_pct": [round(float(x), 6) for x in returns[-1500:]],
        "filters": {"long": "score>=58 + ema_gap>=-0.15", "short": "score<=40 + ema_gap<=0.10 + momentum<=0.15 + not panic-oversold trap",
                    "note": "SL/TP1 = ATR levels identical to live V45; one trade at a time; entry at next open"},
        "v45": {
            "version": V45_VERSION, "verdict": verdict, "max_hold_bars": max_hold,
            "entry_model": "next_bar_open", "same_bar_sl_tp_rule": "SL_FIRST_CONSERVATIVE",
            "round_trip_cost_pct": round(V45_FRICTION_PCT, 4),
            "gross_win_rate": m["gross_win_rate"], "net_win_rate": m["win_rate"],
            "expectancy_r_net": m["expectancy_r"], "avg_cost_r": m["avg_cost_r"],
            "random_entry_percentile": rnd_pct, "random_entry_mean_r": round(float(np.mean(rnd)), 4) if rnd else None,
            "buy_and_hold_pct": bh,
            "reading": ("تا وقتی verdict برابر EDGE_SUPPORTED نشده، این منطق لبه‌ی اثبات‌شده ندارد؛ "
                        "win rate بدون در نظر گرفتن R و هزینه معنا ندارد."),
        },
        "professional": {
            "oos": oos, "drawdown_governor": governor,
            "counterfactual": {"paths": paths, "sample": len(trades)},
            "strategy_lab": strategies,
            "meta_labeling_reference": "V45 shadow outcomes + OOS + side-split",
        },
    }
