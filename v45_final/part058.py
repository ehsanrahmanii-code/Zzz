    with _V40_HIST_LOCK:
        _V40_HIST.update({"ts": now, "by_key": by_key, "g_short": g_short, "g_long": g_long})
        return _V40_HIST


def _v40_horizon_agree(item: dict[str, Any]) -> dict[str, Any]:
    tf = item.get("tf_scores") or item.get("tfs") or {}
    scores = [safe_float(tf.get(k), 50.0) for k in ("15m", "1h", "4h", "1d")]
    leans = [(s - 50.0) / 50.0 for s in scores]
    fc = str((item.get("candle_forecast") or {}).get("overall_bias") or "")
    if fc == "صعودی":
        leans.append(0.4)
    elif fc == "نزولی":
        leans.append(-0.4)
    struct = item.get("structure") if isinstance(item.get("structure"), dict) else {}
    sb = str(struct.get("bias") or item.get("structure_bias") or "")
    if sb == "صعودی":
        leans.append(0.35)
    elif sb == "نزولی":
        leans.append(-0.35)
    # BTC regime soft lean for alts
    btc = str(item.get("btc_trend") or "")
    sym = str(item.get("symbol") or "")
    if "BTC" not in sym.upper():
        if btc == "صعودی":
            leans.append(0.2)
        elif btc == "نزولی":
            leans.append(-0.2)
    if not leans:
        return {"agreement": 0.0, "direction": "WAIT", "mean": 0.0}
    mean = sum(leans) / len(leans)
    var = sum((x - mean) ** 2 for x in leans) / max(1, len(leans))
    cohesion = float(clamp(1.0 - (var ** 0.5) * 1.7, 0.0, 1.0))
    agreement = float(clamp(cohesion * (0.4 + 0.6 * abs(mean)), 0.0, 1.0))
    direction = "LONG" if mean > 0.10 else "SHORT" if mean < -0.10 else "WAIT"
    return {"agreement": round(agreement, 4), "direction": direction, "mean": round(mean, 4)}


def _v40_force_wait(item: dict[str, Any], reason_fa: str, code: str) -> dict[str, Any]:
    x = dict(item or {})
    x["decision_tag"] = x["decision"] = "WAIT"
    x["bias"] = "خنثی"
    x["entry_mode"] = "WAIT"
    x["signal_tag"] = f"V40 PRECISION WAIT — {code}"
    x["central_reason_fa"] = reason_fa
    x["v40_demoted"] = True
    x["v40_demote_code"] = code
    for k in ("stop_loss", "tp1", "tp2"):
        x[k] = "—"
    for k in ("stop_loss_raw", "tp1_raw", "tp2_raw", "effective_rr_tp1", "effective_rr_tp2"):
        x[k] = 0.0
    x["rr_tp1"] = x["rr_tp2"] = "—"
    return x


