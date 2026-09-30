        "icon": item.get("coin_icon"),
        "name": item.get("coin_name"),
        "decision": item.get("decision_tag") or "WAIT",
        "bias": item.get("bias"),
        "grade": grade.get("grade", "—"),
        "grade_label": grade.get("label_fa", "—"),
        "action": grade.get("action", "—"),
        "trust": grade.get("trust_index", 0),
        "quality": item.get("signal_quality"),
        "success_prob": item.get("success_probability"),
        "score": item.get("score"),
        "alignment": item.get("alignment"),
        "neural_score": neural.get("neural_score") or item.get("neural_score"),
        "neural_conf": neural.get("confidence") or item.get("neural_confidence"),
        "price": item.get("price"),
        "entry": item.get("entry_valid"),
        "sl": item.get("stop_loss"),
        "tp1": item.get("tp1"),
        "tp2": item.get("tp2"),
        "rr1": item.get("rr_tp1"),
        "rr2": item.get("rr_tp2"),
        "tag": item.get("signal_tag"),
        "tier_color": grade.get("tier_color", "#94a3b8"),
    }


def rank_market_signals(market_data: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify market into actionable / watch / avoid boards (V28.3).

    - actionable: A+/A directional (primary board)
    - active: any LONG/SHORT (includes B) for HUD counts so the main page
      shows real directional activity, not only institutional A+
    - watchlist: B directional + high opportunity EARLY states
    """
    dossiers = [build_signal_dossier(x) for x in (market_data or []) if x]
    # Enrich dossier with opportunity fields from source items
    by_sym = {str(x.get("symbol")): x for x in (market_data or []) if x}
    for d in dossiers:
        src = by_sym.get(str(d.get("symbol"))) or {}
        d["opportunity_score"] = safe_float(src.get("opportunity_score"), 0)
        d["opportunity_state"] = str(src.get("opportunity_state") or "")
        d["entry_mode"] = str(src.get("entry_mode") or "")
    dossiers.sort(key=lambda d: (
        -GRADE_RANK.get(str(d.get("grade")), 0),
        -safe_float(d.get("opportunity_score"), 0),
        -safe_float(d.get("trust"), 0),
        -safe_float(d.get("quality"), 0),
        -safe_float(d.get("success_prob"), 0),
    ))
    actionable = [d for d in dossiers if d.get("grade") in {"A+", "A"} and d.get("decision") in {"LONG", "SHORT"}]
    active = [d for d in dossiers if d.get("decision") in {"LONG", "SHORT"}]
    watch = [
        d for d in dossiers
        if (d.get("grade") == "B" and d.get("decision") in {"LONG", "SHORT"})
        or str(d.get("opportunity_state") or "").startswith(("EARLY_", "WATCH_"))
    ]
    observe = [d for d in dossiers if d.get("grade") in {"C", "D"} or d.get("decision") == "WAIT"]
    avoid = [d for d in dossiers if d.get("grade") == "F"]
    long_n = sum(1 for d in active if d.get("decision") == "LONG")
    short_n = sum(1 for d in active if d.get("decision") == "SHORT")
    wait_n = sum(1 for d in dossiers if d.get("decision") == "WAIT")
    return {
        "all": dossiers,
        "actionable": actionable,
        "active": active,
        "watchlist": watch,
        "observe": observe[:12],
        "avoid": avoid,
        "counts": {
            "actionable": len(actionable),
            "active": len(active),
            "watch": len(watch),
            "observe": len(observe),
            "avoid": len(avoid),
            "long": long_n,
            "short": short_n,
            "wait": wait_n,
            "total": len(dossiers),
        },
        "top": (actionable[0] if actionable else (active[0] if active else (dossiers[0] if dossiers else None))),
        "top3": (actionable or active)[:3],
        "param_version": TITAN_PARAM_VERSION,
    }




class TitanDecisionCoreV2:
    def validate_data(self, payload: dict[str, Any]) -> bool:
        return all(k in payload and payload[k] is not None for k in ("price", "score"))

    def detect_regime(self, atr_pct: float = 0, trend_score: float = 50) -> str:
        if atr_pct > 5:
            return "high_volatility"
        if trend_score >= 60:
            return "bull_trend"
        if trend_score <= 40:
            return "bear_trend"
        return "sideways"

    def confidence(self, score: float, agreement: float = 100, risk: float = 0) -> float:
        result = float(score)
        result *= max(0.5, agreement / 100)
        result -= risk
        return max(0, min(100, round(result, 2)))

    def decide(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.validate_data(payload):
            return {"decision": "WAIT", "confidence": 0, "reason": "داده کافی نیست"}
        score = float(payload.get("score", 50))
        agreement = float(payload.get("agreement", 70))
        risk = float(payload.get("risk", 0))
        confidence = self.confidence(score, agreement, risk)
        decision = "WAIT"
        if confidence >= 65 and score >= 60:
            decision = "LONG"
        elif confidence >= 65 and score <= 40:
            decision = "SHORT"
        return {
            "decision": decision,
            "confidence": confidence,
            "regime": self.detect_regime(payload.get("atr_pct", 0), score),
            "explanation": ["داده اعتبارسنجی شد", "روند و ریسک بررسی شد", "تصمیم با فیلتر اطمینان صادر شد"],
        }

TITAN_DECISION_CORE = TitanDecisionCoreV2()


# ============================================================
# TITAN DECISION CORE V3 - SAFE INTEGRATION WRAPPER
# Restored from the user's original master build.
# ============================================================

def titan_final_decision(
    score=50,
    price=None,
    ai_votes=None,
    risk=0,
    atr_pct=0,
    metadata=None
):
    """Unified decision gateway for all existing engine outputs."""
    payload = {
        "score": score,
        "price": price,
        "risk": risk,
        "atr_pct": atr_pct,
        "metadata": metadata or {}
    }
    if ai_votes:
        numeric_votes = [float(v) for v in ai_votes.values() if isinstance(v, (int, float))] if isinstance(ai_votes, dict) else []
        payload["agreement"] = (sum(numeric_votes) / len(numeric_votes)) if numeric_votes else 50
        payload["ai_votes"] = ai_votes
    result = TITAN_DECISION_CORE.decide(payload)
    result["system_checks"] = {
        "data_validation": True,
        "confidence_filter": True,
        "risk_filter": True,
        "explainability": True
    }
    return result


def build_titan_analysis(*, symbol: str, price: float, rsi: float, vwap: float, ema20: float, ema50: float, atr: float,
                         volume_spike: bool, btc_trend: str, derivatives: dict[str, Any],
                         tf_results: dict[str, str], tf_scores: dict[str, float]) -> dict[str, Any]:
    vwap_dev = ((price - vwap) / vwap * 100.0) if vwap > 0 else 0.0
    funding = derivatives.get("funding_value")
    oi_delta = safe_float(derivatives.get("oi_delta"), 0.0)
    price_change_proxy = ((price / ema20) - 1.0) * 100.0 if ema20 > 0 else 0.0
    score = 50.0
    reasons_for: list[str] = []
    reasons_against: list[str] = []

    weights = [TF_CFG[t]["weight"] for t in tf_scores]
    weighted_tf = float(np.average(list(tf_scores.values()), weights=weights)) if tf_scores else 50.0
    score += weighted_tf - 50.0
    if ema20 > ema50:
        score += 5.0; reasons_for.append("EMA20 بالاتر از EMA50 است")
    elif ema20 < ema50:
        score -= 5.0; reasons_against.append("EMA20 پایین‌تر از EMA50 است")
    if price > vwap:
        score += 4.0; reasons_for.append("قیمت بالای VWAP است")
    elif price < vwap:
        score -= 4.0; reasons_against.append("قیمت پایین VWAP است")
    if volume_spike:
        if abs(price_change_proxy) > 0.15:
            score += 3.0
        reasons_for.append("حجم نسبت به میانگین بالاتر است")
    if btc_trend == "صعودی" and symbol != "BTC/USDT":
        score += 5.0; reasons_for.append("روند BTC پشتیبان صعود است")
    elif btc_trend == "نزولی" and symbol != "BTC/USDT":
        score -= 5.0; reasons_against.append("روند BTC فشار نزولی ایجاد می‌کند")
    f_adj, f_reason = _funding_bias(funding)
    score += f_adj
    if f_adj > 0: reasons_for.append(f_reason)
    elif f_adj < 0: reasons_against.append(f_reason)
    oi_adj, oi_reason = _oi_bias(oi_delta, price_change_proxy)
    score += oi_adj
    if oi_adj > 0: reasons_for.append(oi_reason)
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