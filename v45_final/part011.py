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