        sig = macd.ewm(span=signal, adjust=False).mean()
        hist = macd - sig
        h0, h1 = float(hist.iloc[-1]), float(hist.iloc[-2]) if len(hist) > 1 else 0.0
        cross = "bull" if h1 <= 0 < h0 else "bear" if h1 >= 0 > h0 else "none"
        return {"macd": round(float(macd.iloc[-1]), 8), "signal": round(float(sig.iloc[-1]), 8),
                "hist": round(h0, 8), "cross": cross}
    except Exception:
        return {"macd": 0.0, "signal": 0.0, "hist": 0.0, "cross": "none"}


def calc_stoch_rsi(close: pd.Series, rsi_period: int = 14, stoch_period: int = 14, k: int = 3, d: int = 3) -> dict[str, float]:
    """Stochastic RSI for timing entries on oversold/overbought extremes."""
    try:
        rsi = wilder_rsi(close, rsi_period)
        if len(rsi) < stoch_period + d:
            return {"k": 50.0, "d": 50.0, "zone": "mid"}
        rmin = rsi.rolling(stoch_period).min()
        rmax = rsi.rolling(stoch_period).max()
        stoch = 100 * (rsi - rmin) / (rmax - rmin).replace(0, np.nan)
        k_line = stoch.rolling(k).mean().fillna(50)
        d_line = k_line.rolling(d).mean().fillna(50)
        kv, dv = float(k_line.iloc[-1]), float(d_line.iloc[-1])
        zone = "oversold" if kv < 20 else "overbought" if kv > 80 else "mid"
        return {"k": round(kv, 2), "d": round(dv, 2), "zone": zone}
    except Exception:
        return {"k": 50.0, "d": 50.0, "zone": "mid"}


def calc_pivot_points(df: pd.DataFrame) -> dict[str, float]:
    """Classic daily pivots from last closed candle high/low/close."""
    try:
        if df is None or len(df) < 2:
            return {}
        row = df.iloc[-1]
        h, l, c = float(row["high"]), float(row["low"]), float(row["close"])
        pp = (h + l + c) / 3.0
        r1 = 2 * pp - l
        s1 = 2 * pp - h
        r2 = pp + (h - l)
        s2 = pp - (h - l)
        r3 = h + 2 * (pp - l)
        s3 = l - 2 * (h - pp)
        return {k: round(v, 8) for k, v in (("pp", pp), ("r1", r1), ("r2", r2), ("r3", r3), ("s1", s1), ("s2", s2), ("s3", s3))}
    except Exception:
        return {}


def calc_volume_delta(df: pd.DataFrame, lookback: int = 24) -> dict[str, float]:
    """Proxy CVD from candle body direction * volume (no tick data required)."""
    try:
        x = df.tail(lookback).copy()
        if x.empty:
            return {"delta": 0.0, "buy_vol": 0.0, "sell_vol": 0.0, "delta_pct": 0.0}
        body_up = (x["close"] >= x["open"]).astype(float)
        buy_v = float((x["vol"] * body_up).sum())
        sell_v = float((x["vol"] * (1 - body_up)).sum())
        total = buy_v + sell_v
        delta = buy_v - sell_v
        return {
            "delta": round(delta, 4),
            "buy_vol": round(buy_v, 4),
            "sell_vol": round(sell_v, 4),
            "delta_pct": round((delta / total * 100) if total > 0 else 0.0, 2),
        }
    except Exception:
        return {"delta": 0.0, "buy_vol": 0.0, "sell_vol": 0.0, "delta_pct": 0.0}


def market_session_utc() -> dict[str, Any]:
    """Current major session and overlap (analysis-only context)."""
    hour = datetime.now(timezone.utc).hour
    if 0 <= hour < 8:
        name, risk_mult = "Asia", 0.95
    elif 8 <= hour < 13:
        name, risk_mult = "London", 1.05
    elif 13 <= hour < 17:
        name, risk_mult = "London-NY Overlap", 1.12
    elif 17 <= hour < 21:
        name, risk_mult = "New York", 1.05
    else:
        name, risk_mult = "Off-hours", 0.88
    return {"session": name, "hour_utc": hour, "liquidity_boost": risk_mult}




