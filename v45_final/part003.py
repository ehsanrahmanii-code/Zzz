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