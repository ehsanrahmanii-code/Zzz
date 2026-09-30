        "safety_block": safety_block,
        "components": {
            "margin": round(margin_score, 1), "quality": round(quality_score, 1),
            "data": round(dq_score, 1), "support": round(support_score, 1),
            "rr": round(rr_score, 1), "contradiction": round(contradiction_score, 1),
            "history": round(history_score, 1),
        },
        "note": "Evidence score only; not a guaranteed probability of profit.",
    }


def _v34_apply(item: dict[str, Any]) -> dict[str, Any]:
    """Final opportunity layer above the canonical evidence stack."""
    try:
        opp = _v34_opportunity(item)
        item["v34_opportunity"] = opp
        item.setdefault("fusion", {})["v34_opportunity"] = opp
        current = str(item.get("decision_tag") or item.get("decision") or "WAIT").upper()
        # Only promote a WAIT that is already supported by the existing central
        # debate. Never flip a valid LONG/SHORT and never bypass hard safety blocks.
        if current == "WAIT" and opp.get("state") == "PROMOTE_EARLY":
            decision = str(opp.get("candidate") or "WAIT")
            item["decision_tag"] = decision
            item["decision"] = decision
            item["bias"] = "صعودی" if decision == "LONG" else "نزولی"
            item["entry_mode"] = "EARLY"
            item["decision_state"] = "CENTRAL_V34_EARLY"
            item["signal_tag"] = f"CENTRAL V34 OPPORTUNITY — {decision}"
            # Confidence is increased modestly by evidence quality, never to 100.
            old = safe_float(item.get("decision_confidence"), 50.0)
            boost = min(8.0, max(2.0, (safe_float(opp.get("score"), 66.0) - 60.0) * 0.20))
            item["decision_confidence"] = round(clamp(max(old, 50.0) + boost, 0.0, 96.0), 1)
            item["central_reason_fa"] = "فرصت نزدیک به فعال‌شدن با اجماع شواهد، کیفیت داده و RR معتبر؛ V34 آن را از WAIT به EARLY ارتقا داد."
            item["v34_promoted"] = True
        else:
            item["v34_promoted"] = False
        item["decision_architecture"] = {
            "type": "SINGLE_CENTRAL_GOVERNOR_WITH_ADAPTIVE_EVIDENCE",
            "authoritative_source": TITAN_CENTRAL_VERSION,
            "opportunity_layer": V34_VERSION,
            "final_decision": item.get("decision_tag", "WAIT"),
            "legacy_engines_are_evidence_only": True,
        }
        return item
    except Exception as exc:
        LOGGER.debug("V34 adaptive trust failed: %s", exc)
        item["v34_opportunity"] = {"version": V34_VERSION, "state": "DEGRADED", "score": 0.0}
        item["v34_promoted"] = False
        return item

# ============================================================
# TITAN V35 — CANONICAL LIVE-PRICE / LEVEL SYNCHRONIZATION
# ------------------------------------------------------------
# One authoritative spot snapshot is used for the public dashboard price,
# entry, SL/TP, RR, forecast anchor and live-price metadata. Closed-candle
# indicators remain based on closed OHLCV; only price-dependent outputs are
# re-anchored. No signal is fabricated when a fresh live price is unavailable.
# ============================================================
V35_VERSION = "TITAN-V35-CANONICAL-LIVE-SNAPSHOT"
V35_MAX_LIVE_AGE_SEC = 8.0
V35_REBASE_MAX_AGE_SEC = 12.0


