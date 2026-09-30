            return list(dict.fromkeys(configured + cached))

    discovered: list[str] = []
    if GEMINI_API_KEY:
        try:
            response = _request_json(
                "GET",
                "https://generativelanguage.googleapis.com/v1beta/models",
                headers={"x-goog-api-key": GEMINI_API_KEY},
                params={"pageSize": 100},
                timeout=12,
            )
            for item in (response or {}).get("models", []) or []:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                methods = item.get("supportedGenerationMethods", []) or []
                if name.startswith("models/"):
                    name = name.split("/", 1)[1]
                if name and "generateContent" in methods:
                    discovered.append(name)
        except Exception as exc:
            LOGGER.warning("Gemini model discovery failed: %s", exc)

    with _GEMINI_MODEL_LOCK:
        _GEMINI_MODEL_CACHE.update(ts=now, models=discovered)
    return list(dict.fromkeys(configured + discovered))

def _call_gemini(payload: dict[str, Any], global_summary: bool = False) -> Optional[str]:
    global GEMINI_LAST_ERROR
    GEMINI_LAST_ERROR = ""
    if not GEMINI_API_KEY:
        GEMINI_LAST_ERROR = "Gemini API key not found"
        return None
    prompt = (
        "تو یک تحلیلگر حرفه‌ای بازار رمزارز زیر نظر موتور TITAN ENTERPRISE هستی. "
        "بر اساس داده‌های واقعی زیر، تحلیل دقیق و کوتاه فارسی ارائه کن. "
        "فقط فارسی بنویس. هیچ واژه انگلیسی یا لاتین مجاز نیست. از ادعاهای بدون داده خودداری کن. خروجی مخصوص داشبورد فارسی باشد.\n"
        + ("یک جمع‌بندی کلان بازار در حداکثر 6 جمله ارائه کن.\n" if global_summary else _build_ai_prompt(payload))
        + json.dumps(payload, ensure_ascii=False, default=str)
    ) if global_summary else (
        "تو تحلیلگر اختصاصی TITAN ENTERPRISE هستی. پاسخ را فقط به زبان فارسی و مبتنی بر داده‌های زیر بده. ممنوعیت مطلق انگلیسی: اگر پاسخ داخلی انگلیسی بود همان را کامل به فارسی روان بازنویسی کن و فقط فارسی برگردان. "
        "جمع‌بندی باید برای داشبورد قابل نمایش باشد و شامل وضعیت بازار، دلیل اصلی، روند، مومنتوم، حجم، حمایت و مقاومت احتمالی، سطوح فیبوناچی، ریسک مهم و وضعیت تایم‌فریم‌ها باشد. خروجی فقط فارسی باشد.\n"
        + _build_ai_prompt(payload)
    )
    models = _gemini_available_models()
    if not models:
        GEMINI_LAST_ERROR = "No Gemini model supporting generateContent was found"
        return None
    for model in models:
        cached = _cached_ai("gemini", model, payload, 600 if global_summary else AI_CACHE_TTL)
        if cached:
            return cached
        response = _request_json(
            "POST",
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 420, "temperature": 0.2},
            },
            timeout=35,
        )
        if response:
            text = _extract_gemini_text(response)
            if text:
                _store_ai("gemini", model, payload, text)
                return text
            feedback = response.get("promptFeedback") or {}
            block = feedback.get("blockReason") or ""
            finish = ""
            try:
                finish = (response.get("candidates") or [{}])[0].get("finishReason", "")
            except Exception:
                pass
            GEMINI_LAST_ERROR = f"Gemini returned no text (blockReason={block or 'none'}, finishReason={finish or 'none'})"
        else:
            GEMINI_LAST_ERROR = f"Gemini request failed for model {model}"
    return None


def _call_openai(payload: dict[str, Any]) -> Optional[str]:
    if not OPENAI_API_KEY: return None
    prompt = _build_ai_prompt(payload)
    for model in _load_model_settings().get("openai_models", []):
        cached = _cached_ai("openai", model, payload)
        if cached: return cached

        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }

        # Primary path: OpenAI Responses API.
        response = _request_json(
            "POST",
            "https://api.openai.com/v1/responses",
            headers=headers,
            json={
                "model": model,
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