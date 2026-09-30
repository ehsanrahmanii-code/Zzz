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