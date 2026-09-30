
    x["success_probability_is_calibrated"] = is_cal
    if not is_cal:
        # Keep the raw confidence for backward compatibility but prevent the
        # dashboard/API from implying that it is a measured win probability.
        x["calibrated_probability"] = None
        x["probability_semantics"] = "model_confidence_not_win_probability"
    else:
        x["probability_semantics"] = "realized_calibrated_probability"

    x["v42_integrity"] = {
        "version": V42_VERSION,
        "passed": not bool(reasons),
        "final_decision": side,
        "candidate_before_seal": x.get("v42_blocked_candidate") or side,
        "reasons": reasons,
        "live_age_sec": round(live_age, 3) if live_age < 1e8 else None,
        "data_quality": round(data_score, 2),
        "rr1": round(rr1, 3),
        "rr2": round(rr2, 3),
        "calibration_samples": cal_n,
        "calibrated": is_cal,
        "timestamp": time.time(),
    }
    arch = dict(x.get("decision_architecture") or {}) if isinstance(x.get("decision_architecture"), dict) else {}
    arch.update({
        "integrity_seal": V42_VERSION,
        "final_decision": side,
        "fail_closed": True,
        "probability_is_calibrated": is_cal,
    })
    x["decision_architecture"] = arch
    x["authority"] = f"{x.get('authority') or TITAN_CENTRAL_VERSION}+{V42_VERSION}"
    return x


def titan_system_audit() -> dict[str, Any]:
    """Offline/runtime audit of the major subsystems and persistence contract."""
    checks: dict[str, Any] = {}
    checks["python_imports"] = True
    checks["central_governor"] = callable(globals().get("_central_decide"))
    checks["real_edge"] = callable(globals().get("_real_edge_engine"))
    checks["v40_precision"] = callable(globals().get("_v40_precision_gate"))
    checks["v42_integrity"] = callable(globals().get("_v42_integrity_seal"))
    checks["v43_unified_governor"] = callable(globals().get("_v43_unified_decide"))
    checks["forecast_evaluator"] = callable(globals().get("_central_evaluate_pending"))
    checks["paper_evaluator"] = callable(globals().get("evaluate_paper_trades"))
    checks["walk_forward"] = callable(globals().get("walk_forward_backtest"))
    checks["neural_engine"] = "TitanNeuralSynapseV9" in globals()
    checks["ai_ensemble"] = callable(globals().get("generate_ai_opinions"))
    checks["live_engine"] = callable(globals().get("start_live_engine"))
    checks["db_path_locked"] = str(DB_PATH).startswith(str(APP_HOME))
    try:
        with DB_LOCK, db_conn() as con:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        required = {"central_predictions", "central_component_stats", "central_arbiter_log"}
        checks["required_tables"] = required.issubset(tables)
        checks["table_count"] = len(tables)
    except Exception as exc:
        checks["required_tables"] = False
        checks["db_error"] = str(exc)[:180]
    checks["passed"] = all(v is True for k, v in checks.items() if k not in {"table_count", "db_error"})
    checks["version"] = V42_VERSION
    checks["timestamp"] = _now_iso()
    return checks


# ============================================================
# TITAN V43 — UNIFIED EVIDENCE COORDINATOR / ONE-BRAIN DECISION
# ============================================================
# This layer is the final decision coordinator.  It runs AFTER the evidence
# enrichment layers (V31/V34/V35/V36/V40), so those modules are not merely
# post-decision safety filters: their outputs become evidence for the same
# central arbiter.  No legacy/candidate decision is treated as a vote.
V43_VERSION = "TITAN-V43-UNIFIED-EVIDENCE-COORDINATOR"
V43_MIN_COMPONENTS = 8
V43_MIN_ACTIVE_GROUPS = 4


def _v43_side_from_score(score: float, deadband: float = 0.08) -> tuple[float, float, str]:
    lean = clamp((safe_float(score, 50.0) - 50.0) / 50.0, -1.0, 1.0)
    conf = clamp(abs(lean), 0.0, 1.0)
    side = "LONG" if lean > deadband else "SHORT" if lean < -deadband else "WAIT"
    return lean, conf, side


