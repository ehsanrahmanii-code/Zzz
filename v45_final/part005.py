    strength = float(clamp(
        (abs(htf - 50) * 0.4 + abs(mtf - 50) * 0.4 + abs(ltf - 50) * 0.2),
        0, 50,
    ))
    return {
        "passed": passed if wanted in {"LONG", "SHORT"} else True,
        "wanted": wanted,
        "htf_score": round(htf, 1),
        "mtf_score": round(mtf, 1),
        "ltf_score": round(ltf, 1),
        "htf_side": htf_side,
        "mtf_side": mtf_side,
        "ltf_side": ltf_side,
        "strength": round(strength, 1),
        "reasons": reasons,
        "tf_results": tf_results,
    }


def forecast_path_accuracy_stats(symbol: str = "") -> dict[str, Any]:
    """Recent directional accuracy of 12-candle path from tracked outcomes."""
    try:
        with _FORECAST_TRACK_LOCK:
            data = _load_forecast_track()
        rows = data.get("events") or []
        if symbol:
            rows = [r for r in rows if r.get("symbol") == symbol]
        rows = rows[-200:]
        if len(rows) < 5:
            return {"samples": len(rows), "dir_acc": 0.5, "weight_scale": 0.35, "mae_pct": None}
        hits = sum(1 for r in rows if r.get("dir_hit"))
        acc = hits / max(1, len(rows))
        # Weight scale: only trust path when accuracy clearly above coin-flip
        if len(rows) < 12:
            scale = 0.40
        elif acc >= 0.58:
            scale = min(1.15, 0.7 + (acc - 0.5) * 2.0)
        elif acc >= 0.52:
            scale = 0.55
        else:
            scale = 0.20
        maes = [safe_float(r.get("mae_pct"), 0) for r in rows if r.get("mae_pct") is not None]
        return {
            "samples": len(rows),
            "dir_acc": round(acc, 3),
            "weight_scale": round(scale, 3),
            "mae_pct": round(float(sum(maes) / len(maes)), 3) if maes else None,
        }
    except Exception as exc:
        LOGGER.debug("forecast track stats: %s", exc)
        return {"samples": 0, "dir_acc": 0.5, "weight_scale": 0.35, "mae_pct": None}


def record_forecast_path_outcome(
    symbol: str,
    predicted_bias: str,
    predicted_move_pct: float,
    actual_move_pct: float,
) -> None:
    """Append path accuracy event for self-weighting of forecast layer."""
    try:
        pred_sign = 1 if predicted_bias == "صعودی" else -1 if predicted_bias == "نزولی" else 0
        act_sign = 1 if actual_move_pct > 0.05 else -1 if actual_move_pct < -0.05 else 0
        dir_hit = bool(pred_sign and act_sign and pred_sign == act_sign)
        mae = abs(predicted_move_pct - actual_move_pct)
        with _FORECAST_TRACK_LOCK:
            data = _load_forecast_track()
            ev = data.setdefault("events", [])
            ev.append({
                "ts": time.time(),
                "symbol": symbol,
                "predicted_bias": predicted_bias,
                "pred_move_pct": round(predicted_move_pct, 4),
                "actual_move_pct": round(actual_move_pct, 4),
                "dir_hit": dir_hit,
                "mae_pct": round(mae, 4),
                "version": TITAN_PARAM_VERSION,
            })
            data["events"] = ev[-500:]
            _save_forecast_track(data)
    except Exception as exc:
        LOGGER.debug("record forecast path: %s", exc)


