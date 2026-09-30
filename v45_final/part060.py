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