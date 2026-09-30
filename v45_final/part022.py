        "ok": True, "symbol": symbol, "timeframe": tf, "candles": len(df), "metrics": metrics,
        "validation_scope": "technical_proxy_only_no_historical_ai_or_derivatives",
        "long_metrics": long_m, "short_metrics": short_m,
        "long_signals": len(long_returns), "short_signals": len(short_returns),
        "directional_signals": len(decisions), "from": float(df["t"].iloc[0]), "to": float(df["t"].iloc[-1]),
        "return_series_pct": [round(float(x), 6) for x in returns[-1500:]],
        "filters": {
            "long": "score>=58 + ema_gap>=-0.15",
            "short": "score<=40 + ema_gap<=0.10 + momentum<=0.15 + not panic-oversold trap",
            "note": "SHORT filters are stricter to reduce false breakdown signals",
        },
        "professional": {
            "oos": oos, "drawdown_governor": governor,
            "counterfactual": {"paths": paths, "sample": len(cf_records)},
            "strategy_lab": strategies,
            "meta_labeling_reference": "OOS + confluence + historical setup stats + side-split",
        },
    }



def _probability_calibration(symbol: str = "", direction: str = "", raw_prob: float = 50.0) -> dict[str, Any]:
    """Delegate to Platt+Isotonic calibrator (forecasts + paper trades)."""
    return calibrate_success_probability(symbol=symbol, direction=direction, raw_prob=raw_prob)


def _proxy_trade_candidates(df: pd.DataFrame, long_threshold: float, short_threshold: float,
                            min_gap_long: float, min_gap_short: float, max_momentum_short: float,
                            start: int, end: int, friction: float) -> list[float]:
    out=[]
    for i in range(max(60,start), min(end, len(df)-1)):
        sample=df.iloc[:i+1]
        direction, score, meta=_tf_forecast(sample)
        entry=float(df['close'].iloc[i]); future=float(df['close'].iloc[i+1])
        rsi=safe_float(meta.get('rsi'),50); gap=safe_float(meta.get('ema_gap'),0); mom=safe_float(meta.get('momentum'),0)
        if direction=='صعودی' and score>=long_threshold and gap>=min_gap_long:
            out.append(((future-entry)/entry)*100-friction)
        elif direction=='نزولی' and score<=short_threshold and gap<=min_gap_short and mom<=max_momentum_short and not(rsi<22 and mom>-0.5):
            out.append(((entry-future)/entry)*100-friction)
    return out

