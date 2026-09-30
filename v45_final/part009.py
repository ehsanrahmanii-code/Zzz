                    fvgs.append({
                        "type": "bearish_fvg",
                        "low": round(gap_lo, 8),
                        "high": round(gap_hi, 8),
                        "mid": round((gap_lo + gap_hi) / 2, 8),
                        "index": i,
                        "guide": "گپ نزولی پرنشده — اغلب به‌عنوان مقاومت پویا؛ پر شدن گپ نشانه فشار خرید یا ادامه نزول است.",
                    })

            # Order block: impulse after opposite candle
            if move > 1.2 * atr_i and float(c.iloc[i - 1]) < float(o.iloc[i - 1]):
                # bullish OB = prior bearish candle
                obs.append({
                    "type": "bullish_ob",
                    "low": round(float(l.iloc[i - 1]), 8),
                    "high": round(float(h.iloc[i - 1]), 8),
                    "mid": round((float(l.iloc[i - 1]) + float(h.iloc[i - 1])) / 2, 8),
                    "index": i - 1,
                    "guide": "بلاک سفارش صعودی: آخرین کندل نزولی قبل از حرکت قوی بالا. بازگشت قیمت به این ناحیه می‌تواند تقاضا را فعال کند.",
                })
            if move < -1.2 * atr_i and float(c.iloc[i - 1]) > float(o.iloc[i - 1]):
                obs.append({
                    "type": "bearish_ob",
                    "low": round(float(l.iloc[i - 1]), 8),
                    "high": round(float(h.iloc[i - 1]), 8),
                    "mid": round((float(l.iloc[i - 1]) + float(h.iloc[i - 1])) / 2, 8),
                    "index": i - 1,
                    "guide": "بلاک سفارش نزولی: آخرین کندل صعودی قبل از حرکت قوی پایین. بازگشت به این ناحیه می‌تواند عرضه را فعال کند.",
                })

        # Keep nearest to price
        def _dist(zone):
            return abs(price - safe_float(zone.get("mid"), price))

        obs = sorted(obs, key=_dist)[:4]
        fvgs = sorted(fvgs, key=_dist)[:4]
        nearest_ob = obs[0] if obs else None
        nearest_fvg = fvgs[0] if fvgs else None
        return {
            "order_blocks": obs,
            "fvgs": fvgs,
            "nearest_ob": nearest_ob,
            "nearest_fvg": nearest_fvg,
            "price": round(price, 8),
        }
    except Exception as exc:
        LOGGER.debug("OB/FVG failed: %s", exc)
        return {"order_blocks": [], "fvgs": [], "nearest_ob": None, "nearest_fvg": None}


def get_depth_snapshot(symbol: str) -> dict[str, Any]:
    """Read cached partial book depth for watchlist symbols."""
    pair = _binance_symbol(symbol)
    with DEPTH_LOCK:
        row = DEPTH_STATE.get(pair) or DEPTH_STATE.get(symbol) or {}
    if not row:
        return {"available": False, "symbol": pair}
    age = time.time() - safe_float(row.get("ts"), 0)
    return {
        "available": age < 30,
        "symbol": pair,
        "bid": row.get("bid"),
        "ask": row.get("ask"),
        "spread_bps": row.get("spread_bps"),
        "bid_vol": row.get("bid_vol"),
        "ask_vol": row.get("ask_vol"),
        "imbalance": row.get("imbalance"),
        "age_sec": round(age, 1),
        "source": row.get("source", "depth"),
    }


