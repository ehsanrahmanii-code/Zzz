                    wins INTEGER DEFAULT 0,
                    losses INTEGER DEFAULT 0,
                    reward_sum REAL DEFAULT 0,
                    penalty_sum REAL DEFAULT 0,
                    weight REAL DEFAULT 1.0,
                    updated_at REAL
                )"""
            )
            con.execute(
                """CREATE TABLE IF NOT EXISTS central_arbiter_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at REAL,
                    symbol TEXT,
                    decision TEXT,
                    verdict TEXT,
                    score REAL,
                    notes TEXT
                )"""
            )
            con.commit()
    except Exception as exc:
        LOGGER.debug("central schema: %s", exc)


def _central_load_weights() -> None:
    global _CENTRAL_WEIGHTS
    try:
        with DB_LOCK, db_conn() as con:
            rows = con.execute(
                "SELECT component,samples,wins,losses,reward_sum,penalty_sum,weight FROM central_component_stats"
            ).fetchall()
        weights = dict(_CENTRAL_WEIGHTS_DEFAULT)
        for row in rows:
            name, samples, wins, losses, reward, penalty, w = row
            # Ignore components from retired decision generations.  Otherwise an
            # old DB can silently resurrect removed/circular voters.
            if name not in _CENTRAL_WEIGHTS_DEFAULT:
                continue
            n = int(samples or 0)
            if n >= 12:
                wr = (wins or 0) / max(1, (wins or 0) + (losses or 0))
                reliability = clamp(0.55 + (wr - 0.5) * 1.4, 0.35, 1.55)
                # mild reward/penalty tilt
                tilt = 1.0 + 0.04 * safe_float(reward, 0) - 0.05 * safe_float(penalty, 0)
                w = clamp(safe_float(_CENTRAL_WEIGHTS_DEFAULT.get(name), 1.0) * reliability * tilt, 0.25, 2.4)
            else:
                w = safe_float(_CENTRAL_WEIGHTS_DEFAULT.get(name), 1.0)
            weights[name] = float(w)
        with _CENTRAL_WEIGHT_LOCK:
            _CENTRAL_WEIGHTS = weights
    except Exception as exc:
        LOGGER.debug("central weight load: %s", exc)


_central_init_schema()
_edge_lab_init_schema()
_central_load_weights()


def _central_votes(item: dict[str, Any]) -> dict[str, dict[str, Any]]:
    votes: dict[str, dict[str, Any]] = {}
    tf = item.get("tf_scores") or item.get("tfs") or {}
    s15 = safe_float(tf.get("15m"), 50.0)
    s1h = safe_float(tf.get("1h"), 50.0)
    s4h = safe_float(tf.get("4h"), 50.0)
    s1d = safe_float(tf.get("1d"), 50.0)
    htf = 0.55 * s4h + 0.45 * s1d
    mtf = s1h
    ltf = s15

    def _from_score(sc: float) -> tuple[float, float, str]:
        lean = clamp((sc - 50.0) / 50.0, -1.0, 1.0)
        conf = clamp(abs(sc - 50.0) / 50.0, 0.0, 1.0)
        side = "LONG" if lean > 0.08 else "SHORT" if lean < -0.08 else "WAIT"
        return lean, conf, side

    for key, sc, label in (
        ("htf_trend", htf, "روند کلان 4h/1d"),
        ("mtf_setup", mtf, "ستاپ 1h"),
        ("ltf_trigger", ltf, "تریگر 15m"),
    ):
        lean, conf, side = _from_score(sc)
        votes[key] = {"lean": lean, "confidence": conf, "side": side, "raw": sc, "label": label}

    score = safe_float(item.get("score"), 50.0)
    lean, conf, side = _from_score(score)
    votes["momentum"] = {"lean": lean, "confidence": conf, "side": side, "raw": score, "label": "مومنتوم هسته"}

    structure = item.get("structure") or {}
    sb = str(structure.get("bias") or item.get("structure_bias") or item.get("bias") or "")
    if sb in {"صعودی", "LONG"}:
        lean, conf = 0.55, 0.55
    elif sb in {"نزولی", "SHORT"}:
        lean, conf = -0.55, 0.55
    else:
        lean, conf = 0.0, 0.2
    votes["structure"] = {
        "lean": lean, "confidence": conf,
        "side": "LONG" if lean > 0 else "SHORT" if lean < 0 else "WAIT",
        "raw": sb or "خنثی", "label": "ساختار قیمت",
    }

    taker_buy = safe_float(item.get("taker_buy_pct"), 50.0)
    if taker_buy == 50 and isinstance(item.get("buy_sell"), dict):
        taker_buy = safe_float((item.get("buy_sell") or {}).get("buy_pct"), 50.0)
    vol_lean = clamp((taker_buy - 50.0) / 35.0, -1.0, 1.0)
    votes["volume_flow"] = {
        "lean": vol_lean,
        "confidence": clamp(abs(taker_buy - 50.0) / 35.0, 0.0, 1.0),
        "side": "LONG" if vol_lean > 0.12 else "SHORT" if vol_lean < -0.12 else "WAIT",
        "raw": taker_buy, "label": "جریان حجم",
    }

    deriv = item.get("derivatives") if isinstance(item.get("derivatives"), dict) else {}
    funding = safe_float(item.get("funding_value"), safe_float(deriv.get("funding_value"), 0.0))
    oi_delta = safe_float(item.get("oi_delta"), safe_float(deriv.get("oi_delta"), 0.0))
    fund_lean = clamp(-funding * 8.0, -1.0, 1.0)
    oi_lean = clamp(oi_delta / 8.0, -1.0, 1.0)
    d_lean = clamp(0.6 * fund_lean + 0.4 * oi_lean, -1.0, 1.0)
    votes["derivatives"] = {
        "lean": d_lean, "confidence": clamp(abs(d_lean), 0.0, 1.0),
        "side": "LONG" if d_lean > 0.12 else "SHORT" if d_lean < -0.12 else "WAIT",
        "raw": {"funding": funding, "oi_delta": oi_delta}, "label": "مشتقات",
    }

    patterns = item.get("patterns") or item.get("pattern_pack") or {}
    pbias = safe_float(patterns.get("score_bias") if isinstance(patterns, dict) else 0.0, safe_float(item.get("pattern_bias"), 0.0))
    p_lean = clamp(pbias / 4.0, -1.0, 1.0)
    votes["pattern"] = {
        "lean": p_lean, "confidence": clamp(abs(p_lean), 0.0, 1.0),
        "side": "LONG" if p_lean > 0.15 else "SHORT" if p_lean < -0.15 else "WAIT",
        "raw": pbias, "label": "الگوی نموداری",
    }

    fc = item.get("candle_forecast") or item.get("forecast") or {}
    fc_bias = str(fc.get("overall_bias") or "")
    if fc_bias == "صعودی":
        f_lean, f_conf = 0.45, 0.4
    elif fc_bias == "نزولی":
        f_lean, f_conf = -0.45, 0.4
    else:
        f_lean, f_conf = 0.0, 0.15
    path_strength = safe_float(fc.get("path_strength"), 0.0) / 40.0
    f_conf = clamp(f_conf + path_strength * 0.3, 0.0, 1.0)
    votes["forecast_path"] = {
        "lean": f_lean, "confidence": f_conf,
        "side": "LONG" if f_lean > 0 else "SHORT" if f_lean < 0 else "WAIT",
        "raw": fc_bias or "خنثی", "label": "مسیر پیش‌بینی",
    }

    # Do NOT vote the previous canonical decision back into the new canonical
    # decision.  It is derived from many of the same inputs and would create
    # circular reinforcement.  It remains available in the audit payload only.

    learning = item.get("v32_learning") or {}
    long_adj = safe_float(learning.get("long_adjustment"), 0.0)
    short_adj = safe_float(learning.get("short_adjustment"), 0.0)
    learn_lean = clamp((long_adj - short_adj) / 8.0, -1.0, 1.0)
    votes["learning_v32"] = {
        "lean": learn_lean,
        "confidence": clamp(abs(learn_lean), 0.0, 1.0),
        "side": "LONG" if learn_lean > 0.12 else "SHORT" if learn_lean < -0.12 else "WAIT",
        "raw": {"long_adj": long_adj, "short_adj": short_adj},
        "label": "یادگیری تاریخی",
    }

    ai = item.get("ai_ensemble") or item.get("ai_opinions") or (item.get("edge") or {}).get("ai") or {}
    ai_side = str(ai.get("majority") or ai.get("side") or item.get("ai_majority") or "WAIT").upper()
    if ai_side in {"صعودی", "BUY", "LONG"}:
        a_lean, a_side = 0.5, "LONG"
    elif ai_side in {"نزولی", "SELL", "SHORT"}:
        a_lean, a_side = -0.5, "SHORT"
    else:
        a_lean, a_side = 0.0, "WAIT"
    a_conf = clamp(safe_float(ai.get("agreement"), 0.0) / 100.0, 0.0, 1.0)
    votes["ai_vote"] = {
        "lean": a_lean, "confidence": max(a_conf, 0.15 if a_side != "WAIT" else 0.05),
        "side": a_side, "raw": ai_side, "label": "رأی AI",
    }

    dq = item.get("data_quality") or {}
    trust = safe_float(dq.get("score"), safe_float(item.get("data_trust"), safe_float(item.get("trust_index"), 70.0)))
    votes["data_trust"] = {
        "lean": 0.0, "confidence": clamp(trust / 100.0, 0.0, 1.0),
        "side": "WAIT", "raw": trust, "label": "اعتماد داده", "trust": trust,
    }
    return votes


def _central_decide(item: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    votes = _central_votes(item)
    with _CENTRAL_WEIGHT_LOCK:
        weights = dict(_CENTRAL_WEIGHTS)

    long_score = short_score = weight_sum = 0.0
    details = []
    for name, v in votes.items():
        if name == "data_trust":
            continue
        w = safe_float(weights.get(name), 1.0)
        lean = safe_float(v.get("lean"), 0.0)
        conf = safe_float(v.get("confidence"), 0.0)
        effective = w * conf
        weight_sum += effective
        if lean > 0:
            long_score += effective * lean
        elif lean < 0:
            short_score += effective * abs(lean)
        details.append({
            "component": name, "label": v.get("label"), "side": v.get("side"),
            "lean": round(lean, 4), "confidence": round(conf, 4), "weight": round(w, 4),
            "contribution": round(effective * lean, 4), "raw": v.get("raw"),
        })
    if weight_sum > 0:
        long_score /= weight_sum
        short_score /= weight_sum

    trust = safe_float((votes.get("data_trust") or {}).get("trust"), 70.0)
    margin = abs(long_score - short_score)
    edge = max(long_score, short_score)
    reasons: list[str] = []
    candidate = "LONG" if long_score > short_score else "SHORT" if short_score > long_score else "WAIT"

    overlap = _edge_overlap_gate(_normalize_symbol(item.get("symbol") or ""), candidate)
    if candidate in {"LONG", "SHORT"} and not overlap.get("ok", True):
        reasons.append(str(overlap.get("reason") or "overlap risk"))
        candidate = "WAIT"

    price = safe_float(str(item.get("price_raw") or item.get("live_price") or item.get("price") or "0").replace(",", ""), 0.0)
    if price <= 0:
        reasons.append("قیمت نامعتبر")
    if trust < _CENTRAL_MIN_TRUST:
        reasons.append(f"اعتماد داده پایین ({trust:.0f})")
    if edge < _CENTRAL_MIN_EDGE:
        reasons.append(f"لبه تصمیم ناکافی ({edge:.3f})")
    if margin < _CENTRAL_MIN_MARGIN:
        reasons.append(f"حاشیه LONG/SHORT کم ({margin:.3f})")

    htf_side = str((votes.get("htf_trend") or {}).get("side") or "WAIT")
    htf_conf = safe_float((votes.get("htf_trend") or {}).get("confidence"), 0)
    if candidate == "LONG" and htf_side == "SHORT" and htf_conf >= 0.35:
        reasons.append("روند کلان مخالف لانگ")
        candidate = "WAIT"
    if candidate == "SHORT" and htf_side == "LONG" and htf_conf >= 0.35:
        reasons.append("روند کلان مخالف شورت")
        candidate = "WAIT"

    # Level integrity / rebuild
    rr1 = safe_float(item.get("rr_tp1"), 0.0)
    if candidate in {"LONG", "SHORT"} and price > 0:
        sl = safe_float(str(item.get("stop_loss") or "0").replace(",", ""), 0.0)
        tp1 = safe_float(str(item.get("tp1") or "0").replace(",", ""), 0.0)
        tp2 = safe_float(str(item.get("tp2") or "0").replace(",", ""), 0.0)
        atr = safe_float(item.get("atr"), price * 0.012) or price * 0.012
        if candidate == "LONG":
            bad = (
                sl <= 0 or tp1 <= 0 or tp2 <= 0
                or not (sl < price < tp1 < tp2)
            )
            if bad:
                sl, tp1, tp2 = price - 1.35 * atr, price + 2.3 * atr, price + 3.5 * atr
        else:
            bad = (
                sl <= 0 or tp1 <= 0 or tp2 <= 0
                or not (tp2 < tp1 < price < sl)
            )
            if bad:
                sl, tp1, tp2 = price + 1.35 * atr, price - 2.3 * atr, price - 3.5 * atr
        item["stop_loss"] = round(sl, 8)
        item["tp1"] = round(tp1, 8)
        item["tp2"] = round(tp2, 8)
        item["stop_loss_raw"] = float(sl)
        item["tp1_raw"] = float(tp1)
        item["tp2_raw"] = float(tp2)
        rr1 = abs(tp1 - price) / max(abs(price - sl), 1e-12)
        rr2 = abs(tp2 - price) / max(abs(price - sl), 1e-12)
        item["rr_tp1"] = round(rr1, 3)
        item["rr_tp2"] = round(rr2, 3)
        item["effective_rr_tp1"] = round(rr1, 3)
        item["effective_rr_tp2"] = round(rr2, 3)
        if rr1 < 1.08:
            reasons.append(f"R:R ضعیف ({rr1:.2f})")
            candidate = "WAIT"
        if candidate == "SHORT":
            if edge < _CENTRAL_MIN_EDGE_SHORT:
                reasons.append(f"لبه SHORT ناکافی ({edge:.3f})")
                candidate = "WAIT"
            if margin < _CENTRAL_MIN_MARGIN_SHORT:
                reasons.append(f"حاشیه SHORT کم ({margin:.3f})")
                candidate = "WAIT"

    decision = candidate if not reasons and candidate in {"LONG", "SHORT"} else "WAIT"
    if decision in {"LONG", "SHORT"}:
        reasons.append("داور مرکزی: اجماع وزنی شواهد کافی است")
    elif not reasons:
        reasons.append("شواهد برای ورود جهت‌دار کافی نیست")

    conf100 = clamp(50.0 + edge * 40.0 + margin * 25.0 + (trust - 50.0) * 0.15, 5.0, 92.0)
    if decision == "WAIT":
        conf100 = min(conf100, 55.0)