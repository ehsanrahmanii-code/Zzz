        now_ms = int(time.time() * 1000)
        df = df[df["T"] < now_ms].sort_values("t").drop_duplicates(subset=["t"], keep="last").reset_index(drop=True)

    if len(df) < 10:
        raise RuntimeError(f"Insufficient closed candles for {symbol} {tf}")
    if cacheable:
        _kline_cache_put(ckey, df)
    return df


def _binance_futures_funding(symbol: str) -> Optional[float]:
    try:
        r = _http_session().get(
            "https://fapi.binance.com/fapi/v1/premiumIndex",
            params={"symbol": _binance_symbol(symbol)}, timeout=8,
        )
        if not r.ok:
            return None
        payload = r.json()
        if not isinstance(payload, dict):
            return None
        return safe_float(payload.get("lastFundingRate")) * 100
    except Exception:
        return None


def _binance_futures_oi(symbol: str) -> Optional[float]:
    try:
        r = _http_session().get(
            "https://fapi.binance.com/fapi/v1/openInterest",
            params={"symbol": _binance_symbol(symbol)}, timeout=8,
        )
        if not r.ok:
            return None
        payload = r.json()
        if not isinstance(payload, dict):
            return None
        value = safe_float(payload.get("openInterest"))
        return value if value > 0 else None
    except Exception:
        return None


def fetch_derivatives(symbol: str) -> dict[str, Any]:
    # Short TTL cache — funding/OI rarely need sub-20s refresh during one scan
    _sym_key = _normalize_symbol(symbol)
    with KLINE_CACHE_LOCK:
        _hit = DERIV_CACHE.get(_sym_key)
        if _hit and (time.time() - _hit[0]) < DERIV_CACHE_TTL:
            return _hit[1]
    clean = _binance_symbol(symbol)
    base = clean.replace("USDT", "")
    raw_oi = 0.0
    oi_kind = "unknown"
    funding: Optional[float] = None
    cg_usd = cg_qty = cg_delta = None
    source_parts: list[str] = []

    if COINGLASS_API_KEY:
        headers = {"CG-API-KEY": COINGLASS_API_KEY}
        try:
            res = _http_session().get(
                "https://open-api-v4.coinglass.com/api/futures/open-interest/exchange-list",
                params={"symbol": base}, headers=headers, timeout=10,
            ).json()
            if str(res.get("code")) in {"0", "200"}:
                rows = res.get("data") or []
                row = next((r for r in rows if str(r.get("exchange", "")).lower() == "all"), rows[0] if rows else None)
                if row:
                    cg_qty = safe_float(row.get("open_interest_quantity"), 0)
                    cg_usd = safe_float(row.get("open_interest_usd"), 0)
                    cg_delta = safe_float(row.get("open_interest_change_percent_5m"), 0)
                    if cg_usd and cg_usd > 0:
                        raw_oi, oi_kind = cg_usd, "usd"
                    elif cg_qty and cg_qty > 0:
                        raw_oi, oi_kind = cg_qty, "base"
                    if raw_oi > 0:
                        source_parts.append("CoinGlass-OI")
        except Exception as exc:
            LOGGER.warning("CoinGlass OI failed for %s: %s", symbol, exc)
        try:
            res = _http_session().get(
                "https://open-api-v4.coinglass.com/api/futures/funding-rate/exchange-list",
                params={"symbol": base}, headers=headers, timeout=10,
            ).json()
            if str(res.get("code")) in {"0", "200"}:
                rows = res.get("data") or []
                row = next((r for r in rows if str(r.get("symbol", "")).upper() == base), rows[0] if rows else None)
                if row:
                    vals = [safe_float(x.get("funding_rate"), np.nan) for x in (row.get("stablecoin_margin_list") or [])]
                    vals = [x for x in vals if np.isfinite(x)]
                    if vals:
                        funding = float(np.mean(vals)) * 100
                        source_parts.append("CoinGlass-Funding")
        except Exception as exc:
            LOGGER.warning("CoinGlass funding failed for %s: %s", symbol, exc)

    if funding is None:
        funding = _binance_futures_funding(symbol)
        if funding is not None:
            source_parts.append("Binance-Funding")
    if raw_oi <= 0:
        fallback_oi = _binance_futures_oi(symbol)
        if fallback_oi is not None:
            raw_oi, oi_kind = fallback_oi, "base"
            source_parts.append("Binance-OI")

    now = time.time()
    delta = cg_delta if cg_delta is not None else 0.0
    with OI_LOCK:
        previous = OI_HISTORY.get(symbol)
        if cg_delta is None and previous and previous[2] == oi_kind:
            prev_oi, prev_ts, _ = previous
            if prev_oi > 0 and raw_oi > 0 and now - prev_ts <= 900:
                delta = ((raw_oi - prev_oi) / prev_oi) * 100
        if raw_oi > 0:
            OI_HISTORY[symbol] = (raw_oi, now, oi_kind)

    if cg_usd and cg_usd > 0:
        oi_disp = f"${smart_format(cg_usd)}"
    elif cg_qty and cg_qty > 0:
        oi_disp = f"{smart_format(cg_qty)} {base}"
    elif raw_oi > 0:
        oi_disp = f"{smart_format(raw_oi)} {base}"
    else:
        oi_disp = "N/A"
    ls = fetch_binance_long_short_ratio(symbol)
    taker = fetch_binance_taker_buy_sell(symbol)
    if ls.get("source") and ls.get("source") != "N/A":
        source_parts.append(str(ls.get("source")))
    if taker.get("source") and taker.get("source") != "N/A":
        source_parts.append(str(taker.get("source")))
    out = {
        "oi": oi_disp,
        "raw_oi": raw_oi,
        "oi_delta": delta,
        "funding_value": funding,
        "funding": f"{funding:+.4f}%" if funding is not None else "N/A",
        "source": " + ".join(dict.fromkeys(source_parts)) if source_parts else "N/A",
        "long_short": ls,
        "taker": taker,
        "long_ratio": ls.get("long_ratio"),
        "short_ratio": ls.get("short_ratio"),
        "long_short_ratio": ls.get("long_short_ratio"),
        "top_long_ratio": ls.get("top_long_ratio"),
        "taker_buy_pct": taker.get("buy_pct", 50),
        "taker_sell_pct": taker.get("sell_pct", 50),
    }
    with KLINE_CACHE_LOCK:
        DERIV_CACHE[_normalize_symbol(symbol)] = (time.time(), out)
        if len(DERIV_CACHE) > 80:
            for k, _ in sorted(DERIV_CACHE.items(), key=lambda x: x[1][0])[:20]:
                DERIV_CACHE.pop(k, None)
    return out


def fetch_btc_trend() -> str:
    try:
        df = fetch_klines("BTC/USDT", "1h", 60)
        ema = df["close"].ewm(span=20, adjust=False).mean().iloc[-1]
        return "صعودی" if float(df["close"].iloc[-1]) >= float(ema) else "نزولی"
    except Exception as exc:
        LOGGER.warning("BTC trend failed: %s", exc)
        return "خنثی"


def fetch_macro() -> dict[str, Any]:
    fear_value = "N/A"
    fear_text = "داده نیست"
    dominance = "N/A"
    sources: list[str] = []
    try:
        payload = _http_session().get("https://api.alternative.me/fng/", params={"limit": 1}, timeout=8).json()
        data = payload.get("data") or []
        if data:
            fear_value = data[0].get("value", "N/A")
            fear_text = data[0].get("value_classification", "N/A")
            sources.append("Alternative.me")
    except Exception as exc:
        LOGGER.warning("Fear & Greed failed: %s", exc)
    try:
        payload = _http_session().get("https://api.coingecko.com/api/v3/global", timeout=8).json()
        btc_dom = safe_float((payload.get("data") or {}).get("market_cap_percentage", {}).get("btc"), np.nan)
        if np.isfinite(btc_dom):
            dominance = f"{btc_dom:.2f}%"
            sources.append("CoinGecko")
    except Exception as exc:
        LOGGER.warning("CoinGecko macro failed: %s", exc)
    return {"fear_greed_val": fear_value, "fear_greed_text": fear_text, "global_status": " / ".join(sources) or "N/A", "dominance_btc": dominance}

# ============================================================
# TECHNICALS / DECISION CORE
# ============================================================




# === TITAN V6.2 PROFESSIONAL MODULES ===
# 1) Platt + Isotonic calibration from paper trades
# 2) BTC correlation filter for alts in high-vol
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