                out["source"] = (out.get("source") or "") + "+TopTrader"
    except Exception as exc:
        LOGGER.debug("Top trader ratio failed %s: %s", symbol, exc)
    return out


def fetch_binance_taker_buy_sell(symbol: str) -> dict[str, Any]:
    """Taker buy/sell volume ratio — real order-flow proxy."""
    pair = _binance_symbol(symbol)
    try:
        r = _http_session().get(
            "https://fapi.binance.com/futures/data/takerlongshortRatio",
            params={"symbol": pair, "period": "1h", "limit": 1},
            timeout=8,
        )
        if r.ok:
            data = r.json()
            if isinstance(data, list) and data:
                row = data[-1]
                buy = safe_float(row.get("buyVol"))
                sell = safe_float(row.get("sellVol"))
                ratio = safe_float(row.get("buySellRatio"))
                total = buy + sell
                return {
                    "buy_vol": buy, "sell_vol": sell,
                    "buy_sell_ratio": round(ratio, 4) if ratio else None,
                    "buy_pct": round(buy / total * 100, 1) if total > 0 else 50.0,
                    "sell_pct": round(sell / total * 100, 1) if total > 0 else 50.0,
                    "source": "Binance-Taker",
                }
    except Exception as exc:
        LOGGER.debug("Taker ratio failed %s: %s", symbol, exc)
    return {"buy_pct": 50.0, "sell_pct": 50.0, "buy_sell_ratio": None, "source": "N/A"}


def _ls_bias(ls: dict[str, Any], direction_wanted: int) -> tuple[float, str]:
    """Crowd positioning bias: extreme long crowding is short-friendly and vice versa."""
    ratio = safe_float(ls.get("long_short_ratio"), 1.0)
    if ratio <= 0:
        return 0.0, "فاقد داده L/S"
    if ratio >= 1.8:
        return (-5.0 if direction_wanted >= 0 else 4.0), "ازدحام شدید لانگ (ضدجمعیت نزولی)"
    if ratio >= 1.35:
        return (-2.5 if direction_wanted >= 0 else 2.0), "فشار لانگ بالا"
    if ratio <= 0.55:
        return (5.0 if direction_wanted <= 0 else -4.0), "ازدحام شدید شورت (ضدجمعیت صعودی)"
    if ratio <= 0.75:
        return (2.5 if direction_wanted <= 0 else -2.0), "فشار شورت بالا"
    return 0.0, "نسبت لانگ/شورت متعادل"



def clamp(value: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, value)))


# ============================================================
# TITAN V8 — CONFIDENCE ENGINE (Entry Ladder · DQ · Forecast Track · Portfolio)
# Analysis-only. Raises bar for LONG/SHORT; never invents edge.
# ============================================================

_FORECAST_TRACK_LOCK = threading.RLock()
_PORTFOLIO_SIGNAL_LOCK = threading.RLock()
_RECENT_DIRECTIONAL_SIGNALS: list[dict[str, Any]] = []


def _forecast_track_path() -> Path:
    return MEMORY_DIR / "forecast_path_accuracy.json"


def _load_forecast_track() -> dict[str, Any]:
    data = _load_json(_forecast_track_path(), {})
    return data if isinstance(data) else {}


def _save_forecast_track(data: dict[str, Any]) -> None:
    _save_json(_forecast_track_path(), data)