def walk_forward_backtest(symbol: str, tf: str = "1h", limit: int = 1200, train: int = 300, test: int = 100) -> dict[str, Any]:
    """Purged walk-forward proxy validation with train-only parameter selection.

    This is still a technical proxy (historical AI/derivatives are not reconstructed),
    but unlike the older implementation it actually tunes thresholds on the training
    segment, inserts a purge gap, and reports parameter stability and test-only results.
    """
    limit=min(max(int(limit),train+test+40),MAX_BACKTEST_CANDLES)
    try: df=fetch_klines(symbol,tf,limit)
    except Exception as exc: return {"ok":False,"error":str(exc)}
    friction=TOTAL_ENTRY_BUFFER*2.0*100
    windows=[]; all_test=[]; all_long=[]; all_short=[]; chosen=[]; i=60; purge=1
    grid=[(58,42,-0.15,0.10,0.15),(60,40,-0.10,0.08,0.10),(62,38,-0.05,0.05,0.05),
          (64,36,0.00,0.03,0.00),(60,39,-0.20,0.12,0.20)]
    while i+train+purge+test<=len(df):
        tr=df.iloc[i:i+train]; te=df.iloc[i+train+purge:i+train+purge+test]
        scored=[]
        for params in grid:
            rs=_proxy_trade_candidates(df,*params,i,i+train,friction)
            if len(rs)<8: continue
            m=_safe_return_series(rs,return_unit='pct')
            # Penalize unstable/small samples and large drawdown; choose only on TRAIN.
            obj=safe_float(m.get('expectancy'),-999)-0.10*safe_float(m.get('max_drawdown'),0)+0.002*min(len(rs),100)
            scored.append((obj,params,m))
        if not scored: best=(grid[0],{})
        else:
            best=max(scored,key=lambda z:z[0]); best=(best[1],best[2])
        params=best[0]; chosen.append(params)
        long_t,short_t,gap_l,gap_s,mom_s=params
        rs=[]; lr=[]; sr=[]
        for j in range(len(te)-1):
            sample=df.iloc[:i+train+purge+j+1]
            direction,score,meta=_tf_forecast(sample)
            entry=float(te['close'].iloc[j]); future=float(te['close'].iloc[j+1])
            rsi=safe_float(meta.get('rsi'),50); gap=safe_float(meta.get('ema_gap'),0); mom=safe_float(meta.get('momentum'),0)
            if direction=='صعودی' and score>=long_t and gap>=gap_l:
                x=((future-entry)/entry)*100-friction; rs.append(x);lr.append(x)
            elif direction=='نزولی' and score<=short_t and gap<=gap_s and mom<=mom_s and not(rsi<22 and mom>-0.5):
                x=((entry-future)/entry)*100-friction; rs.append(x);sr.append(x)
        wm=_safe_return_series(rs,return_unit='pct'); wm['long']=_safe_return_series(lr,return_unit='pct'); wm['short']=_safe_return_series(sr,return_unit='pct')
        wm['selected_params']={'long_score':long_t,'short_score':short_t,'long_gap':gap_l,'short_gap':gap_s,'short_momentum':mom_s,'train_trade_count':int(safe_float(best[1].get('trades'),0)) if isinstance(best[1],dict) else 0}
        windows.append(wm); all_test.extend(rs);all_long.extend(lr);all_short.extend(sr);i+=test
    agg=_safe_return_series(all_test,return_unit='pct')
    stability={}
    if chosen:
        for idx,name in enumerate(('long_score','short_score','long_gap','short_gap','short_momentum')):
            vals=[p[idx] for p in chosen]; stability[name]={'min':min(vals),'max':max(vals),'mean':round(float(np.mean(vals)),4),'unique':len(set(vals))}
    return {'ok':True,'symbol':symbol,'timeframe':tf,'windows':len(windows),'aggregate':agg,
            'long_aggregate':_safe_return_series(all_long,return_unit='pct'),'short_aggregate':_safe_return_series(all_short,return_unit='pct'),
            'window_metrics':windows,'purge_candles':purge,
            'validation_scope':'technical_proxy_with_train_only_threshold_selection_and_purge',
            'parameter_stability':stability,'selected_parameters_history':chosen,
            'professional':{'out_of_sample':TITAN_EDGE_SUITE.out_of_sample_check(all_test,return_unit='pct'),
                            'drawdown_governor':TITAN_EDGE_SUITE.drawdown_governor(all_test,unit='pct'),
                            'strategy_lab':TITAN_EDGE_SUITE.strategy_lab(df)}}

# ============================================================
# LIVE ENGINE
# ============================================================


def _register_live_price(symbol: str, price: float, source: str = "REST") -> None:
    if price <= 0: return
    symbol = _normalize_symbol(symbol)
    with LIVE_LOCK:
        previous = LIVE_PRICES.get(symbol, {})
        LIVE_PRICES[symbol] = {"price": float(price), "source": source, "ts": time.time(), "age_ms": 0, "change_pct": ((price / previous["price"] - 1) * 100) if previous.get("price") else 0.0}


def _live_status() -> dict[str, Any]:
    now = time.time()
    with LIVE_LOCK:
        rows = dict(LIVE_PRICES)
    if not rows:
        return {"status": "NO_DATA", "count": 0, "median_age_ms": None, "sources": [], "websocket": bool(_websocket_client)}
    ages = []; sources = set()
    for item in rows.values():
        age = max(0, now - float(item.get("ts", now))) * 1000; item["age_ms"] = round(age, 1); ages.append(age); sources.add(item.get("source", "REST"))
    median_age = statistics.median(ages) if ages else None
    return {"status": "LIVE" if median_age is not None and median_age < 10000 else "DELAYED", "count": len(rows), "median_age_ms": round(median_age, 1) if median_age is not None else None, "sources": sorted(sources), "websocket": bool(_websocket_client)}


def _rest_live_price_worker() -> None:
    while not LIVE_STOP.is_set():
        try:
            for symbol, price in _fetch_live_prices(USER_SETTINGS.get("active_coins") or DEFAULT_COINS).items(): _register_live_price(symbol, price, "REST")
        except Exception as exc: LOGGER.warning("Live REST worker failed: %s", exc)
        LIVE_STOP.wait(LIVE_PRICE_POLL_SECONDS)


