    elif oi_adj < 0: reasons_against.append(oi_reason)

    score = clamp(score, 0, 100)
    bias = "صعودی" if score >= 58 else "نزولی" if score <= 42 else "خنثی"
    agreement_count = sum(
        1 for direction in tf_results.values()
        if (bias == "صعودی" and "صعودی" in direction)
        or (bias == "نزولی" and "نزولی" in direction)
        or (bias == "خنثی" and "خنثی" in direction)
    )
    alignment = clamp(50 + agreement_count * 10 + abs(score - 50) * 0.25, 50, 95)

    rsi_note = "متعادل"
    if rsi >= 70:
        rsi_note = "اشباع خرید / ریسک اصلاح"; reasons_against.append("RSI بالاتر از 70 است")
    elif rsi <= 30:
        rsi_note = "اشباع فروش / احتمال واکنش"; reasons_for.append("RSI پایین 30 است")
    if not reasons_for: reasons_for.append("تأیید جهت‌دار قوی از داده‌های فعلی دیده نشد")
    if not reasons_against: reasons_against.append("مخالفت جدی در داده‌های موجود دیده نشد")

    volatility_pct = atr / price * 100 if price > 0 else 0.0
    conviction = "بالا" if alignment >= 78 and abs(score - 50) >= 18 else "متوسط" if alignment >= 65 else "پایین"
    if bias == "صعودی":
        invalidation = "شکست معتبر EMA50/VWAP و افت امتیاز زیر 50."
    elif bias == "نزولی":
        invalidation = "بازپس‌گیری معتبر EMA50/VWAP و رشد امتیاز بالای 50."
    else:
        invalidation = "خروج از محدوده خنثی با تأیید حجم و همسویی چندتایم‌فریمی."
    summary = (f"TITAN: سوگیری {bias} با امتیاز {round(score)}/100 و همسویی {round(alignment)}/100. "
               f"RSI {rsi:.1f}، انحراف VWAP {vwap_dev:+.2f}% و ATR حدود {volatility_pct:.2f}%. "
               f"اعتماد سیستم {conviction} است؛ خروجی احتمالاتی است، نه تضمین سود.")
    return {
        "bias": bias, "score": int(round(score)), "alignment": int(round(alignment)), "conviction": conviction,
        "summary": summary, "reasons_for": reasons_for[:4], "reasons_against": reasons_against[:4],
        "invalidation": invalidation, "vwap_dev": vwap_dev, "rsi_note": rsi_note,
        "funding_note": f_reason, "oi_note": oi_reason,
    }