def calibrate_success_probability_v8(
    symbol: str = "",
    direction: str = "",
    raw_prob: float = 50.0,
    regime: str = "",
) -> dict[str, Any]:
    """Regime- and side-aware calibration with honest sample caps."""
    base = calibrate_success_probability(symbol=symbol, direction=direction, raw_prob=raw_prob)
    n = int(base.get("samples") or 0)
    cal = safe_float(base.get("calibrated"), raw_prob)
    # Conservative certainty caps by sample size
    if n < 8:
        cap = CALIB_CAP_LOW_N
        method = "prior_capped"
    elif n < CALIB_MIN_SAMPLES_FULL:
        cap = CALIB_CAP_MID_N
        method = str(base.get("method") or "mid_n") + "+cap"
    else:
        cap = CALIB_CAP_HIGH_N
        method = str(base.get("method") or "full")
    # Mild regime shrink when high-vol (harder to be sure)
    reg = str(regime or "").lower()
    if "high_vol" in reg or "high_volatility" in reg:
        cal = 50.0 + (cal - 50.0) * 0.85
        cap = min(cap, 70.0)
    cal = float(clamp(cal, 5.0, cap))
    base["calibrated"] = round(cal, 1)
    base["cap"] = cap
    base["method"] = method
    base["regime"] = regime or "unknown"
    base["direction"] = direction
    base["param_version"] = TITAN_PARAM_VERSION
    base["honest_label"] = (
        f"کالیبره {cal:.0f}% · n={n} · سقف {cap:.0f}% · {method}"
    )
    return base


def portfolio_side_pressure(decision_tag: str, symbol: str) -> dict[str, Any]:
    """Limit clustered same-side alt signals (correlation risk proxy)."""
    if decision_tag not in {"LONG", "SHORT"}:
        return {"ok": True, "same_side": 0, "penalty": 0.0, "reason": ""}
    now = time.time()
    with _PORTFOLIO_SIGNAL_LOCK:
        global _RECENT_DIRECTIONAL_SIGNALS
        _RECENT_DIRECTIONAL_SIGNALS = [
            s for s in _RECENT_DIRECTIONAL_SIGNALS
            if now - safe_float(s.get("ts"), 0) < 3600 and s.get("symbol") != symbol
        ]
        same = [s for s in _RECENT_DIRECTIONAL_SIGNALS if s.get("side") == decision_tag]
        count = len(same)
        penalty = 0.0
        ok = True
        reason = ""
        if count >= MAX_PORTFOLIO_SAME_SIDE:
            ok = False
            penalty = 15.0
            reason = f"سبد اشباع {decision_tag}: {count}+ سیگنال هم‌جهت در ۱ ساعت"
        elif count >= MAX_PORTFOLIO_SAME_SIDE - 1:
            penalty = 8.0
            reason = f"فشار سبد {decision_tag}: {count} سیگنال هم‌جهت"
        return {"ok": ok, "same_side": count, "penalty": penalty, "reason": reason}


def register_portfolio_signal(symbol: str, decision_tag: str) -> None:
    if decision_tag not in {"LONG", "SHORT"}:
        return
    with _PORTFOLIO_SIGNAL_LOCK:
        _RECENT_DIRECTIONAL_SIGNALS.append({
            "symbol": symbol, "side": decision_tag, "ts": time.time(), "v": TITAN_PARAM_VERSION,
        })
        if len(_RECENT_DIRECTIONAL_SIGNALS) > 80:
            del _RECENT_DIRECTIONAL_SIGNALS[:-60]