def _v43_add_vote(votes: dict, name: str, score: float, label: str, group: str,
                  available: bool = True, confidence: float | None = None) -> None:
    if not available:
        return
    lean, conf, side = _v43_side_from_score(score)
    if confidence is not None:
        conf = clamp(safe_float(confidence, conf), 0.0, 1.0)
    votes[name] = {
        "lean": lean, "confidence": conf, "side": side,
        "raw": round(safe_float(score, 50.0), 4), "label": label,
        "group": group, "v43": True,
    }


def _v43_unified_evidence(item: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Build one auditable evidence map from all available downstream modules.

    The function intentionally converts *module outputs* into evidence rather
    than copying their prior decisions.  This prevents circular reinforcement
    while still making the complete analytical stack visible to the governor.
    """
    votes = _central_votes(item)
    registry: list[dict[str, Any]] = []

    def reg(name: str, group: str, used: bool, note: str = ""):
        registry.append({"module": name, "group": group, "used": bool(used), "note": note})

    # Neural intelligence -------------------------------------------------
    neural = item.get("neural_v9") or (item.get("fusion") or {}).get("neural_v9") or {}
    if isinstance(neural, dict) and neural:
        nscore = safe_float(neural.get("neural_score"), 50.0)
        nconf = clamp(safe_float(neural.get("confidence"), 0.0) / 100.0, 0.0, 1.0)
        _v43_add_vote(votes, "neural_v9", nscore, "سیناپس عصبی V9", "AI_NEURAL", True, max(nconf, 0.05))
        reg("TitanNeuralSynapseV9", "AI_NEURAL", True)
    else:
        reg("TitanNeuralSynapseV9", "AI_NEURAL", False, "no runtime output")

    # Market regime / structure / liquidity / precision ------------------
    regime = item.get("regime") if isinstance(item.get("regime"), dict) else {}
    rname = str(regime.get("regime") or item.get("market_regime") or "").lower()
    rconf = clamp(safe_float(regime.get("confidence"), 0.0) / 100.0, 0.0, 1.0)
    if rname:
        rscore = 65.0 if "up" in rname or rname == "breakout_watch" else 35.0 if "down" in rname else 50.0
        _v43_add_vote(votes, "regime_engine", rscore, "رژیم بازار", "MARKET_CONTEXT", True, max(rconf, 0.20))
        reg("regime", "MARKET_CONTEXT", True, rname)
    else:
        reg("regime", "MARKET_CONTEXT", False)

    structure = item.get("structure") if isinstance(item.get("structure"), dict) else {}
    se = str(structure.get("event") or "").upper()
    sb = str(structure.get("bias") or "").upper()
    if se or sb:
        if se in {"BOS_UP", "BULL_STRUCTURE"} or sb in {"LONG", "صعودی"}: sscore = 68.0
        elif se in {"BOS_DOWN", "BEAR_STRUCTURE"} or sb in {"SHORT", "نزولی"}: sscore = 32.0
        else: sscore = 50.0
        sc = clamp(safe_float(structure.get("confirmation_score"), 50.0) / 100.0, 0.0, 1.0)
        _v43_add_vote(votes, "structure_engine", sscore, "موتور ساختار", "MARKET_CONTEXT", True, max(sc, 0.15))
        reg("structure", "MARKET_CONTEXT", True, se or sb)
    else:
        reg("structure", "MARKET_CONTEXT", False)

    liquidity = item.get("liquidity") if isinstance(item.get("liquidity"), dict) else {}
    if liquidity:
        pressure = clamp(safe_float(liquidity.get("pressure"), 0.0), -1.0, 1.0)
        _v43_add_vote(votes, "liquidity_engine", 50.0 + pressure * 35.0, "نقدشوندگی/فشار", "FLOW", True, clamp(abs(pressure) + 0.15, 0, 1))
        reg("liquidity", "FLOW", True)
    else:
        reg("liquidity", "FLOW", False)

    precision = item.get("precision") if isinstance(item.get("precision"), dict) else {}
    if precision:
        ps = safe_float(precision.get("score"), 50.0)
        _v43_add_vote(votes, "precision_engine", ps, "دقت ورود", "ENTRY_RISK", True, 0.75)
        reg("precision", "ENTRY_RISK", True)
    else:
        reg("precision", "ENTRY_RISK", False)

    # V31 complete suite: use the suite-level independent evidence score and
    # explicitly expose all its internal modules as participating metadata.
    v31 = item.get("v31_edge_suite") if isinstance(item.get("v31_edge_suite"), dict) else {}
    if v31:
        ev = v31.get("evidence_fusion") or {}
        adv = v31.get("adversarial") or {}
        ent = v31.get("entry_stability") or {}
        unc = v31.get("uncertainty") or {}
        robust = safe_float(adv.get("robustness"), 50.0)
        entry = safe_float(ent.get("score"), 50.0)
        indep = clamp(safe_float(ev.get("independence_score"), 0.5), 0.0, 1.0)
        uncertainty = clamp(safe_float(unc.get("uncertainty"), 50.0), 0.0, 100.0)
        v31_score = clamp(0.40 * robust + 0.35 * entry + 25.0 * indep + 0.15 * (100.0 - uncertainty), 0, 100)
        _v43_add_vote(votes, "v31_edge_suite", v31_score, "مجموعه 21 ماژول V31", "ROBUSTNESS_LEARNING", True, 0.75)
        for k, val in v31.items():
            reg("V31." + k, "ROBUSTNESS_LEARNING", isinstance(val, dict) or isinstance(val, (bool, int, float)))
    else:
        reg("V31.edge_suite", "ROBUSTNESS_LEARNING", False)

    # V34 adaptive trust / opportunity -----------------------------------
    v34 = item.get("v34_opportunity") if isinstance(item.get("v34_opportunity"), dict) else {}
    if v34:
        opp = safe_float(v34.get("score"), safe_float(v34.get("opportunity_score"), 50.0))
        _v43_add_vote(votes, "v34_opportunity", opp, "اعتماد تطبیقی/فرصت", "ROBUSTNESS_LEARNING", True, 0.70)
        reg("V34.adaptive_trust", "ROBUSTNESS_LEARNING", True)
    else:
        reg("V34.adaptive_trust", "ROBUSTNESS_LEARNING", False)

    # V36 horizon agreement + cross-asset resonance ---------------------
    v36 = item.get("v36_resonance") if isinstance(item.get("v36_resonance"), dict) else {}
    fusion = item.get("fusion") if isinstance(item.get("fusion"), dict) else {}
    horizon = v36.get("horizon_agreement") if isinstance(v36.get("horizon_agreement"), dict) else {}
    if not horizon:
        horizon = item.get("horizon_agreement") if isinstance(item.get("horizon_agreement"), dict) else {}
    if horizon:
        ag = clamp(safe_float(horizon.get("agreement"), 0.5), 0.0, 1.0)
        direction = str(horizon.get("direction") or "WAIT").upper()
        hscore = 50.0 + (ag * 40.0 if direction == "LONG" else -ag * 40.0 if direction == "SHORT" else 0.0)
        _v43_add_vote(votes, "v36_horizon", hscore, "توافق افق‌های زمانی V36", "MTF_CROSS_ASSET", True, max(ag, 0.15))
        reg("V36.horizon_agreement", "MTF_CROSS_ASSET", True)
    else:
        reg("V36.horizon_agreement", "MTF_CROSS_ASSET", False)
    if v36:
        penalty = safe_float(v36.get("penalty"), 0.0)
        resonance = clamp(50.0 - penalty * 2.0, 0.0, 100.0)
        _v43_add_vote(votes, "v36_resonance", resonance, "رزونانس بین‌دارایی V36", "MTF_CROSS_ASSET", True, 0.65)
        reg("V36.cross_asset_resonance", "MTF_CROSS_ASSET", True)
    else:
        reg("V36.cross_asset_resonance", "MTF_CROSS_ASSET", False)

    # V40 precision is a gate AND an evidence source.  Hard blocks remain
    # authoritative vetoes below, while its score participates in consensus.
    v40 = item.get("v40_precision") if isinstance(item.get("v40_precision"), dict) else {}
    if v40:
        v40_score = safe_float(v40.get("score"), 50.0)
        _v43_add_vote(votes, "v40_precision", v40_score, "گیت دقت V40", "ENTRY_RISK", True, 0.80)
        reg("V40.precision_gate", "ENTRY_RISK", True)
    else:
        reg("V40.precision_gate", "ENTRY_RISK", False)

    # Macro / BTC context -------------------------------------------------
    btc = str(item.get("btc_trend") or "").strip()
    if btc:
        bscore = 65.0 if btc in {"صعودی", "LONG", "UP"} else 35.0 if btc in {"نزولی", "SHORT", "DOWN"} else 50.0
        _v43_add_vote(votes, "btc_macro_context", bscore, "رژیم BTC/ماکرو", "MARKET_CONTEXT", True, 0.55)
        reg("BTC/macro", "MARKET_CONTEXT", True, btc)
    else:
        reg("BTC/macro", "MARKET_CONTEXT", False)

    # Forecast, calibration, learning, research and performance ------------
    fc = item.get("candle_forecast") or item.get("forecast") or {}
    if isinstance(fc, dict) and fc:
        bias = str(fc.get("overall_bias") or "")
        move = safe_float(fc.get("expected_move_pct"), 0.0)
        fscore = 50.0 + clamp(move * 4.0, -20.0, 20.0)
        if bias == "صعودی": fscore = max(fscore, 53.0)
        elif bias == "نزولی": fscore = min(fscore, 47.0)
        _v43_add_vote(votes, "forecast_engine", fscore, "پیش‌بینی مسیر", "FORECAST", True, 0.60)
        reg("forecast", "FORECAST", True)
    else:
        reg("forecast", "FORECAST", False)

    cal = item.get("probability_calibration") if isinstance(item.get("probability_calibration"), dict) else {}
    if cal:
        cval = safe_float(cal.get("calibrated"), 50.0)
        cn = int(safe_float(cal.get("samples"), 0))
        cconf = clamp(cn / 100.0, 0.15, 1.0)
        _v43_add_vote(votes, "realized_calibration", cval, "کالیبراسیون realized", "ROBUSTNESS_LEARNING", True, cconf)
        reg("realized_calibration", "ROBUSTNESS_LEARNING", True, f"samples={cn}")
    else:
        reg("realized_calibration", "ROBUSTNESS_LEARNING", False)

    learning = item.get("v32_learning") or {}
    if isinstance(learning, dict) and learning:
        ladj = safe_float(learning.get("long_adjustment"), 0.0)
        sadj = safe_float(learning.get("short_adjustment"), 0.0)
        lscore = 50.0 + clamp((ladj - sadj) * 2.0, -20.0, 20.0)
        _v43_add_vote(votes, "learning_engine", lscore, "یادگیری تاریخی", "ROBUSTNESS_LEARNING", True, 0.55)
        reg("learning", "ROBUSTNESS_LEARNING", True)
    else:
        reg("learning", "ROBUSTNESS_LEARNING", False)

    # Hard veto aggregation from every downstream safety layer.
    vetoes: list[str] = []
    if v40:
        vetoes.extend([str(v) for v in (v40.get("hard_blocks") or []) if str(v)])
    if v31 and bool(v31.get("safety_wait")):
        vetoes.append("V31 safety_wait")
    if v36 and bool(v36.get("kill")):
        vetoes.append("V36 kill")
    if v36 and bool(v36.get("blocked")):
        vetoes.append("V36 blocked")

    active = [v for v in votes.values() if v.get("v43")]
    groups = {str(v.get("group")) for v in active if v.get("group")}
    participation = {
        "active_components": len(active),
        "active_groups": len(groups),
        "required_components": V43_MIN_COMPONENTS,
        "required_groups": V43_MIN_ACTIVE_GROUPS,
        "sufficient": len(active) >= V43_MIN_COMPONENTS and len(groups) >= V43_MIN_ACTIVE_GROUPS,
        "registry": registry,
        "hard_vetoes": vetoes,
    }
    return votes, participation


def _v43_unified_decide(item: dict[str, Any]) -> dict[str, Any]:
    """Re-arbitrate the fully enriched snapshot through one central brain."""
    x = dict(item or {})
    votes, participation = _v43_unified_evidence(x)
    with _CENTRAL_WEIGHT_LOCK:
        weights = dict(_CENTRAL_WEIGHTS)
    # New coordinator weights are intentionally bounded and lower than the
    # primary TF/structure spine to avoid double-counting correlated evidence.
    extra_defaults = {
        "neural_v9": 1.00, "regime_engine": 0.85, "structure_engine": 0.95,