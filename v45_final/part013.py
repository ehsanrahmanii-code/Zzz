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