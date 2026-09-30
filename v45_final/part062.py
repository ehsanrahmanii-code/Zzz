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