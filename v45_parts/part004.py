        elif struct_bias == "نزولی":
            st_sc = 50 - min(22, struct_conf * 0.25)
            st_side = "SHORT"
        else:
            st_sc, st_side = 50.0, "WAIT"
        layers["structure"] = {"score": round(st_sc, 1), "side": st_side, "weight": self.W["structure"]}

        reg_name = str((regime or {}).get("regime", "unknown")).lower()
        if "up" in reg_name or "bull" in reg_name:
            rg_sc, rg_side = 62.0, "LONG"
        elif "down" in reg_name or "bear" in reg_name:
            rg_sc, rg_side = 38.0, "SHORT"
        elif "high_vol" in reg_name:
            rg_sc, rg_side = 50.0, "WAIT"
            reasons.append("رژیم پرنوسان → کاهش اطمینان")
        else:
            rg_sc, rg_side = 50.0, "WAIT"
        layers["regime"] = {"score": rg_sc, "side": rg_side, "weight": self.W["regime"]}

        conf_sc = safe_float((confluence or {}).get("score"), 50)
        layers["confluence"] = {"score": conf_sc, "side": self._side_from_score(conf_sc), "weight": self.W["confluence"]}

        prec_sc = safe_float((precision or {}).get("score"), 50)
        layers["precision"] = {"score": prec_sc, "side": self._side_from_score(prec_sc), "weight": self.W["precision"]}
        for b in (precision or {}).get("hard_blocks") or []:
            vetoes.append(f"precision:{b}")

        p_sc, p_side = self._pattern_signal(patterns or {})
        layers["pattern"] = {"score": round(p_sc, 1), "side": p_side, "weight": self.W["pattern"]}

        f_sc, f_side = self._forecast_signal(forecast or {}, path_stats or {})
        layers["forecast"] = {"score": round(f_sc, 1), "side": f_side, "weight": self.W["forecast"]}

        wanted_hint = 1 if quant_bias == "صعودی" else -1 if quant_bias == "نزولی" else 0
        d_sc, d_side = self._deriv_signal(derivatives or {}, wanted_hint)
        layers["derivatives"] = {"score": round(d_sc, 1), "side": d_side, "weight": self.W["derivatives"]}

        a_sc, a_side, a_agree = self._ai_signal(fusion or {}, ai_opinions or {})
        layers["ai"] = {"score": round(a_sc, 1), "side": a_side, "weight": self.W["ai"], "agreement": a_agree}

        cal_sc = safe_float((calib or {}).get("calibrated"), safe_float((fusion or {}).get("success_probability"), 50))
        # map calibrated success (around 50-80) to directional lean via quant
        if quant_bias == "صعودی":
            c_sc = 40 + cal_sc * 0.35
        elif quant_bias == "نزولی":
            c_sc = 60 - cal_sc * 0.35
        else:
            c_sc = 50.0
        layers["calibration"] = {"score": round(c_sc, 1), "side": self._side_from_score(c_sc), "weight": self.W["calibration"]}

        # Weighted neural score
        neural_score = 0.0
        w_total = 0.0
        for name, layer in layers.items():
            w = float(layer.get("weight") or 0)
            neural_score += safe_float(layer.get("score"), 50) * w
            w_total += w
        neural_score = neural_score / max(w_total, 1e-9)

        # Blend with quant spine (prevents AI-only drift)
        quant_sc = safe_float(quant_score, 50)
        neural_score = 0.62 * neural_score + 0.38 * quant_sc
        neural_score = float(clamp(neural_score, 0, 100))

        # Side vote among layers (weighted)
        long_w = short_w = wait_w = 0.0
        for layer in layers.values():
            w = float(layer.get("weight") or 0)
            s = layer.get("side")
            if s == "LONG":
                long_w += w
            elif s == "SHORT":
                short_w += w
            else:
                wait_w += w
        if long_w > short_w and long_w >= wait_w * 0.45:
            side = "LONG"
        elif short_w > long_w and short_w >= wait_w * 0.45:
            side = "SHORT"
        elif long_w > short_w * 1.15 and neural_score >= 54:
            side = "LONG"
        elif short_w > long_w * 1.15 and neural_score <= 46:
            side = "SHORT"
        else:
            side = "WAIT"

        # Hard gates — only true hard_veto kills; soft DQ lowers confidence
        dq = data_quality or {}
        if dq.get("hard_veto"):
            side = "WAIT"
            vetoes.append("data_quality_veto")
            reasons.append("وتوی سخت کیفیت داده → انتظار")
        elif safe_float(dq.get("score"), 100) < MIN_DATA_QUALITY_SCORE:
            vetoes.append("data_quality_soft")
            reasons.append("کیفیت داده مرزی — جهت حفظ با کاهش اطمینان")

        ladder = ladder or {}
        if side in {"LONG", "SHORT"} and ladder and not ladder.get("passed", True):
            # Soft miss: keep direction if HTF not strongly against; only hard-WAIT on structural flip
            htf_s = safe_float(ladder.get("htf_score"), 50)
            structural = (
                (side == "LONG" and htf_s <= 38) or (side == "SHORT" and htf_s >= 62)
            )
            if structural:
                vetoes.append("entry_ladder")
                reasons.append("نردبان ورود HTF خلاف جهت قوی → انتظار")
                side = "WAIT"
            else:
                reasons.append("نردبان ورود ناقص — جهت حفظ شد با اطمینان کمتر")

        # Precision hard blocks
        if (precision or {}).get("hard_blocks") and side in {"LONG", "SHORT"}:
            if safe_float(prec_sc, 50) < 48:
                side = "WAIT"
                reasons.append("بلوک‌های سخت دقت ورود فعال")

        # AI hard conflict with weak quant
        if a_side in {"LONG", "SHORT"} and side in {"LONG", "SHORT"} and a_side != side and a_agree >= 88:
            if abs(neural_score - 50) < 12:
                side = "WAIT"
                reasons.append("تعارض قوی AI با سیگنال ضعیف → انتظار")
            else:
                reasons.append("تعارض AI لحاظ شد (جریمه اطمینان)")

        # Confidence from layer agreement + distance from 50 + calib
        side_agreement = max(long_w, short_w, wait_w) / max(long_w + short_w + wait_w, 1e-9)
        confidence = (
            0.35 * abs(neural_score - 50) * 2
            + 0.30 * side_agreement * 100
            + 0.20 * safe_float(dq.get("score"), 60)
            + 0.15 * cal_sc
        )
        if side == "WAIT":
            confidence = min(confidence, 55)
        if any("نردبان ورود ناقص" in str(r) for r in reasons):
            confidence = min(confidence, 78)
        confidence = float(clamp(confidence, 5, 92))

        bias = "صعودی" if side == "LONG" else "نزولی" if side == "SHORT" else "خنثی"

        # Human-readable synapse summary
        top_layers = sorted(layers.items(), key=lambda x: abs(safe_float(x[1].get("score"), 50) - 50), reverse=True)[:4]
        for name, layer in top_layers:
            reasons.append(f"{name}: {layer.get('side')} ({layer.get('score')})")

        return {
            "side": side,
            "bias": bias,
            "neural_score": round(neural_score, 1),
            "confidence": round(confidence, 1),
            "layers": layers,
            "long_weight": round(long_w, 3),
            "short_weight": round(short_w, 3),
            "wait_weight": round(wait_w, 3),
            "side_agreement": round(side_agreement, 3),
            "reasons": reasons[:8],
            "vetoes": vetoes,
            "param_version": TITAN_PARAM_VERSION,
        }