def extract_structured_ai_vote(text: str) -> dict[str, Any]:
    """Parse free-text or JSON-ish AI reply into side + confidence."""
    t = str(text or "").strip()
    if not t:
        return {"side": "WAIT", "confidence": 0, "raw": ""}
    # Try JSON fragment
    try:
        if "{" in t and "}" in t:
            frag = t[t.find("{"): t.rfind("}") + 1]
            obj = json.loads(frag)
            side = str(obj.get("side") or obj.get("decision") or obj.get("bias") or "WAIT").upper()
            if side in {"صعودی", "LONG", "BUY"}:
                side = "LONG"
            elif side in {"نزولی", "SHORT", "SELL"}:
                side = "SHORT"
            else:
                side = "WAIT"
            conf = safe_float(obj.get("confidence", obj.get("prob", 50)), 50)
            return {"side": side, "confidence": float(clamp(conf, 0, 100)), "raw": t[:200]}
    except Exception:
        pass
    low = t.lower()
    # Prefer an explicit final decision over incidental words such as
    # "کاهش ریسک" or "رشد هزینه" that are not a market-direction vote.
    final_markers = (
        ("نتیجه نهایی", "fa"), ("final result", "en"),
        ("decision", "en"), ("تصمیم", "fa"),
    )
    final_chunk = ""
    for marker, _ in final_markers:
        pos = low.rfind(marker.lower()) if marker.isascii() else t.rfind(marker)
        if pos >= 0:
            final_chunk = t[pos:pos + 140]
            break
    final_low = final_chunk.lower()
    if final_chunk:
        if any(k in final_low or k in final_chunk for k in ("نزولی", "فروش", "short", "sell")):
            side = "SHORT"
        elif any(k in final_low or k in final_chunk for k in ("صعودی", "خرید", "long", "buy")):
            side = "LONG"
        elif any(k in final_low or k in final_chunk for k in ("انتظار", "wait", "خنثی", "neutral", "no trade")):
            side = "WAIT"
        else:
            side = "WAIT"
    else:
        # Fallback lexical parser. Keep phrases with explicit direction rather
        # than generic words like "کاهش" which frequently describe risk/volatility.
        short_keys = ("short", "sell", "نزولی", "فروش", "ریزش", "نزول")
        long_keys = ("long", "buy", "صعودی", "خرید", "رشد", "صعود")
        wait_keys = ("wait", "خنثی", "انتظار", "no trade", "حاشیه‌نشین")
        side = "WAIT"
        if any(k in low or k in t for k in short_keys):
            side = "SHORT"
        elif any(k in low or k in t for k in long_keys):
            side = "LONG"
        if any(k in low or k in t for k in wait_keys) and side != "WAIT":
            if t.count("انتظار") + low.count("wait") >= 1 and ("اما" in t or "but" in low):
                side = "WAIT"
    conf = 55.0
    for token in ("90", "85", "80", "75", "70", "65", "60"):
        if token in t:
            conf = float(token)
            break
    if side == "WAIT":
        conf = min(conf, 50)
    return {"side": side, "confidence": conf, "raw": t[:200]}


def meta_label_v8(
    *,
    confluence_score: float,
    precision_score: float,
    alignment: float,
    success_prob: float,
    ai_conflict: bool,
    stretch_atr: float,
    ladder_passed: bool,
    data_quality: float,
    hist_wr: float,
) -> dict[str, Any]:
    """Second-stage accept/reject: only ACCEPT enables high-conviction tags."""
    score = (
        0.22 * safe_float(confluence_score, 50)
        + 0.20 * safe_float(precision_score, 50)
        + 0.15 * safe_float(alignment, 50)
        + 0.18 * safe_float(success_prob, 50)
        + 0.12 * safe_float(data_quality, 50)
        + 0.08 * safe_float(hist_wr, 50)
        + 0.05 * (70 if ladder_passed else 30)
    )
    if ai_conflict:
        score -= 5
    if stretch_atr > 3.4:
        score -= min(12.0, (stretch_atr - 3.4) * 4)
    score = float(clamp(score, 0, 100))
    if score >= 62 and data_quality >= (MIN_DATA_QUALITY_SCORE - 4) and not ai_conflict:
        label = "ACCEPT"
    elif score < 42 or data_quality < 42:
        label = "REJECT"
    else:
        label = "WATCH"
    return {
        "label": label,
        "probability": round(score, 1),
        "param_version": TITAN_PARAM_VERSION,
        "gates": {
            "ladder": ladder_passed,
            "dq": data_quality >= MIN_DATA_QUALITY_SCORE,
            "ai_conflict": ai_conflict,
        },
    }



def smart_format(value: Any) -> str:
    try:
        number = float(value)
        if not math.isfinite(number):
            return "N/A"
    except (TypeError, ValueError):
        return "N/A"
    if abs(number) >= 100:
        return f"{number:,.2f}"
    if abs(number) >= 1:
        return f"{number:,.4f}"
    if abs(number) >= 0.0001:
        return f"{number:,.6f}"
    return f"{number:.8f}"


def _normalize_symbol(symbol: str) -> str:
    value = str(symbol or "").upper().replace("-", "/").replace(" ", "")
    if not value:
        return ""
    if "/" not in value:
        value += "/USDT"
    return value


def _normalize_symbol_for_binance(symbol: str) -> str:
    value = str(symbol or "").upper().replace("/", "").replace("-", "")