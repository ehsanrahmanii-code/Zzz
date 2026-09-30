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
        try:
            _save_json(self.memory_path, self.memory)
        except Exception as exc:
            LOGGER.debug("Professional edge memory save skipped: %s", exc)

    # 1) Signal Confluence Engine
    def signal_confluence(self, *, score=50, alignment=50, rsi=50, price=0, vwap=0,
                          ema20=0, ema50=0, volume_spike=False, derivatives=None,
                          structure=None, regime="unknown"):
        derivatives = derivatives or {}
        structure = structure or {}
        checks = []
        points = []
        if score >= 60:
            checks.append(("momentum", 1)); points.append("مومنتوم صعودی")
        elif score <= 40:
            checks.append(("momentum", 1)); points.append("مومنتوم نزولی")
        else:
            checks.append(("momentum", 0))
        checks.append(("mtf", clamp(alignment / 100.0, 0, 1)))
        if price and vwap:
            checks.append(("vwap", 1 if (score >= 60 and price >= vwap) or (score <= 40 and price <= vwap) else 0.35))
        if ema20 and ema50:
            ema_ok = 1 if (score >= 60 and ema20 >= ema50) or (score <= 40 and ema20 <= ema50) else 0.25
            checks.append(("trend", ema_ok))
        checks.append(("volume", 1.0 if volume_spike else 0.4))
        oi = safe_float(derivatives.get("oi_delta"), 0)
        funding = safe_float(derivatives.get("funding_value"), 0)
        oi_score = 0.55
        if score >= 60 and oi > 0: oi_score = 0.9
        elif score <= 40 and oi > 0: oi_score = 0.8
        elif oi < 0: oi_score = 0.4
        checks.append(("open_interest", oi_score))
        structure_score = safe_float(structure.get("confirmation_score"), 50) / 100.0
        checks.append(("structure", clamp(structure_score, 0, 1)))
        regime_bonus = 1.0 if regime not in {"range", "unknown"} else 0.65
        checks.append(("regime", regime_bonus))
        raw = sum(v for _, v in checks) / max(1, len(checks))
        confluence = int(round(clamp(35 + raw * 65, 0, 100)))
        disagreement = [name for name, val in checks if val < 0.5]
        return {"score": confluence, "components": {k: round(float(v), 3) for k, v in checks},
                "disagreements": disagreement, "label": "STRONG CONFLUENCE" if confluence >= 80 else "CONFIRMED" if confluence >= 68 else "WATCH"}

    # 2) Regime Detection Engine
    def regime_detection(self, df, atr=None, score=50):
        try:
            close = df["close"].astype(float)
            if len(close) < 60: return {"regime": "unknown", "confidence": 0, "features": {}}
            ret20 = float(close.iloc[-1] / close.iloc[-21] - 1) if len(close) > 21 else 0.0
            ret5 = float(close.iloc[-1] / close.iloc[-6] - 1) if len(close) > 6 else 0.0
            atr_pct = float(atr / close.iloc[-1] * 100) if atr is not None and close.iloc[-1] else 0.0
            ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
            ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
            slope = abs(ret20) * 100
            if atr_pct >= 4.5:
                regime = "high_volatility"
            elif ret20 > 0.05 and ema20 > ema50 and slope > 1.5:
                regime = "trend_up"
            elif ret20 < -0.05 and ema20 < ema50 and slope > 1.5:
                regime = "trend_down"
            elif abs(ret5) > 0.02 and abs(ret20) < 0.04:
                regime = "breakout_watch"
            elif atr_pct < 1.2 and abs(ret20) < 0.025:
                regime = "range"
            else:
                regime = "transition"
            score_fit = 100 - min(80, abs((score - 50) - (20 if "up" in regime else -20 if "down" in regime else 0)) * 1.8)
            return {"regime": regime, "confidence": int(round(clamp(score_fit, 20, 95))),
                    "features": {"ret5_pct": round(ret5*100,3), "ret20_pct": round(ret20*100,3), "atr_pct": round(atr_pct,3), "ema_spread_pct": round((ema20/ema50-1)*100,3) if ema50 else 0}}
        except Exception as exc:
            LOGGER.debug("Regime detection failed: %s", exc)
            return {"regime": "unknown", "confidence": 0, "features": {}}

    # 3) Liquidity / Order-Flow Proxy
    def liquidity_map(self, df, current_price):
        try:
            data = df.tail(60).copy()
            price = float(current_price)
            if data.empty or price <= 0: raise ValueError("invalid liquidity input")
            vol = pd.to_numeric(data["vol"], errors="coerce").fillna(0)
            high_vol = data.loc[vol.nlargest(min(8, len(vol))).index]
            upper = float(high_vol["high"].median()) if not high_vol.empty else price
            lower = float(high_vol["low"].median()) if not high_vol.empty else price
            ranges = {"upper_pool": round(upper, 8), "lower_pool": round(lower, 8),
                      "upper_distance_pct": round((upper/price-1)*100,3),
                      "lower_distance_pct": round((lower/price-1)*100,3)}
            if upper > price * 1.003 and lower < price * 0.997:
                state = "balanced_liquidity"
            elif upper > price * 1.01:
                state = "overhead_liquidity"
            elif lower < price * 0.99:
                state = "downside_liquidity"
            else:
                state = "compressed"
            # buy/sell pressure proxy from candle location + volume
            clv = ((data["close"] - data["low"]) - (data["high"] - data["close"])) / (data["high"] - data["low"]).replace(0, np.nan)
            pressure = float((clv.fillna(0) * vol).sum() / max(float(vol.sum()), 1.0))
            return {"state": state, "pressure": round(pressure, 3), "map": ranges,
                    "liquidity_bias": "buying" if pressure > 0.12 else "selling" if pressure < -0.12 else "balanced"}
        except Exception as exc: