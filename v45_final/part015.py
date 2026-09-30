            lp2 = LIVE_PRICES.get(_normalize_symbol(symbol)) or {}
            if lp2.get("ts"):
                live_age_sec = time.time() - safe_float(lp2.get("ts"), 0)
        # Perf: compute each series once; defer heavy forecast until structure/regime exist
        close_1h = df1h["close"]
        rsi_series_1h = wilder_rsi(close_1h)
        rsi = float(rsi_series_1h.iloc[-1])
        atr = float(calc_atr(df1h).iloc[-1])
        vwap = calc_vwap(df15)
        ema20_s = close_1h.ewm(span=20, adjust=False).mean()
        ema50_s = close_1h.ewm(span=50, adjust=False).mean()
        ema20 = float(ema20_s.iloc[-1])
        ema50 = float(ema50_s.iloc[-1])
        vol15 = df15["vol"]
        if len(vol15) > 1:
            vol_mean = float(vol15.iloc[:-1].ewm(span=20, adjust=False).mean().iloc[-1])
        else:
            vol_mean = float(vol15.mean()) if len(vol15) else 0.0
        cur_vol = float(vol15.iloc[-1]) if len(vol15) else 0.0
        volume_spike = cur_vol > vol_mean * 1.20 if vol_mean > 0 else False
        derivatives = derivatives_box.get("d") or fetch_derivatives(symbol)
        macd_info = calc_macd(close_1h)
        stoch_info = calc_stoch_rsi(close_1h)
        pivots = calc_pivot_points(df1h)
        vol_delta = calc_volume_delta(df15, 24)
        session_info = market_session_utc()
        pattern_pack = detect_chart_patterns(df1h, rsi_series_1h)
        # Placeholder; full forecast runs once after structure/regime (avoids 2x path cost)
        candle_forecast = {"ok": False, "candles": [], "horizon": 12}
        structure_zones = detect_order_blocks_fvg(df1h)
        depth_snap = get_depth_snapshot(symbol)
        # Soft score nudges from advanced layers (symmetric, no long bias)
        adv_nudge = 0.0
        if macd_info.get("cross") == "bull":
            adv_nudge += 3.0
        elif macd_info.get("cross") == "bear":
            adv_nudge -= 3.0
        if macd_info.get("hist", 0) > 0:
            adv_nudge += 1.5
        elif macd_info.get("hist", 0) < 0:
            adv_nudge -= 1.5
        if stoch_info.get("zone") == "oversold":
            adv_nudge += 2.5
        elif stoch_info.get("zone") == "overbought":
            adv_nudge -= 2.5
        if vol_delta.get("delta_pct", 0) > 12:
            adv_nudge += 2.0
        elif vol_delta.get("delta_pct", 0) < -12:
            adv_nudge -= 2.0
        ls_ratio = safe_float((derivatives.get("long_short") or {}).get("long_short_ratio"), 1.0)
        if ls_ratio >= 1.6:
            adv_nudge -= 2.5  # crowded long -> mild short pressure
        elif ls_ratio <= 0.65:
            adv_nudge += 2.5  # crowded short -> mild long pressure
        taker_buy = safe_float(derivatives.get("taker_buy_pct"), 50)
        if taker_buy >= 58:
            adv_nudge += 1.5
        elif taker_buy <= 42:
            adv_nudge -= 1.5
        adv_nudge += safe_float(pattern_pack.get("score_bias"), 0)
        # Align quant score with probabilistic candle path (12-step)
        fc_bias = str((candle_forecast or {}).get("overall_bias") or "")
        fc_str = safe_float((candle_forecast or {}).get("path_strength"), 0)
        if fc_bias == "صعودی":
            adv_nudge += min(4.0, 1.2 + fc_str * 0.06)
        elif fc_bias == "نزولی":
            adv_nudge -= min(4.0, 1.2 + fc_str * 0.06)
        adv_nudge *= float(session_info.get("liquidity_boost", 1.0))
        adv_nudge = float(clamp(adv_nudge, -10.0, 10.0))

        tf_results: dict[str, str] = {}
        tf_scores: dict[str, float] = {}
        for tf, df in frames.items():
            direction, score, _ = _tf_forecast(df)
            tf_results[tf] = "🟢 صعودی" if direction == "صعودی" else "🔴 نزولی" if direction == "نزولی" else "⚖️ خنثی"
            tf_scores[tf] = score
        base_score = float(np.average([tf_scores[t] for t in TF_CFG], weights=[TF_CFG[t]["weight"] for t in TF_CFG]))
        btc_adjust = 5.0 if symbol != "BTC/USDT" and btc_trend == "صعودی" else -5.0 if symbol != "BTC/USDT" and btc_trend == "نزولی" else 0.0
        provisional = clamp(base_score + btc_adjust, 0, 100)

        titan = build_titan_analysis(symbol=symbol, price=price, rsi=rsi, vwap=vwap, ema20=ema20, ema50=ema50,
                                     atr=atr, volume_spike=volume_spike, btc_trend=btc_trend, derivatives=derivatives,
                                     tf_results=tf_results, tf_scores=tf_scores)
        # Apply advanced technical / positioning nudge before structure refine
        score_n = int(round(clamp(safe_float(titan.get("score"), 50) + adv_nudge, 0, 100)))
        titan["score"] = score_n
        if score_n >= 58:
            titan["bias"] = "صعودی"
        elif score_n <= 42:
            titan["bias"] = "نزولی"
        else:
            titan["bias"] = "خنثی"
        bias, score_int, alignment = titan["bias"], titan["score"], titan["alignment"]
        titan["adv_layers"] = {
            "macd": macd_info, "stoch_rsi": stoch_info, "pivots": pivots,
            "volume_delta": vol_delta, "session": session_info, "nudge": round(adv_nudge, 2),
            "long_short_ratio": ls_ratio, "taker_buy_pct": taker_buy,
        }
        swing_low = float(df1h["low"].tail(12).min())
        swing_high = float(df1h["high"].tail(12).max())
        tech = technical_layers(df1h)
        fib = tech.get("fibonacci") or {}
        sr = tech.get("support_resistance") or {}
        bb = tech.get("bollinger") or {}

        # TITAN PROFESSIONAL EDGE SUITE: structure/regime first so levels & bias use them.
        structure = TITAN_EDGE_SUITE.market_structure(df1h)
        regime = TITAN_EDGE_SUITE.regime_detection(df1h, atr=atr, score=score_int)
        # Re-forecast with structure/regime context so path ↔ structure stay aligned
        try:
            candle_forecast = forecast_future_candles(
                df1h, horizon=12, patterns=pattern_pack,
                macd=macd_info, stoch=stoch_info,
                structure=structure, regime=regime,
            )
        except Exception:
            pass
        liquidity = TITAN_EDGE_SUITE.liquidity_map(df15, price)
        confluence = TITAN_EDGE_SUITE.signal_confluence(
            score=score_int, alignment=alignment, rsi=rsi, price=price, vwap=vwap,
            ema20=ema20, ema50=ema50, volume_spike=volume_spike, derivatives=derivatives,
            structure=structure, regime=regime.get("regime", "unknown"))
        precision_pre = _precision_engine_snapshot(
            df15, df1h, price, atr, rsi, vwap, ema20, ema50, bias, volume_spike,
            structure, regime, derivatives)
        hist_wr = TITAN_EDGE_SUITE.historical_win_rate_for_item({"bias": bias})
        preliminary_quality = int(round(clamp(
            0.35 * alignment
            + 0.30 * confluence["score"]
            + 0.20 * abs(score_int - 50) * 2
            + 0.10 * (80 if volume_spike else 40)
            + 0.05 * safe_float(structure.get("confirmation_score"), 50)
            + 0.10 * safe_float(precision_pre.get("score"), 50),
            0, 100)))
        meta = TITAN_EDGE_SUITE.meta_label(confluence["score"], preliminary_quality, hist_wr)

        # Multi-layer directional refine (LONG / SHORT / WAIT)
        bias, decision_tag = refine_bias_with_edge(
            bias, score_int, alignment, structure, regime, confluence, meta)
        titan["bias"] = bias

        # Early AI lean (status-only providers skipped later); soft confirmation only
        # Full AI text is generated after levels — ensemble still runs post-AI.

        sl, tp1, tp2 = calculate_levels(
            price, atr, swing_low, swing_high, bias,
            vwap=vwap, ema20=ema20, ema50=ema50,
            structure=structure, confluence=safe_float(confluence.get("score"), 50),
            order_blocks_fvg=structure_zones, fibonacci=fib, forecast=candle_forecast,
        )
        ai = generate_ai_opinions(symbol, price, rsi, vwap, ema20, ema50, atr, volume_spike, btc_trend, derivatives, tf_results, titan)
        _record_data_quality(symbol, frames, derivatives)

        # Adaptive fusion: quant + structure + regime + confluence + AI + history
        ai_pre = TITAN_EDGE_SUITE.ai_ensemble(ai, bias)
        fusion = TITAN_ADAPTIVE.fuse_decision(
            symbol=symbol,
            quant_bias=bias,
            score=float(score_int),
            alignment=float(alignment),
            structure=structure,
            regime=regime,
            confluence=confluence,
            meta=meta,
            ai_ensemble=ai_pre,
            forecast=candle_forecast,
            patterns=pattern_pack,
        )
        prev_bias, prev_tag = bias, decision_tag
        bias = fusion.get("bias", bias)
        decision_tag = fusion.get("decision", decision_tag)
        # Recompute precision for the final fused direction; never let AI alone bypass a poor entry.
        precision = _precision_engine_snapshot(
            df15, df1h, price, atr, rsi, vwap, ema20, ema50, bias, volume_spike,
            structure, regime, derivatives)
        pscore = safe_float(precision.get("score"), 50)
        if decision_tag in {"LONG", "SHORT"}:
            # Only invalid price/ATR hard-kills. Soft precision only tags risk.
            severe_blocks = [x for x in (precision.get("hard_blocks") or []) if x in {"invalid_price_or_atr"}]
            if severe_blocks:
                decision_tag, bias = "WAIT", "خنثی"
                fusion["precision_veto"] = True
                fusion["precision_reason"] = severe_blocks
            elif pscore < 40 or "overextended_entry" in (precision.get("hard_blocks") or []):
                fusion["precision_soft"] = True
                fusion["precision_reason"] = [f"precision_soft={pscore:.0f}"]

        # --- V8 Data Quality hard gate ---
        dq = assess_data_quality(
            symbol=symbol, price=price, live_age_sec=live_age_sec,
            df15=df15, df1h=df1h, derivatives=derivatives, frames=frames,
        )
        fusion["data_quality"] = dq
        if dq.get("hard_veto") and decision_tag in {"LONG", "SHORT"}:
            decision_tag, bias = "WAIT", "خنثی"
            fusion["dq_veto"] = True
            fusion.setdefault("explanation", []).append(
                f"وتوی کیفیت داده ({dq.get('score')}) · {', '.join((dq.get('reasons') or [])[:3])}"
            )

        # --- V8 Entry Ladder (4h/1d → 1h → 15m) ---
        # V28.4: ladder is advisory quality penalty, not a hard WAIT kill-switch.
        ladder = entry_ladder_gate(tf_scores, tf_results, decision_tag, bias)
        fusion["entry_ladder"] = ladder
        if decision_tag in {"LONG", "SHORT"} and not ladder.get("passed", True):
            fusion["ladder_soft"] = True
            fusion.setdefault("explanation", []).append(
                "نردبان ورود ناقص (نرم): " + ", ".join((ladder.get("reasons") or [])[:4])
            )

        # --- V8 Forecast path weight from tracked accuracy ---
        fc_stats = forecast_path_accuracy_stats(symbol)
        fusion["forecast_accuracy"] = fc_stats
        if decision_tag in {"LONG", "SHORT"} and candle_forecast.get("ok"):
            fc_side = candle_forecast.get("overall_bias")
            aligned = (decision_tag == "LONG" and fc_side == "صعودی") or (decision_tag == "SHORT" and fc_side == "نزولی")
            if not aligned and safe_float(fc_stats.get("weight_scale"), 0) >= 0.7 and safe_float(fc_stats.get("samples"), 0) >= 12:
                # Trusted path disagrees → soft demote to WAIT if other edges weak
                if safe_float(fusion.get("fused_score"), 0) < 0.28 and pscore < 60:
                    decision_tag, bias = "WAIT", "خنثی"
                    fusion["forecast_veto"] = True
                    fusion.setdefault("explanation", []).append("مسیر ۱۲ کندلی معتبر خلاف جهت ستاپ ضعیف")

        # --- V8 Portfolio crowding (soft: penalty only, do not erase real edges) ---
        port = portfolio_side_pressure(decision_tag, symbol)
        fusion["portfolio"] = port
        if decision_tag in {"LONG", "SHORT"} and not port.get("ok", True):
            fusion["portfolio_soft"] = True
            fusion.setdefault("explanation", []).append((port.get("reason") or "فشار سبد") + " · فقط هشدار")
            if isinstance(fusion.get("success_probability"), (int, float)):
                fusion["success_probability"] = float(clamp(
                    safe_float(fusion.get("success_probability"), 50) - 8, 5, 88
                ))
        elif port.get("penalty", 0) and isinstance(fusion.get("success_probability"), (int, float)):
            fusion["success_probability"] = float(clamp(
                safe_float(fusion.get("success_probability"), 50) - port["penalty"] * 0.35, 5, 88
            ))

        # BTC correlation filter for alts in high-vol
        atr_pct_now = (atr / price * 100) if price > 0 else 0.0
        try:
            corr_info = compute_btc_correlation(symbol)
            decision_tag, bias, corr_note = apply_btc_correlation_filter(
                symbol, decision_tag, bias, atr_pct_now, btc_trend, corr_info)
            fusion["btc_correlation"] = corr_note
        except Exception as _corr_exc:
            LOGGER.debug("corr filter skip: %s", _corr_exc)
            corr_note = {}
        # Order blocks / FVG + depth already computed once above (perf: no double work)
        if not structure_zones:
            try:
                structure_zones = detect_order_blocks_fvg(df1h)
            except Exception:
                structure_zones = {"order_blocks": [], "fvgs": [], "nearest_ob": None, "nearest_fvg": None}
        if not depth_snap:
            depth_snap = get_depth_snapshot(symbol)
        titan["bias"] = bias
        titan["fusion"] = {
            "fused_score": fusion.get("fused_score"),
            "success_probability": fusion.get("success_probability"),
            "explanation": fusion.get("explanation"),
            "ai_majority": fusion.get("ai_majority"),
            "weights": fusion.get("weights"),
            "reliability": fusion.get("reliability"),
            "thresholds": fusion.get("thresholds"),
            "prior_quant": prev_bias,
            "prior_tag": prev_tag,
        }
        # Recalculate levels if direction changed after fusion
        if bias != prev_bias or decision_tag != prev_tag:
            sl, tp1, tp2 = calculate_levels(
                price, atr, swing_low, swing_high, bias,
                vwap=vwap, ema20=ema20, ema50=ema50,
                structure=structure, confluence=safe_float(confluence.get("score"), 50),
                order_blocks_fvg=structure_zones, fibonacci=fib, forecast=candle_forecast,
            )
        # Soft score nudge toward fused conviction (display only, clamped)
        try:
            fused_nudge = int(round(safe_float(fusion.get("fused_score"), 0) * 8))
            score_int = int(clamp(score_int + fused_nudge, 0, 100))
            titan["score"] = score_int
        except Exception:
            pass

        volatility_pct = atr / price * 100 if price > 0 else 0.0
        risk_distance_pct = abs(price - sl) / price * 100 if price > 0 else 0.0
        rr_tp1 = abs(tp1 - price) / max(abs(price - sl), 1e-12)
        rr_tp2 = abs(tp2 - price) / max(abs(price - sl), 1e-12)

        ai_consensus = TITAN_EDGE_SUITE.ai_ensemble(ai, bias)
        drawdown_values = []
        try:
            with DB_LOCK, db_conn() as con:
                drawdown_values = [safe_float(r[0]) for r in con.execute("SELECT r_multiple FROM paper_trades WHERE status='CLOSED' AND r_multiple IS NOT NULL ORDER BY closed_at ASC LIMIT 300").fetchall()]
        except Exception:
            drawdown_values = []
        governor = TITAN_EDGE_SUITE.drawdown_governor(drawdown_values)
        adaptive = TITAN_EDGE_SUITE.adaptive_risk(
            base_risk=1.0, volatility_pct=volatility_pct,
            confidence=meta["probability"], regime=regime.get("regime", "unknown"),