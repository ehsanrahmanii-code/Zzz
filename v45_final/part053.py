
    scorecard = []
    for d in details:
        aligned = decision != "WAIT" and d["side"] == decision
        opposed = decision != "WAIT" and d["side"] in {"LONG", "SHORT"} and d["side"] != decision
        scorecard.append({**d, "aligned": aligned, "opposed": opposed,
                          "preview": "reward" if aligned else "penalty" if opposed else "neutral"})

    meta = {
        "version": TITAN_CENTRAL_VERSION,
        "decision": decision,
        "long_score": round(long_score, 5),
        "short_score": round(short_score, 5),
        "edge": round(edge, 5),
        "margin": round(margin, 5),
        "confidence": round(conf100, 2),
        "trust": round(trust, 2),
        "rr1": round(rr1, 3),
        "reasons": reasons,
        "components": scorecard,
        "weights": {k: round(v, 4) for k, v in weights.items()},
        "entry_quality": round(clamp((edge * 45.0 + margin * 30.0 + trust * 0.25), 0.0, 100.0), 2),
        "directional_bias": round((long_score - short_score) * 100.0, 2),
        "overlap": overlap,
        "authoritative": True,
        "timestamp": time.time(),
    }
    return decision, meta



def _real_edge_engine(item: dict[str, Any], decision: str, meta: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Final real-edge gate: regime + structure + liquidity + MTF + entry + risk.

    This layer is deliberately conservative.  It does not invent probability;
    it can only confirm an existing directional candidate or demote it to WAIT.
    """
    x = item or {}
    d = str(decision or "WAIT").upper()
    price = safe_float(x.get("price_raw"), 0.0)
    atr = safe_float(x.get("atr"), 0.0)
    regime = x.get("regime") if isinstance(x.get("regime"), dict) else {}
    structure = x.get("structure") if isinstance(x.get("structure"), dict) else {}
    liquidity = x.get("liquidity") if isinstance(x.get("liquidity"), dict) else {}
    precision = x.get("precision") if isinstance(x.get("precision"), dict) else {}
    fusion = x.get("fusion") if isinstance(x.get("fusion"), dict) else {}
    tf = x.get("tf_results") if isinstance(x.get("tf_results"), dict) else {}

    reg_name = str(regime.get("regime") or "unknown").lower()
    reg_conf = clamp(safe_float(regime.get("confidence"), 0), 0, 100)
    struct_event = str(structure.get("event") or "UNKNOWN").upper()
    struct_conf = clamp(safe_float(structure.get("confirmation_score"), 0), 0, 100)
    liq_pressure = safe_float(liquidity.get("pressure"), 0)
    liq_bias = str(liquidity.get("liquidity_bias") or "unknown").lower()
    precision_score = clamp(safe_float(precision.get("score"), 50), 0, 100)
    alignment = clamp(safe_float(x.get("alignment"), safe_float(meta.get("alignment"), 50)), 0, 100)

    # 1) True trend/regime compatibility.
    if d == "LONG":
        regime_side_ok = reg_name in {"trend_up", "breakout_watch"} or "up" in reg_name
        structure_ok = struct_event in {"BOS_UP", "BULL_STRUCTURE"}
        flow_ok = liq_pressure >= -0.05
    elif d == "SHORT":
        regime_side_ok = reg_name in {"trend_down", "breakout_watch"} or "down" in reg_name
        structure_ok = struct_event in {"BOS_DOWN", "BEAR_STRUCTURE"}
        flow_ok = liq_pressure <= 0.05
    else:
        regime_side_ok = structure_ok = flow_ok = False

    # 2) Multi-timeframe alignment: use existing per-TF evidence when present.
    tf_sides=[]
    for key,val in tf.items():
        if isinstance(val, dict):
            side=str(val.get("side") or val.get("bias") or "").upper()
            if side in {"LONG","SHORT"}: tf_sides.append(side)
    if tf_sides and d in {"LONG","SHORT"}:
        aligned_n=sum(1 for side in tf_sides if side==d)
        mtf_pct=aligned_n/max(1,len(tf_sides))*100.0
    else:
        mtf_pct=alignment

    # 3) Dynamic entry zone.  Current live price is the anchor; the zone is not
    # a promise of fill, it is a bounded pullback/confirmation area.
    if price > 0 and atr > 0:
        zone_width=max(price*0.0012, atr*0.30)
        if d == "LONG":
            entry_low, entry_high = price-zone_width, price+zone_width*0.20
        elif d == "SHORT":
            entry_low, entry_high = price-zone_width*0.20, price+zone_width
        else:
            entry_low, entry_high = price-zone_width, price+zone_width
    else:
        zone_width=0.0; entry_low=entry_high=price

    overextended = "overextended_entry" in [str(v) for v in (precision.get("hard_blocks") or [])]
    if price > 0 and atr > 0:
        vwap=safe_float(x.get("vwap"), price)
        stretch_atr=abs(price-vwap)/atr if vwap > 0 else 0.0
    else:
        stretch_atr=0.0
    entry_state="OPTIMAL"
    if overextended or stretch_atr > 2.2:
        entry_state="LATE"
    elif stretch_atr > 1.25:
        entry_state="EARLY/EXTENDED"

    # 4) Risk/exit integrity.
    sl=safe_float(x.get("stop_loss_raw"), safe_float(x.get("stop_loss"), 0))
    tp1=safe_float(x.get("tp1_raw"), safe_float(x.get("tp1"), 0))
    tp2=safe_float(x.get("tp2_raw"), safe_float(x.get("tp2"), 0))
    risk_dist=abs(price-sl) if price>0 and sl>0 else 0.0
    rr1=abs(tp1-price)/max(risk_dist,1e-12) if risk_dist else 0.0
    rr2=abs(tp2-price)/max(risk_dist,1e-12) if risk_dist else 0.0
    level_ok=(d=="LONG" and sl<price<tp1<tp2) or (d=="SHORT" and tp2<tp1<price<sl)

    # 5) Correlation/portfolio concentration already maintained by overlap gate;
    # surface its live state rather than hiding it.
    corr=fusion.get("btc_correlation") if isinstance(fusion.get("btc_correlation"),dict) else {}
    corr_blocked=bool(corr.get("blocked") or corr.get("veto"))

    # 6) No-trade intelligence: reasons are explicit and auditable.
    blocks=[]
    if d in {"LONG","SHORT"}:
        if not regime_side_ok: blocks.append("regime_conflict")
        if not structure_ok: blocks.append("structure_not_confirmed")
        if mtf_pct < 55: blocks.append("mtf_alignment_low")
        if struct_conf < 48: blocks.append("structure_confidence_low")
        if reg_conf < 45: blocks.append("regime_confidence_low")
        if not flow_ok: blocks.append("liquidity_flow_conflict")
        if corr_blocked: blocks.append("correlation_risk")
        if overextended or entry_state == "LATE": blocks.append("late_entry")
        if not level_ok: blocks.append("invalid_levels")
        if rr1 < 1.10 or rr2 < 1.40: blocks.append("weak_rr")
        if precision_score < 44: blocks.append("entry_quality_low")

    # 7) Composite quality.  This is a quality score, NOT a win probability.
    regime_component=reg_conf if regime_side_ok else max(0.0, reg_conf-35)
    structure_component=struct_conf if structure_ok else max(0.0, struct_conf-30)
    liquidity_component=50 + liq_pressure*200
    liquidity_component=clamp(liquidity_component if d=="LONG" else 100-liquidity_component,0,100)
    rr_component=clamp(50 + (rr1-1)*20 + (rr2-1.5)*10,0,100)
    real_quality=clamp(
        regime_component*0.20 + structure_component*0.22 + mtf_pct*0.18
        + precision_score*0.18 + liquidity_component*0.10 + rr_component*0.12,
        0,100)
    if d=="WAIT": real_quality=min(real_quality,55)

    # 8) Path simulation is a transparent ATR/level proxy, never labeled as realized.
    expected_mae_r=0.65 if atr>0 else None
    expected_mfe_r=rr2 if rr2>0 else None
    path_quality=clamp((safe_float(expected_mfe_r,0)/max(safe_float(expected_mae_r,1),1e-9))*30,0,100) if expected_mfe_r else 0

    # 9) Conservative final gate. Existing Central Governor remains authoritative;
    # this layer only demotes a candidate when the evidence is materially unsafe.
    final=d
    min_q = 58.0 if d == "SHORT" else 55.0
    if d in {"LONG","SHORT"} and (blocks or real_quality < min_q):
        final="WAIT"
    if final != d and d in {"LONG","SHORT"}:
        blocks.append("REAL_EDGE_FINAL_GATE")

    lifecycle="WAITING_ENTRY" if final in {"LONG","SHORT"} and entry_state!="OPTIMAL" else "READY" if final in {"LONG","SHORT"} else "NO_TRADE"
    return final, {
        "version":"V30-REAL-EDGE",
        "direction":final,
        "candidate_direction":d,
        "regime":reg_name,
        "regime_confidence":round(reg_conf,1),
        "structure_event":struct_event,
        "structure_confidence":round(struct_conf,1),
        "mtf_alignment_pct":round(mtf_pct,1),
        "liquidity_bias":liq_bias,
        "liquidity_pressure":round(liq_pressure,4),
        "entry_quality":round(precision_score,1),
        "entry_zone":{"low":round(entry_low,8),"high":round(entry_high,8),"width":round(zone_width,8)},
        "entry_state":entry_state,
        "rr_tp1":round(rr1,3),"rr_tp2":round(rr2,3),"levels_valid":bool(level_ok),
        "correlation":corr,
        "real_edge_quality":round(real_quality,1),
        "path_quality":round(path_quality,1),
        "expected_mae_r_proxy":expected_mae_r,
        "expected_mfe_r_proxy":round(expected_mfe_r,3) if expected_mfe_r is not None else None,
        "no_trade_reasons":blocks,
        "lifecycle":lifecycle,
        "probability_note":"کیفیت تصمیم است، نه احتمال برد؛ probability فقط از calibration realized استفاده می‌شود.",
        "champion_challenger":"shadow_only_until_OOS_validation",
        "signal_invalidation":"ساختار/رژیم/سطح حدضرر نقض شود یا قیمت خارج از منطق ورود شود.",
    }

def _central_seal(item: dict[str, Any]) -> dict[str, Any]:
    x = dict(item or {})
    # refresh live price if possible
    try:
        sym = str(x.get("symbol") or "")
        with LIVE_LOCK:
            info = LIVE_PRICES.get(_normalize_symbol(sym)) or {}
        live_px = safe_float(info.get("price"), 0.0)
        if live_px > 0:
            x["price_raw"] = live_px
            x["live_price"] = live_px
            x["entry_raw"] = live_px
            x["price"] = smart_format(live_px)
            x["entry_valid"] = smart_format(live_px)
            age = time.time() - safe_float(info.get("ts"), time.time())
            x["live_price_age_sec"] = round(age, 2)
    except Exception:
        pass

    decision, meta = _central_decide(x)
    # V30 Real Edge Engine: final quality/no-trade gate. It never creates a
    # direction from nothing; it only confirms or demotes the Central decision.
    try:
        edge_decision, edge_pack = _real_edge_engine(x, decision, meta)
        if edge_decision != decision:
            meta = dict(meta)
            meta.setdefault("reasons", [])
            meta["reasons"] = list(meta.get("reasons") or []) + [
                "V30 REAL EDGE: " + ", ".join(edge_pack.get("no_trade_reasons") or ["quality_gate"])
            ]
            meta["entry_quality"] = edge_pack.get("real_edge_quality", meta.get("entry_quality", 50))
            meta["real_edge"] = edge_pack
            meta["decision_before_real_edge"] = decision
            decision = edge_decision
        else:
            meta = dict(meta)
            meta["real_edge"] = edge_pack
            meta["entry_quality"] = edge_pack.get("real_edge_quality", meta.get("entry_quality", 50))
    except Exception as _re_exc:
        LOGGER.debug("V30 real edge gate failed: %s", _re_exc)
        meta = dict(meta)
        meta["real_edge"] = {"version":"V30-REAL-EDGE","status":"degraded","error":str(_re_exc)[:180]}
    bias = "صعودی" if decision == "LONG" else "نزولی" if decision == "SHORT" else "خنثی"
    x["decision"] = decision
    x["decision_tag"] = decision
    x["bias"] = bias
    x["entry_mode"] = "EARLY" if decision in {"LONG", "SHORT"} else "WAIT"
    x["signal_tag"] = f"CENTRAL — {decision}"
    x["decision_state"] = f"CENTRAL_{decision}"
    x["authority"] = TITAN_CENTRAL_VERSION
    x["architecture"] = "SINGLE_CENTRAL_GOVERNOR"
    conf = safe_float(meta.get("confidence"), 50.0)
    x["decision_confidence"] = conf
    # This number is a model-confidence proxy, not a calibrated probability
    # of profit.  Keep the legacy fields for dashboard compatibility but expose
    # the distinction explicitly so users do not read 80 as "80% win chance".
    cal_pack = _edge_calibrate_central(conf, str(decision), str(x.get("symbol") or ""))
    x["calibrated_probability"] = cal_pack.get("calibrated")
    x["success_prob"] = conf
    x["success_probability"] = safe_float(cal_pack.get("calibrated"), conf)
    x["success_probability_is_calibrated"] = bool(cal_pack.get("is_calibrated"))
    x["probability_calibration"] = cal_pack
    x["entry_quality"] = safe_float(meta.get("entry_quality"), 50.0)
    x["directional_bias"] = safe_float(meta.get("directional_bias"), 0.0)
    x["edge_lab_version"] = EDGE_LAB_VERSION
    x["central_decision"] = meta
    x["decision_reasons"] = list(meta.get("reasons") or [])
    x["central_reason_fa"] = " · ".join(x["decision_reasons"][:4])
    x["decision_architecture"] = {
        "type": "SINGLE_CENTRAL_GOVERNOR",
        "authoritative_source": TITAN_CENTRAL_VERSION,
        "final_decision": decision,
        "legacy_engines_are_evidence_only": True,
    }
    for key in ("canonical_decision", "v32_decision", "v31_decision", "arbiter_verdict"):
        prev = x.get(key)
        if isinstance(prev, dict):
            prev = dict(prev)
            prev["decision"] = decision
            prev["overridden_by"] = TITAN_CENTRAL_VERSION
            x[key] = prev
    return x


def _central_record_prediction(item: dict[str, Any]) -> None:
    """Persist only independent directional observations.

    A scan can run every ~45s, but the same setup must not become dozens of
    pseudo-samples.  WAIT is kept in the arbiter log for auditability, while
    only LONG/SHORT observations enter the learning dataset with a cooldown.
    """
    try:
        meta = item.get("central_decision") or {}
        decision = str(item.get("decision_tag") or "WAIT").upper()
        symbol = _normalize_symbol(item.get("symbol") or "")
        now = time.time()

        with DB_LOCK, db_conn() as con:
            # V45: one arbiter row per symbol/decision per 30s (scan + live refresh used to double-write).
            _v45_dup = con.execute(
                "SELECT 1 FROM central_arbiter_log WHERE symbol=? AND decision=? AND created_at>? LIMIT 1",
                (symbol, decision, now - 30)).fetchone()
            if not _v45_dup:
                con.execute(
                    """INSERT INTO central_arbiter_log(created_at,symbol,decision,verdict,score,notes)
                       VALUES(?,?,?,?,?,?)""",
                    (
                        now, symbol, decision,
                        "ACCEPT" if decision in {"LONG", "SHORT"} else "WAIT",
                        safe_float(meta.get("confidence"), 0.0),
                        " · ".join((meta.get("reasons") or [])[:4]),