def calculate_levels(
    price: float,
    atr: float,
    swing_low: float,
    swing_high: float,
    bias: str,
    *,
    vwap: float = 0.0,
    ema20: float = 0.0,
    ema50: float = 0.0,
    structure: Optional[dict[str, Any]] = None,
    confluence: float = 50.0,
    order_blocks_fvg: Optional[dict[str, Any]] = None,
    fibonacci: Optional[dict[str, Any]] = None,
    forecast: Optional[dict[str, Any]] = None,
) -> tuple[float, float, float]:
    """Professional multi-anchor SL/TP: ATR + swing + structure + OB/FVG + fib + path.

    Higher confluence tightens risk and stretches reward slightly for high-conviction setups.
    Forecast path can stretch TP2 toward the expected mid of the 12-candle scenario.
    Always analysis-only — never executes orders.
    """
    rm = clamp(safe_float(USER_SETTINGS.get("risk_multiplier"), 1.2), 0.2, 5.0)
    atr = max(float(atr), price * 0.0005)
    friction = price * TOTAL_ENTRY_BUFFER
    structure = structure or {}
    conf = clamp(safe_float(confluence, 50.0), 0.0, 100.0)
    conf_factor = 0.85 + (conf / 100.0) * 0.30  # 0.85 .. 1.15
    rr1_mult = 1.5 * conf_factor
    rr2_mult = 2.6 * conf_factor

    struct_low = safe_float(structure.get("swing_low"), swing_low)
    struct_high = safe_float(structure.get("swing_high"), swing_high)
    if struct_low <= 0:
        struct_low = swing_low
    if struct_high <= 0:
        struct_high = swing_high

    anchors_below = [p for p in (swing_low, struct_low, ema50 if ema50 > 0 else None, vwap if 0 < vwap < price else None) if p and p > 0]
    anchors_above = [p for p in (swing_high, struct_high, ema50 if ema50 > 0 else None, vwap if vwap > price else None) if p and p > 0]

    # Order-block / FVG as structural SL magnets
    obf = order_blocks_fvg or {}
    nearest_ob = obf.get("nearest_ob") or {}
    nearest_fvg = obf.get("nearest_fvg") or {}
    if nearest_ob.get("type") == "bullish_ob" and safe_float(nearest_ob.get("low"), 0) > 0:
        anchors_below.append(safe_float(nearest_ob.get("low")))
    if nearest_ob.get("type") == "bearish_ob" and safe_float(nearest_ob.get("high"), 0) > 0:
        anchors_above.append(safe_float(nearest_ob.get("high")))
    if nearest_fvg.get("type") == "bullish_fvg" and safe_float(nearest_fvg.get("low"), 0) > 0:
        anchors_below.append(safe_float(nearest_fvg.get("low")))
    if nearest_fvg.get("type") == "bearish_fvg" and safe_float(nearest_fvg.get("high"), 0) > 0:
        anchors_above.append(safe_float(nearest_fvg.get("high")))

    # Fibonacci 0.618 / 0.786 as optional anchors near price
    fib = fibonacci or {}
    for fk in ("0.618", "0.786", "0.500"):
        fv = safe_float(fib.get(fk), 0)
        if fv <= 0:
            continue
        if fv < price:
            anchors_below.append(fv)
        elif fv > price:
            anchors_above.append(fv)

    # Forecast path target (step ~6 and step ~12 mid)
    fc = forecast or {}
    fc_candles = fc.get("candles") or []
    path_tp_boost = 1.0
    path_target = None
    if fc_candles and fc.get("ok"):
        mid_step = fc_candles[min(5, len(fc_candles) - 1)]
        far_step = fc_candles[min(len(fc_candles) - 1, 11)]
        path_target = safe_float(far_step.get("close"), 0)
        strength = safe_float(fc.get("path_strength"), 0)
        path_tp_boost = 1.0 + min(0.22, strength / 200.0)

    if bias == "صعودی":
        atr_sl = price - rm * atr
        swing_sl = max(anchors_below) - 0.25 * atr if anchors_below else atr_sl
        sl = min(atr_sl, swing_sl) - friction
        if sl >= price:
            sl = price - max(rm * atr, price * 0.004) - friction
        dist = max(price - sl, atr * 0.9)
        tp1 = price + rr1_mult * dist * path_tp_boost + friction
        tp2 = price + rr2_mult * dist * path_tp_boost + friction
        if path_target and path_target > price:
            # Soft pull TP2 toward forecast mid if further than RR path
            tp2 = max(tp2, min(path_target, price + 4.2 * dist))
        return float(sl), float(tp1), float(tp2)

    if bias == "نزولی":
        atr_sl = price + rm * atr
        swing_sl = min(anchors_above) + 0.25 * atr if anchors_above else atr_sl
        sl = max(atr_sl, swing_sl) + friction
        if sl <= price:
            sl = price + max(rm * atr, price * 0.004) + friction
        dist = max(sl - price, atr * 0.9)
        tp1 = price - rr1_mult * dist * path_tp_boost - friction
        tp2 = price - rr2_mult * dist * path_tp_boost - friction
        if path_target and path_target < price:
            tp2 = min(tp2, max(path_target, price - 4.2 * dist))
        return float(sl), float(tp1), float(tp2)

    return (
        float(price - 1.6 * atr - friction),
        float(price + 1.6 * atr + friction),
        float(price + 3.0 * atr + friction),
    )