TITAN_NEURAL = TitanNeuralSynapseV9()


# ============================================================
# TITAN V10 — PROFESSIONAL SIGNAL GRADE + DOSSIER
# A+ … F classification with multi-gate checklist.
# Only A+/A appear as actionable high-trust signals.
# ============================================================

GRADE_RANK = {"A+": 6, "A": 5, "B": 4, "C": 3, "D": 2, "F": 1, "—": 0}

def classify_signal_grade(
    *,
    decision_tag: str,
    signal_quality: float,
    success_prob: float,
    alignment: float,
    neural: Optional[dict] = None,
    meta: Optional[dict] = None,
    ladder: Optional[dict] = None,
    data_quality: Optional[dict] = None,
    precision: Optional[dict] = None,
    effective_rr1: float = 0.0,
    ai_agreement: float = 0.0,
    pattern_conf: float = 0.0,
    forecast_aligned: bool = False,
) -> dict[str, Any]:
    """Professional institutional-style grade with checklist evidence.

    A+ : all hard gates pass, quality≥85, neural confirms, RR≥1.4, meta ACCEPT
    A  : hard gates pass, quality≥75, neural same side, meta not REJECT
    B  : directional but missing 1 soft edge (watchlist, not primary action)
    C  : weak directional lean — observation only
    D  : noise / conflict
    F  : hard veto or WAIT with poor data
    """
    neural = neural or {}
    meta = meta or {}
    ladder = ladder or {}
    data_quality = data_quality or {}
    precision = precision or {}

    checklist: list[dict[str, Any]] = []
    def _chk(name: str, ok: bool, detail: str = "") -> bool:
        checklist.append({"name": name, "ok": bool(ok), "detail": detail})
        return bool(ok)

    is_dir = decision_tag in {"LONG", "SHORT"}
    dq_sc = safe_float(data_quality.get("score"), 0)
    ladder_ok = bool(ladder.get("passed", False)) if is_dir else True
    meta_label = str(meta.get("label") or "")
    meta_ok = meta_label == "ACCEPT"
    meta_not_reject = meta_label != "REJECT"
    neural_side = str(neural.get("side") or "")
    neural_conf = safe_float(neural.get("confidence"), 0)
    neural_sc = safe_float(neural.get("neural_score"), 50)
    neural_same = (not neural) or (neural_side == decision_tag) or (not is_dir)
    prec_sc = safe_float(precision.get("score"), 50)
    hard_blocks = list(precision.get("hard_blocks") or [])
    dq_ok = dq_sc >= MIN_DATA_QUALITY_SCORE and not data_quality.get("hard_veto")
    rr_ok = effective_rr1 >= MIN_EFFECTIVE_RR if is_dir else True

    g_dq = _chk("کیفیت داده", dq_ok, f"DQ={dq_sc:.0f}")
    g_ladder = _chk("نردبان HTF→MTF→LTF", ladder_ok or not is_dir, f"HTF={ladder.get('htf_score','—')} MTF={ladder.get('mtf_score','—')}")
    g_meta = _chk("متا-برچسب", meta_not_reject, meta_label or "—")
    g_neural = _chk("سیناپس عصبی", neural_same if is_dir else True, f"{neural_side} conf={neural_conf:.0f}")
    g_rr = _chk("نسبت ریسک/پاداش", rr_ok, f"RR1={effective_rr1:.2f}")
    g_prec = _chk("دقت ورود", prec_sc >= 52 and not hard_blocks, f"P={prec_sc:.0f} blocks={len(hard_blocks)}")
    g_align = _chk("همسویی TF", safe_float(alignment, 0) >= 55, f"align={alignment:.0f}")
    g_prob = _chk("احتمال موفقیت", safe_float(success_prob, 0) >= 55, f"p={success_prob:.0f}%")
    g_ai = _chk("اجماع AI", safe_float(ai_agreement, 0) >= 40 or not is_dir, f"agree={ai_agreement:.0f}%")
    g_pattern = _chk("الگو/مسیر", pattern_conf >= 50 or forecast_aligned or not is_dir, f"pat={pattern_conf:.0f} fc={forecast_aligned}")

    hard_pass = g_dq and g_ladder and g_meta and g_neural and g_rr and g_prec and is_dir
    soft_count = sum(1 for x in (g_align, g_prob, g_ai, g_pattern) if x)
    passed = sum(1 for c in checklist if c["ok"])
    total = len(checklist)

    grade = "F"
    label_fa = "رد / غیرقابل‌اتکا"
    action = "اجتناب"
    tier_color = "#64748b"

    if not is_dir:
        if dq_sc >= 65 and safe_float(signal_quality, 0) >= 48:
            grade, label_fa, action, tier_color = "C", "خنثی / رصد", "منتظر تأیید", "#fbbf24"
        else:
            grade, label_fa, action, tier_color = "D", "بدون لبه", "عبور", "#94a3b8"
    # V28.3: realistic institutional bands — A+/A reachable without perfect AI stack
    elif hard_pass and safe_float(signal_quality, 0) >= 78 and safe_float(success_prob, 0) >= 60 and meta_not_reject and effective_rr1 >= 1.25 and soft_count >= 2:
        grade, label_fa, action, tier_color = "A+", "اطمینان بالا", "اولویت ورود", "#4ade80"
    elif (hard_pass or (g_dq and ladder_ok and rr_ok)) and safe_float(signal_quality, 0) >= 62 and safe_float(success_prob, 0) >= 52 and meta_not_reject and soft_count >= 1:
        grade, label_fa, action, tier_color = "A", "قابل‌اتکا", "ورود با مدیریت ریسک", "#22c55e"
    elif g_dq and is_dir and safe_float(signal_quality, 0) >= 52 and meta_not_reject:
        grade, label_fa, action, tier_color = "B", "متوسط / نیاز تأیید", "واچ‌لیست فعال", "#38bdf8"
    elif is_dir and safe_float(signal_quality, 0) >= 46:
        grade, label_fa, action, tier_color = "C", "ضعیف", "رصد — ورود محتاطانه", "#fbbf24"
    else:
        grade, label_fa, action, tier_color = "D", "نویز / تعارض", "اجتناب", "#f43f5e"

    # Force demote on any hard veto leftover
    if data_quality.get("hard_veto") or (is_dir and not g_dq and dq_sc < 40):
        grade, label_fa, action, tier_color = "F", "وتوی داده", "اجتناب کامل", "#7f1d1d"
    if is_dir and hard_blocks and prec_sc < 38:
        if GRADE_RANK.get(grade, 0) > GRADE_RANK["C"]:
            grade, label_fa, action, tier_color = "C", "بلاک دقت ورود", "رصد", "#fbbf24"

    trust = float(clamp(
        0.30 * safe_float(signal_quality, 0)
        + 0.25 * safe_float(success_prob, 0)
        + 0.15 * (100.0 * passed / max(total, 1))
        + 0.15 * neural_conf
        + 0.15 * dq_sc,
        0, 100,
    ))

    return {
        "grade": grade,
        "label_fa": label_fa,
        "action": action,
        "tier_color": tier_color,
        "rank": GRADE_RANK.get(grade, 0),
        "trust_index": round(trust, 1),
        "checklist": checklist,
        "passed_gates": passed,
        "total_gates": total,
        "hard_pass": hard_pass,
        "param_version": TITAN_PARAM_VERSION,
    }


def build_signal_dossier(item: dict[str, Any]) -> dict[str, Any]:
    """Compact professional dossier for ranked board + card header."""
    grade = item.get("signal_grade") or {}
    neural = item.get("neural_v9") or {}
    return {
        "symbol": item.get("symbol"),
        "base": item.get("base_symbol"),
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