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