# === TITAN PATTERN + FUTURE CANDLE FORECAST ENGINE ===
PATTERN_GUIDE = {
    "سرشانه": {
        "name_en": "Head & Shoulders",
        "meaning": "الگوی بازگشتی نزولی: سه قله که قله میانی (سر) بالاتر از دو شانه است. خط گردن اتصال کف‌های بین شانه و سر است.",
        "expect": "با شکست معتبر خط گردن به سمت پایین، انتظار ادامه نزول تا اندازه ارتفاع سر تا خط گردن وجود دارد. حد ضرر بالای شانه راست.",
        "bias": "نزولی",
    },
    "سرشانه معکوس": {
        "name_en": "Inverse Head & Shoulders",
        "meaning": "الگوی بازگشتی صعودی: سه کف که کف میانی (سر) پایین‌تر از دو شانه است.",
        "expect": "با شکست خط گردن به بالا، انتظار رشد تا اندازه ارتفاع الگو. حد ضرر زیر شانه راست.",
        "bias": "صعودی",
    },
    "سقف دوقلو": {
        "name_en": "Double Top",
        "meaning": "دو قله تقریباً هم‌تراز پس از روند صعودی؛ نشانه ضعف خریداران.",
        "expect": "شکست کف میانی (خط گردن) معمولاً ادامه نزول را تقویت می‌کند. هدف تقریبی: فاصله قله تا گردن.",
        "bias": "نزولی",
    },
    "کف دوقلو": {
        "name_en": "Double Bottom",
        "meaning": "دو کف تقریباً هم‌تراز پس از روند نزولی؛ نشانه ضعف فروشندگان.",
        "expect": "شکست سقف میانی معمولاً ادامه صعود را تقویت می‌کند. هدف تقریبی: فاصله کف تا گردن.",
        "bias": "صعودی",
    },
    "واگرایی صعودی": {
        "name_en": "Bullish Divergence",
        "meaning": "قیمت کف پایین‌تر می‌سازد اما RSI/MACD کف بالاتر می‌سازد — ضعف فروش.",
        "expect": "احتمال واکنش صعودی یا پایان موقت نزول؛ تأیید با برگشت قیمت و حجم لازم است.",
        "bias": "صعودی",
    },
    "واگرایی نزولی": {
        "name_en": "Bearish Divergence",
        "meaning": "قیمت سقف بالاتر می‌سازد اما RSI/MACD سقف پایین‌تر می‌سازد — ضعف خرید.",
        "expect": "احتمال اصلاح یا برگشت نزولی؛ تأیید با شکست ساختار لازم است.",
        "bias": "نزولی",
    },
    "مثلث فشرده": {
        "name_en": "Symmetrical / Tight Range",
        "meaning": "نوسان در حال فشرده شدن؛ انرژی برای شکست انباشته می‌شود.",
        "expect": "شکست با حجم می‌تواند حرکت جهت‌دار ایجاد کند؛ جهت از ساختار چندتایم‌فریمی خوانده شود.",
        "bias": "خنثی",
    },
}


def _find_swing_points(series: pd.Series, order: int = 3) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """Local swing highs/lows as (index_position, value)."""
    vals = series.astype(float).tolist()
    highs, lows = [], []
    n = len(vals)
    for i in range(order, n - order):
        window = vals[i - order:i + order + 1]
        if vals[i] == max(window) and vals[i] > vals[i - 1] and vals[i] > vals[i + 1]:
            highs.append((i, vals[i]))
        if vals[i] == min(window) and vals[i] < vals[i - 1] and vals[i] < vals[i + 1]:
            lows.append((i, vals[i]))
    return highs, lows