def assess_data_quality(
    *,
    symbol: str,
    price: float,
    live_age_sec: Optional[float],
    df15: Optional[pd.DataFrame],
    df1h: Optional[pd.DataFrame],
    derivatives: dict[str, Any],
    frames: Optional[dict] = None,
) -> dict[str, Any]:
    """Hard data-quality score + veto reasons. Low quality forces WAIT."""
    reasons: list[str] = []
    score = 100.0
    n15 = len(df15) if df15 is not None else 0
    n1h = len(df1h) if df1h is not None else 0
    if price <= 0:
        reasons.append("invalid_price")
        score -= 40
    if live_age_sec is None:
        score -= 8
        reasons.append("no_live_ts")
    elif live_age_sec > MAX_LIVE_PRICE_AGE_SEC:
        score -= min(25.0, 8 + (live_age_sec - MAX_LIVE_PRICE_AGE_SEC) * 0.8)
        reasons.append(f"stale_live_{live_age_sec:.0f}s")
    if n1h < MIN_CLOSED_CANDLES_1H:
        score -= 20
        reasons.append(f"thin_1h_{n1h}")
    if n15 < MIN_CLOSED_CANDLES_15M:
        score -= 12
        reasons.append(f"thin_15m_{n15}")
    if frames:
        missing = [tf for tf in ("15m", "1h", "4h", "1d") if tf not in frames or frames[tf] is None or len(frames[tf]) < 30]
        if missing:
            score -= 6 * len(missing)
            reasons.append("missing_tf:" + ",".join(missing))
    fund = derivatives.get("funding_value")
    if fund is None and str(derivatives.get("funding", "N/A")) == "N/A":
        score -= 6
        reasons.append("no_funding")
    if safe_float(derivatives.get("raw_oi"), 0) <= 0 and str(derivatives.get("oi", "N/A")) == "N/A":
        score -= 5
        reasons.append("no_oi")
    score = float(clamp(score, 0, 100))
    # Hard veto only for truly unusable data — borderline quality is soft penalty.
    hard_veto = (
        "invalid_price" in reasons
        or n1h < 25
        or score < 32
    )
    return {
        "score": round(score, 1),
        "hard_veto": hard_veto,
        "reasons": reasons,
        "live_age_sec": live_age_sec,
        "candles_1h": n1h,
        "candles_15m": n15,
        "param_version": TITAN_PARAM_VERSION,
    }


def entry_ladder_gate(
    tf_scores: dict[str, float],
    tf_results: dict[str, str],
    decision_tag: str,
    bias: str,
) -> dict[str, Any]:
    """Mandatory HTF→MTF→LTF alignment before directional signal.

    4h/1d = macro direction, 1h = setup, 15m = trigger lean.
    """
    s15 = safe_float(tf_scores.get("15m"), 50)
    s1h = safe_float(tf_scores.get("1h"), 50)
    s4h = safe_float(tf_scores.get("4h"), 50)
    s1d = safe_float(tf_scores.get("1d"), 50)
    htf = 0.55 * s4h + 0.45 * s1d
    mtf = s1h
    ltf = s15

    def _side(sc: float) -> str:
        if sc >= 54:
            return "LONG"
        if sc <= 46:
            return "SHORT"
        return "WAIT"

    htf_side, mtf_side, ltf_side = _side(htf), _side(mtf), _side(ltf)
    wanted = decision_tag if decision_tag in {"LONG", "SHORT"} else (
        "LONG" if bias == "صعودی" else "SHORT" if bias == "نزولی" else "WAIT"
    )
    passed = True
    reasons: list[str] = []
    if wanted == "LONG":
        if htf < ENTRY_LADDER_MIN_HTF_SCORE:
            passed = False
            reasons.append(f"HTF_weak_{htf:.0f}")
        if mtf < ENTRY_LADDER_MIN_MTF_SCORE:
            passed = False
            reasons.append(f"MTF_weak_{mtf:.0f}")
        if htf_side == "SHORT" or mtf_side == "SHORT":
            passed = False
            reasons.append("HTF/MTF_against_long")
        # LTF should not be strongly opposite
        if ltf <= 40:
            passed = False
            reasons.append(f"LTF_against_{ltf:.0f}")
    elif wanted == "SHORT":
        if htf > (100 - ENTRY_LADDER_MIN_HTF_SCORE):
            passed = False
            reasons.append(f"HTF_weak_short_{htf:.0f}")
        if mtf > (100 - ENTRY_LADDER_MIN_MTF_SCORE):
            passed = False
            reasons.append(f"MTF_weak_short_{mtf:.0f}")
        if htf_side == "LONG" or mtf_side == "LONG":
            passed = False
            reasons.append("HTF/MTF_against_short")
        if ltf >= 60:
            passed = False
            reasons.append(f"LTF_against_{ltf:.0f}")
    else:
        reasons.append("no_directional_want")

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