def _websocket_worker() -> None:
    if _websocket_client is None: return
    while not LIVE_STOP.is_set():
        try:
            symbols = [_normalize_symbol_for_binance(s).lower() for s in (USER_SETTINGS.get("active_coins") or DEFAULT_COINS)]
            streams = "/".join(f"{s}@miniTicker" for s in symbols)
            ws = _websocket_client.create_connection(f"wss://data-stream.binance.vision/stream?streams={streams}", timeout=10)
            ws.settimeout(10)
            while not LIVE_STOP.is_set():
                raw = ws.recv()
                if not raw: break
                data = json.loads(raw).get("data", {})
                symbol = str(data.get("s", "")); price = safe_float(data.get("c"), 0)
                if symbol and price > 0: _register_live_price(symbol, price, "WebSocket")
            try: ws.close()
            except Exception: pass
        except Exception as exc:
            LOGGER.info("WebSocket unavailable; REST fallback active: %s", exc); LIVE_STOP.wait(5)


def start_live_engine() -> None:
    if any(t.is_alive() for t in LIVE_THREADS): return
    LIVE_STOP.clear()
    rest = threading.Thread(target=_rest_live_price_worker, name="titan-live-rest", daemon=True)
    rest.start(); LIVE_THREADS.append(rest)
    if _websocket_client is not None:
        ws = threading.Thread(target=_websocket_worker, name="titan-live-ws", daemon=True)
        ws.start(); LIVE_THREADS.append(ws)
        # Depth only for a few liquid symbols — lower battery/CPU on mobile
        depth_t = threading.Thread(target=_depth_websocket_worker, name="titan-depth-ws", daemon=True)
        depth_t.start(); LIVE_THREADS.append(depth_t)

# ============================================================
# MARKET CACHE / COMMAND CENTER
# ============================================================


def _load_market_cache() -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    data = _load_json(MARKET_CACHE_PATH, {})
    if not isinstance(data, dict): return [], "", {}
    return data.get("data", []) if isinstance(data.get("data"), list) else [], str(data.get("gemini_summary", "") or ""), data.get("macro", {}) if isinstance(data.get("macro"), dict) else {}


def _global_ai_summary(market_data: list[dict[str, Any]], macro: dict[str, Any]) -> str:
    payload = {"macro": macro, "coins": [{"symbol": x.get("symbol"), "bias": x.get("bias"), "score": x.get("score"), "alignment": x.get("alignment")} for x in market_data[:8]]}
    return _call_gemini(payload, global_summary=True) or ""


def _market_pulse_snapshot(market_data: list[dict[str, Any]], macro: dict[str, Any]) -> dict[str, Any]:
    items = market_data or []
    scores = [safe_float(x.get("score"), 50) for x in items]
    alignments = [safe_float(x.get("alignment"), 50) for x in items]
    bullish = sum(1 for x in items if x.get("bias") == "صعودی")
    bearish = sum(1 for x in items if x.get("bias") == "نزولی")
    neutral = max(0, len(items) - bullish - bearish)
    avg_score = float(np.mean(scores)) if scores else 50.0
    avg_alignment = float(np.mean(alignments)) if alignments else 0.0
    leader = max(items, key=lambda x: safe_float(x.get("signal_quality"), 0), default=None)
    if avg_score >= 62: regime = "متمایل به صعود"
    elif avg_score <= 38: regime = "متمایل به نزول"
    else: regime = "خنثی / دوطرفه"
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), "regime": regime,
        "avg_score": round(avg_score, 1), "avg_alignment": round(avg_alignment, 1),
        "breadth": {"bullish": bullish, "bearish": bearish, "neutral": neutral, "total": len(items)},
        "leader": {"symbol": leader.get("symbol"), "score": leader.get("score"), "quality": leader.get("signal_quality"), "tag": leader.get("signal_tag")} if leader else None,
        "btc_trend": macro.get("btc_trend", "N/A"), "fear_greed": macro.get("fear_greed_val", "N/A"),
        "confluence_avg": round(float(np.mean([safe_float(x.get("edge",{}).get("confluence",{}).get("score"),50) for x in items])) if items else 0,1),
        "meta_accept": sum(1 for x in items if x.get("edge",{}).get("meta",{}).get("label") == "ACCEPT"),
        "defensive_count": sum(1 for x in items if x.get("edge",{}).get("governor",{}).get("state") in {"DEFENSIVE","REDUCED"}),
    }