def _v35_get_live_snapshot(symbol: str, max_age: float = V35_MAX_LIVE_AGE_SEC) -> dict[str, Any]:
    """Return the freshest available Binance spot snapshot for one symbol."""
    sym = _normalize_symbol(symbol)
    now = time.time()
    with LIVE_LOCK:
        info = dict(LIVE_PRICES.get(sym) or {})
    px = safe_float(info.get("price"), 0.0)
    ts = safe_float(info.get("ts"), 0.0)
    age = now - ts if ts > 0 else float("inf")
    if px > 0 and age <= float(max_age):
        return {"price": px, "ts": ts, "age_sec": max(0.0, age),
                "source": info.get("source") or "Binance"}

    # The background live engine normally keeps this hot. A direct refresh is
    # the fail-safe for a slow/stopped worker, and is limited to this symbol.
    try:
        fresh = _fetch_live_prices([sym])
        px = safe_float(fresh.get(sym), 0.0)
        if px > 0:
            _register_live_price(sym, px, "REST-direct")
            with LIVE_LOCK:
                info = dict(LIVE_PRICES.get(sym) or {})
            ts = safe_float(info.get("ts"), time.time())
            return {"price": px, "ts": ts,
                    "age_sec": max(0.0, time.time() - ts),
                    "source": info.get("source") or "REST-direct"}
    except Exception as exc:
        LOGGER.debug("V35 direct live snapshot failed %s: %s", sym, exc)

    return {"price": px, "ts": ts, "age_sec": age,
            "source": info.get("source") or "cache", "fresh": False}