def _v40_precision_gate(item: dict[str, Any], cache_rows: Optional[list] = None) -> dict[str, Any]:
    """Final public authority — history + integrity + multi-horizon confluence."""
    x = dict(item or {})
    decision = str(x.get("decision_tag") or x.get("decision") or "WAIT").upper()
    notes: list[str] = []
    hist = _v40_refresh_hist()
    sym = _normalize_symbol(x.get("symbol") or "")
    key = f"{sym}|{decision}"
    st = (hist.get("by_key") or {}).get(key) or {"wins": 0, "losses": 0, "samples": 0, "wr": 50.0}
    g_short = hist.get("g_short") or {"wr": 50.0, "samples": 0}
    g_long = hist.get("g_long") or {"wr": 50.0, "samples": 0}

    if decision in {"LONG", "SHORT"}:
        if st.get("samples", 0) >= V40_BAN_N and st.get("wr", 50) < V40_BAN_WR:
            return _v40_force_wait(
                x, f"سابقه {sym} {decision}: WR {st['wr']:.0f}% از {int(st['samples'])} — مسدود.", "HISTORY_BAN")
        if decision == "SHORT" and g_short.get("samples", 0) >= V40_GLOBAL_SHORT_N and g_short.get("wr", 50) < V40_GLOBAL_SHORT_WR:
            return _v40_force_wait(
                x, f"رژیم SHORT ضعیف (WR {g_short['wr']:.0f}%) — SHORT جدید نیست.", "SHORT_REGIME_BLOCK")
        # Soft BTC regime: haircut weak alt-SHORT in BTC uptrend; allow strong ones
        if decision == "SHORT" and "BTC" not in sym.upper() and str(x.get("btc_trend") or "") == "صعودی":
            conf0 = safe_float(x.get("decision_confidence"), 50.0)
            if conf0 < 62:
                return _v40_force_wait(x, "شورت ضعیف آلت در روند صعودی BTC", "BTC_REGIME_SOFT")
            x["decision_confidence"] = round(max(52.0, conf0 - 8.0), 1)
            notes.append("btc_up_short_haircut")

    price = safe_float(x.get("price_raw") or x.get("live_price") or x.get("entry_raw"), 0.0)
    live_sync = bool(x.get("live_sync", False))
    live_age = safe_float(x.get("live_price_age_sec"), 999.0)
    if decision in {"LONG", "SHORT"}:
        if price <= 0:
            return _v40_force_wait(x, "قیمت نامعتبر", "NO_PRICE")
        if live_age > 30:
            return _v40_force_wait(x, f"قیمت زنده خیلی کهنه ({live_age:.0f}s)", "STALE_LIVE")
        if not live_sync or live_age > V40_MIN_LIVE_AGE:
            conf_now = safe_float(x.get("decision_confidence"), 50.0)
            x["decision_confidence"] = round(max(50.0, conf_now - 4.0), 1)
            notes.append(f"live_soft_age_{live_age:.0f}s")

    if decision in {"LONG", "SHORT"} and price > 0:
        sl = safe_float(x.get("stop_loss_raw"), safe_float(str(x.get("stop_loss") or "0").replace(",", ""), 0.0))
        tp1 = safe_float(x.get("tp1_raw"), safe_float(str(x.get("tp1") or "0").replace(",", ""), 0.0))
        tp2 = safe_float(x.get("tp2_raw"), safe_float(str(x.get("tp2") or "0").replace(",", ""), 0.0))
        try:
            chk = _v12_level_integrity(price, sl, tp1, tp2, decision)
            need_rebuild = (not chk.get("ok")) or safe_float(chk.get("rr1"), 0) < V40_MIN_RR1 or safe_float(chk.get("rr2"), 0) < V40_MIN_RR2
            if need_rebuild:
                rsl, rtp1, rtp2 = _v12_rebuild_directional_levels(x, decision)
                chk2 = _v12_level_integrity(price, rsl, rtp1, rtp2, decision)
                if chk2.get("ok") and safe_float(chk2.get("rr1"), 0) >= V40_MIN_RR1 and safe_float(chk2.get("rr2"), 0) >= V40_MIN_RR2:
                    x["stop_loss_raw"], x["tp1_raw"], x["tp2_raw"] = float(rsl), float(rtp1), float(rtp2)
                    x["stop_loss"], x["tp1"], x["tp2"] = smart_format(rsl), smart_format(rtp1), smart_format(rtp2)
                    x["rr_tp1"], x["rr_tp2"] = chk2.get("rr1"), chk2.get("rr2")
                    x["effective_rr_tp1"], x["effective_rr_tp2"] = x["rr_tp1"], x["rr_tp2"]
                    notes.append("levels_rebuilt")
                else:
                    return _v40_force_wait(x, "سطوح یا R:R زیر از استاندارد V40", "BAD_LEVELS")
            else:
                x["rr_tp1"], x["rr_tp2"] = chk.get("rr1"), chk.get("rr2")
                x["effective_rr_tp1"], x["effective_rr_tp2"] = x["rr_tp1"], x["rr_tp2"]
        except Exception:
            return _v40_force_wait(x, "خطا در اعتبارسنجی سطوح", "LEVEL_ERROR")

    agree = _v40_horizon_agree(x)
    if decision in {"LONG", "SHORT"}:
        a_score = safe_float(agree.get("agreement"), 0)
        a_dir = agree.get("direction")
        # Hard kill only when horizons clearly oppose the decision with decent cohesion
        if a_dir in {"LONG", "SHORT"} and a_dir != decision and a_score >= 0.45:
            return _v40_force_wait(
                x, f"اجماع افق‌ها مخالف جهت ({a_dir}, a={a_score:.2f})", "HORIZON_CONFLICT")
        # Soft path: weak agreement reduces confidence instead of killing the opportunity
        if a_dir != decision or a_score < V40_MIN_AGREE:
            conf_now = safe_float(x.get("decision_confidence"), 50.0)
            haircut = 6.0 if a_score < 0.25 else 3.0
            x["decision_confidence"] = round(max(50.0, conf_now - haircut), 1)
            notes.append(f"horizon_soft_{a_dir}_{a_score:.2f}")
        else:
            notes.append(f"horizon_ok_{a_score:.2f}")

    conf = safe_float(x.get("decision_confidence"), 50.0)
    if decision in {"LONG", "SHORT"} and conf < 48.0:
        return _v40_force_wait(x, f"اطمینان خیلی پایین ({conf:.0f})", "LOW_CONF")
    if decision in {"LONG", "SHORT"} and conf < V40_MIN_CONF:
        notes.append(f"conf_borderline_{conf:.0f}")

    atr = safe_float(x.get("atr"), 0.0)
    vwap = safe_float(x.get("vwap"), price)
    stretch = abs(price - vwap) / atr if atr > 0 and price > 0 else 0.0
    if decision in {"LONG", "SHORT"} and stretch > MAX_STRETCH_ATR:
        return _v40_force_wait(x, f"ورود دیر ATR-stretch={stretch:.2f}", "OVEREXTENDED")

    try:
        port = portfolio_side_pressure(decision, sym)
        if decision in {"LONG", "SHORT"} and not port.get("ok", True):
            return _v40_force_wait(x, str(port.get("reason") or "اشباع سبد"), "PORTFOLIO")
    except Exception:
        pass

    if decision in {"LONG", "SHORT"} and st.get("samples", 0) >= V40_BAN_N and st.get("wr", 50) < V40_SOFT_WR:
        conf = max(V40_MIN_CONF, conf - min(15.0, (V40_SOFT_WR - st["wr"]) * 0.4))
        notes.append("hist_haircut")
    if decision in {"LONG", "SHORT"} and st.get("samples", 0) >= 4:
        cap = min(82.0, max(58.0, st["wr"] + 12.0))
        conf = min(conf, cap)
    if decision == "SHORT" and g_short.get("samples", 0) >= 10:
        conf = min(conf, max(58.0, g_short["wr"] + 10.0))
    if decision == "LONG" and g_long.get("samples", 0) >= 10:
        conf = min(conf, max(58.0, g_long["wr"] + 12.0))

    x["decision_confidence"] = round(float(clamp(conf, 0, 82)), 1)
    x["success_prob"] = x["decision_confidence"]
    cal = x.get("probability_calibration") if isinstance(x.get("probability_calibration"), dict) else {}
    is_cal = bool(cal.get("is_calibrated") or safe_float(cal.get("samples"), 0) >= 8)
    cal_val = safe_float(cal.get("calibrated"), conf)
    x["success_probability"] = round(float(clamp(cal_val if is_cal else conf, 5, 80)), 1)
    x["success_probability_is_calibrated"] = is_cal
    x["probability_disclaimer"] = (
        "احتمال کالیبره‌شده از نتایج واقعی" if is_cal else "اطمینان مدل است، نه احتمال تضمینی سود"
    )
    x["reliability_note"] = "فقط سیگنال عبورکرده از V40 Self-Healing Precision منتشر می‌شود."

    if decision == "WAIT":
        x["decision"] = x["decision_tag"] = "WAIT"
        x["bias"] = "خنثی"
    else:
        x["decision"] = x["decision_tag"] = decision
        x["bias"] = "صعودی" if decision == "LONG" else "نزولی"
        try:
            register_portfolio_signal(sym, decision)
        except Exception:
            pass

    x["v40_precision"] = {
        "version": V40_VERSION,
        "passed": decision in {"LONG", "SHORT"},
        "decision": decision,
        "history": st,
        "global_short_wr": g_short.get("wr"),
        "global_long_wr": g_long.get("wr"),
        "horizon": agree,
        "stretch_atr": round(stretch, 2),
        "notes": notes,
        "live_age_sec": round(live_age, 2) if live_age < 1e5 else None,
    }
    x.setdefault("fusion", {})["v40_precision"] = x["v40_precision"]
    arch = dict(x.get("decision_architecture") or {}) if isinstance(x.get("decision_architecture"), dict) else {}
    arch["precision_layer"] = V40_VERSION
    arch["final_decision"] = decision
    arch["self_healing"] = True
    x["decision_architecture"] = arch
    x["authority"] = f"{TITAN_CENTRAL_VERSION}+{V40_VERSION}"
    return x



