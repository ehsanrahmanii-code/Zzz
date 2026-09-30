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
        "liquidity_engine": 0.55, "precision_engine": 0.70, "v31_edge_suite": 0.80,
        "v34_opportunity": 0.70, "v36_horizon": 0.75, "v36_resonance": 0.55,
        "v40_precision": 0.80, "btc_macro_context": 0.55, "forecast_engine": 0.50,
        "realized_calibration": 0.60, "learning_engine": 0.55,
    }
    for k, v in extra_defaults.items():
        weights.setdefault(k, v)

    long_num = short_num = den = 0.0
    details = []
    for name, v in votes.items():
        if name == "data_trust":
            continue
        w = safe_float(weights.get(name), 1.0)
        eff = w * clamp(safe_float(v.get("confidence"), 0.0), 0.0, 1.0)
        lean = clamp(safe_float(v.get("lean"), 0.0), -1.0, 1.0)
        den += eff
        if lean > 0: long_num += eff * lean
        elif lean < 0: short_num += eff * abs(lean)
        details.append({"component": name, "group": v.get("group", "CORE"), "side": v.get("side"),
                        "lean": round(lean, 4), "confidence": round(safe_float(v.get("confidence"), 0), 4),
                        "weight": round(w, 4), "contribution": round(eff * lean, 4), "raw": v.get("raw")})
    long_score = long_num / max(den, 1e-9)
    short_score = short_num / max(den, 1e-9)
    edge = max(long_score, short_score)
    margin = abs(long_score - short_score)
    trust = safe_float((votes.get("data_trust") or {}).get("trust"), 70.0)
    candidate = "LONG" if long_score > short_score else "SHORT" if short_score > long_score else "WAIT"
    reasons = []
    if not participation["sufficient"]:
        reasons.append("اجماع ناکافی: مشارکت ماژول‌ها کم است")
    if trust < _CENTRAL_MIN_TRUST: reasons.append(f"اعتماد داده پایین ({trust:.0f})")
    if edge < _CENTRAL_MIN_EDGE: reasons.append(f"لبه تصمیم ناکافی ({edge:.3f})")
    if margin < _CENTRAL_MIN_MARGIN: reasons.append(f"حاشیه تصمیم کم ({margin:.3f})")
    reasons.extend(participation["hard_vetoes"])

    # Existing overlap gate remains a portfolio-level veto.
    overlap = _edge_overlap_gate(_normalize_symbol(x.get("symbol") or ""), candidate)
    if candidate in {"LONG", "SHORT"} and not overlap.get("ok", True):
        reasons.append(str(overlap.get("reason") or "overlap risk"))

    # Directional level contract is not allowed to be invented at this stage.
    price = _v42_price(x)
    sl = safe_float(x.get("stop_loss_raw"), safe_float(x.get("stop_loss"), 0.0))
    tp1 = safe_float(x.get("tp1_raw"), safe_float(x.get("tp1"), 0.0))
    tp2 = safe_float(x.get("tp2_raw"), safe_float(x.get("tp2"), 0.0))
    if candidate in {"LONG", "SHORT"} and not _v42_levels_ok(price, sl, tp1, tp2, candidate):
        reasons.append("سطوح نهایی با جهت اجماع منطبق نیست")

    decision = candidate if not reasons and candidate in {"LONG", "SHORT"} else "WAIT"
    conf = clamp(50.0 + edge * 38.0 + margin * 28.0 + (trust - 50.0) * 0.12, 5.0, 94.0)
    if decision == "WAIT": conf = min(conf, 55.0)
    scorecard = []
    for d in details:
        scorecard.append({**d, "aligned": decision in {"LONG", "SHORT"} and d["side"] == decision,
                          "opposed": decision in {"LONG", "SHORT"} and d["side"] in {"LONG", "SHORT"} and d["side"] != decision})

    x["decision"] = decision
    x["decision_tag"] = decision
    x["bias"] = "صعودی" if decision == "LONG" else "نزولی" if decision == "SHORT" else "خنثی"
    x["entry_mode"] = "EARLY" if decision in {"LONG", "SHORT"} else "WAIT"
    x["signal_tag"] = f"UNIFIED-CENTRAL — {decision}"
    x["decision_state"] = f"UNIFIED_CENTRAL_{decision}"
    x["decision_confidence"] = round(conf, 2)
    x["directional_bias"] = round((long_score - short_score) * 100.0, 2)
    x["unified_central"] = {
        "version": V43_VERSION, "decision": decision,
        "candidate": candidate, "long_score": round(long_score, 5), "short_score": round(short_score, 5),
        "edge": round(edge, 5), "margin": round(margin, 5), "confidence": round(conf, 2),
        "trust": round(trust, 2), "components": scorecard,
        "weights": {k: round(v, 4) for k, v in weights.items()},
        "participation": participation, "overlap": overlap,
        "reasons": reasons, "authoritative": True, "timestamp": time.time(),
    }
    x["decision_reasons"] = reasons
    x["central_reason_fa"] = " · ".join(reasons[:6]) if reasons else "اجماع کامل شواهد"
    x["decision_architecture"] = {
        **(dict(x.get("decision_architecture") or {}) if isinstance(x.get("decision_architecture"), dict) else {}),
        "type": "ONE_BRAIN_MANY_EVIDENCE_CHANNELS",
        "authoritative_source": V43_VERSION,
        "final_decision": decision,
        "all_available_modules_are_evidence": True,
        "circular_previous_decisions_excluded": True,
        "module_participation": participation,
    }
    x["authority"] = V43_VERSION
    return x