def refine_bias_with_edge(
    bias: str,
    score: int,
    alignment: float,
    structure: dict[str, Any],
    regime: dict[str, Any],
    confluence: dict[str, Any],
    meta: dict[str, Any],
) -> tuple[str, str]:
    """Balanced multi-layer LONG/SHORT decision — no long-only bias.

    Requires structural + regime + confluence agreement. Symmetric thresholds
    for both directions so SHORT setups are not systematically suppressed.
    """
    struct_bias = str((structure or {}).get("bias", "خنثی"))
    regime_name = str((regime or {}).get("regime", "unknown"))
    conf_score = safe_float((confluence or {}).get("score"), 50)
    meta_label = str((meta or {}).get("label", "WATCH"))
    meta_prob = safe_float((meta or {}).get("probability"), 50)

    long_votes = 0.0
    short_votes = 0.0

    # Core quant bias (symmetric)
    if bias == "صعودی":
        long_votes += 2.0
    elif bias == "نزولی":
        short_votes += 2.0
    else:
        # neutral core still allows promotion from structure/regime
        if score >= 55:
            long_votes += 0.5
        elif score <= 45:
            short_votes += 0.5

    if struct_bias == "صعودی":
        long_votes += 1.5
    elif struct_bias == "نزولی":
        short_votes += 1.5

    if regime_name in {"trend_up", "breakout_watch"} or "up" in regime_name:
        long_votes += 1.2
    elif regime_name in {"trend_down"} or "down" in regime_name:
        short_votes += 1.2
    elif regime_name == "high_volatility":
        # volatility does not favor either side
        pass

    # Confluence strengthens whichever side score already leans
    if conf_score >= 68:
        if score >= 55:
            long_votes += 1.0
        elif score <= 45:
            short_votes += 1.0
    if conf_score >= 78:
        if score >= 52:
            long_votes += 0.5
        elif score <= 48:
            short_votes += 0.5

    if meta_label == "ACCEPT" and meta_prob >= 68:
        if score >= 54:
            long_votes += 1.0
        elif score <= 46:
            short_votes += 1.0

    # High-conviction directional (V28.5: reachable with real multi-layer lean)
    if long_votes >= 3.0 and short_votes <= 1.8 and alignment >= 48 and score >= 52:
        return "صعودی", "LONG"
    if short_votes >= 3.0 and long_votes <= 1.8 and alignment >= 48 and score <= 48:
        return "نزولی", "SHORT"

    # Moderate conviction
    if bias == "صعودی" and long_votes >= short_votes + 0.6 and score >= 54 and alignment >= 48:
        return "صعودی", "LONG"
    if bias == "نزولی" and short_votes >= long_votes + 0.6 and score <= 46 and alignment >= 48:
        return "نزولی", "SHORT"

    # Score-led when layers agree mildly
    if long_votes >= short_votes + 1.2 and score >= 56 and alignment >= 50:
        return "صعودی", "LONG"
    if short_votes >= long_votes + 1.2 and score <= 44 and alignment >= 50:
        return "نزولی", "SHORT"

    # Structure-led override when quant is neutral but structure is clear
    if bias == "خنثی":
        if long_votes >= 2.8 and short_votes <= 1.2 and score >= 52 and alignment >= 52:
            return "صعودی", "LONG"
        if short_votes >= 2.8 and long_votes <= 1.2 and score <= 48 and alignment >= 52:
            return "نزولی", "SHORT"

    return "خنثی", "WAIT"

# ============================================================
# AI LAYER
# ============================================================

DEFAULT_MODEL_SETTINGS = {
    "openai_models": ["gpt-4o-mini"],
    "gemini_models": ["gemini-2.5-flash", "gemini-2.0-flash"],
    "grok_models": ["grok-4-1-fast-reasoning"],
    "claude_models": ["claude-sonnet-4-6"],
    "deepseek_models": ["deepseek-chat"],
}


def _load_model_settings() -> dict[str, Any]:
    data = _load_json(MODEL_SETTINGS_PATH, DEFAULT_MODEL_SETTINGS)
    out = {k: list(v) for k, v in DEFAULT_MODEL_SETTINGS.items()}
    if isinstance(data, dict):
        for key in out:
            if isinstance(data.get(key), list):
                vals = [str(x).strip() for x in data[key] if str(x).strip()]
                if vals: out[key] = vals
    return out


def _build_ai_prompt(payload: dict[str, Any]) -> str:
    return (
        "دستور اجباری زبان: فقط فارسی. هیچ کلمه لاتین، انگلیسی یا مخفف انگلیسی ننویس. "
        "به‌جای Long بگو خرید/صعودی، به‌جای Short بگو فروش/نزولی، به‌جای Wait بگو انتظار. "
        "به‌جای RSI بگو شاخص قدرت نسبی، به‌جای VWAP بگو میانگین وزنی حجم، به‌جای Funding بگو نرخ تأمین مالی. "
        "تو تحلیل‌گر محافظه‌کار بازار رمزارز هستی. فقط از داده‌های زیر استفاده کن. تضمین سود نده. "
        "تناقض روند، مومنتوم، میانگین‌ها، حجم و مشتقات را بگو. حداکثر ۵ جمله کوتاه فارسی روان. "
        "جمله آخر دقیقاً با یکی از این سه قالب تمام شود: «نتیجه نهایی: صعودی» یا «نتیجه نهایی: نزولی» یا «نتیجه نهایی: انتظار».\n"
        + json.dumps(payload, ensure_ascii=False, default=str)
    )