def detect_chart_patterns(df: pd.DataFrame, rsi_series: Optional[pd.Series] = None) -> dict[str, Any]:
    """Detect standard patterns: H&S, double top/bottom, RSI divergence, tight range."""
    patterns: list[dict[str, Any]] = []
    try:
        if df is None or len(df) < 40:
            return {"patterns": [], "primary": None, "score_bias": 0.0}
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        close = df["close"].astype(float)
        swing_highs, _ = _find_swing_points(high, 3)
        _, swing_lows = _find_swing_points(low, 3)

        # Double Top
        if len(swing_highs) >= 2:
            (i1, h1), (i2, h2) = swing_highs[-2], swing_highs[-1]
            if i2 > i1 and abs(h1 - h2) / max(h1, 1e-12) < 0.015:
                mid_low = float(low.iloc[i1:i2 + 1].min()) if i2 > i1 else float(low.iloc[-1])
                if float(close.iloc[-1]) < (h1 + h2) / 2:
                    conf = 62 + (10 if float(close.iloc[-1]) < mid_low else 0)
                    patterns.append({
                        "id": "سقف دوقلو", "confidence": min(88, conf),
                        "levels": {"peak1": round(h1, 8), "peak2": round(h2, 8), "neck": round(mid_low, 8)},
                        "guide": PATTERN_GUIDE["سقف دوقلو"],
                    })

        # Double Bottom
        if len(swing_lows) >= 2:
            (i1, l1), (i2, l2) = swing_lows[-2], swing_lows[-1]
            if i2 > i1 and abs(l1 - l2) / max(abs(l1), 1e-12) < 0.015:
                mid_high = float(high.iloc[i1:i2 + 1].max()) if i2 > i1 else float(high.iloc[-1])
                if float(close.iloc[-1]) > (l1 + l2) / 2:
                    conf = 62 + (10 if float(close.iloc[-1]) > mid_high else 0)
                    patterns.append({
                        "id": "کف دوقلو", "confidence": min(88, conf),
                        "levels": {"trough1": round(l1, 8), "trough2": round(l2, 8), "neck": round(mid_high, 8)},
                        "guide": PATTERN_GUIDE["کف دوقلو"],
                    })

        # Head & Shoulders (3 highs: L-shoulder, head, R-shoulder)
        if len(swing_highs) >= 3:
            (i0, s0), (i1, head), (i2, s1) = swing_highs[-3], swing_highs[-2], swing_highs[-1]
            if head > s0 and head > s1 and abs(s0 - s1) / max(head, 1e-12) < 0.04 and i0 < i1 < i2:
                neck = float(low.iloc[i0:i2 + 1].min())
                conf = 70 if float(close.iloc[-1]) < neck * 1.01 else 58
                patterns.append({
                    "id": "سرشانه", "confidence": conf,
                    "levels": {"left": round(s0, 8), "head": round(head, 8), "right": round(s1, 8), "neck": round(neck, 8)},
                    "guide": PATTERN_GUIDE["سرشانه"],
                })

        # Inverse H&S
        if len(swing_lows) >= 3:
            (i0, s0), (i1, head), (i2, s1) = swing_lows[-3], swing_lows[-2], swing_lows[-1]
            if head < s0 and head < s1 and abs(s0 - s1) / max(abs(head), 1e-12) < 0.04 and i0 < i1 < i2:
                neck = float(high.iloc[i0:i2 + 1].max())
                conf = 70 if float(close.iloc[-1]) > neck * 0.99 else 58
                patterns.append({
                    "id": "سرشانه معکوس", "confidence": conf,
                    "levels": {"left": round(s0, 8), "head": round(head, 8), "right": round(s1, 8), "neck": round(neck, 8)},
                    "guide": PATTERN_GUIDE["سرشانه معکوس"],
                })

        # RSI divergence
        rsi = rsi_series if rsi_series is not None else wilder_rsi(close)
        if len(close) >= 30 and len(rsi) >= 30:
            c_tail = close.tail(30)
            r_tail = rsi.tail(30)
            price_ll = float(c_tail.min()) == float(c_tail.iloc[-1]) or (
                float(c_tail.iloc[-1]) <= float(c_tail.iloc[:-5].min()) * 1.002
            )
            price_hh = float(c_tail.iloc[-1]) >= float(c_tail.iloc[:-5].max()) * 0.998
            rsi_now = float(r_tail.iloc[-1])
            rsi_prev_min = float(r_tail.iloc[:-5].min())
            rsi_prev_max = float(r_tail.iloc[:-5].max())
            if price_ll and rsi_now > rsi_prev_min + 3:
                patterns.append({
                    "id": "واگرایی صعودی", "confidence": 65,
                    "levels": {"rsi": round(rsi_now, 1)},
                    "guide": PATTERN_GUIDE["واگرایی صعودی"],
                })
            if price_hh and rsi_now < rsi_prev_max - 3:
                patterns.append({
                    "id": "واگرایی نزولی", "confidence": 65,
                    "levels": {"rsi": round(rsi_now, 1)},
                    "guide": PATTERN_GUIDE["واگرایی نزولی"],
                })

        # Tight range / triangle proxy
        recent = close.tail(20)
        atr_pct = float((high.tail(20) - low.tail(20)).mean() / close.iloc[-1] * 100) if float(close.iloc[-1]) else 0
        if atr_pct < 1.4 and float(recent.max() / recent.min() - 1) * 100 < 3.5:
            patterns.append({
                "id": "مثلث فشرده", "confidence": 55,
                "levels": {"range_high": round(float(recent.max()), 8), "range_low": round(float(recent.min()), 8)},
                "guide": PATTERN_GUIDE["مثلث فشرده"],
            })

        patterns.sort(key=lambda x: -x.get("confidence", 0))
        primary = patterns[0] if patterns else None
        score_bias = 0.0
        if primary:
            g = primary.get("guide") or {}
            b = g.get("bias", "خنثی")
            conf = primary.get("confidence", 50) / 100.0
            if b == "صعودی":
                score_bias = 4.0 * conf
            elif b == "نزولی":
                score_bias = -4.0 * conf
        return {"patterns": patterns[:5], "primary": primary, "score_bias": round(score_bias, 2)}
    except Exception as exc:
        LOGGER.debug("pattern detect failed: %s", exc)
        return {"patterns": [], "primary": None, "score_bias": 0.0}


