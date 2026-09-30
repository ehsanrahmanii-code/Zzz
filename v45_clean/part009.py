                "input": prompt,
                "max_output_tokens": 420,
            },
            timeout=30,
        )
        if response:
            text = _extract_openai_response(response)
            if text:
                _store_ai("openai", model, payload, text)
                return text

        # Compatibility fallback: Chat Completions API.
        response = _request_json(
            "POST",
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 420,
            },
            timeout=30,
        )
        if response:
            text = _extract_chat_completion(response)
            if text:
                _store_ai("openai", model, payload, text)
                return text
    return None


def _call_openai_compatible(provider: str, api_key: str, base_url: str, models: list[str], payload: dict[str, Any]) -> Optional[str]:
    if not api_key: return None
    prompt = _build_ai_prompt(payload)
    for model in models:
        cached = _cached_ai(provider, model, payload)
        if cached: return cached
        response = _request_json("POST", f"{base_url}/chat/completions",
                                 headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                                 json={"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 420}, timeout=30)
        if response:
            text = _extract_chat_completion(response)
            if text:
                _store_ai(provider, model, payload, text); return text
    return None


def _call_claude(payload: dict[str, Any]) -> Optional[str]:
    if not CLAUDE_API_KEY: return None
    prompt = _build_ai_prompt(payload)
    for model in _load_model_settings().get("claude_models", []):
        cached = _cached_ai("claude", model, payload)
        if cached: return cached
        response = _request_json("POST", "https://api.anthropic.com/v1/messages",
                                 headers={"x-api-key": CLAUDE_API_KEY, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                                 json={"model": model, "max_tokens": 420, "messages": [{"role": "user", "content": prompt}]}, timeout=30)
        if response:
            chunks = [str(x.get("text", "")) for x in response.get("content", []) or [] if isinstance(x, dict) and x.get("type") == "text"]
            text = _clean_ai_text(" ".join(chunks))
            if text:
                _store_ai("claude", model, payload, text); return text
    return None


def generate_ai_opinions(symbol: str, price: float, rsi: float, vwap: float, ema20: float, ema50: float, atr: float,
                         vol_spike: bool, btc_trend: str, derivatives: dict[str, Any], tf_results: dict[str, str],
                         titan: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    # Bulk dashboard refresh must not wait on 5 LLM providers (often 10–40s each).
    if DASHBOARD_FAST_SCAN and not force:
        # V29: never block the market scan on an LLM, but do reuse a fresh
        # Gemini opinion produced asynchronously by the previous scan. This
        # makes AI a real evidence channel without making the dashboard wait.
        cached_ai = {}
        try:
            raw = _load_json(AI_SYMBOL_CACHE_PATH, {})
            if isinstance(raw, dict):
                row = raw.get(_normalize_symbol(symbol)) or {}
                if isinstance(row, dict) and (time.time() - safe_float(row.get("ts"), 0)) <= AUTO_AI_REFRESH_SECONDS:
                    cached_ai = row
        except Exception:
            cached_ai = {}
        if cached_ai.get("text"):
            return {
                "providers": ["gemini"],
                "gemini": cached_ai.get("text", ""),
                "internal": (titan or {}).get("summary") or "",
                "titan": (titan or {}).get("summary") or "",
                "ai_status": {"gemini": "تحلیل Gemini تازه/کش‌شده", "openai": "غیرفعال در اسکن سریع",
                              "grok": "غیرفعال در اسکن سریع", "claude": "غیرفعال در اسکن سریع",
                              "deepseek": "غیرفعال در اسکن سریع"},
                "fast_scan": True,
                "cached_at": cached_ai.get("ts"),
            }
        return {
            "providers": [],
            "internal": (titan or {}).get("summary") or "",
            "titan": (titan or {}).get("summary") or "",
            "ai_status": {
                "gemini": "در صف تحلیل پس‌زمینه",
                "openai": "غیرفعال در اسکن سریع",
                "grok": "غیرفعال در اسکن سریع",
                "claude": "غیرفعال در اسکن سریع",
                "deepseek": "غیرفعال در اسکن سریع",
            },
            "fast_scan": True,
        }
    payload = {
        "symbol": symbol, "price": price, "rsi": round(rsi, 2), "vwap": round(vwap, 8), "ema20": round(ema20, 8),
        "ema50": round(ema50, 8), "atr": round(atr, 8), "volume_spike": vol_spike, "btc_trend": btc_trend,
        "oi": derivatives.get("oi"), "oi_delta": derivatives.get("oi_delta"), "funding": derivatives.get("funding"),
        "timeframes": tf_results, "titan_bias": titan["bias"], "titan_score": titan["score"], "titan_alignment": titan["alignment"],
    }
    result: dict[str, Any] = {"providers": [], "internal": titan["summary"], "titan": titan["summary"], "ai_status": {}}
    jobs = {
        "gemini": (bool(GEMINI_API_KEY), lambda: _call_gemini(payload)),
        "openai": (bool(OPENAI_API_KEY), lambda: _call_openai(payload)),
        "grok": (bool(GROK_API_KEY), lambda: _call_openai_compatible("grok", GROK_API_KEY, "https://api.x.ai/v1", _load_model_settings().get("grok_models", []), payload)),
        "claude": (bool(CLAUDE_API_KEY), lambda: _call_claude(payload)),
        "deepseek": (bool(DEEPSEEK_API_KEY), lambda: _call_openai_compatible("deepseek", DEEPSEEK_API_KEY, "https://api.deepseek.com", _load_model_settings().get("deepseek_models", []), payload)),
    }
    for name, (enabled, _) in jobs.items(): result["ai_status"][name] = "در انتظار" if enabled else "فعال نیست"
    active = [(name, fn) for name, (enabled, fn) in jobs.items() if enabled]
    if active:
        executor = _get_ai_pool(max(3, len(active)))
        futures = {executor.submit(fn): name for name, fn in active}
        for future in as_completed(futures):
            name = futures[future]
            try:
                text = future.result(timeout=18)
                if text:
                    result[name] = text; result["providers"].append(name); result["ai_status"][name] = "تحلیل آماده"
                else:
                    result["ai_status"][name] = "فعال نیست"
            except Exception as exc:
                result["ai_status"][name] = "فعال نیست"; LOGGER.warning("AI provider %s failed: %s", name, exc)
    return result

# ============================================================
# ASSET ANALYSIS / QUALITY
# ============================================================


def _record_data_quality(symbol: str, frames: dict[str, pd.DataFrame], derivatives: dict[str, Any], macro_ok: bool = True) -> None:
    try:
        candles_ok = int(all(isinstance(frames.get(tf), pd.DataFrame) and len(frames.get(tf)) >= 10 for tf in TF_CFG))
        volume_ok = int(all("vol" in frames[tf].columns and float(frames[tf]["vol"].tail(20).sum()) > 0 for tf in TF_CFG))
        funding_ok = int(derivatives.get("funding_value") is not None)
        oi_ok = int(safe_float(derivatives.get("raw_oi"), 0) > 0)
        overall = int(candles_ok and volume_ok and (funding_ok or oi_ok) and macro_ok)
        with DB_LOCK, db_conn() as con:
            con.execute("INSERT INTO data_quality(created_at,symbol,source,latency_ms,candles_ok,volume_ok,funding_ok,oi_ok,macro_ok,overall_ok,details) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (time.time(), symbol, "Binance/CoinGlass", 0.0, candles_ok, volume_ok, funding_ok, oi_ok, int(macro_ok), overall, json.dumps({"candles": candles_ok, "volume": volume_ok, "funding": funding_ok, "oi": oi_ok, "macro": int(macro_ok)}, ensure_ascii=False)))
    except Exception as exc:
        LOGGER.info("Data quality record skipped: %s", exc)


def _create_alert(severity: str, symbol: str, category: str, message: str) -> None:
    try:
        with DB_LOCK, db_conn() as con:
            con.execute("INSERT INTO alerts(created_at,severity,symbol,category,message) VALUES(?,?,?,?,?)", (time.time(), severity, symbol, category, message))
    except Exception:
        pass


def analyze_asset(symbol: str, btc_trend: str) -> Optional[dict[str, Any]]:
    started = time.perf_counter()
    try:
        requested = {tf: (120 if tf in ("15m", "1h") else 90) for tf in TF_CFG}
        frames: dict[str, pd.DataFrame] = {}
        derivatives_box: dict[str, Any] = {"d": None}
        pool = _get_kline_pool(5)
        futs = {pool.submit(fetch_klines, symbol, tf, requested[tf]): ("kl", tf) for tf in TF_CFG}
        futs[pool.submit(fetch_derivatives, symbol)] = ("deriv", None)
        for future in as_completed(futs):
            kind, key = futs[future]
            try:
                val = future.result()
                if kind == "kl":
                    frames[key] = val
                else:
                    derivatives_box["d"] = val
            except Exception as exc:
                if kind == "kl":
                    raise
                LOGGER.debug("deriv parallel fail %s: %s", symbol, exc)
        df15, df1h = frames["15m"], frames["1h"]
        signal_close = float(df1h["close"].iloc[-1])
        # Indicators use only CLOSED candles; entry/levels use a fresh spot price when available.
        # This removes the old up-to-one-hour stale-entry problem without leaking an open candle
        # into EMA/RSI/ATR calculations.
        live_price = None
        with LIVE_LOCK:
            lp = LIVE_PRICES.get(_normalize_symbol(symbol)) or {}
            if time.time() - safe_float(lp.get("ts"), 0) <= 15:
                live_price = safe_float(lp.get("price"), 0) or None
        if not live_price:
            live_price = _fetch_live_prices([symbol]).get(_normalize_symbol(symbol))
        price = float(live_price or signal_close)
        live_age_sec = None
        with LIVE_LOCK:
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