        )

        # 7) Chart pattern
        primary = pattern.get("primary") or {}
        pb = str((primary.get("guide") or {}).get("bias") or "")
        pc = clamp(
            safe_float(primary.get("confidence"), 0) / 100.0,
            0, 1,
        )
        add(
            "pattern",
            pc if pb == "صعودی" else -pc if pb == "نزولی" else 0,
            0.06,
            pc,
            pb or "neutral",
        )

        # 8) Existing neural V9
        nside = str(neural.get("side") or "WAIT")
        nconf = clamp(
            safe_float(neural.get("confidence"), 0) / 100.0,
            0, 1,
        )
        add(
            "neural_v9",
            nconf if nside == "LONG" else -nconf if nside == "SHORT" else 0,
            0.12,
            nconf,
            f"confidence={nconf * 100:.1f}",
        )

        # 9) AI ensemble
        amaj = str(
            ai.get("majority")
            or ai.get("ai_majority")
            or item.get("ai_majority")
            or "WAIT"
        )
        aagree = clamp(
            safe_float(
                ai.get(
                    "majority_agreement",
                    ai.get(
                        "agreement",
                        (item.get("fusion") or {}).get(
                            "ai_agreement", 0
                        ),
                    ),
                ),
                0,
            ) / 100.0,
            0, 1,
        )
        add(
            "ai_ensemble",
            aagree if amaj == "LONG" else -aagree if amaj == "SHORT" else 0,
            0.10,
            aagree,
            f"majority={amaj}",
        )

        # 10) Historical memory
        long_h = self._history(symbol, "صعودی")
        short_h = self._history(symbol, "نزولی")
        hist_edge = (
            (long_h["recent_wr"] - short_h["recent_wr"]) / 50.0
        ) * 0.5
        hist_quality = min(
            1.0,
            (long_h["samples"] + short_h["samples"]) / 30.0,
        )
        add(
            "historical_memory",
            hist_edge,
            0.08,
            hist_quality,
            f"L={long_h['recent_wr']:.1f}%/{long_h['samples']} "
            f"S={short_h['recent_wr']:.1f}%/{short_h['samples']}",
        )

        total_w = sum(
            x["weight"] * max(0.05, x["quality"])
            for x in evidence
        )
        net = (
            sum(
                x["edge"] * x["weight"] * max(0.05, x["quality"])
                for x in evidence
            ) / max(total_w, 1e-9)
        )
        strength = abs(net)
        side = (
            "LONG"
            if net >= CNS_PROMOTE_MIN_MARGIN
            else "SHORT"
            if net <= -CNS_PROMOTE_MIN_MARGIN
            else "WAIT"
        )

        vetoes = []
        dq_score = safe_float(dq.get("score"), 100)

        if dq.get("hard_veto"):
            vetoes.append("data_quality")
        elif dq_score < MIN_DATA_QUALITY_SCORE:
            vetoes.append("data_quality_soft")

        if precision.get("hard_blocks"):
            # Only invalid blocks are hard; others soft
            hard_p = [x for x in precision.get("hard_blocks")[:4] if x == "invalid_price_or_atr"]
            soft_p = [x for x in precision.get("hard_blocks")[:4] if x != "invalid_price_or_atr"]
            if hard_p:
                vetoes.extend([f"precision:{x}" for x in hard_p])
            if soft_p:
                vetoes.extend([f"precision_soft:{x}" for x in soft_p])

        if safe_float(item.get("effective_rr_tp1"), 0) < CNS_MIN_RR:
            # Soft RR below floor — does not block promote alone when other edges strong
            if safe_float(item.get("effective_rr_tp1"), 0) < 0.85:
                vetoes.append("rr")
            else:
                vetoes.append("rr_soft")

        if (
            ladder
            and side in {"LONG", "SHORT"}
            and not ladder.get("passed", True)
        ):
            # Soft ladder unless HTF is strongly opposite
            htf_s = safe_float(ladder.get("htf_score"), 50)
            if (side == "LONG" and htf_s <= 36) or (side == "SHORT" and htf_s >= 64):
                vetoes.append("entry_ladder")
            else:
                vetoes.append("entry_ladder_soft")

        if (
            amaj in {"LONG", "SHORT"}
            and side in {"LONG", "SHORT"}
            and amaj != side
            and aagree >= CNS_HARD_CONFLICT
        ):
            vetoes.append("ai_hard_conflict")

        chosen_hist = (
            long_h if side == "LONG" else short_h
        )
        hist_penalty = (
            chosen_hist["samples"] >= CNS_MIN_HISTORY
            and chosen_hist["recent_wr"] < 42
        )
        if hist_penalty:
            vetoes.append("weak_historical_side")

        # Promotion from WAIT requires independent evidence, not one large score.
        # Soft vetoes (suffix _soft) do not block promotion.
        quality = safe_float(item.get("signal_quality"), 0)
        hard_veto_names = {
            v for v in vetoes
            if not str(v).endswith("_soft") and "soft:" not in str(v)
        }
        promote = (
            side in {"LONG", "SHORT"}
            and strength >= CNS_PROMOTE_MIN_STRENGTH
            and abs(net) >= CNS_PROMOTE_MIN_MARGIN
            and quality >= CNS_PROMOTE_MIN_QUALITY
            and dq_score >= CNS_PROMOTE_MIN_DQ
            and nconf * 100 >= CNS_PROMOTE_MIN_NEURAL
            and safe_float(item.get("effective_rr_tp1"), 0) >= CNS_PROMOTE_MIN_RR
            and tf_meta["coherence"] >= 0.50
            and not hard_veto_names
            and not hist_penalty
        )

        existing = str(item.get("decision_tag") or "WAIT")
        opposite = (
            "SHORT"
            if existing == "LONG"
            else "LONG"
            if existing == "SHORT"
            else ""
        )

        strong_contradiction = (
            existing in {"LONG", "SHORT"}
            and side == opposite
            and strength >= 0.72
            and abs(net) >= 0.28
        )

        # Evidence-strength index; this is NOT a guaranteed win probability.
        confidence = clamp(
            50
            + strength * 45
            + tf_meta["coherence"] * 10
            - len(vetoes) * 8,
            5, 95,
        )
        if chosen_hist["samples"] < CNS_MIN_HISTORY:
            confidence = min(confidence, 82)

        action = "WAIT"
        reason = "شواهد مستقل برای تصمیم جهتی کافی نیست"

        if strong_contradiction:
            reason = "شبکه شواهد مستقل خلاف تصمیم قبلی است"
        elif existing in {"LONG", "SHORT"}:
            action = existing
            reason = "تصمیم موجود توسط شبکه شواهد مستقل بررسی و تأیید شد"
        elif promote:
            action = side
            reason = "فرصت مرزی با اجماع چندلایه و کیفیت داده کافی ارتقا یافت"

        entry_mode = "WAIT"
        if action in {"LONG", "SHORT"}:
            timing = str(precision.get("entry_timing") or "").upper()
            if (
                bool(ladder.get("passed", False))
                and timing in {"READY", "TRIGGER", "OPTIMAL", "GOOD"}
            ):
                entry_mode = "READY"
            else:
                entry_mode = "EARLY"

        return {
            "version": CNS_VERSION,
            "action": action,
            "side": side,
            "entry_mode": entry_mode,
            "net_score": round(net, 4),
            "directional_strength": round(strength, 3),
            "confidence": round(confidence, 1),
            "promoted": bool(promote and existing == "WAIT"),
            "contradiction": bool(strong_contradiction),
            "vetoes": vetoes,
            "reason": reason,
            "tf_coherence": tf_meta["coherence"],
            "tf": tf_meta["frames"],
            "historical": {"long": long_h, "short": short_h},
            "ai_reliability": (
                self._ai_reliability(symbol, amaj)
                if amaj in {"LONG", "SHORT"}
                else {"samples": 0, "aligned": 0, "alignment_pct": 50.0, "providers": {}, "mode": "neutral"}
            ),
            "evidence": evidence,
            "independent_layers": len(
                [e for e in evidence if e["quality"] >= 0.55]
            ),
        }