def _depth_websocket_worker() -> None:
    """Lightweight partial book depth for a few liquid symbols only (mobile-friendly)."""
    if _websocket_client is None:
        return
    streams = "/".join(f"{s.lower()}@depth5@1000ms" for s in DEPTH_WATCHLIST)
    url = f"wss://data-stream.binance.vision/stream?streams={streams}"
    while not LIVE_STOP.is_set():
        try:
            ws = _websocket_client.create_connection(url, timeout=15)
            ws.settimeout(25)
            LOGGER.info("Depth WebSocket connected for %s", DEPTH_WATCHLIST)
            while not LIVE_STOP.is_set():
                raw = ws.recv()
                if not raw:
                    break
                try:
                    msg = json.loads(raw)
                    data = msg.get("data") or msg
                    bids = data.get("bids") or data.get("b") or []
                    asks = data.get("asks") or data.get("a") or []
                    stream = str(msg.get("stream") or "")
                    sym = stream.split("@")[0].upper() if "@" in stream else ""
                    if not sym and data.get("s"):
                        sym = str(data["s"]).upper()
                    if not bids or not asks or not sym:
                        continue
                    best_bid = safe_float(bids[0][0])
                    best_ask = safe_float(asks[0][0])
                    bid_vol = sum(safe_float(x[1]) for x in bids[:5])
                    ask_vol = sum(safe_float(x[1]) for x in asks[:5])
                    mid = (best_bid + best_ask) / 2 if best_bid and best_ask else 0
                    spread_bps = ((best_ask - best_bid) / mid * 10000) if mid else 0
                    imb = (bid_vol - ask_vol) / max(bid_vol + ask_vol, 1e-12)
                    with DEPTH_LOCK:
                        DEPTH_STATE[sym] = {
                            "bid": best_bid,
                            "ask": best_ask,
                            "bid_vol": round(bid_vol, 4),
                            "ask_vol": round(ask_vol, 4),
                            "spread_bps": round(spread_bps, 2),
                            "imbalance": round(imb, 4),
                            "ts": time.time(),
                            "source": "DepthWS",
                        }
                except Exception:
                    continue
            try:
                ws.close()
            except Exception:
                pass
        except Exception as exc:
            LOGGER.info("Depth WS unavailable (REST only): %s", exc)
            LIVE_STOP.wait(8)



def wilder_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).replace([np.inf, -np.inf], np.nan).fillna(50.0)


