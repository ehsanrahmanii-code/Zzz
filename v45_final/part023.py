def _v29_num_price(value: Any) -> float:
    """Parse TITAN display prices safely."""
    try:
        s = str(value or "").replace(",", "").replace("$", "").replace("USDT", "").strip()
        return float(s)
    except Exception:
        return 0.0


def _v29_shift_price_field(value: Any, ratio: float) -> Any:
    p = _v29_num_price(value)
    if p <= 0 or not math.isfinite(ratio):
        return value
    return smart_format(p * ratio)


def _v29_sync_snapshot_to_live(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Rebase only price-dependent dashboard outputs to the newest Binance spot
    price. Closed-candle indicators remain untouched; entry/SL/TP and the
    scenario path move with the live reference price.
    """
    if not data:
        return data
    now = time.time()
    with LIVE_LOCK:
        live_map = {
            k: dict(v) for k, v in LIVE_PRICES.items()
            if safe_float(v.get("price"), 0) > 0
        }
    for item in data:
        sym = _normalize_symbol(item.get("symbol", ""))
        lp = live_map.get(sym)
        if not lp:
            continue
        live = safe_float(lp.get("price"), 0)
        if live <= 0:
            continue
        old = _v29_num_price(item.get("price"))
        if old <= 0:
            item["price"] = smart_format(live)
            item["entry_valid"] = smart_format(live)
            continue

        ratio = live / old
        # Keep the canonical signal timestamp/price for audit, but expose a
        # second, authoritative live price for the current UI.
        item.setdefault("signal_snapshot", {})
        item["signal_snapshot"].setdefault("price", old)
        item["signal_snapshot"].setdefault("timestamp", item.get("scan_timestamp", now))
        item["price"] = smart_format(live)
        item["price_raw"] = float(live)
        item["live_price"] = float(live)
        item["entry_valid"] = smart_format(live)
        item["entry_raw"] = float(live)
        for key in ("stop_loss", "tp1", "tp2"):
            if key in item:
                item[key] = _v29_shift_price_field(item.get(key), ratio)

        # Recompute price-relative risk metrics from the live price.
        sl = _v29_num_price(item.get("stop_loss"))
        tp1 = _v29_num_price(item.get("tp1"))
        tp2 = _v29_num_price(item.get("tp2"))
        if sl > 0:
            item["stop_loss_raw"] = float(sl)
            if tp1 > 0: item["tp1_raw"] = float(tp1)
            if tp2 > 0: item["tp2_raw"] = float(tp2)
            item["risk_distance_pct"] = round(abs(live - sl) / live * 100.0, 3)
            item["rr_tp1"] = round(abs(tp1 - live) / max(abs(live - sl), 1e-12), 2) if tp1 > 0 else item.get("rr_tp1", 0)
            item["rr_tp2"] = round(abs(tp2 - live) / max(abs(live - sl), 1e-12), 2) if tp2 > 0 else item.get("rr_tp2", 0)
            item["effective_rr_tp1"] = item["rr_tp1"]
            item["effective_rr_tp2"] = item["rr_tp2"]

        scan_ts = safe_float(item.get("scan_timestamp"), now)
        item["live_price"] = live
        item["live_price_source"] = lp.get("source", "Binance")
        item["live_price_ts"] = safe_float(lp.get("ts"), now)
        item["live_price_age_sec"] = round(max(0.0, now - safe_float(lp.get("ts"), now)), 2)
        item["live_sync"] = True
        item["price_delta_from_scan_pct"] = round((live / old - 1.0) * 100.0, 4)
        item["signal_age_sec"] = round(max(0.0, now - scan_ts), 1)

        # Re-anchor future candle scenario to the same live price while keeping
        # its modeled percentage geometry unchanged.
        fc = item.get("candle_forecast")
        if isinstance(fc, dict):
            fc["last_price"] = round(live, 8)
            for candle in fc.get("candles", []) or []:
                if isinstance(candle, dict):
                    for k in ("open", "high", "low", "close", "mid", "band_low", "band_high"):
                        if k in candle:
                            try:
                                candle[k] = round(float(candle[k]) * ratio, 8)
                            except Exception:
                                pass
    return data


def _v29_async_gemini_enrichment(snapshot: list[dict[str, Any]], macro: dict[str, Any]) -> None:
    """Low-latency asynchronous Gemini evidence pass; never blocks market scan."""
    if not GEMINI_API_KEY or not snapshot:
        return
    try:
        ordered = sorted(
            snapshot,
            key=lambda x: (
                -safe_float(x.get("signal_quality"), 0),
                -safe_float(x.get("success_probability"), 0),
            ),
        )[:AUTO_AI_TOP_N]
        raw = _load_json(AI_SYMBOL_CACHE_PATH, {})
        cache = raw if isinstance(raw, dict) else {}
        jobs = []
        for item in ordered:
            sym = _normalize_symbol(item.get("symbol", ""))
            payload = {
                "task": "TITAN evidence review only; do not invent prices; use supplied live price.",
                "symbol": sym,
                "live_price": _v29_num_price(item.get("price")),
                "decision": item.get("decision_tag", "WAIT"),
                "score": item.get("score", 50),
                "signal_quality": item.get("signal_quality", 0),
                "success_probability": item.get("success_probability", 50),
                "timeframes": item.get("tf_scores", {}),
                "bias": item.get("bias"),
                "entry": item.get("entry_valid"),
                "stop_loss": item.get("stop_loss"),
                "tp1": item.get("tp1"),
                "tp2": item.get("tp2"),
                "rsi": item.get("rsi"),
                "macd": item.get("macd"),
                "derivatives": {
                    "oi": item.get("coinglass_oi"),
                    "funding": item.get("coinglass_funding"),
                    "taker_buy_pct": item.get("taker_buy_pct"),
                    "long_short_ratio": item.get("long_short_ratio"),
                },
                "macro": {
                    "btc_trend": macro.get("btc_trend"),
                    "fear_greed": macro.get("fear_greed_val"),
                },
            }
            jobs.append((sym, payload))

        def one(sym_payload):
            sym, payload = sym_payload
            try:
                result = _call_gemini(payload)
                if result:
                    return sym, {"ts": time.time(), "text": result, "source": "Gemini", "price": payload["live_price"]}
            except Exception as exc:
                LOGGER.debug("V29 async Gemini %s failed: %s", sym, exc)
            return sym, None

        pool = _get_ai_pool(min(4, max(1, len(jobs))))
        futures = [pool.submit(one, j) for j in jobs]
        for fut in as_completed(futures):
            sym, row = fut.result()
            if row:
                cache[sym] = row

        _save_json(AI_SYMBOL_CACHE_PATH, cache)

        # Feed fresh Gemini evidence into the in-memory dashboard without
        # forcing a page reload. The next automatic scan also consumes it.
        with CACHE_LOCK:
            current = CACHE.get("data") or []
            by = {_normalize_symbol(x.get("symbol", "")): x for x in current}
            for sym, row in cache.items():
                if sym in by and isinstance(by[sym], dict) and row.get("text"):
                    ai = by[sym].get("ai_opinions") if isinstance(by[sym].get("ai_opinions"), dict) else {}
                    ai = dict(ai)
                    ai["gemini"] = row["text"]
                    ai["providers"] = list(dict.fromkeys((ai.get("providers") or []) + ["gemini"]))
                    ai["ai_status"] = dict(ai.get("ai_status") or {})
                    ai["ai_status"]["gemini"] = "تحلیل Gemini زنده"
                    ai["cached_at"] = row.get("ts")
                    by[sym]["ai_opinions"] = ai
            CACHE["data"] = _v29_sync_snapshot_to_live(list(by.values()))
            CACHE["timestamp"] = time.time()
            snap = CACHE["data"]
            summary = CACHE.get("gemini_summary") or ""
            macro_now = CACHE.get("macro") or macro
        _save_json(MARKET_CACHE_PATH, {
            "timestamp": time.time(), "data": snap,
            "gemini_summary": summary, "macro": macro_now
        })
    except Exception as exc:
        LOGGER.warning("V29 Gemini enrichment failed: %s", exc)


def _v29_auto_loop() -> None:
    """Permanent autonomous maintenance loop independent of browser requests.

    Three independent maintenance lanes are kept alive:
      1) live multi-asset market scans;
      2) forecast/outcome resolution and learning calibration;
      3) throttled historical-performance/backtest snapshots.

    The performance lane is dispatched in its own daemon thread so an Android
    backtest cannot block the live dashboard or the 45-second market scanner.
    """
    last_scan = 0.0
    while True:
        try:
            now = time.time()
            if now - last_scan >= AUTO_SCAN_INTERVAL_SECONDS:
                started = time.perf_counter()
                queued = _background_market_refresh(False)
                last_scan = now
                LOGGER.info(
                    "V29 autonomous scan %s in %.1fms",
                    "queued" if queued else "already-running",
                    (time.perf_counter() - started) * 1000,
                )

            # Resolve matured forecasts and rebuild the conservative learning
            # profile from actual outcomes. This never invents a result.
            _scan_supervisor_tick()
            _safe_background_forecast_maintenance()

            # Historical performance is throttled internally (currently every
            # 5 minutes) and rotates through symbols. Dispatching it separately
            # prevents a slow backtest/API call from freezing live updates.
            try:
                if now - _PERFORMANCE_LAST_RUN >= PERFORMANCE_AUTO_INTERVAL_SECONDS:
                    threading.Thread(
                        target=autonomous_performance_maintenance,
                        kwargs={"force": False},
                        name="titan-performance-maintenance",
                        daemon=True,
                    ).start()
            except Exception as perf_exc:
                LOGGER.debug("Performance maintenance dispatch failed: %s", perf_exc)
        except Exception as exc:
            LOGGER.warning("V29 autonomous loop error: %s", exc)
        LIVE_STOP.wait(AUTO_MAINTENANCE_INTERVAL_SECONDS)


def update_cache(force: bool = False) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    global CACHE
    reload_keys()
    now = time.time()
    with CACHE_LOCK:
        if CACHE["data"] and not force and now - CACHE["timestamp"] < MARKET_CACHE_TTL:
            return CACHE["data"], CACHE["gemini_summary"], CACHE["macro"]
    with UPDATE_LOCK:
        with CACHE_LOCK:
            if CACHE["data"] and not force and time.time() - CACHE["timestamp"] < MARKET_CACHE_TTL:
                return CACHE["data"], CACHE["gemini_summary"], CACHE["macro"]
        coins = USER_SETTINGS.get("active_coins") or DEFAULT_COINS
        scan_started=time.time()
        _scan_progress_update(status="running",phase="دریافت داده‌های زنده و کلان",started_at=scan_started,finished_at=0.0,completed=0,total=len(coins),percent=4,message="در حال دریافت قیمت، BTC و داده‌های کلان…",fresh=False)
        # Bootstrap: macro + BTC + batch live prices in parallel (one REST round-trip for all coins)
        def _batch_live():
            try:
                prices = _fetch_live_prices(list(coins))
                for sym, px in prices.items():
                    _register_live_price(sym, px, "REST-batch")
                return len(prices)
            except Exception as exc:
                LOGGER.debug("batch live prices: %s", exc)
                return 0
        with ThreadPoolExecutor(max_workers=3) as meta_ex:
            btc_future = meta_ex.submit(fetch_btc_trend)
            macro_future = meta_ex.submit(fetch_macro)
            live_future = meta_ex.submit(_batch_live)
            btc_trend = btc_future.result()
            macro = macro_future.result()
            try:
                live_future.result(timeout=8)
            except Exception:
                pass
        macro["btc_trend"] = btc_trend
        _scan_progress_update(phase="تحلیل تک‌تک ارزها با موتور یکپارچه",percent=12,message="داده‌های اولیه آماده شد؛ تحلیل ارزها در حال انجام است…")
        results: list[dict[str, Any]] = []
        scan_t0 = time.perf_counter()
        pool = _get_analysis_pool(min(14, max(6, len(coins))))
        futures = {pool.submit(analyze_asset, symbol, btc_trend): symbol for symbol in coins}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception as exc:
                LOGGER.exception("Asset analysis failed for %s: %s", symbol, exc)
            finally:
                done=len(results)
                pct=12 + int(72 * min(1.0, done/max(1,len(coins))))
                _scan_progress_update(completed=done,percent=pct,message=f"تحلیل {done}/{len(coins)} ارز تکمیل شد…")
        if not results:
            stale_data, stale_summary, stale_macro = _load_market_cache()
            with CACHE_LOCK: CACHE.update(timestamp=time.time(), data=stale_data, gemini_summary=stale_summary, macro=stale_macro)
            return stale_data, stale_summary, stale_macro
        order = {coin: i for i, coin in enumerate(coins)}
        # V28.4: directional first (LONG/SHORT), then grade, quality, original order
        def _result_rank(x: dict) -> tuple:
            dec = str(x.get("decision_tag") or "WAIT").upper()
            dir_pri = 0 if dec in {"LONG", "SHORT"} else 1