TITAN_CNS = TitanCognitiveNexusV10()

# Preserve the original V10 analyzer as the audited core. The wrapper is the
# final arbitration layer used by update_cache, so the existing dashboard/API
# contract remains backward compatible.
_analyze_asset_core = analyze_asset


def _v12_parse_price(value: Any) -> float:
    """Parse dashboard-formatted prices without assuming a fixed decimal format."""
    try:
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value or "").replace(",", "").replace(" ", "")
        return float(s)
    except Exception:
        return 0.0


def _v12_rebuild_directional_levels(item: dict[str, Any], direction: str) -> tuple[float, float, float]:
    """Rebuild directional SL/TP when the final arbitration changes a neutral side.

    The core analyzer normally has full ATR/structure context. If a final CNS
    promotion changes WAIT -> LONG/SHORT, this guard reconstructs a conservative
    directional set from the already-computed neutral risk distance instead of
    leaving a bullish signal with bullish TP but a neutral/inconsistent SL.
    """
    price = _v12_parse_price(item.get("price"))
    old_sl = _v12_parse_price(item.get("stop_loss"))
    if price <= 0:
        return 0.0, 0.0, 0.0

    # A neutral core uses approximately 1.6 ATR plus friction. Recover a safe
    # ATR estimate from that distance, with a volatility-based floor.
    neutral_dist = abs(price - old_sl)
    vol_pct = safe_float(item.get("volatility_pct"), 0.0)
    atr_est = max(
        neutral_dist / 1.6 if neutral_dist > 0 else 0.0,
        price * max(vol_pct / 100.0, 0.0025),
        price * 0.0005,
    )

    # Use a conservative local swing proxy. This is deliberately derived from
    # existing validated price/risk data; it never invents a market level.
    swing_low = price - 2.0 * atr_est
    swing_high = price + 2.0 * atr_est

    titan = item.get("titan_analysis") or {}
    adv = titan.get("adv_layers") or {}
    # These values are optional; missing values are allowed.
    vwap = safe_float(adv.get("vwap"), 0.0)
    if direction == "LONG":
        bias = "صعودی"
    elif direction == "SHORT":
        bias = "نزولی"
    else:
        return 0.0, 0.0, 0.0

    sl, tp1, tp2 = calculate_levels(
        price=price,
        atr=atr_est,
        swing_low=swing_low,
        swing_high=swing_high,
        bias=bias,
        vwap=vwap,
        ema20=0.0,
        ema50=0.0,
        structure=(item.get("edge") or {}).get("structure") or {},
        confluence=safe_float((item.get("edge") or {}).get("confluence", {}).get("score"), 50.0),
        order_blocks_fvg=None,
        fibonacci=None,
        forecast=item.get("candle_forecast") or {},
    )
    return float(sl), float(tp1), float(tp2)