def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    previous_close = df["close"].shift(1)
    tr = pd.concat([(df["high"] - df["low"]), (df["high"] - previous_close).abs(), (df["low"] - previous_close).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean().bfill()


def calc_vwap(df: pd.DataFrame) -> float:
    if df.empty:
        return float("nan")
    timestamps = pd.to_datetime(df["t"], unit="ms", utc=True)
    latest_day = timestamps.iloc[-1].date()
    session_df = df[timestamps.dt.date == latest_day]
    if session_df.empty:
        session_df = df
    typical = (session_df["high"] + session_df["low"] + session_df["close"]) / 3.0
    volume_sum = float(session_df["vol"].sum())
    return float((typical * session_df["vol"]).sum() / volume_sum) if volume_sum > 0 else float(session_df["close"].iloc[-1])


def _tf_forecast(df: pd.DataFrame, fast: int = 20, slow: int = 50) -> tuple[str, float, dict[str, float]]:
    """Multi-factor TF score: EMA structure + momentum + RSI + ADX + volume + MACD + candle pressure.

    Symmetric for LONG/SHORT. Higher ADX amplifies directional conviction; low ADX shrinks
    extremes toward neutral so sideways markets do not fake strong signals.
    """
    if df is None or len(df) < slow + 5:
        return "خنثی", 50.0, {"rsi": 50.0, "momentum": 0.0, "ema_gap": 0.0, "adx": 0.0, "vol_z": 0.0}
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    vol = df["vol"].astype(float) if "vol" in df.columns else pd.Series([1.0] * len(df))
    fast_ema = close.ewm(span=fast, adjust=False).mean()
    slow_ema = close.ewm(span=slow, adjust=False).mean()
    rsi_value = float(wilder_rsi(close).iloc[-1])
    lookback = min(8, len(close) - 1)
    momentum = (float(close.iloc[-1]) / float(close.iloc[-1 - lookback]) - 1) * 100
    ema_gap = (float(fast_ema.iloc[-1]) / float(slow_ema.iloc[-1]) - 1) * 100

    # ADX (trend strength) — soft gate
    adx_val = 20.0
    try:
        if "_adx_series" in globals():
            adx_s = _adx_series(df, 14)
            adx_val = float(adx_s.iloc[-1]) if adx_s is not None and len(adx_s) else 20.0
        else:
            # lightweight ATR-based trend proxy
            tr = pd.concat([(high - low), (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
            atr14 = tr.ewm(alpha=1/14, adjust=False).mean()
            up = high.diff().clip(lower=0)
            dn = (-low.diff()).clip(lower=0)
            plus_dm = up.where(up > dn, 0.0)
            minus_dm = dn.where(dn > up, 0.0)
            plus_di = 100 * plus_dm.ewm(alpha=1/14, adjust=False).mean() / atr14.replace(0, np.nan)
            minus_di = 100 * minus_dm.ewm(alpha=1/14, adjust=False).mean() / atr14.replace(0, np.nan)
            dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)).fillna(20)
            adx_val = float(dx.ewm(alpha=1/14, adjust=False).mean().iloc[-1])
    except Exception:
        adx_val = 20.0
    adx_val = float(clamp(adx_val if math.isfinite(adx_val) else 20.0, 0, 60))

    # Volume z-score (last vs 20-bar mean)
    vol_z = 0.0
    try:
        v_mean = float(vol.tail(21).iloc[:-1].mean()) or 1.0
        v_std = float(vol.tail(21).iloc[:-1].std()) or 1.0
        vol_z = (float(vol.iloc[-1]) - v_mean) / max(v_std, 1e-9)
        vol_z = float(np.clip(vol_z, -3.0, 3.0))
    except Exception:
        vol_z = 0.0

    # MACD hist tilt
    macd_tilt = 0.0
    try:
        m = calc_macd(close)
        hist = safe_float(m.get("hist"), 0)
        last_px = float(close.iloc[-1]) or 1.0
        macd_tilt = float(np.clip(hist / max(last_px * 0.002, 1e-12), -1.5, 1.5))
        if m.get("cross") == "bull":
            macd_tilt += 0.35
        elif m.get("cross") == "bear":
            macd_tilt -= 0.35
    except Exception:
        pass

    # Candle body pressure (last 3)
    pressure = 0.0
    try:
        for i in range(-3, 0):
            o, c = float(df["open"].iloc[i]), float(close.iloc[i])
            rng = max(float(high.iloc[i]) - float(low.iloc[i]), 1e-12)
            pressure += ((c - o) / rng) * (0.5 if i == -3 else 0.75 if i == -2 else 1.0)
        pressure = float(np.clip(pressure / 2.25, -1.0, 1.0))
    except Exception:
        pressure = 0.0

    score = 50.0
    # Structure (EMA) — primary directional spine
    score += 14.0 if float(close.iloc[-1]) > float(fast_ema.iloc[-1]) else -14.0
    score += 12.0 if float(fast_ema.iloc[-1]) > float(slow_ema.iloc[-1]) else -12.0
    # Momentum
    score += float(np.clip(momentum * 3.2, -12.0, 12.0))
    # RSI mean-reversion mild + trend confirmation
    if rsi_value < 28:
        score += 4.0
    elif rsi_value < 38:
        score += 1.5
    elif rsi_value > 72:
        score -= 4.0
    elif rsi_value > 62:
        score -= 1.5
    # EMA gap magnitude
    score += float(np.clip(ema_gap * 1.1, -5.5, 5.5))
    # MACD + candle pressure
    score += macd_tilt * 4.5
    score += pressure * 5.0
    # Volume confirms move direction
    if abs(momentum) > 0.15:
        score += float(np.clip(vol_z * (1.0 if momentum > 0 else -1.0) * 2.2, -5.0, 5.0))

    # ADX scaling: low ADX compresses toward 50; high ADX preserves extremes
    adx_scale = float(clamp(0.55 + (adx_val / 40.0) * 0.55, 0.55, 1.15))
    score = 50.0 + (score - 50.0) * adx_scale
    score = float(clamp(score, 0, 100))

    direction = "صعودی" if score >= 54 else "نزولی" if score <= 46 else "خنثی"
    return direction, score, {
        "rsi": round(rsi_value, 2),
        "momentum": round(momentum, 4),
        "ema_gap": round(ema_gap, 4),
        "adx": round(adx_val, 2),
        "vol_z": round(vol_z, 3),
        "macd_tilt": round(macd_tilt, 3),
        "pressure": round(pressure, 3),
        "adx_scale": round(adx_scale, 3),
    }


def _funding_bias(funding: Optional[float]) -> tuple[float, str]:
    if funding is None:
        return 0.0, "فاقد داده"
    if funding >= 0.08:
        return -7.0, "ازدحام لانگ / ریسک بازگشت"
    if funding >= 0.03:
        return -3.0, "فشار لانگ متوسط"
    if funding <= -0.08:
        return 7.0, "ازدحام شورت / ریسک پوشش شورت"
    if funding <= -0.03:
        return 3.0, "فشار شورت متوسط"
    return 0.0, "خنثی"


def _oi_bias(oi_delta: float, price_change: float) -> tuple[float, str]:
    if not math.isfinite(oi_delta):
        return 0.0, "فاقد داده"
    if price_change > 0 and oi_delta > 1.0:
        return 4.0, "افزایش قیمت + افزایش OI"
    if price_change < 0 and oi_delta > 1.0:
        return -4.0, "کاهش قیمت + افزایش OI"
    if price_change > 0 and oi_delta < -1.0:
        return 2.0, "افزایش قیمت + کاهش OI"
    if price_change < 0 and oi_delta < -1.0:
        return -2.0, "کاهش قیمت + کاهش OI"
    return 0.0, "OI بدون تأیید قوی"