def _cache_key(provider: str, model: str, payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps({"provider": provider, "model": model, "payload": payload}, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _cached_ai(provider: str, model: str, payload: dict[str, Any], ttl: int = AI_CACHE_TTL) -> Optional[str]:
    cache = _load_json(AI_CACHE_PATH, {})
    item = cache.get(_cache_key(provider, model, payload)) if isinstance(cache, dict) else None
    if isinstance(item, dict) and time.time() - safe_float(item.get("ts"), 0) < ttl:
        return str(item.get("text")) if item.get("text") else None
    return None


def _store_ai(provider: str, model: str, payload: dict[str, Any], text: str) -> None:
    cache = _load_json(AI_CACHE_PATH, {})
    if not isinstance(cache, dict): cache = {}
    cache[_cache_key(provider, model, payload)] = {"ts": time.time(), "text": text}
    if len(cache) > 800:
        items = sorted(cache.items(), key=lambda x: safe_float(x[1].get("ts"), 0))
        for key, _ in items[:len(cache) - 800]: cache.pop(key, None)
    _save_json(AI_CACHE_PATH, cache)


def _persianize_ai_text(value: str) -> str:
    """Light glossary swap so dashboard stays Persian even if model leaks English terms."""
    if not value:
        return value
    pairs = [
        ("LONG", "خرید"), ("SHORT", "فروش"), ("WAIT", "انتظار"),
        ("Long", "خرید"), ("Short", "فروش"), ("Wait", "انتظار"),
        ("bullish", "صعودی"), ("bearish", "نزولی"), ("neutral", "خنثی"),
        ("Bullish", "صعودی"), ("Bearish", "نزولی"), ("Neutral", "خنثی"),
        ("support", "حمایت"), ("resistance", "مقاومت"),
        ("Support", "حمایت"), ("Resistance", "مقاومت"),
        ("Funding", "نرخ تأمین مالی"), ("funding", "نرخ تأمین مالی"),
        ("Open Interest", "بهره باز"), ("open interest", "بهره باز"),
        ("momentum", "مومنتوم"), ("Momentum", "مومنتوم"),
        ("breakout", "شکست سطح"), ("Breakout", "شکست سطح"),
        ("overbought", "اشباع خرید"), ("oversold", "اشباع فروش"),
        ("risk", "ریسک"), ("Risk", "ریسک"),
        ("entry", "ورود"), ("stop loss", "حد ضرر"), ("take profit", "حد سود"),
        ("Buy", "خرید"), ("Sell", "فروش"), ("buy", "خرید"), ("sell", "فروش"),
        ("HIGH CONVICTION", "اطمینان بالا"), ("CONFIRMED SETUP", "ستاپ تأییدشده"),
        ("WATCH", "تحت نظر"), ("LOW EDGE", "لبه ضعیف"),
    ]
    out = value
    for en, fa in pairs:
        out = out.replace(en, fa)
    return out


def _clean_ai_text(text: Any) -> str:
    """Normalize AI output and push toward Persian dashboard display."""
    if text is None:
        return ""
    if isinstance(text, (list, tuple)):
        text = " ".join(str(x) for x in text)
    value = " ".join(str(text).strip().split())
    if not value:
        return ""
    value = _persianize_ai_text(value)
    return value[:12000]


def _extract_gemini_text(response: dict[str, Any]) -> str:
    chunks: list[str] = []
    for candidate in response.get("candidates", []) or []:
        for part in (candidate.get("content") or {}).get("parts", []) or []:
            if part.get("text"): chunks.append(str(part["text"]))
    return _clean_ai_text(" ".join(chunks))


def _extract_chat_completion(response: dict[str, Any]) -> str:
    try:
        choices = response.get("choices") or []
        if not choices: return ""
        content = (choices[0].get("message") or {}).get("content", "")
        if isinstance(content, list):
            content = " ".join(str(x.get("text", "")) for x in content if isinstance(x, dict))
        return _clean_ai_text(content)
    except Exception:
        return ""


def _extract_openai_response(response: dict[str, Any]) -> str:
    """Extract text from the OpenAI Responses API across compatible response shapes."""
    try:
        # Preferred Responses API convenience field.
        output_text = response.get("output_text")
        if output_text:
            return _clean_ai_text(output_text)

        chunks: list[str] = []
        for item in response.get("output", []) or []:
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []) or []:
                if not isinstance(content, dict):
                    continue
                if content.get("text"):
                    chunks.append(str(content["text"]))
        return _clean_ai_text(" ".join(chunks))
    except Exception:
        return ""


GEMINI_LAST_ERROR = ""
_GEMINI_MODEL_CACHE: dict[str, Any] = {"ts": 0.0, "models": []}
_GEMINI_MODEL_CACHE_TTL = 900.0
_GEMINI_MODEL_LOCK = threading.RLock()

def _gemini_available_models(force: bool = False) -> list[str]:
    """Return configured Gemini models first and cache API discovery.

    Model discovery is metadata, not market data; repeating it for every coin
    creates needless latency and can itself consume rate-limit budget.
    """
    configured = [str(x).strip() for x in _load_model_settings().get("gemini_models", []) if str(x).strip()]
    now = time.time()
    with _GEMINI_MODEL_LOCK:
        cached = list(_GEMINI_MODEL_CACHE.get("models") or [])
        if cached and not force and now - safe_float(_GEMINI_MODEL_CACHE.get("ts"), 0) < _GEMINI_MODEL_CACHE_TTL:
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