def _v12_level_integrity(price: float, sl: float, tp1: float, tp2: float, direction: str) -> dict[str, Any]:
    """Hard validation of direction/levels/RR before a directional signal is exposed."""
    if not all(math.isfinite(x) for x in (price, sl, tp1, tp2)) or price <= 0:
        return {"ok": False, "reason": "invalid_numeric_levels", "rr1": 0.0, "rr2": 0.0}

    risk = abs(price - sl)
    if risk <= price * 0.0002:
        return {"ok": False, "reason": "risk_distance_too_small", "rr1": 0.0, "rr2": 0.0}

    if direction == "LONG":
        orientation = sl < price < tp1 <= tp2
    elif direction == "SHORT":
        orientation = tp2 <= tp1 < price < sl
    else:
        orientation = False

    rr1 = abs(tp1 - price) / risk
    rr2 = abs(tp2 - price) / risk
    ok = bool(orientation and rr1 >= MIN_EFFECTIVE_RR and rr2 >= rr1)
    return {
        "ok": ok,
        "reason": "ok" if ok else ("bad_orientation" if not orientation else "rr_below_threshold"),
        "rr1": round(rr1, 3),
        "rr2": round(rr2, 3),
    }


def _v12_persist_ai_votes(symbol: str, item: dict[str, Any]) -> None:
    """Persist provider votes without creating scan-by-scan duplicate spam."""
    try:
        ai_obj = item.get("ai_opinions") or {}
        titan_side = str(item.get("decision_tag") or "WAIT")
        now = time.time()

        with DB_LOCK, db_conn() as con:
            for provider, raw in ai_obj.items():
                if (
                    provider in {"providers", "ai_status", "internal", "titan"}
                    or not isinstance(raw, str)
                    or not raw.strip()
                ):
                    continue

                vote = extract_structured_ai_vote(raw).get("side", "WAIT")
                recent = con.execute(
                    "SELECT 1 FROM ai_votes "
                    "WHERE symbol=? AND provider=? AND direction=? AND titan_direction=? "
                    "AND created_at>? LIMIT 1",
                    (symbol, provider, vote, titan_side, now - 90.0),
                ).fetchone()
                if recent:
                    continue

                con.execute(
                    "INSERT INTO ai_votes("
                    "created_at,symbol,provider,direction,titan_direction,aligned,latency_ms"
                    ") VALUES(?,?,?,?,?,?,?)",
                    (
                        now,
                        symbol,
                        provider,
                        vote,
                        titan_side,
                        int(vote == titan_side),
                        None,
                    ),
                )
    except Exception as exc:
        LOGGER.debug("V12 AI vote persistence failed %s: %s", symbol, exc)