# ============================================================
# TITAN V42 — INTEGRITY / RISK / PROVENANCE SEAL
# ============================================================
# This is intentionally a *last-mile* layer.  It does not create signals.
# It validates that every published directional signal is internally coherent,
# fresh, risk-defined, auditable, and clearly separated from calibrated odds.
V42_VERSION = "TITAN-V42-INTEGRITY-SEAL"
V42_MAX_LIVE_AGE = 12.0
V42_MIN_RR1 = 1.10
V42_MIN_RR2 = 1.40
V42_MIN_DATA = 45.0
V42_MIN_CAL_SAMPLES = 30
V42_MAX_ATR_STRETCH = 3.25


def _v42_price(x: dict[str, Any]) -> float:
    return safe_float(x.get("price_raw"), safe_float(x.get("live_price"), safe_float(str(x.get("price") or "0").replace(",", ""), 0.0)))


def _v42_levels_ok(price: float, sl: float, tp1: float, tp2: float, side: str) -> bool:
    if min(price, sl, tp1, tp2) <= 0:
        return False
    if side == "LONG":
        return sl < price < tp1 < tp2
    if side == "SHORT":
        return tp2 < tp1 < price < sl
    return True


def _v42_integrity_seal(item: dict[str, Any]) -> dict[str, Any]:
    """Final fail-closed contract for the public signal object.

    The seal is deliberately independent of the score-producing engines.  It
    catches stale data, malformed levels, weak RR, contradictory direction,
    uncalibrated probability claims, and missing audit/provenance fields.
    """
    x = dict(item or {})
    side = str(x.get("decision_tag") or x.get("decision") or "WAIT").upper()
    price = _v42_price(x)
    sl = safe_float(x.get("stop_loss_raw"), safe_float(x.get("stop_loss"), 0.0))
    tp1 = safe_float(x.get("tp1_raw"), safe_float(x.get("tp1"), 0.0))
    tp2 = safe_float(x.get("tp2_raw"), safe_float(x.get("tp2"), 0.0))
    atr = safe_float(x.get("atr"), 0.0)
    live_age = safe_float(x.get("live_price_age_sec"), 1e9)
    dq = x.get("data_quality") if isinstance(x.get("data_quality"), dict) else {}
    data_score = safe_float(dq.get("score"), safe_float(x.get("data_trust"), 0.0))
    reasons: list[str] = []

    if side in {"LONG", "SHORT"}:
        if price <= 0:
            reasons.append("invalid_price")
        if live_age > V42_MAX_LIVE_AGE:
            reasons.append("stale_live_price")
        if data_score and data_score < V42_MIN_DATA:
            reasons.append("low_data_quality")
        if not _v42_levels_ok(price, sl, tp1, tp2, side):
            reasons.append("invalid_directional_levels")
        risk = abs(price - sl)
        rr1 = abs(tp1 - price) / risk if risk > 0 else 0.0
        rr2 = abs(tp2 - price) / risk if risk > 0 else 0.0
        if rr1 < V42_MIN_RR1:
            reasons.append("rr1_below_floor")
        if rr2 < V42_MIN_RR2:
            reasons.append("rr2_below_floor")
        if atr > 0 and risk > 0 and risk / atr > V42_MAX_ATR_STRETCH:
            reasons.append("stop_distance_extreme")
    else:
        rr1 = rr2 = 0.0

    # Probability must never be presented as calibrated unless it is backed by
    # realized samples.  This field is a contract guard, not a prediction.
    cal = x.get("probability_calibration") if isinstance(x.get("probability_calibration"), dict) else {}
    cal_n = int(safe_float(cal.get("samples"), 0))
    is_cal = bool(x.get("success_probability_is_calibrated") and cal.get("is_calibrated"))
    if side in {"LONG", "SHORT"} and is_cal and cal_n < V42_MIN_CAL_SAMPLES:
        is_cal = False
        reasons.append("calibration_sample_floor")

    # A signal can only be published directionally if its final risk contract
    # is coherent.  WAIT is the safe state and remains fully auditable.
    if side in {"LONG", "SHORT"} and reasons:
        x["decision_tag"] = "WAIT"
        x["decision"] = "WAIT"
        x["bias"] = "خنثی"
        x["entry_mode"] = "WAIT"
        x["signal_tag"] = "V42 INTEGRITY BLOCK"
        x["v42_blocked_candidate"] = side
        side = "WAIT"