def forecast_future_candles(
    df: pd.DataFrame,
    horizon: int = 12,
    patterns: Optional[dict] = None,
    *,
    macd: Optional[dict] = None,
    stoch: Optional[dict] = None,
    structure: Optional[dict] = None,
    regime: Optional[dict] = None,
) -> dict[str, Any]:
    """Multi-factor probabilistic path for the next N candles (default 12).

    Blends: historical return distribution, short/medium momentum, EMA structure,
    MACD/Stoch tilt, chart-pattern bias, analogue matching, and soft mean-reversion
    over longer horizons. Analysis-only — not a guarantee of future prices.
    """
    try:
        horizon = int(clamp(horizon, 3, 24))
        if df is None or len(df) < 50:
            return {"ok": False, "candles": [], "narrative": "داده کافی برای پیش‌بینی نیست", "horizon": horizon}
        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        vol = df["vol"].astype(float) if "vol" in df.columns else pd.Series([1.0] * len(df))
        rets = close.pct_change().dropna().tail(160)
        if len(rets) < 20:
            return {"ok": False, "candles": [], "narrative": "تاریخچه بازده ناکافی", "horizon": horizon}

        mu = float(rets.mean())
        sigma = float(rets.std()) or 1e-6
        # Multi-horizon momentum
        mom3 = float(close.iloc[-1] / close.iloc[-4] - 1) if len(close) > 4 else 0.0
        mom5 = float(close.iloc[-1] / close.iloc[-6] - 1) if len(close) > 6 else 0.0
        mom12 = float(close.iloc[-1] / close.iloc[-13] - 1) if len(close) > 13 else 0.0
        ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
        ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1]) if len(close) >= 50 else ema20
        ema_gap = (ema20 / ema50 - 1.0) if ema50 > 0 else 0.0
        price_vs_ema = (float(close.iloc[-1]) / ema20 - 1.0) if ema20 > 0 else 0.0

        # Base drift: recent mean + momentum blend + structure
        mu_adj = mu * 0.28 + mom3 * 0.18 + mom5 * 0.22 + mom12 * 0.12 + ema_gap * 0.20
        # Soft mean-reversion when stretched vs EMA20
        if abs(price_vs_ema) > 0.025:
            mu_adj -= price_vs_ema * 0.15

        # Pattern tilt
        pbias = safe_float((patterns or {}).get("score_bias"), 0) / 100.0
        mu_adj += pbias * abs(sigma) * 2.2

        # MACD / Stoch confirmation
        macd = macd or {}
        stoch = stoch or {}
        if macd.get("cross") == "bull":
            mu_adj += abs(sigma) * 0.35
        elif macd.get("cross") == "bear":
            mu_adj -= abs(sigma) * 0.35
        hist = safe_float(macd.get("hist"), 0)
        if hist != 0:
            last_px = float(close.iloc[-1])
            mu_adj += float(np.clip(hist / max(last_px * 0.01, 1e-12), -0.8, 0.8)) * abs(sigma) * 0.25
        zone = str(stoch.get("zone") or "mid")
        if zone == "oversold":
            mu_adj += abs(sigma) * 0.20
        elif zone == "overbought":
            mu_adj -= abs(sigma) * 0.20

        # Regime / structure soft bias
        regime_name = str((regime or {}).get("regime", "")).lower()
        if "up" in regime_name or "bull" in regime_name:
            mu_adj += abs(sigma) * 0.12
        elif "down" in regime_name or "bear" in regime_name:
            mu_adj -= abs(sigma) * 0.12
        struct_bias = str((structure or {}).get("bias", "") or "")
        if struct_bias == "صعودی":
            mu_adj += abs(sigma) * 0.10
        elif struct_bias == "نزولی":
            mu_adj -= abs(sigma) * 0.10

        # Volume confirmation of last move
        try:
            v_tail = vol.tail(8)
            c_tail = close.tail(8)
            if len(v_tail) >= 4 and float(v_tail.mean()) > 0:
                up_vol = float(v_tail[c_tail.diff() > 0].sum())
                dn_vol = float(v_tail[c_tail.diff() < 0].sum())
                if up_vol + dn_vol > 0:
                    vol_skew = (up_vol - dn_vol) / (up_vol + dn_vol)
                    mu_adj += vol_skew * abs(sigma) * 0.18
        except Exception:
            pass

        last = float(close.iloc[-1])
        atr = float((high - low).tail(14).mean()) or last * 0.01

        # Historical analogue (longer window for 12-step path)
        analogue_note = ""
        best_corr, best_fwd = 0.0, None
        try:
            window = 12 if len(close) > 80 else 8
            target = close.pct_change().dropna().tail(window).values
            rets_all = close.pct_change().dropna().values
            # Stride search for speed (dashboard scans many symbols)
            _step = 2 if len(rets_all) > 80 else 1
            for i in range(window, max(window + 1, len(rets_all) - horizon - 1), _step):
                seg = rets_all[i - window:i]
                if len(seg) != window:
                    continue
                if float(np.std(seg)) < 1e-12 or float(np.std(target)) < 1e-12:
                    continue
                corr = float(np.corrcoef(seg, target)[0, 1])
                if math.isfinite(corr) and corr > best_corr and corr > 0.50:
                    best_corr = corr
                    best_fwd = rets_all[i:i + horizon]
            if best_fwd is not None and len(best_fwd) >= 1:
                fwd_sum = float(np.sum(best_fwd))
                analogue_note = (
                    f"نزدیک‌ترین الگوی تاریخی با همبستگی {best_corr:.0%} در ادامه "
                    f"{'مثبت' if fwd_sum > 0 else 'منفی'} حدود {abs(fwd_sum)*100:.2f}% حرکت داشته است."
                )
        except Exception:
            pass

        candles = []
        px = last
        # Confidence decays slower for short steps, faster for far steps
        for step in range(1, horizon + 1):
            # Dampen drift with horizon (uncertainty + mean reversion)
            damp = 1.0 / (1.0 + 0.045 * (step - 1))
            step_mu = mu_adj * damp
            drift = step_mu * step
            # Wider bands for longer horizon
            band = sigma * (step ** 0.55) * (1.45 + 0.04 * step)
            mid = last * (1 + drift)
            # Blend analogue path if available
            if best_fwd is not None and step <= len(best_fwd):
                ana = last * (1 + float(np.sum(best_fwd[:step])))
                mid = 0.62 * mid + 0.38 * ana
            lo = mid * (1 - band) - 0.12 * atr * (1 + 0.03 * step)
            hi = mid * (1 + band) + 0.12 * atr * (1 + 0.03 * step)
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