def _v12_finalize_signal(item: dict[str, Any], cns: dict[str, Any]) -> None:
    """Apply CNS action only when the final public signal remains internally coherent."""
    current = str(item.get("decision_tag") or "WAIT")
    action = str(cns.get("action") or "WAIT")
    fusion = item.setdefault("fusion", {})
    integrity = {
        "version": "V12-CNS-PRO-MAX",
        "core_decision": current,
        "cns_proposal": action,
        "applied": False,
        "level_rebuilt": False,
        "reason": "",
    }

    if action in {"LONG", "SHORT"} and action != current:
        # If CNS proposes a new direction, rebuild levels first.
        sl, tp1, tp2 = _v12_rebuild_directional_levels(item, action)
        price = _v12_parse_price(item.get("price"))
        check = _v12_level_integrity(price, sl, tp1, tp2, action)

        if check["ok"]:
            item["stop_loss"] = smart_format(sl)
            item["tp1"] = smart_format(tp1)
            item["tp2"] = smart_format(tp2)
            item["effective_rr_tp1"] = check["rr1"]
            item["effective_rr_tp2"] = check["rr2"]
            item["rr_tp1"] = check["rr1"]
            item["rr_tp2"] = check["rr2"]
            item["decision_tag"] = action
            item["bias"] = "صعودی" if action == "LONG" else "نزولی"
            item["signal_tag"] = "CNS OPPORTUNITY" if cns.get("promoted") else "CNS CONFIRMED"
            fusion["cns_override"] = True
            fusion["cns_override_reason"] = cns.get("reason")
            integrity.update(applied=True, level_rebuilt=True, reason="directional_levels_rebuilt_and_validated")
        else:
            # Never expose a direction with stale/inconsistent levels.
            integrity["reason"] = f"CNS proposal rejected by level integrity: {check['reason']}"
            fusion["cns_override"] = False
            fusion["cns_override_reason"] = integrity["reason"]

    elif action == "WAIT" and current in {"LONG", "SHORT"}:
        # A strong independent contradiction is materially different from a
        # neutral/soft disagreement. Never keep a directional signal when the
        # evidence graph itself has a high-strength opposite side.
        severe = [v for v in (cns.get("vetoes") or []) if str(v) in {"data_quality", "ai_hard_conflict"}]
        contradiction = bool(cns.get("contradiction"))
        strength = safe_float(cns.get("directional_strength"), 0)
        if contradiction or (severe and strength < 0.35):
            item["decision_tag"] = "WAIT"
            item["bias"] = "خنثی"
            item["signal_tag"] = "CNS BLOCK"
            fusion["cns_override"] = True
            fusion["cns_override_reason"] = cns.get("reason") or "strong independent contradiction"
            integrity.update(applied=True, reason="independent_evidence_blocked_core_direction")
        else:
            fusion["cns_soft_block"] = True
            fusion["cns_override_reason"] = cns.get("reason")
            integrity.update(applied=False, reason="cns_soft_block_direction_kept")

    else:
        integrity["reason"] = "core_and_cns_decision_consistent"

    # Rebuild the canonical object after the final action, not before it.
    item["decision_integrity"] = integrity
    item["canonical_decision"] = {
        "decision": item.get("decision_tag", "WAIT"),
        "bias": item.get("bias", "خنثی"),
        "confidence": cns.get("confidence", 0),
        "signal_quality": item.get("signal_quality", 0),
        "success_probability": item.get("success_probability", 50),
        "cns_version": CNS_VERSION,
        "reason": cns.get("reason", ""),
        "entry_mode": cns.get("entry_mode", "WAIT"),
        "level_integrity": integrity["reason"],
    }


def analyze_asset(symbol: str, btc_trend: str) -> Optional[dict[str, Any]]:
    """V12 CNS PRO MAX public analyzer.

    The V10/V11 core remains the data/indicator/forecast engine. This final
    layer performs evidence arbitration, decision integrity, and learning-memory
    hygiene so no final LONG/SHORT can be emitted with contradictory levels.
    """
    item = _analyze_asset_core(symbol, btc_trend)
    if not item:
        return None

    try:
        cns = TITAN_CNS.evaluate(item)
        item["cognitive_nexus"] = cns
        item.setdefault("fusion", {})["cognitive_nexus"] = cns
        item["cns_action"] = cns.get("action", "WAIT")
        item["cns_confidence"] = cns.get("confidence", 0)
        item["cns_strength"] = cns.get("directional_strength", 0)
        item["entry_mode"] = cns.get("entry_mode", "WAIT")

        _v12_finalize_signal(item, cns)

        # If a promoted signal changed direction, cap displayed confidence until
        # its first live outcome exists. This avoids presenting a fresh promotion
        # as if it were historically proven.
        if cns.get("promoted") and item.get("decision_tag") in {"LONG", "SHORT"}: