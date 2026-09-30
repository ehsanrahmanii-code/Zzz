# 3) Order-Block / Fair Value Gap (FVG)
# 4) Depth WebSocket for default liquid symbols only

DEPTH_WATCHLIST = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
DEPTH_STATE: dict[str, dict[str, Any]] = {}
DEPTH_LOCK = threading.RLock()
BTC_RETURNS_CACHE: dict[str, Any] = {"ts": 0.0, "rets": None}

# Short-TTL cache for per-symbol BTC correlation (avoids repeated kline fetches)
BTC_CORR_CACHE: dict[str, tuple[float, dict]] = {}
BTC_CORR_CACHE_TTL = 90.0




def _pava_isotonic(xs: list[float], ys: list[float], ws: Optional[list[float]] = None) -> list[float]:
    """Pool-Adjacent-Violators for non-decreasing calibration curve."""
    n = len(ys)
    if n == 0:
        return []
    w = ws if ws and len(ws) == n else [1.0] * n
    y = list(ys)
    weight = [float(x) for x in w]
    i = 0
    while i < n - 1:
        if y[i] <= y[i + 1] + 1e-12:
            i += 1
            continue
        # merge i and i+1
        total_w = weight[i] + weight[i + 1]
        avg = (y[i] * weight[i] + y[i + 1] * weight[i + 1]) / max(total_w, 1e-12)
        y[i] = avg
        weight[i] = total_w
        del y[i + 1]
        del weight[i + 1]
        n -= 1
        if i > 0:
            i -= 1
    # expand back — simple: rebuild from unique pools by re-running with block sizes
    # For sparse bins we already merged; return monotone ys of same length as input via projection
    # Rebuild properly:
    y0 = list(ys)
    w0 = [float(x) for x in (ws if ws and len(ws) == len(ys) else [1.0] * len(ys))]
    blocks = [[i] for i in range(len(y0))]
    vals = [y0[i] for i in range(len(y0))]
    weights = [w0[i] for i in range(len(y0))]
    changed = True
    while changed:
        changed = False
        i = 0
        while i < len(vals) - 1:
            if vals[i] > vals[i + 1] + 1e-12:
                new_w = weights[i] + weights[i + 1]
                new_v = (vals[i] * weights[i] + vals[i + 1] * weights[i + 1]) / max(new_w, 1e-12)
                vals[i] = new_v
                weights[i] = new_w
                blocks[i] = blocks[i] + blocks[i + 1]
                del vals[i + 1]
                del weights[i + 1]
                del blocks[i + 1]
                changed = True
                if i > 0:
                    i -= 1
            else:
                i += 1
    out = [0.0] * len(y0)
    for b, v in zip(blocks, vals):
        for idx in b:
            out[idx] = v
    return out


def _platt_scale(raw_probs: list[float], labels: list[float], x_query: float) -> Optional[float]:
    """Fit simple Platt logistic P = 1/(1+exp(A*f+B)) via Newton on 2 params; return calibrated for x_query in [0,1]."""
    try:
        import math as _m
        n = len(raw_probs)
        if n < 12:
            return None
        # features as logit of raw
        f = []
        for p in raw_probs:
            p = clamp(p, 1e-4, 1 - 1e-4)
            f.append(_m.log(p / (1 - p)))
        y = labels
        A, B = 0.0, 0.0
        for _ in range(40):
            gA = gB = 0.0
            hAA = hAB = hBB = 0.0
            for fi, yi in zip(f, y):
                z = A * fi + B
                # stable sigmoid
                if z >= 0:
                    ez = _m.exp(-z)
                    p = 1.0 / (1.0 + ez)
                else:
                    ez = _m.exp(z)
                    p = ez / (1.0 + ez)
                diff = p - yi
                gA += diff * fi
                gB += diff
                w = p * (1 - p)
                hAA += w * fi * fi
                hAB += w * fi
                hBB += w
            # damped Newton
            det = hAA * hBB - hAB * hAB
            if abs(det) < 1e-12:
                break
            dA = (hBB * gA - hAB * gB) / det
            dB = (hAA * gB - hAB * gA) / det
            A -= 0.7 * dA
            B -= 0.7 * dB
            if abs(dA) + abs(dB) < 1e-6:
                break
        xq = clamp(x_query, 1e-4, 1 - 1e-4)
        fq = _m.log(xq / (1 - xq))
        z = A * fq + B
        if z >= 0:
            ez = _m.exp(-z)
            return 1.0 / (1.0 + ez)
        ez = _m.exp(z)
        return ez / (1.0 + ez)
    except Exception:
        return None


def calibrate_success_probability(
    symbol: str = "",
    direction: str = "",
    raw_prob: float = 50.0,
) -> dict[str, Any]:
    """Platt + Isotonic calibration using forecasts AND closed paper trades.

    Returns calibrated probability in 0-100 scale with diagnostics.
    """
    raw = float(clamp(raw_prob, 1.0, 99.0))
    pairs: list[tuple[float, float]] = []
    sources_used: list[str] = []
    try:
        where = ["outcome IN ('WIN','LOSS')", "success_prob > 0"]
        args: list[Any] = []
        if symbol:
            where.append("symbol=?")
            args.append(symbol)
        if direction in {"صعودی", "نزولی", "LONG", "SHORT"}:
            # map
            dmap = {"LONG": "صعودی", "SHORT": "نزولی"}
            dval = dmap.get(direction, direction)
            where.append("direction=?")
            args.append(dval)
        with DB_LOCK, db_conn() as con:
            rows = con.execute(
                "SELECT success_prob, outcome FROM forecasts WHERE " + " AND ".join(where)
                + " ORDER BY evaluated_at DESC, id DESC LIMIT 800",
                args,
            ).fetchall()
            for r in rows:
                pp = safe_float(r[0], 50) / 100.0
                yy = 1.0 if str(r[1]).upper() == "WIN" else 0.0
                if math.isfinite(pp):
                    pairs.append((clamp(pp, 0, 1), yy))
            if pairs:
                sources_used.append("forecasts")
            # Paper trades with stored entry probability contribute honest samples.
            paper_where = ["status='CLOSED'", "success_prob > 0", "pnl_pct IS NOT NULL"]
            paper_args: list[Any] = []
            if symbol:
                paper_where.append("symbol=?")
                paper_args.append(symbol)
            if direction in {"صعودی", "نزولی", "LONG", "SHORT"}:
                dmap = {"LONG": "صعودی", "SHORT": "نزولی"}
                dval = dmap.get(direction, direction)
                paper_where.append("decision=?")
                paper_args.append(dval)
            prows = con.execute(
                "SELECT success_prob, pnl_pct FROM paper_trades WHERE "
                + " AND ".join(paper_where)
                + " ORDER BY closed_at DESC, id DESC LIMIT 400",
                paper_args,
            ).fetchall()
            paper_n = 0
            for r in prows:
                pp = safe_float(r[0], 0) / 100.0
                pnl = safe_float(r[1], 0)
                if not math.isfinite(pp) or pp <= 0:
                    continue
                yy = 1.0 if pnl > 0 else 0.0
                pairs.append((clamp(pp, 0, 1), yy))
                paper_n += 1
            if paper_n:
                sources_used.append("paper_trades")
    except Exception as exc:
        LOGGER.debug("calibration data load failed: %s", exc)

    if len(pairs) < 8:
        return {
            "raw": round(raw, 1),
            "calibrated": round(raw, 1),
            "samples": len(pairs),
            "method": "prior_only",
            "platt": None,
            "isotonic": None,
            "sources": sources_used,
        }

    probs = [p for p, _ in pairs]
    labels = [y for _, y in pairs]
    x = raw / 100.0

    # Platt
    platt_p = _platt_scale(probs, labels, x)

    # Isotonic on 10 bins
    bins = []
    for k in range(10):
        lo, hi = k / 10, (k + 1) / 10
        vals = [y for px, y in pairs if (lo <= px < hi) or (k == 9 and lo <= px <= hi)]
        if vals:
            rate = (sum(vals) + 2.0) / (len(vals) + 4.0)  # Beta(2,2)
            bins.append((lo + 0.05, rate, len(vals)))
    xs = [b[0] for b in bins]
    ys = [b[1] for b in bins]
    ws = [b[2] for b in bins]
    iso = _pava_isotonic(xs, ys, ws) if bins else []
    iso_p = None
    if bins and iso:
        if x <= xs[0]:
            iso_p = iso[0]
        elif x >= xs[-1]:
            iso_p = iso[-1]
        else:
            j = 0
            for i in range(len(xs) - 1):
                if xs[i] <= x <= xs[i + 1]:
                    j = i
                    break
            span = max(xs[j + 1] - xs[j], 1e-9)
            iso_p = iso[j] + (iso[j + 1] - iso[j]) * (x - xs[j]) / span

    # Blend: prefer isotonic when samples high; Platt for smooth mid-range
    n = len(pairs)
    if platt_p is not None and iso_p is not None:
        w_iso = min(0.65, n / 120.0)
        cal = (1 - w_iso) * platt_p + w_iso * iso_p
        method = "platt+isotonic"
    elif iso_p is not None:
        cal = iso_p
        method = "isotonic"
    elif platt_p is not None:
        cal = platt_p
        method = "platt"
    else:
        cal = x
        method = "raw"

    # Shrink toward raw when n small
    shrink = min(1.0, n / 80.0)
    cal = shrink * cal + (1 - shrink) * x
    # Conservative cap: never claim >88% from calibration alone
    cal = clamp(cal, 0.08, 0.88)

    # ECE / Brier rough
    brier = sum((p - y) ** 2 for p, y in pairs) / max(1, n)
    ece = 0.0
    if bins:
        for (_, rate, cnt), mid in zip(bins, xs):
            ece += (cnt / n) * abs(rate - mid)

    return {
        "raw": round(raw, 1),
        "calibrated": round(cal * 100.0, 1),
        "samples": n,
        "method": method,
        "platt": round(platt_p * 100, 1) if platt_p is not None else None,
        "isotonic": round(iso_p * 100, 1) if iso_p is not None else None,
        "ece": round(ece, 4),
        "brier": round(brier, 4),
        "sources": sources_used,
    }


def compute_btc_correlation(symbol: str, lookback: int = 48) -> dict[str, Any]:
    """Pearson correlation of recent 1h returns vs BTC — for high-vol alt filter."""
    try:
        if symbol in {"BTC/USDT", "BTCUSDT"}:
            return {"corr": 1.0, "samples": lookback, "regime": "self"}
        now = time.time()
        _ck = f"{_normalize_symbol(symbol)}|{lookback}"
        _hit = BTC_CORR_CACHE.get(_ck)
        if _hit and (now - _hit[0]) < BTC_CORR_CACHE_TTL:
            return _hit[1]
        global BTC_RETURNS_CACHE
        btc_rets = BTC_RETURNS_CACHE.get("rets")
        if btc_rets is None or now - float(BTC_RETURNS_CACHE.get("ts") or 0) > 180:
            btc_df = fetch_klines("BTC/USDT", "1h", lookback + 5)
            btc_rets = btc_df["close"].astype(float).pct_change().dropna().tail(lookback)
            BTC_RETURNS_CACHE = {"ts": now, "rets": btc_rets}
        alt_df = fetch_klines(symbol, "1h", lookback + 5)
        alt_rets = alt_df["close"].astype(float).pct_change().dropna().tail(lookback)
        n = min(len(btc_rets), len(alt_rets))
        if n < 12:
            return {"corr": 0.0, "samples": n, "regime": "insufficient"}
        a = alt_rets.tail(n).values
        b = btc_rets.tail(n).values
        if float(np.std(a)) < 1e-12 or float(np.std(b)) < 1e-12:
            return {"corr": 0.0, "samples": n, "regime": "flat"}
        corr = float(np.corrcoef(a, b)[0, 1])
        if not math.isfinite(corr):
            corr = 0.0
        _out = {"corr": round(corr, 3), "samples": n, "regime": "high_beta" if corr >= 0.75 else "decoupled" if corr < 0.35 else "normal"}
        BTC_CORR_CACHE[_ck] = (now, _out)
        if len(BTC_CORR_CACHE) > 60:
            for _k, _ in sorted(BTC_CORR_CACHE.items(), key=lambda x: x[1][0])[:15]:
                BTC_CORR_CACHE.pop(_k, None)
        return _out
    except Exception as exc:
        LOGGER.debug("btc corr failed %s: %s", symbol, exc)
        return {"corr": 0.0, "samples": 0, "regime": "error"}


def apply_btc_correlation_filter(
    symbol: str,
    decision_tag: str,
    bias: str,
    atr_pct: float,
    btc_trend: str,
    corr_info: Optional[dict] = None,
) -> tuple[str, str, dict[str, Any]]:
    """In high-vol regimes, block alt longs when BTC is bearish & correlation is high (and vice versa)."""
    info = corr_info or compute_btc_correlation(symbol)
    note = {
        "corr": info.get("corr"),
        "corr_regime": info.get("regime"),
        "filter_applied": False,
        "reason": "",
    }
    if symbol in {"BTC/USDT", "BTCUSDT"}:
        return decision_tag, bias, note
    corr = safe_float(info.get("corr"), 0)
    high_vol = atr_pct >= 3.5
    # Only act in high volatility or very high beta
    if not high_vol and corr < 0.8:
        return decision_tag, bias, note
    if corr < 0.55:
        note["reason"] = "همبستگی پایین با BTC — فیلتر غیرفعال"
        return decision_tag, bias, note

    if decision_tag == "LONG" and btc_trend == "نزولی" and corr >= 0.65:
        note["filter_applied"] = True
        note["reason"] = f"آلت لانگ در رژیم پرنوسان با همبستگی BTC={corr:.2f} و روند نزولی BTC مسدود شد"
        return "WAIT", "خنثی", note
    if decision_tag == "SHORT" and btc_trend == "صعودی" and corr >= 0.65:
        note["filter_applied"] = True
        note["reason"] = f"آلت شورت در رژیم پرنوسان با همبستگی BTC={corr:.2f} و روند صعودی BTC مسدود شد"
        return "WAIT", "خنثی", note
    note["reason"] = "فیلتر همبستگی BTC عبور کرد"
    return decision_tag, bias, note


def detect_order_blocks_fvg(df: pd.DataFrame, lookback: int = 40) -> dict[str, Any]:
    """Simple Order-Block and Fair Value Gap detection on closed candles.

    Bullish OB: last down candle before strong impulsive up move.
    Bearish OB: last up candle before strong impulsive down move.
    FVG: 3-candle gap where candle[i-2].high < candle[i].low (bull) or reverse (bear).
    """
    try:
        if df is None or len(df) < 15:
            return {"order_blocks": [], "fvgs": [], "nearest_ob": None, "nearest_fvg": None}
        d = df.tail(lookback).reset_index(drop=True)
        o = d["open"].astype(float)
        h = d["high"].astype(float)
        l = d["low"].astype(float)
        c = d["close"].astype(float)
        atr_s = (h - l).rolling(14).mean().bfill()
        obs: list[dict[str, Any]] = []
        fvgs: list[dict[str, Any]] = []
        price = float(c.iloc[-1])

        for i in range(3, len(d) - 1):
            body = abs(float(c.iloc[i]) - float(o.iloc[i]))
            atr_i = float(atr_s.iloc[i]) or price * 0.01
            move = float(c.iloc[i]) - float(c.iloc[i - 1])
            # Bullish FVG: gap up between candle i-2 high and candle i low
            if float(h.iloc[i - 2]) < float(l.iloc[i]):
                gap_lo, gap_hi = float(h.iloc[i - 2]), float(l.iloc[i])
                if gap_hi - gap_lo > 0.15 * atr_i:
                    fvgs.append({
                        "type": "bullish_fvg",
                        "low": round(gap_lo, 8),
                        "high": round(gap_hi, 8),
                        "mid": round((gap_lo + gap_hi) / 2, 8),
                        "index": i,
                        "guide": "گپ صعودی پرنشده — اغلب به‌عنوان حمایت پویا عمل می‌کند؛ پر شدن گپ می‌تواند ادامه یا برگشت باشد.",
                    })
            # Bearish FVG
            if float(l.iloc[i - 2]) > float(h.iloc[i]):
                gap_hi, gap_lo = float(l.iloc[i - 2]), float(h.iloc[i])
                if gap_hi - gap_lo > 0.15 * atr_i:
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