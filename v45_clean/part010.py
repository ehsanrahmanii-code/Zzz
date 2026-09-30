            drawdown_pct=governor.get("drawdown_pct", 0))
        risk = {**adaptive, "governor_state": governor.get("state"), "governor_multiplier": governor.get("risk_multiplier")}
        # Professional composite quality: alignment + confluence + meta + AI agreement + structure
        ai_agree = safe_float(ai_consensus.get("agreement"), 0)
        signal_quality = int(round(clamp(
            preliminary_quality * 0.45
            + confluence["score"] * 0.20
            + meta["probability"] * 0.15
            + ai_agree * 0.10
            + safe_float(structure.get("confirmation_score"), 50) * 0.07
            + pscore * 0.15,
            0, 100)))
        if governor.get("state") == "DEFENSIVE":
            signal_quality = min(signal_quality, 62)
        if decision_tag == "WAIT":
            signal_quality = min(signal_quality, 70)
        # Blend adaptive success probability into quality
        success_prob = safe_float((titan.get("fusion") or {}).get("success_probability"), 50)
        # Precision is an entry-quality correction, not a claim of calibrated probability.
        success_prob = float(clamp(0.88 * success_prob + 0.12 * pscore, 5, 88))
        try:
            cal_dir = "صعودی" if decision_tag == "LONG" else "نزولی" if decision_tag == "SHORT" else ""
            cal_pack = calibrate_success_probability_v8(
                symbol, cal_dir, success_prob, regime=str((regime or {}).get("regime", "")),
            )
            success_prob = float(clamp(safe_float(cal_pack.get("calibrated"), success_prob), 5, 88))
            if isinstance(titan.get("fusion"), dict):
                titan["fusion"]["success_probability"] = success_prob
                titan["fusion"]["probability_calibration"] = cal_pack
                titan["fusion"]["param_version"] = TITAN_PARAM_VERSION
        except Exception as _cal_exc:
            LOGGER.debug("post cal failed: %s", _cal_exc)
            cal_pack = {}
        # V8 meta-label final accept/reject
        try:
            stretch = max(
                safe_float((precision or {}).get("stretch_vwap_atr"), 0),
                safe_float((precision or {}).get("stretch_ema_atr"), 0),
            )
            meta_v8 = meta_label_v8(
                confluence_score=safe_float(confluence.get("score"), 50),
                precision_score=pscore,
                alignment=float(alignment),
                success_prob=success_prob,
                ai_conflict=bool((titan.get("fusion") or {}).get("ai_conflict")),
                stretch_atr=stretch,
                ladder_passed=bool((fusion.get("entry_ladder") or {}).get("passed", True)),
                data_quality=safe_float((fusion.get("data_quality") or {}).get("score"), 50),
                hist_wr=safe_float(hist_wr, 50) if not isinstance(hist_wr, dict) else safe_float(hist_wr.get("win_rate"), 50),
            )
            fusion["meta_v8"] = meta_v8
            titan["fusion"]["meta_v8"] = meta_v8
            if decision_tag in {"LONG", "SHORT"} and meta_v8.get("label") == "REJECT":
                # V28.4: soft — keep direction, tag risk, lower quality
                fusion["meta_soft_reject"] = True
                fusion.setdefault("explanation", []).append("متا-برچسب V8 رد نرم → جهت حفظ با کاهش کیفیت")
            if decision_tag in {"LONG", "SHORT"}:
                register_portfolio_signal(symbol, decision_tag)
        except Exception as _mv:
            LOGGER.debug("meta_v8 failed: %s", _mv)

        # --- V9 Neural Synapse: full-system coherence gate ---
        try:
            path_stats = forecast_path_accuracy_stats(symbol)
            calib_v9 = calibrate_success_probability_v8(
                symbol=symbol,
                direction=decision_tag if decision_tag in {"LONG", "SHORT"} else ("LONG" if bias == "صعودی" else "SHORT" if bias == "نزولی" else ""),
                raw_prob=safe_float(fusion.get("success_probability"), 50),
                regime=str((regime or {}).get("regime", "")),
            )
            fusion["probability_calibration"] = calib_v9
            _prec_for_neural = precision_pre
            try:
                if "precision" in locals() and isinstance(precision, dict):
                    _prec_for_neural = precision
            except Exception:
                pass
            _ai_for_neural = ai if isinstance(ai, dict) else {}
            _dq_for_neural = fusion.get("data_quality") or {}
            neural = TITAN_NEURAL.fuse(
                tf_scores=tf_scores,
                structure=structure,
                regime=regime,
                confluence=confluence,
                precision=_prec_for_neural,
                patterns=pattern_pack,
                forecast=candle_forecast,
                path_stats=path_stats,
                derivatives=derivatives,
                fusion=fusion,
                ai_opinions=_ai_for_neural,
                data_quality=_dq_for_neural,
                ladder=fusion.get("entry_ladder") or {},
                calib=calib_v9,
                quant_bias=bias,
                quant_score=float(score_int),
            )
            fusion["neural_v9"] = neural
            titan["fusion"]["neural_v9"] = neural
            titan["neural_score"] = neural.get("neural_score")
            titan["neural_confidence"] = neural.get("confidence")
            # Neural can only demote or confirm — never invent a side from WAIT quant without ladder
            n_side = neural.get("side", "WAIT")
            n_conf = safe_float(neural.get("confidence"), 0)
            if decision_tag in {"LONG", "SHORT"}:
                # Opportunity-preserving rule: a neutral neural layer is not enough by itself
                # to erase a strong, data-valid directional setup. Only demote when the
                # neural layer is materially uncertain AND the directional edge is weak.
                _dq_now = safe_float((fusion.get("data_quality") or {}).get("score"), 0)
                _sq_now = safe_float(signal_quality, 0)
                _edge_now = abs(safe_float(neural.get("neural_score"), 50) - 50)
                if n_side == "WAIT" and n_conf >= 70:
                    # Neutral neural never kills a data-valid directional edge by itself.
                    fusion.setdefault("explanation", []).append(
                        "سیناپس عصبی خنثی — جهت کمی حفظ شد (V28.5)"
                    )
                    signal_quality = min(int(signal_quality), 70)
                elif n_side != decision_tag and n_side in {"LONG", "SHORT"} and n_conf >= 82:
                    # Only extreme opposite neural with weak edge demotes to WAIT.
                    if _sq_now < 55 and _edge_now < 8:
                        decision_tag, bias = "WAIT", "خنثی"
                        fusion.setdefault("explanation", []).append(
                            f"سیناپس عصبی خلاف جهت قوی ({n_side}) conf={n_conf:.0f} + لبه ضعیف → انتظار"
                        )
                    else:
                        fusion.setdefault("explanation", []).append(
                            f"تعارض Neural ثبت شد اما Edge حفظ شد · {decision_tag}"
                        )
                        signal_quality = min(int(signal_quality), 68)
                elif n_side == decision_tag and n_conf >= 62:
                    fusion.setdefault("explanation", []).append(
                        f"سیناپس عصبی V9 تأیید {n_side} · score={neural.get('neural_score')} · conf={n_conf:.0f}"
                    )
            elif decision_tag == "WAIT" and n_side in {"LONG", "SHORT"} and n_conf >= 52:
                # Balanced opportunity promotion: allow a strong consensus setup to surface
                # even when one timeframe is merely early/neutral. Hard data failures and
                # strong opposite HTF/MTF structure still block the promotion.
                trial_ladder = entry_ladder_gate(tf_scores, tf_results, n_side, neural.get("bias", "خنثی"))
                _dq_promote = safe_float((fusion.get("data_quality") or {}).get("score"), 0)
                _rr_promote = _friction_adjusted_rr(price, sl, tp1)
                _neural_dir_ok = (safe_float(neural.get("neural_score"), 50) >= 55) if n_side == "LONG" else (safe_float(neural.get("neural_score"), 50) <= 45)
                _opportunity_ok = _dq_promote >= MIN_DATA_QUALITY_SCORE and _neural_dir_ok
                _quality_ok = safe_float(signal_quality, 0) >= 58 and pscore >= 52 and success_prob >= 52 and _rr_promote >= 1.10
                _hard_opposite = (
                    (n_side == "LONG" and trial_ladder.get("htf_side") == "SHORT" and trial_ladder.get("htf_score",50) <= 43)
                    or (n_side == "SHORT" and trial_ladder.get("htf_side") == "LONG" and trial_ladder.get("htf_score",50) >= 57)
                )
                if _opportunity_ok and _quality_ok and not _hard_opposite:
                    decision_tag = n_side
                    bias = neural.get("bias", "صعودی" if n_side == "LONG" else "نزولی")
                    fusion["opportunity_mode"] = True
                    fusion.setdefault("explanation", []).append(
                        f"Opportunity Engine: {n_side} فعال شد · Neural={n_conf:.0f} · RR={_rr_promote:.2f} · تایم‌فریم‌ها در آستانه ورود"
                    )
            # Soft quality blend with neural confidence
            if isinstance(neural.get("neural_score"), (int, float)):
                signal_quality = int(round(clamp(
                    0.55 * signal_quality + 0.25 * safe_float(fusion.get("success_probability"), 50)
                    + 0.10 * pscore + 0.10 * n_conf,
                    0, 100,
                )))
        except Exception as _neu:
            LOGGER.debug("neural synapse V9 failed: %s", _neu)

        signal_quality = int(round(clamp(0.60 * signal_quality + 0.25 * success_prob + 0.15 * pscore, 0, 100)))
        if decision_tag == "WAIT":
            signal_quality = min(signal_quality, 68)
        effective_rr1 = _friction_adjusted_rr(price, sl, tp1)
        effective_rr2 = _friction_adjusted_rr(price, sl, tp2)
        if decision_tag in {"LONG", "SHORT"} and effective_rr1 < MIN_EFFECTIVE_RR:
            # V28.4: keep direction; only hard-kill if RR is tiny AND quality is weak.
            if effective_rr1 < 0.85 and (signal_quality < 50 or success_prob < 48):
                decision_tag, bias = "WAIT", "خنثی"
                signal_quality = min(signal_quality, 55)
                fusion["rr_veto"] = True
            else:
                fusion["rr_warning"] = True
                fusion["rr_warning_value"] = round(effective_rr1, 2)
                signal_quality = min(signal_quality, 72)
        # If AI majority conflicts hard, cap quality
        if (titan.get("fusion") or {}).get("ai_majority") in {"LONG", "SHORT"}:
            if decision_tag not in {"WAIT", (titan.get("fusion") or {}).get("ai_majority")} and ai_pre.get("providers", 0) >= 2:
                signal_quality = min(signal_quality, 60)

        meta_v8_label = str(((fusion.get("meta_v8") or {}).get("label") if isinstance(fusion, dict) else "") or meta.get("label") or "")
        neural_pack = (fusion.get("neural_v9") or {}) if isinstance(fusion, dict) else {}
        neural_side = str(neural_pack.get("side") or "")
        neural_conf = safe_float(neural_pack.get("confidence"), 0)
        neural_ok = (not neural_pack) or (neural_side in {decision_tag, "WAIT"} and neural_side != "WAIT") or (neural_side == decision_tag)
        if neural_pack and decision_tag in {"LONG", "SHORT"}:
            neural_ok = neural_side == decision_tag and neural_conf >= 55
        if (
            signal_quality >= 82
            and meta_v8_label == "ACCEPT"
            and decision_tag in {"LONG", "SHORT"}
            and success_prob >= 62
            and bool((fusion.get("entry_ladder") or {}).get("passed", False))
            and not fusion.get("dq_veto")
            and neural_ok
            and neural_conf >= 58
        ):
            signal_tag = "HIGH CONVICTION"
        elif signal_quality >= 70 and decision_tag in {"LONG", "SHORT"} and success_prob >= 56 and meta_v8_label != "REJECT" and (not neural_pack or neural_side in {decision_tag, "WAIT"}):
            signal_tag = "CONFIRMED SETUP"
        elif signal_quality >= 55:
            signal_tag = "WATCH"
        else:
            signal_tag = "LOW EDGE"

        signal_grade: dict[str, Any] = {"grade": "—", "label_fa": "—", "action": "—", "trust_index": 0, "checklist": [], "rank": 0}
        # --- V10 Professional Grade ---
        try:
            _pat_primary = (pattern_pack or {}).get("primary") or {}
            _pat_conf = safe_float(_pat_primary.get("confidence"), 0)
            _fc_bias = str((candle_forecast or {}).get("overall_bias") or "")
            _fc_aligned = (
                (decision_tag == "LONG" and _fc_bias == "صعودی")
                or (decision_tag == "SHORT" and _fc_bias == "نزولی")
            )
            signal_grade = classify_signal_grade(
                decision_tag=decision_tag,
                signal_quality=float(signal_quality),
                success_prob=float(success_prob),
                alignment=float(alignment),
                neural=neural_pack if isinstance(neural_pack, dict) else fusion.get("neural_v9"),
                meta=fusion.get("meta_v8") or meta,
                ladder=fusion.get("entry_ladder") or {},
                data_quality=fusion.get("data_quality") or {},
                precision=precision if isinstance(precision, dict) else precision_pre,
                effective_rr1=float(effective_rr1) if effective_rr1 is not None else 0.0,
                ai_agreement=safe_float((fusion.get("ai_agreement") if isinstance(fusion, dict) else None) or (ai_consensus or {}).get("agreement"), 0),
                pattern_conf=_pat_conf,
                forecast_aligned=_fc_aligned,
            )
            # V28.4: only hard F + data veto kills direction; D/C stay visible as risk-tagged signals
            if decision_tag in {"LONG", "SHORT"} and signal_grade.get("grade") == "F" and (fusion.get("data_quality") or {}).get("hard_veto"):
                decision_tag, bias = "WAIT", "خنثی"
                signal_tag = "LOW EDGE"
                titan["bias"] = bias
                fusion.setdefault("explanation", []).append(
                    f"درجه F + وتوی داده → سیگنال لغو شد ({signal_grade.get('label_fa')})"
                )
            elif decision_tag in {"LONG", "SHORT"} and signal_grade.get("grade") in {"C", "D"}:
                signal_tag = "WATCH" if signal_grade.get("grade") == "C" else "LOW EDGE"
                fusion.setdefault("explanation", []).append(
                    f"درجه {signal_grade.get('grade')} → جهت حفظ شد با برچسب ریسک ({signal_grade.get('label_fa')})"
                )
            fusion["signal_grade"] = signal_grade
            titan["fusion"]["signal_grade"] = signal_grade
            titan["bias"] = bias
        except Exception as _gr:
            LOGGER.debug("signal grade failed: %s", _gr)
            signal_grade = {"grade": "—", "label_fa": "نامشخص", "action": "—", "trust_index": 0, "checklist": [], "rank": 0}

        # V27.3 FINAL BALANCED OPPORTUNITY PASS
        # Purpose: prevent a valid directional setup from being flattened to WAIT by
        # a single soft/secondary gate, while keeping hard data/safety vetoes intact.
        try:
            _f = fusion if isinstance(fusion, dict) else {}
            _dqf = safe_float((_f.get("data_quality") or {}).get("score"), 0)
            _neuf = (_f.get("neural_v9") or {}) if isinstance(_f, dict) else {}
            _nside = str(_neuf.get("side") or "")
            _nscore = safe_float(_neuf.get("neural_score"), 50)
            _nconf = safe_float(_neuf.get("confidence"), 0)
            _a_major = str(_f.get("ai_majority") or "")
            _cand = _nside if _nside in {"LONG","SHORT"} else _a_major if _a_major in {"LONG","SHORT"} else (
                "LONG" if bias == "صعودی" else "SHORT" if bias == "نزولی" else (
                    "LONG" if score_int >= 55 else "SHORT" if score_int <= 45 else ""
                )
            )
            _tfvals = [safe_float(v,50) for v in (tf_scores or {}).values()]
            _tfavg = float(np.mean(_tfvals)) if _tfvals else 50.0
            _dir_edge = abs(float(score_int)-50.0)
            _rr_ok = safe_float(effective_rr1, 0) >= MIN_EFFECTIVE_RR
            _meta_final = str((_f.get("meta_v8") or {}).get("label") or "")
            _hard_block = bool(
                _f.get("dq_veto")
                or _f.get("portfolio_veto")
                or (_meta_final == "REJECT" and _dqf < 48)
                or (_f.get("ai_conflict") and _nconf >= 82)
            )
            _grade_now = str((signal_grade or {}).get("grade") or "")
            _strong_dir = (
                _cand in {"LONG","SHORT"}
                and _dqf >= 46
                and _dir_edge >= 3.5
                and safe_float(alignment,0) >= 44
                and safe_float(pscore,0) >= 40
                and safe_float(success_prob,0) >= 44
                and _rr_ok
                and not _hard_block
                and _grade_now not in {"F"}
            )
            _support_votes = 0
            _support_reasons = []
            _struct_final = _f.get("structure") or {}
            if _cand == "LONG":
                if _nside == "LONG" and _nconf >= 52:
                    _support_votes += 1; _support_reasons.append("neural")
                if _a_major == "LONG":
                    _support_votes += 1; _support_reasons.append("ai")
                if score_int >= 54:
                    _support_votes += 1; _support_reasons.append("score")
                if _tfavg >= 53:
                    _support_votes += 1; _support_reasons.append("tf")
                if str(_struct_final.get("bias") or "") == "صعودی":
                    _support_votes += 1; _support_reasons.append("structure")
            elif _cand == "SHORT":
                if _nside == "SHORT" and _nconf >= 52:
                    _support_votes += 1; _support_reasons.append("neural")
                if _a_major == "SHORT":
                    _support_votes += 1; _support_reasons.append("ai")
                if score_int <= 46:
                    _support_votes += 1; _support_reasons.append("score")
                if _tfavg <= 47:
                    _support_votes += 1; _support_reasons.append("tf")
                if str(_struct_final.get("bias") or "") == "نزولی":
                    _support_votes += 1; _support_reasons.append("structure")
            _candidate_support = _support_votes >= 2
            if decision_tag == "WAIT" and _strong_dir and _candidate_support:
                _hard_htf_opposite = (
                    (_cand == "LONG" and safe_float((_f.get("entry_ladder") or {}).get("htf_score"),50) <= 34)
                    or (_cand == "SHORT" and safe_float((_f.get("entry_ladder") or {}).get("htf_score"),50) >= 66)
                )
                if not _hard_htf_opposite:
                    decision_tag = _cand
                    bias = "صعودی" if _cand == "LONG" else "نزولی"
                    _f["opportunity_mode"] = True
                    _f.setdefault("explanation", []).append(
                        f"Opportunity-Preserve V28.2: {_cand} فعال شد؛ لبه جهت‌دار واقعی، RR کافی، بدون وتوی سخت و {_support_votes} شاهد مستقل ({', '.join(_support_reasons[:4])})."
                    )
                    signal_quality = max(signal_quality, min(82, int(round(52 + _dir_edge * 1.6))))
            # WAIT only when no independent directional evidence exists.
        except Exception as _opp_final_exc:
            LOGGER.debug("final opportunity pass failed: %s", _opp_final_exc)

        edge = {
            "confluence": confluence, "regime": regime, "liquidity": liquidity, "structure": structure,
            "ai": ai_consensus, "meta": meta, "risk": risk, "governor": governor,
            "strategy_lab": TITAN_EDGE_SUITE.strategy_lab(df1h),
            "decision_tag": decision_tag,
            "fusion": titan.get("fusion") or {},
            "precision": precision,
        }

        base_symbol = symbol.split("/")[0].upper()
        coin_name, coin_icon = COIN_META.get(base_symbol, (base_symbol, "●"))
        color = "#4ade80" if score_int >= 60 else "#f43f5e" if score_int <= 40 else "#fbbf24"
        return {
            "symbol": symbol, "base_symbol": base_symbol, "coin_name": coin_name, "coin_icon": coin_icon,
            "tv_symbol": _binance_symbol(symbol), "price": smart_format(price), "rsi": f"{rsi:.1f}",
            "entry_valid": smart_format(price), "tp1": smart_format(tp1), "tp2": smart_format(tp2), "stop_loss": smart_format(sl),
            "coinglass_oi": derivatives["oi"], "coinglass_funding": derivatives["funding"], "derivatives_source": derivatives["source"],
            "btc_trend": btc_trend, "tfs": tf_results, "titan_analysis": titan, "ai_opinions": ai,
            "alignment": alignment, "bias": bias, "score": score_int, "score_bar": score_int, "score_color": color,
            "score_icon": "🟢" if score_int >= 60 else "🔴" if score_int <= 40 else "🟡", "volume_spike": volume_spike,
            "provisional_tf_score": round(provisional, 1), "volatility_pct": round(volatility_pct, 3),
            "risk_distance_pct": round(risk_distance_pct, 3), "rr_tp1": round(rr_tp1, 2), "rr_tp2": round(rr_tp2, 2),
            "effective_rr_tp1": round(effective_rr1, 2), "effective_rr_tp2": round(effective_rr2, 2),
            "precision": precision, "entry_timing": precision.get("entry_timing", "CAUTIOUS"),
            "signal_quality": signal_quality, "signal_tag": signal_tag,
            "fusion": titan.get("fusion") or {}, "edge": edge, "decision_tag": decision_tag,
            "success_probability": safe_float((titan.get("fusion") or {}).get("success_probability"), 50),
            "ai_majority": (titan.get("fusion") or {}).get("ai_majority"),
            "ai_conflict": bool((titan.get("fusion") or {}).get("ai_conflict")),
            "decision_terminal": TITAN_EDGE_SUITE.decision_terminal({
                "symbol": symbol, "price": smart_format(price), "bias": bias,
                "rr_tp1": round(rr_tp1, 2), "rr_tp2": round(rr_tp2, 2), "effective_rr_tp1": round(effective_rr1, 2),
                "precision": precision, "signal_quality": signal_quality,
                "signal_tag": signal_tag, "edge": edge, "decision_tag": decision_tag}),
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "macd": macd_info,
            "stoch_rsi": stoch_info,
            "pivots": {k: smart_format(v) for k, v in (pivots or {}).items()},
            "volume_delta": vol_delta,
            "session": session_info,
            "long_short_ratio": derivatives.get("long_short_ratio"),
            "long_ratio": derivatives.get("long_ratio"),
            "short_ratio": derivatives.get("short_ratio"),
            "top_long_ratio": derivatives.get("top_long_ratio"),
            "taker_buy_pct": derivatives.get("taker_buy_pct"),
            "taker_sell_pct": derivatives.get("taker_sell_pct"),
            "adv_nudge": round(adv_nudge, 2),
            "patterns": pattern_pack,
            "candle_forecast": candle_forecast,
            "rsi_value": round(rsi, 2),
            "macd_hist": macd_info.get("hist"),
            "macd_cross": macd_info.get("cross"),
            "btc_correlation": (fusion.get("btc_correlation") if isinstance(fusion, dict) else None) or {},
            "order_blocks_fvg": structure_zones,
            "depth": depth_snap,
            "technical": {
                "fibonacci": {k: smart_format(v) for k, v in fib.items()},
                "support": smart_format(sr.get("support")) if sr.get("support") is not None else "N/A",
                "resistance": smart_format(sr.get("resistance")) if sr.get("resistance") is not None else "N/A",
                "bollinger": {
                    "upper": smart_format(bb.get("upper")) if bb.get("upper") is not None else "N/A",
                    "middle": smart_format(bb.get("middle")) if bb.get("middle") is not None else "N/A",
                    "lower": smart_format(bb.get("lower")) if bb.get("lower") is not None else "N/A",
                },
            },
            "tf_scores": {k: round(float(v), 1) for k, v in tf_scores.items()},
            "buy_sell": (lambda _bp: {
                "pressure": edge.get("liquidity", {}).get("pressure", 0),
                "bias": edge.get("liquidity", {}).get("liquidity_bias", "unknown"),
                "state": edge.get("liquidity", {}).get("state", "unknown"),
                "buy_pct": int(_bp),
                "sell_pct": int(100 - _bp),
                "taker_buy_pct": safe_float(derivatives.get("taker_buy_pct"), 50),
                "taker_sell_pct": safe_float(derivatives.get("taker_sell_pct"), 50),
                "volume_delta_pct": safe_float(vol_delta.get("delta_pct"), 0),
            })(clamp(
                0.45 * (50 + safe_float(edge.get("liquidity", {}).get("pressure"), 0) * 80)
                + 0.35 * safe_float(derivatives.get("taker_buy_pct"), 50)
                + 0.20 * (50 + safe_float(vol_delta.get("delta_pct"), 0) * 0.8),
                5, 95)),
            "whale": {
                "oi": derivatives.get("oi", "N/A"),
                "oi_delta": round(safe_float(derivatives.get("oi_delta"), 0), 3),
                "funding": derivatives.get("funding", "N/A"),
                "note": titan.get("oi_note", "") or titan.get("funding_note", ""),
                "label": (
                    "ورود نهنگ / افزایش موقعیت" if safe_float(derivatives.get("oi_delta"), 0) > 1.5
                    else "خروج نقدینگی" if safe_float(derivatives.get("oi_delta"), 0) < -1.5
                    else "رفتار خنثی نهنگ"
                ),
            },
            "sentiment": {
                "rsi": round(rsi, 1),
                "rsi_note": titan.get("rsi_note", ""),
                "funding_note": titan.get("funding_note", ""),
                "score": score_int,
                "label": "مثبت" if score_int >= 60 else "منفی" if score_int <= 40 else "خنثی",
            },
            "data_quality": fusion.get("data_quality") if isinstance(fusion, dict) else {},
            "entry_ladder": fusion.get("entry_ladder") if isinstance(fusion, dict) else {},
            "meta_v8": fusion.get("meta_v8") if isinstance(fusion, dict) else {},
            "neural_v9": fusion.get("neural_v9") if isinstance(fusion, dict) else {},
            "neural_score": (fusion.get("neural_v9") or {}).get("neural_score") if isinstance(fusion, dict) else None,
            "neural_confidence": (fusion.get("neural_v9") or {}).get("confidence") if isinstance(fusion, dict) else None,
            "signal_grade": signal_grade if isinstance(signal_grade, dict) else (fusion.get("signal_grade") if isinstance(fusion, dict) else {}),
            "grade": (signal_grade.get("grade") if isinstance(signal_grade, dict) else None) or "—",
            "grade_label": (signal_grade.get("label_fa") if isinstance(signal_grade, dict) else None) or "—",
            "grade_action": (signal_grade.get("action") if isinstance(signal_grade, dict) else None) or "—",
            "trust_index": (signal_grade.get("trust_index") if isinstance(signal_grade, dict) else None) or 0,
            "grade_checklist": (signal_grade.get("checklist") if isinstance(signal_grade, dict) else None) or [],
            "forecast_accuracy": fusion.get("forecast_accuracy") if isinstance(fusion, dict) else {},
            "param_version": TITAN_PARAM_VERSION,
            "confidence_gates": {
                "dq_veto": bool(isinstance(fusion, dict) and fusion.get("dq_veto")),
                "ladder_veto": bool(isinstance(fusion, dict) and fusion.get("ladder_veto")),
                "forecast_veto": bool(isinstance(fusion, dict) and fusion.get("forecast_veto")),
                "portfolio_veto": bool(isinstance(fusion, dict) and fusion.get("portfolio_veto")),
                "precision_veto": bool(isinstance(fusion, dict) and fusion.get("precision_veto")),
                "neural_veto": bool(isinstance(fusion, dict) and (fusion.get("neural_v9") or {}).get("side") == "WAIT" and decision_tag in {"LONG", "SHORT"}),
            },
        }
    except Exception as exc:
        LOGGER.exception("analyze_asset failed for %s: %s", symbol, exc)
        return None


# ============================================================
# TITAN PROFESSIONAL EDGE SUITE - 12 ADDITIVE MODULES
# No external dependency. Every module is fail-safe and analysis-only.
# ============================================================

class TitanProfessionalEdgeSuite:
    """Twelve professional research layers wired into the existing TITAN pipeline.

    1) Signal Confluence Engine
    2) Regime Detection Engine
    3) Liquidity / Order-Flow Proxy
    4) Market Structure Engine
    5) Walk-Forward / OOS validator
    6) Strategy Laboratory
    7) Meta-Labeling
    8) Adaptive Risk Engine
    9) Drawdown Governor
    10) AI Ensemble Consensus
    11) Counterfactual Engine
    12) Decision Terminal payload builder

    The engine is deliberately dependency-free and conservative: missing market/API data
    lowers confidence instead of inventing values. It never executes real orders.
    """

    def __init__(self):
        self.name = "TITAN PROFESSIONAL EDGE SUITE"
        self.memory_path = MEMORY_DIR / "professional_edge_memory.json"
        self.memory = self._load_memory()

    def _load_memory(self):
        try:
            data = _load_json(self.memory_path, {})
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_memory(self):