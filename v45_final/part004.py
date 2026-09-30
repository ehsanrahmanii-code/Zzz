            o = px
            c = mid
            h = max(o, c, hi * 0.35 + mid * 0.65)
            l = min(o, c, lo * 0.35 + mid * 0.65)
            direction = "صعودی" if c >= o else "نزولی"
            conf = clamp(78 - step * 3.2 + abs(pbias) * 70 + (best_corr * 12 if best_corr else 0), 22, 82)
            candles.append({
                "step": step,
                "open": round(float(o), 8),
                "high": round(float(h), 8),
                "low": round(float(l), 8),
                "close": round(float(c), 8),
                "mid": round(float(mid), 8),
                "band_low": round(float(lo), 8),
                "band_high": round(float(hi), 8),
                "direction": direction,
                "confidence": round(conf, 1),
                "analogue_corr": round(best_corr, 3) if best_corr else None,
            })
            px = float(c)

        primary = (patterns or {}).get("primary")
        if primary:
            pname = primary.get("id", "")
            guide = primary.get("guide") or {}
            narrative = (
                f"پیش‌بینی احتمالی {horizon} کندل بعدی با مدل چندعاملی (بازده، مومنتوم چندافق، EMA، MACD/Stoch، "
                f"الگوی «{pname}» و آنالوگ تاریخی). {guide.get('expect', '')} "
                f"{analogue_note} این خروجی سناریویی است و تضمین سود نیست."
            )
        else:
            narrative = (
                f"پیش‌بینی احتمالی {horizon} کندل با توزیع بازده، مومنتوم، ساختار EMA و شباهت الگویی. "
                f"{analogue_note} خروجی سناریویی است، نه قطعی."
            )
        up_steps = sum(1 for c in candles if c["direction"] == "صعودی")
        overall = "صعودی" if up_steps > horizon * 0.55 else "نزولی" if up_steps < horizon * 0.45 else "خنثی"
        # Path conviction: magnitude of expected move vs sigma
        expected_move = (candles[-1]["close"] / last - 1.0) if candles else 0.0
        path_strength = float(clamp(abs(expected_move) / max(sigma * (horizon ** 0.5), 1e-9) * 25, 0, 40))
        return {
            "ok": True,
            "horizon": horizon,
            "overall_bias": overall,
            "candles": candles,
            "narrative": narrative,
            "last_price": round(last, 8),
            "mu": round(mu_adj, 6),
            "sigma": round(sigma, 6),
            "expected_move_pct": round(expected_move * 100, 3),
            "path_strength": round(path_strength, 1),
            "analogue_corr": round(best_corr, 3) if best_corr else None,
            "components": {
                "mom3": round(mom3, 6), "mom5": round(mom5, 6), "mom12": round(mom12, 6),
                "ema_gap": round(ema_gap, 6), "pattern_bias": round(pbias, 4),
            },
        }
    except Exception as exc:
        LOGGER.debug("forecast_future_candles failed: %s", exc)
        return {"ok": False, "candles": [], "narrative": str(exc)[:200], "horizon": horizon}


def fetch_binance_long_short_ratio(symbol: str) -> dict[str, Any]:
    """Global long/short account ratio from Binance Futures (free public endpoint)."""
    pair = _binance_symbol(symbol)
    out: dict[str, Any] = {"long_ratio": None, "short_ratio": None, "long_short_ratio": None, "source": "N/A"}
    try:
        r = _http_session().get(
            "https://fapi.binance.com/futures/data/globalLongShortAccountRatio",
            params={"symbol": pair, "period": "1h", "limit": 1},
            timeout=8,
        )
        if r.ok:
            data = r.json()
            if isinstance(data, list) and data:
                row = data[-1]
                lr = safe_float(row.get("longAccount"))
                sr = safe_float(row.get("shortAccount"))
                ratio = safe_float(row.get("longShortRatio"))
                out.update({
                    "long_ratio": round(lr * 100, 2) if lr else None,
                    "short_ratio": round(sr * 100, 2) if sr else None,
                    "long_short_ratio": round(ratio, 4) if ratio else None,
                    "source": "Binance-LSR",
                })
    except Exception as exc:
        LOGGER.debug("LSR fetch failed %s: %s", symbol, exc)
    try:
        r = _http_session().get(
            "https://fapi.binance.com/futures/data/topLongShortAccountRatio",
            params={"symbol": pair, "period": "1h", "limit": 1},
            timeout=8,
        )
        if r.ok:
            data = r.json()
            if isinstance(data, list) and data:
                row = data[-1]
                out["top_long_ratio"] = round(safe_float(row.get("longAccount")) * 100, 2)
                out["top_short_ratio"] = round(safe_float(row.get("shortAccount")) * 100, 2)
                out["top_long_short_ratio"] = round(safe_float(row.get("longShortRatio")), 4)
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
