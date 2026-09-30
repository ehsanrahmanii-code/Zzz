        )
        forecast = item.get("candle_forecast") or {}
        pattern = item.get("patterns") or {}
        ai = edge.get("ai") or {}
        dq = item.get("data_quality") or {}
        ladder = item.get("entry_ladder") or {}

        evidence = []

        def add(
            name: str,
            edge_value: float,
            weight: float,
            quality: float = 1.0,
            note: str = "",
        ):
            evidence.append({
                "name": name,
                "edge": clamp(edge_value, -1, 1),
                "weight": max(0.0, weight),
                "quality": clamp(quality, 0, 1),
                "note": note,
            })

        # 1) Multi-timeframe spine
        add(
            "multi_tf",
            tf_long - tf_short,
            0.22,
            tf_meta["coherence"],
            f"coherence={tf_meta['coherence']:.2f}",
        )

        # 2) Market structure
        sb = str(structure.get("bias") or "")
        sc = clamp(
            safe_float(structure.get("confirmation_score"), 50),
            0, 100,
        )
        structure_edge = 0.0
        if sb == "صعودی":
            structure_edge = (sc - 50) / 50
        elif sb == "نزولی":
            structure_edge = -(sc - 50) / 50
        add("structure", structure_edge, 0.13, sc / 100.0, sb or "neutral")

        # 3) Regime
        rn = str(regime.get("regime") or "").lower()
        reg_edge = 0.0
        if "up" in rn or "bull" in rn:
            reg_edge = 0.45
        elif "down" in rn or "bear" in rn:
            reg_edge = -0.45
        add(
            "regime",
            reg_edge,
            0.08,
            0.85 if reg_edge else 0.45,
            rn or "unknown",
        )

        # 4) Confluence
        cs = clamp(safe_float(confluence.get("score"), 50), 0, 100)
        qbias = str(item.get("bias") or "")
        confluence_edge = 0.0
        if qbias == "صعودی":
            confluence_edge = (cs - 50) / 50
        elif qbias == "نزولی":
            confluence_edge = -(cs - 50) / 50
        add(
            "confluence",
            confluence_edge,
            0.12,
            cs / 100.0,
            f"score={cs:.1f}",
        )

        # 5) Entry precision
        ps = clamp(safe_float(precision.get("score"), 50), 0, 100)
        pside = 1 if qbias == "صعودی" else -1 if qbias == "نزولی" else 0
        add(
            "precision",
            pside * (ps - 50) / 50,
            0.10,
            ps / 100.0,
            str(precision.get("entry_timing") or ""),
        )

        # 6) Probabilistic forecast path
        fb = str(forecast.get("overall_bias") or "")
        fstrength = clamp(
            safe_float(forecast.get("path_strength"), 0) / 40.0,
            0, 1,
        )
        add(
            "forecast",
            fstrength if fb == "صعودی" else -fstrength if fb == "نزولی" else 0,
            0.09,
            1.0 if forecast.get("ok") else 0.0,
            f"corr={safe_float(forecast.get('analogue_corr'), 0):.2f}",
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