# ---- Public gateways ----
_CENTRAL_PREV_ANALYZE = analyze_asset
_CENTRAL_PREV_UPDATE = update_cache


def analyze_asset(symbol: str, btc_trend: str) -> Optional[dict[str, Any]]:
    """Sole public analyzer — evidence stack, then V40 precision seal."""
    try:
        base = _CENTRAL_PREV_ANALYZE(symbol, btc_trend)
        if not base:
            return None
        if btc_trend and not base.get("btc_trend"):
            base["btc_trend"] = btc_trend
        sealed = _central_seal(base)
        sealed = _v31_apply(sealed)
        sealed = _v34_apply(sealed)
        snapshot = _v35_get_live_snapshot(symbol)
        sealed = _v35_rebase_price_dependent_outputs(sealed, snapshot)
        try:
            with CACHE_LOCK:
                _rows = list(CACHE.get("data") or [])
        except Exception:
            _rows = []
        sealed = _v36_apply(sealed, _rows)
        sealed = _v40_precision_gate(sealed, _rows)
        # V43 is the actual final arbiter: every enriched module votes here.
        sealed = _v43_unified_decide(sealed)
        sealed = _v42_integrity_seal(sealed)
        try:
            _central_record_prediction(sealed)
        except Exception as rec_exc:
            LOGGER.debug("record after V40: %s", rec_exc)
        return sealed
    except Exception as exc:
        LOGGER.exception("Central analyze failed %s: %s", symbol, exc)
        try:
            if "base" in locals() and base:
                _fb = _v40_precision_gate(_central_seal(base), [])
                _fb = _v43_unified_decide(_fb)
                return _v42_integrity_seal(_fb)
        except Exception:
            pass
        return None


def update_cache(force: bool = False) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    """Central-owned scan with progress heartbeat + emergency fallback."""
    coins = list(USER_SETTINGS.get("active_coins") or DEFAULT_COINS)
    total = max(1, len(coins))
    scan_started = time.time()
    with CACHE_LOCK:
        cached_n = len(CACHE.get("data") or [])
        cache_age = time.time() - safe_float(CACHE.get("timestamp"), 0.0)
        cached_data = list(CACHE.get("data") or [])
        cached_summary = CACHE.get("gemini_summary") or ""
        cached_macro = dict(CACHE.get("macro") or {})
    ttl = float(globals().get("MARKET_CACHE_TTL", 40))
    do_force = bool(force) or cached_n <= 0 or cache_age >= ttl

    if not do_force and cached_n > 0:
        _scan_progress_update(
            status="complete", phase="داده از کش", completed=cached_n,
            total=max(total, cached_n), percent=100,
            last_success_at=time.time() - cache_age if cache_age < 1e9 else time.time(),
            message=f"کش تازه · {cached_n} ارز · سن {cache_age:.0f}s", fresh=False,
        )
        return cached_data, cached_summary, cached_macro

    _scan_progress_update(
        status="running", phase="آماده‌سازی داور مرکزی", started_at=scan_started,
        finished_at=0.0, completed=0, total=total, percent=3,
        message=f"داور مرکزی · اسکن {total} ارز…", fresh=False,
    )
    hb_stop = threading.Event()

    def _hb():
        while not hb_stop.wait(1.1):
            try:
                snap = _scan_progress_snapshot()
                if str(snap.get("status") or "") != "running":
                    break
                started = safe_float(snap.get("started_at"), scan_started)
                elapsed = max(0.0, time.time() - started)
                completed = int(snap.get("completed") or 0)
                soft = min(90.0, 4.0 + (elapsed / max(12.0, total * 2.5)) * 78.0 + completed * (70.0 / total))
                if soft > safe_float(snap.get("percent"), 0):
                    _scan_progress_update(percent=round(soft, 1),
                                          message=snap.get("message") or f"تحلیل زنده · {completed}/{total}")
            except Exception:
                break

    threading.Thread(target=_hb, name="titan-progress-hb", daemon=True).start()
    try:
        try:
            _central_evaluate_pending()
        except Exception:
            pass
        try:
            if "v32_evaluate_pending" in globals():
                v32_evaluate_pending()
        except Exception:
            pass

        data, summary, macro = _CENTRAL_PREV_UPDATE(True)
        sealed: list[dict[str, Any]] = []
        n_items = max(1, len(data or []))
        for idx, item in enumerate(data or [], 1):
            try:
                if str(item.get("authority", "")) == TITAN_CENTRAL_VERSION:
                    sealed.append(item)
                else:
                    sealed.append(_central_seal(item))
            except Exception:
                if item:
                    sealed.append(item)
            if idx == n_items or idx % 3 == 0:
                _scan_progress_update(
                    completed=idx, total=max(total, n_items),
                    percent=min(98, 85 + int(12 * idx / n_items)),
                    phase="مهر داور مرکزی", message=f"مهر مرکزی {idx}/{n_items}",
                )
        finished = time.time()
        with CACHE_LOCK:
            CACHE["data"] = sealed
            if sealed:
                CACHE["timestamp"] = finished
                if summary is not None:
                    CACHE["gemini_summary"] = summary
                if macro is not None:
                    CACHE["macro"] = macro
        if sealed:
            _scan_progress_update(
                status="complete", phase="اسکن کامل شد", completed=len(sealed),
                total=max(total, len(sealed)), percent=100, finished_at=finished,
                last_success_at=finished, elapsed_sec=round(finished - scan_started, 1),
                message=f"داور مرکزی · {len(sealed)} ارز · {round(finished - scan_started, 1)}s",
                fresh=True,
            )
            try:
                if "store_forecasts" in globals():
                    store_forecasts(sealed)
            except Exception:
                pass
            return sealed, summary, macro

        emergency = _emergency_live_cards(coins)
        if emergency:
            with CACHE_LOCK:
                CACHE["data"] = emergency
                CACHE["timestamp"] = finished
            _scan_progress_update(
                status="complete", phase="قیمت زنده اضطراری", completed=len(emergency),
                total=max(total, len(emergency)), percent=100, finished_at=finished,
                last_success_at=finished,
                message=f"اسکن کامل ناموفق؛ {len(emergency)} قیمت زنده",
                fresh=False,
            )
            return emergency, summary or "", macro or {}
        if cached_n > 0:
            _scan_progress_update(
                status="complete", phase="بازیابی کش", completed=cached_n,
                total=max(total, cached_n), percent=100, finished_at=finished,
                message=f"نمایش {cached_n} ارز از کش", fresh=False,
            )
            return cached_data, cached_summary, cached_macro
        _scan_progress_update(
            status="failed", phase="اسکن بدون نتیجه", percent=100, finished_at=finished,
            message="نتیجه‌ای برنگشت؛ اسکن بعدی خودکار است", fresh=False,
        )
        return [], summary or "", macro or {}
    except Exception as exc:
        LOGGER.exception("Central update_cache: %s", exc)
        finished = time.time()
        try:
            emergency = _emergency_live_cards(coins)
        except Exception:
            emergency = []
        if emergency:
            with CACHE_LOCK:
                CACHE["data"] = emergency
                CACHE["timestamp"] = finished
            _scan_progress_update(
                status="complete", phase="بازیابی اضطراری", percent=100,
                completed=len(emergency), finished_at=finished,
                message=f"خطا در اسکن · {len(emergency)} قیمت زنده", fresh=False,
            )
            return emergency, "", {}
        _scan_progress_update(
            status="failed", phase="خطای اسکن", percent=100, finished_at=finished,
            message=f"خطا: {str(exc)[:200]}", fresh=False,
        )
        with CACHE_LOCK:
            return list(CACHE.get("data") or []), CACHE.get("gemini_summary") or "", CACHE.get("macro") or {}
    finally:
        hb_stop.set()


# Patch index to never serve blank Android shell
_CENTRAL_PREV_INDEX = index


def index():
    try:
        with CACHE_LOCK:
            n = len(CACHE.get("data") or [])
        if n <= 0:
            try:
                emergency = _emergency_live_cards()
                if emergency:
                    with CACHE_LOCK:
                        if not CACHE.get("data"):
                            CACHE["data"] = emergency