def _v35_rebase_price_dependent_outputs(item: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """Make all public price/entry/exit outputs coherent with one live price."""
    if not item or not snapshot:
        return item
    live = safe_float(snapshot.get("price"), 0.0)
    if live <= 0:
        item["live_sync"] = False
        item["live_sync_reason"] = "fresh_live_price_unavailable"
        return item

    now = time.time()
    old = _v29_num_price(item.get("price_raw") or item.get("price"))
    if old <= 0:
        old = live
    ratio = live / old if old > 0 else 1.0

    item.setdefault("signal_snapshot", {})
    if "price" not in item["signal_snapshot"]:
        item["signal_snapshot"]["price"] = old
        item["signal_snapshot"]["timestamp"] = item.get("scan_timestamp", now)

    item["price_raw"] = live
    item["live_price"] = live
    item["entry_raw"] = live
    item["price"] = smart_format(live)
    item["entry_valid"] = smart_format(live)

    # Directional exits are percentage-rebased from the exact signal snapshot.
    # If a final direction was promoted after the original levels were built,
    # rebuild them from the current price and validate orientation/RR first.
    decision = str(item.get("decision_tag") or item.get("decision") or "WAIT").upper()
    if decision in {"LONG", "SHORT"}:
        for key in ("stop_loss", "tp1", "tp2"):
            if key in item:
                item[key] = _v29_shift_price_field(item.get(key), ratio)

        sl = _v29_num_price(item.get("stop_loss"))
        tp1 = _v29_num_price(item.get("tp1"))
        tp2 = _v29_num_price(item.get("tp2"))
        check = _v12_level_integrity(live, sl, tp1, tp2, decision)
        if not check.get("ok"):
            rsl, rtp1, rtp2 = _v12_rebuild_directional_levels(item, decision)
            check2 = _v12_level_integrity(live, rsl, rtp1, rtp2, decision)
            if check2.get("ok"):
                sl, tp1, tp2 = rsl, rtp1, rtp2
                check = check2
                item["level_rebased_by_v35"] = True
            else:
                # Never expose a directional signal with invalid levels.
                item["decision_tag"] = "WAIT"
                item["decision"] = "WAIT"
                item["bias"] = "خنثی"
                item["entry_mode"] = "WAIT"
                item["signal_tag"] = "V35 SAFETY WAIT — LIVE LEVELS INVALID"
                item["level_rebased_by_v35"] = False
                item["live_sync_reason"] = "directional_levels_invalid_after_live_rebase"
                sl = tp1 = tp2 = 0.0
        if sl > 0 and tp1 > 0 and tp2 > 0:
            item["stop_loss_raw"] = float(sl)
            item["tp1_raw"] = float(tp1)
            item["tp2_raw"] = float(tp2)
            item["stop_loss"] = smart_format(sl)
            item["tp1"] = smart_format(tp1)
            item["tp2"] = smart_format(tp2)
            item["rr_tp1"] = check.get("rr1", 0.0)
            item["rr_tp2"] = check.get("rr2", 0.0)
            item["effective_rr_tp1"] = item["rr_tp1"]
            item["effective_rr_tp2"] = item["rr_tp2"]
    else:
        # WAIT has no actionable exit levels. Its entry anchor is always live.
        item["entry_raw"] = live
        item["entry_valid"] = smart_format(live)

    sl = _v29_num_price(item.get("stop_loss"))
    tp1 = _v29_num_price(item.get("tp1"))
    tp2 = _v29_num_price(item.get("tp2"))
    if sl > 0:
        risk = abs(live - sl)
        item["risk_distance_pct"] = round(risk / live * 100.0, 3)
        if risk > 0 and tp1 > 0:
            item["rr_tp1"] = round(abs(tp1 - live) / risk, 3)
            item["effective_rr_tp1"] = item["rr_tp1"]
        if risk > 0 and tp2 > 0:
            item["rr_tp2"] = round(abs(tp2 - live) / risk, 3)
            item["effective_rr_tp2"] = item["rr_tp2"]

    # Keep scenario prices anchored to exactly the same live reference.
    fc = item.get("candle_forecast")
    if isinstance(fc, dict):
        fc["last_price"] = round(live, 8)
        if old > 0 and math.isfinite(ratio) and ratio > 0:
            for candle in fc.get("candles", []) or []:
                if isinstance(candle, dict):
                    for key in ("open", "high", "low", "close", "mid", "band_low", "band_high"):
                        if key in candle:
                            try:
                                candle[key] = round(float(candle[key]) * ratio, 8)
                            except Exception:
                                pass

    age = max(0.0, now - safe_float(snapshot.get("ts"), now))
    item["live_price_source"] = snapshot.get("source") or "Binance"
    item["live_price_ts"] = safe_float(snapshot.get("ts"), now)
    item["live_price_age_sec"] = round(age, 3)
    item["live_sync"] = bool(age <= V35_MAX_LIVE_AGE_SEC)
    item["price_delta_from_scan_pct"] = round((live / old - 1.0) * 100.0, 4) if old > 0 else 0.0
    item["price_sync_version"] = V35_VERSION
    item["price_sync"] = {
        "authoritative_price": live,
        "source": item["live_price_source"],
        "timestamp": item["live_price_ts"],
        "age_sec": item["live_price_age_sec"],
        "entry_anchor": live,
        "levels_rebased": bool(item.get("level_rebased_by_v35", False) or decision in {"LONG", "SHORT"}),
        "single_price_source_for_public_outputs": True,
    }
    return item



# ============================================================
# TITAN V36 — QUANTUM RESONANCE EDGE (magical upgrade layer)
# ------------------------------------------------------------
# Cross-asset resonance, drift-aware confidence decay, and
# multi-horizon agreement score. Analysis-only; never invents
# win probability. Can only demote unsafe signals or modestly
# boost a coherent multi-horizon edge that is already present.
# ============================================================
V36_VERSION = "TITAN-V36-QUANTUM-RESONANCE-EDGE"
V36_DRIFT_KILL_PCT = 1.85
V36_RESONANCE_BOOST_MIN = 0.62
V36_MAX_CONF_BOOST = 6.0
_V36_RESONANCE_CACHE: dict[str, Any] = {"ts": 0.0, "matrix": {}}
_V36_RESONANCE_LOCK = threading.RLock()


def _v36_horizon_agreement(item: dict[str, Any]) -> dict[str, Any]:
    """Score agreement across HTF/MTF/LTF + forecast path + structure."""
    tf = item.get("tf_scores") or item.get("tfs") or {}
    s15 = safe_float(tf.get("15m"), 50.0)
    s1h = safe_float(tf.get("1h"), 50.0)
    s4h = safe_float(tf.get("4h"), 50.0)
    s1d = safe_float(tf.get("1d"), 50.0)
    decision = str(item.get("decision_tag") or item.get("decision") or "WAIT").upper()

    def lean(sc: float) -> float:
        return clamp((sc - 50.0) / 50.0, -1.0, 1.0)

    leans = [lean(s15), lean(s1h), lean(s4h), lean(s1d)]
    fc = item.get("candle_forecast") or {}
    fc_bias = str(fc.get("overall_bias") or "")
    if fc_bias == "صعودی":
        leans.append(0.45)
    elif fc_bias == "نزولی":
        leans.append(-0.45)
    struct = item.get("structure") if isinstance(item.get("structure"), dict) else {}
    sb = str(struct.get("bias") or item.get("structure_bias") or "")
    if sb == "صعودی":
        leans.append(0.40)
    elif sb == "نزولی":
        leans.append(-0.40)

    if not leans:
        return {"agreement": 0.0, "direction": "WAIT", "n": 0}
    mean = sum(leans) / len(leans)
    var = sum((x - mean) ** 2 for x in leans) / max(1, len(leans))
    cohesion = float(clamp(1.0 - (var ** 0.5) * 1.8, 0.0, 1.0))
    magnitude = abs(mean)
    agreement = float(clamp(cohesion * (0.45 + 0.55 * magnitude), 0.0, 1.0))
    direction = "LONG" if mean > 0.08 else "SHORT" if mean < -0.08 else "WAIT"
    aligned = direction == decision if decision in {"LONG", "SHORT"} else False
    return {
        "agreement": round(agreement, 4),
        "mean_lean": round(mean, 4),
        "cohesion": round(cohesion, 4),
        "direction": direction,
        "aligned_with_decision": aligned,
        "n": len(leans),
    }


def _v36_price_drift_gate(item: dict[str, Any]) -> dict[str, Any]:
    """Kill directional signals when live price has run away from the scan snapshot."""
    snap = item.get("signal_snapshot") if isinstance(item.get("signal_snapshot"), dict) else {}
    snap_px = safe_float(snap.get("price"), 0.0)
    live = safe_float(item.get("price_raw") or item.get("live_price"), 0.0)
    decision = str(item.get("decision_tag") or item.get("decision") or "WAIT").upper()
    if snap_px <= 0 or live <= 0 or decision not in {"LONG", "SHORT"}:
        return {"drift_pct": 0.0, "kill": False, "reason": ""}
    drift = (live / snap_px - 1.0) * 100.0
    adverse = (decision == "LONG" and drift > V36_DRIFT_KILL_PCT) or (
        decision == "SHORT" and drift < -V36_DRIFT_KILL_PCT
    )
    extreme = abs(drift) > V36_DRIFT_KILL_PCT * 1.6
    kill = bool(adverse or extreme)
    reason = ""
    if adverse:
        reason = f"adverse_drift_{drift:+.2f}%"
    elif extreme:
        reason = f"extreme_drift_{drift:+.2f}%"
    return {"drift_pct": round(drift, 3), "kill": kill, "reason": reason, "snap": snap_px, "live": live}


def _v36_cross_asset_resonance(symbol: str, decision: str, cache_rows: list) -> dict[str, Any]:
    """Soft portfolio resonance: same-side cluster reduces edge quality."""
    if decision not in {"LONG", "SHORT"} or not cache_rows:
        return {"same_side": 0, "penalty": 0.0, "note": ""}
    majors = {"BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT"}
    sym = _normalize_symbol(symbol)
    same = 0
    for row in cache_rows:
        other = _normalize_symbol(row.get("symbol") or "")
        if other == sym:
            continue
        od = str(row.get("decision_tag") or row.get("decision") or "").upper()
        if od == decision:
            same += 1
    penalty = 0.0
    note = ""
    if same >= 6:
        penalty = 10.0
        note = f"رزونانس سبد: {same} سیگنال هم‌جهت فعال"
    elif same >= 4:
        penalty = 5.0
        note = f"فشار خوشه‌ای: {same} سیگنال هم‌جهت"
    if sym in majors and same >= 3:
        penalty = max(penalty, 4.0)
    return {"same_side": same, "penalty": penalty, "note": note}


def _v36_apply(item: dict[str, Any], cache_rows: Optional[list] = None) -> dict[str, Any]:
    """Quantum Resonance final polish — demote on drift, modest boost on pure agreement."""
    try:
        decision = str(item.get("decision_tag") or item.get("decision") or "WAIT").upper()
        agree = _v36_horizon_agreement(item)
        drift = _v36_price_drift_gate(item)
        resonance = _v36_cross_asset_resonance(
            str(item.get("symbol") or ""), decision, list(cache_rows or [])
        )
        killed = False
        boosted = False
        notes: list[str] = []

        if decision in {"LONG", "SHORT"} and drift.get("kill"):
            item["decision_tag"] = "WAIT"
            item["decision"] = "WAIT"
            item["bias"] = "خنثی"
            item["entry_mode"] = "WAIT"
            item["signal_tag"] = "V36 RESONANCE WAIT — PRICE DRIFT"
            item["central_reason_fa"] = (
                f"قیمت از اسنپ‌شات سیگنال بیش از حد فاصله گرفته ({drift.get('reason')}); "
                "سیگنال جهت‌دار باطل شد."
            )
            killed = True
            notes.append(str(drift.get("reason") or "drift_kill"))

        if not killed and decision in {"LONG", "SHORT"}:
            if (
                agree.get("direction") in {"LONG", "SHORT"}
                and agree.get("direction") != decision
                and agree.get("agreement", 0) >= 0.55
            ):
                item["decision_tag"] = "WAIT"
                item["decision"] = "WAIT"
                item["bias"] = "خنثی"
                item["entry_mode"] = "WAIT"
                item["signal_tag"] = "V36 RESONANCE WAIT — HORIZON DISCORD"
                item["central_reason_fa"] = "اجماع افق‌های زمانی با جهت سیگنال در تضاد است."
                killed = True
                notes.append("horizon_discord")
            elif agree.get("aligned_with_decision") and agree.get("agreement", 0) >= V36_RESONANCE_BOOST_MIN:
                conf = safe_float(item.get("decision_confidence"), 50.0)
                boost = min(V36_MAX_CONF_BOOST, (agree["agreement"] - V36_RESONANCE_BOOST_MIN) * 18.0)
                boost = max(0.0, boost - safe_float(resonance.get("penalty"), 0.0) * 0.35)
                if boost >= 1.0:
                    item["decision_confidence"] = round(clamp(conf + boost, 0.0, 96.0), 1)
                    boosted = True
                    notes.append(f"resonance_boost_+{boost:.1f}")
            if resonance.get("penalty", 0) >= 8 and not killed:
                conf = safe_float(item.get("decision_confidence"), 50.0)
                item["decision_confidence"] = round(max(35.0, conf - resonance["penalty"]), 1)
                notes.append(resonance.get("note") or "cluster_pressure")

        item["v36_resonance"] = {
            "version": V36_VERSION,
            "horizon_agreement": agree,
            "price_drift": drift,
            "cross_asset": resonance,
            "killed": killed,
            "boosted": boosted,
            "notes": notes,
        }
        item.setdefault("fusion", {})["v36_resonance"] = item["v36_resonance"]
        arch = item.get("decision_architecture") if isinstance(item.get("decision_architecture"), dict) else {}
        arch = dict(arch)
        arch["resonance_layer"] = V36_VERSION
        arch["final_decision"] = item.get("decision_tag", "WAIT")
        item["decision_architecture"] = arch
        return item
    except Exception as exc:
        LOGGER.debug("V36 resonance failed: %s", exc)
        item["v36_resonance"] = {"version": V36_VERSION, "error": str(exc)[:180]}
        return item



# ============================================================
# TITAN V40 — FIVE HARD FIXES IN ONE LAYER
# 1) Precision thresholds already applied globally
# 2) Paper integrity already applied
# 3) DB self-heal on startup (corrupt paper + stuck PENDING)
# 4) Unified maintenance brain (central/v32/forecast/journal/paper)
# 5) Final precision gate (history ban + confluence + integrity)
# ============================================================
V40_VERSION = "TITAN-V41-BALANCED-OPPORTUNITY"
V40_MIN_LIVE_AGE = 12.0
V40_MIN_RR1 = 1.10
V40_MIN_RR2 = 1.40
V40_MIN_CONF = 52.0
V40_MIN_AGREE = 0.38
V40_BAN_WR = 30.0
V40_BAN_N = 8
V40_SOFT_WR = 40.0
V40_GLOBAL_SHORT_WR = 35.0
V40_GLOBAL_SHORT_N = 20
V40_LOOKBACK = 250
_V40_HIST: dict[str, Any] = {"ts": 0.0, "by_key": {}, "g_short": {}, "g_long": {}}
_V40_HIST_LOCK = threading.RLock()


def _v40_db_self_heal() -> dict[str, Any]:
    """One-shot hygiene: close corrupt papers, expire impossible PENDING rows."""
    report = {"paper_invalid": 0, "paper_absurd_r": 0, "forecast_expired": 0,
              "v32_expired": 0, "journal_expired": 0, "central_forced": 0}
    now = time.time()
    try:
        with DB_LOCK, db_conn() as con:
            # Corrupt closed papers with exit=0 or |R|>20
            cur = con.execute(
                "SELECT id, entry, exit_price, r_multiple, tp1, sl FROM paper_trades WHERE status='CLOSED'"
            ).fetchall()
            for row in cur:
                rid = row[0]
                entry = safe_float(row[1], 0)
                exit_px = safe_float(row[2], 0)
                r_mult = safe_float(row[3], 0)
                tp1 = safe_float(row[4], 0)
                sl = safe_float(row[5], 0)
                bad = False
                reason = None
                if tp1 <= 0 or sl <= 0 or entry <= 0:
                    bad, reason = True, "INVALID_LEVELS_HEALED"
                elif exit_px <= 0:
                    bad, reason = True, "INVALID_EXIT_HEALED"
                elif abs(r_mult) > 8:
                    bad, reason = True, "ABSURD_R_HEALED"
                if bad:
                    con.execute(
                        "UPDATE paper_trades SET pnl_pct=0, r_multiple=0, reason=?, exit_price=? WHERE id=?",
                        (reason, entry if exit_px <= 0 else exit_px, rid),
                    )
                    report["paper_absurd_r" if "R" in (reason or "") else "paper_invalid"] += 1
            # Open papers with invalid levels
            for row in con.execute("SELECT id, entry, sl, tp1 FROM paper_trades WHERE status='OPEN'").fetchall():
                if safe_float(row[1], 0) <= 0 or safe_float(row[2], 0) <= 0 or safe_float(row[3], 0) <= 0:
                    con.execute(
                        "UPDATE paper_trades SET status='CLOSED', exit_price=?, pnl_pct=0, r_multiple=0, closed_at=?, reason=? WHERE id=?",
                        (safe_float(row[1], 0), now, "INVALID_LEVELS", row[0]),
                    )
                    report["paper_invalid"] += 1
            # Forecasts stuck PENDING past horizon+1h → MISS
            for row in con.execute(
                "SELECT id, created_at, horizon_minutes FROM forecasts WHERE outcome='PENDING'"
            ).fetchall():
                end = safe_float(row[1], 0) + int(row[2] or 240) * 60 + 3600
                if now >= end:
                    con.execute(
                        "UPDATE forecasts SET outcome='MISS', evaluated_at=?, hit_type='HEALED_EXPIRE' WHERE id=?",
                        (now, row[0]),
                    )
                    report["forecast_expired"] += 1
            # V32 audit stuck past horizon+2h
            try:
                for row in con.execute(
                    "SELECT id, created_at, horizon_minutes FROM v32_forecast_audit WHERE outcome='PENDING'"
                ).fetchall():
                    end = safe_float(row[1], 0) + int(row[2] or 240) * 60 + 7200
                    if now >= end:
                        con.execute(
                            "UPDATE v32_forecast_audit SET outcome='EXPIRED', evaluated_at=?, return_pct=0 WHERE id=?",
                            (now, row[0]),
                        )
                        report["v32_expired"] += 1
            except Exception:
                pass
            # V22 journal PENDING older than 6h → EXPIRED
            try:
                for row in con.execute(
                    "SELECT id, created_at FROM decision_journal_v22 WHERE outcome='PENDING'"
                ).fetchall():
                    if now - safe_float(row[1], 0) > 6 * 3600:
                        con.execute(
                            "UPDATE decision_journal_v22 SET outcome='EXPIRED' WHERE id=?",
                            (row[0],),