_BACKGROUND_REFRESH_LOCK = threading.Lock()
_BACKGROUND_REFRESH_RUNNING = False
_SCAN_PROGRESS_LOCK = threading.Lock()
_SCAN_PROGRESS = {
    "status":"idle", "phase":"آماده", "started_at":0.0, "finished_at":0.0,
    "completed":0, "total":0, "percent":0, "message":"هنوز اسکن جدیدی اجرا نشده است",
    "last_success_at":0.0, "elapsed_sec":0.0, "fresh":False
}

def _scan_progress_update(**kwargs):
    with _SCAN_PROGRESS_LOCK:
        _SCAN_PROGRESS.update(kwargs)
        if _SCAN_PROGRESS.get("started_at"):
            _SCAN_PROGRESS["elapsed_sec"] = round(max(0.0, time.time()-float(_SCAN_PROGRESS["started_at"])),1)
        return dict(_SCAN_PROGRESS)

def _scan_progress_snapshot():
    with _SCAN_PROGRESS_LOCK:
        out=dict(_SCAN_PROGRESS)
        if out.get("started_at"):
            out["elapsed_sec"]=round(max(0.0,time.time()-float(out["started_at"])),1)
        return out

def _scan_supervisor_tick() -> None:
    """Android watchdog: recover a stalled scanner without starting duplicate scans."""
    try:
        p = _scan_progress_snapshot()
        if p.get("status") == "running":
            started = float(p.get("started_at") or 0.0)
            # A phone/network stall should not leave the UI permanently stuck.
            if started and time.time() - started > max(180.0, AUTO_SCAN_INTERVAL_SECONDS * 4):
                LOGGER.warning("Android scan watchdog: stale scan detected; releasing refresh gate")
                _scan_progress_update(status="stalled", phase="watchdog", message="اسکن قبلی متوقف شده بود؛ تلاش مجدد…", fresh=False)
                global _BACKGROUND_REFRESH_RUNNING
                with _BACKGROUND_REFRESH_LOCK:
                    _BACKGROUND_REFRESH_RUNNING = False
    except Exception as exc:
        LOGGER.debug("scan watchdog failed: %s", exc)


def _background_market_refresh(force: bool = False) -> bool:
    """Refresh market data outside the request thread so the dashboard can render immediately."""
    global _BACKGROUND_REFRESH_RUNNING
    with _BACKGROUND_REFRESH_LOCK:
        if _BACKGROUND_REFRESH_RUNNING:
            return False
        _BACKGROUND_REFRESH_RUNNING = True
    def _runner():
        global _BACKGROUND_REFRESH_RUNNING
        try:
            update_cache(force)
        except Exception as exc:
            LOGGER.exception("Background market refresh failed: %s", exc)
        finally:
            with _BACKGROUND_REFRESH_LOCK:
                _BACKGROUND_REFRESH_RUNNING = False
    threading.Thread(target=_runner, name="titan-market-refresh", daemon=True).start()
    return True

def _fast_market_snapshot() -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    """Return memory cache first, then disk cache, without network calls."""
    with CACHE_LOCK:
        cached_data = list(CACHE.get("data") or [])
        cached_summary = CACHE.get("gemini_summary") or ""
        cached_macro = CACHE.get("macro") or {}
    if cached_data:
        # Single-source price rule: even RAM-cache hits must pass through the
        # same LIVE_PRICES rebase before any API/dashboard consumer receives them.
        try:
            live_data = _v29_sync_snapshot_to_live(cached_data)
            with CACHE_LOCK:
                CACHE["data"] = live_data
            return live_data, cached_summary, cached_macro
        except Exception as exc:
            LOGGER.debug("Live RAM snapshot sync failed: %s", exc)
            return cached_data, cached_summary, cached_macro
    data, summary, macro = _load_market_cache()
    if data:
        # Preserve the timestamp written by the scan instead of replacing it
        # with application restart time. This is critical for truthful freshness.
        raw=_load_json(MARKET_CACHE_PATH,{})
        stored_ts=safe_float(raw.get("timestamp"),0.0) if isinstance(raw,dict) else 0.0
        with CACHE_LOCK:
            CACHE.update(timestamp=stored_ts or time.time(), data=data, gemini_summary=summary, macro=macro)
    # Critical consistency rule: cached analytical state may be 40s old, but the
    # displayed market price must always come from the freshest live ticker.
    if data:
        try:
            data = _v29_sync_snapshot_to_live(list(data))
            with CACHE_LOCK:
                CACHE["data"] = data
        except Exception as exc:
            LOGGER.debug("Live snapshot sync failed: %s", exc)
    return data or [], summary or "", macro or {}

