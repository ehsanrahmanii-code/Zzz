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
            side_pri = 0 if dec == "LONG" else 1 if dec == "SHORT" else 2
            g = str(x.get("grade") or ((x.get("signal_grade") or {}).get("grade")) or "—")
            return (
                dir_pri,
                side_pri,
                -GRADE_RANK.get(g, 0),
                -safe_float(x.get("opportunity_score"), 0),
                -safe_float(x.get("trust_index"), 0),
                -safe_float(x.get("signal_quality"), 0),
                order.get(x.get("symbol"), 999),
            )
        results.sort(key=_result_rank)
        scan_timestamp=time.time()
        for _item in results:
            _item["scan_timestamp"]=scan_timestamp
            _item["scan_time_utc"]=datetime.fromtimestamp(scan_timestamp,timezone.utc).isoformat(timespec="seconds")
        try:
            signal_board = rank_market_signals(results)
            macro["signal_board"] = signal_board
            macro["actionable_count"] = signal_board.get("counts", {}).get("actionable", 0)
            macro["grade_summary"] = {
                g: sum(1 for r in results if (r.get("grade") or (r.get("signal_grade") or {}).get("grade")) == g)
                for g in ("A+", "A", "B", "C", "D", "F")
            }
        except Exception as _sb:
            LOGGER.debug("signal board failed: %s", _sb)
            macro["signal_board"] = {"actionable": [], "watchlist": [], "counts": {}}
        try:
            # V32 records one timeframe-specific decision per symbol at scan time.
            # It is deduplicated and later evaluated only against historical OHLC.
            v32_record_scan_predictions(results)
            v32_evaluate_pending()
            store_forecasts(results)
            for item in results:
                _g = str(item.get("grade") or (item.get("signal_grade") or {}).get("grade") or "")
                if (item.get("decision_tag") in {"LONG", "SHORT"}
                    and item.get("alignment", 0) >= 65
                    and item.get("signal_quality", 0) >= MIN_DIRECTIONAL_QUALITY
                    and item.get("bias") in {"صعودی", "نزولی"}
                    and _g in {"A+", "A", "B"}):
                    paper_open_signal(item)
            evaluate_paper_trades(); evaluate_pending_forecasts()
        except Exception as exc: LOGGER.warning("Forecast/paper batch failed: %s", exc)
        # Do NOT block first dashboard paint on Gemini. The market result is complete and
        # usable at this point; keep the previous summary until the fresh AI summary arrives.
        with CACHE_LOCK:
            previous_summary = CACHE.get("gemini_summary") or ""
        if not previous_summary:
            _, previous_summary, _ = _load_market_cache()
        payload = {"timestamp": time.time(), "data": results, "gemini_summary": previous_summary, "macro": macro}
        finished=time.time()
        _scan_progress_update(status="complete",phase="اسکن کامل شد",completed=len(results),total=len(coins),percent=100,finished_at=finished,last_success_at=finished,elapsed_sec=round(finished-scan_started,1),message=f"اسکن جدید کامل شد · {len(results)}/{len(coins)} ارز · داده تازه",fresh=True)
        LOGGER.info("update_cache analyze done in %.1fs coins=%s", time.perf_counter()-scan_t0, len(results))
        results = _v29_sync_snapshot_to_live(results)
        payload["data"] = results
        _save_json(MARKET_CACHE_PATH, payload)
        with CACHE_LOCK:
            CACHE.update(timestamp=time.time(), data=results, gemini_summary=previous_summary, macro=macro)
        # Gemini is deliberately asynchronous: it enriches the live snapshot and
        # is consumed by the next scan, while the current dashboard stays fast.
        threading.Thread(
            target=_v29_async_gemini_enrichment,
            args=(list(results), dict(macro)),
            name="titan-gemini-enrichment",
            daemon=True,
        ).start()
        # Gemini global summary is also non-blocking.
        def _ai_summary_refresh(snapshot, macro_snapshot):
            try:
                fresh = _global_ai_summary(snapshot, macro_snapshot)
                if fresh:
                    with CACHE_LOCK:
                        CACHE["gemini_summary"] = fresh
                    current = _load_market_cache()
                    _save_json(MARKET_CACHE_PATH, {"timestamp": time.time(), "data": current[0] or snapshot, "gemini_summary": fresh, "macro": macro_snapshot})
            except Exception as exc:
                LOGGER.warning("Async Gemini dashboard summary failed: %s", exc)
        threading.Thread(target=_ai_summary_refresh, args=(results, macro), name="titan-gemini-summary", daemon=True).start()
        return results, previous_summary, macro

# ============================================================
# ADVANCED METRICS
# ============================================================


def get_advanced_metrics() -> dict[str, Any]:
    live = _live_status(); audit = get_audit_stats()
    with DB_LOCK, db_conn() as con:
        paper_total = con.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]
        paper_closed = con.execute("SELECT COUNT(*) FROM paper_trades WHERE status='CLOSED'").fetchone()[0]
        paper_open = con.execute("SELECT COUNT(*) FROM paper_trades WHERE status='OPEN'").fetchone()[0]
        paper_values = [safe_float(r[0]) for r in con.execute("SELECT r_multiple FROM paper_trades WHERE status='CLOSED' AND r_multiple IS NOT NULL").fetchall()]
        alerts = [dict(r) for r in con.execute("SELECT id,created_at,severity,symbol,category,message FROM alerts ORDER BY id DESC LIMIT 10").fetchall()]
        quality = con.execute("SELECT COUNT(*), COALESCE(SUM(overall_ok),0) FROM data_quality").fetchone()
    governor = TITAN_EDGE_SUITE.drawdown_governor(paper_values)
    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "live": live, "historical": audit,
            "paper": {"total": int(paper_total), "closed": int(paper_closed), "open": int(paper_open), **_safe_return_series(paper_values)},
            "data_quality": {"samples": int(quality[0]), "healthy": int(quality[1]), "cache_ttl_seconds": MARKET_CACHE_TTL},
            "drawdown_governor": governor, "edge_suite": {"modules": 12, "status": "ACTIVE", "name": TITAN_EDGE_SUITE.name}, "alerts": alerts}
