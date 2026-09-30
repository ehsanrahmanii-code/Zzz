                        )
                        report["journal_expired"] += 1
            except Exception:
                pass
            con.commit()
    except Exception as exc:
        LOGGER.warning("V40 DB self-heal failed: %s", exc)
        report["error"] = str(exc)[:200]
    LOGGER.info("V40 DB self-heal: %s", report)
    return report


def _v40_unified_maintenance() -> dict[str, Any]:
    """Always-on evaluation brain so PENDING does not rot and learning continues."""
    out: dict[str, Any] = {}
    try:
        out["central"] = _central_evaluate_pending() if "_central_evaluate_pending" in globals() else {}
    except Exception as exc:
        out["central_err"] = str(exc)[:120]
    try:
        if "v32_evaluate_pending" in globals():
            out["v32"] = v32_evaluate_pending()
    except Exception as exc:
        out["v32_err"] = str(exc)[:120]
    try:
        evaluate_pending_forecasts()
        out["forecasts"] = "ok"
    except Exception as e:
        out["forecasts_err"] = str(e)[:120]
    try:
        evaluate_paper_trades()
        out["paper"] = "ok"
    except Exception as e:
        out["paper_err"] = str(e)[:120]
    try:
        _central_load_weights()
        out["weights_reloaded"] = True
    except Exception:
        pass
    try:
        with _V40_HIST_LOCK:
            _V40_HIST["ts"] = 0.0  # force hist refresh next gate
    except Exception:
        pass
    return out


def _v40_maintenance_loop() -> None:
    """Dedicated self-healing loop — independent of scan success."""
    # Initial heal once storage is ready
    try:
        _v40_db_self_heal()
    except Exception as exc:
        LOGGER.debug("initial heal: %s", exc)
    while not LIVE_STOP.is_set():
        try:
            _v40_unified_maintenance()
        except Exception as exc:
            LOGGER.debug("V40 maintenance: %s", exc)
        LIVE_STOP.wait(35)


def _v40_refresh_hist(force: bool = False) -> dict[str, Any]:
    now = time.time()
    with _V40_HIST_LOCK:
        if not force and _V40_HIST["ts"] and now - _V40_HIST["ts"] < 45:
            return _V40_HIST
    by_key: dict[str, dict[str, float]] = {}
    g_short = {"wins": 0.0, "losses": 0.0}
    g_long = {"wins": 0.0, "losses": 0.0}
    try:
        with DB_LOCK, db_conn() as con:
            rows = con.execute(
                """SELECT symbol, decision, outcome FROM central_predictions
                   WHERE outcome IN ('WIN','LOSS') AND decision IN ('LONG','SHORT')
                   ORDER BY id DESC LIMIT ?""",
                (V40_LOOKBACK,),
            ).fetchall()
        for r in rows:
            sym = _normalize_symbol(r[0] if not isinstance(r, sqlite3.Row) else r["symbol"])
            side = str((r[1] if not isinstance(r, sqlite3.Row) else r["decision"]) or "").upper()
            outc = str((r[2] if not isinstance(r, sqlite3.Row) else r["outcome"]) or "").upper()
            key = f"{sym}|{side}"
            st = by_key.setdefault(key, {"wins": 0.0, "losses": 0.0})
            if outc == "WIN":
                st["wins"] += 1
                (g_short if side == "SHORT" else g_long)["wins"] += 1
            else:
                st["losses"] += 1
                (g_short if side == "SHORT" else g_long)["losses"] += 1
        for st in by_key.values():
            n = st["wins"] + st["losses"]
            st["samples"] = n
            st["wr"] = 100.0 * st["wins"] / n if n else 50.0
        for g in (g_short, g_long):
            n = g["wins"] + g["losses"]
            g["samples"] = n
            g["wr"] = 100.0 * g["wins"] / n if n else 50.0
    except Exception as exc:
        LOGGER.debug("V40 hist: %s", exc)
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