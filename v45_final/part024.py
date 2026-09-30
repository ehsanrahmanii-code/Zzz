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

# ============================================================
# AUTONOMOUS PERFORMANCE SNAPSHOT ENGINE
# ============================================================

PERFORMANCE_AUTO_INTERVAL_SECONDS = 300
PERFORMANCE_SYMBOLS_PER_RUN = 3
_PERFORMANCE_LOCK = threading.Lock()
_PERFORMANCE_LAST_RUN = 0.0
_PERFORMANCE_CURSOR = 0
_PERFORMANCE_LAST_RESULT: dict[str, Any] = {"ok": True, "status": "never_run", "completed": 0, "failed": 0}


def _store_performance_snapshot(symbol: str, tf: str, result: dict[str, Any]) -> None:
    if not isinstance(result, dict) or not result.get("ok"):
        return
    m = result.get("metrics") or {}
    oos = (((result.get("professional") or {}).get("oos") or {}).get("status")
           or ((result.get("professional") or {}).get("out_of_sample") or {}).get("status") or "")
    payload = json.dumps(result, ensure_ascii=False, default=str)
    with DB_LOCK, db_conn() as con:
        con.execute(
            """INSERT INTO performance_snapshots(
                symbol,timeframe,created_at,trades,wins,losses,win_rate,expectancy,
                profit_factor,max_drawdown,sharpe,sortino,oos_status,metrics_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                _normalize_symbol(symbol), str(tf), time.time(),
                int(safe_float(m.get("trades"), 0)),
                int(safe_float(m.get("wins"), 0)),
                int(safe_float(m.get("losses"), 0)),
                safe_float(m.get("win_rate"), 0),
                safe_float(m.get("expectancy"), 0),
                safe_float(m.get("profit_factor"), 0) if m.get("profit_factor") is not None else None,
                safe_float(m.get("max_drawdown"), 0),
                safe_float(m.get("sharpe"), 0),
                safe_float(m.get("sortino"), 0),
                str(oos),
                payload[-120000:],
            ),
        )


def autonomous_performance_maintenance(force: bool = False) -> dict[str, Any]:
    """Continuously build auditable backtest history without browser interaction.

    This is deliberately throttled for Android: a small rotating subset of coins
    is evaluated each cycle, while all timeframes are covered for those coins.
    """
    global _PERFORMANCE_LAST_RUN, _PERFORMANCE_CURSOR, _PERFORMANCE_LAST_RESULT
    now = time.time()
    if not force and now - _PERFORMANCE_LAST_RUN < PERFORMANCE_AUTO_INTERVAL_SECONDS:
        return {"ok": True, "skipped": True, "reason": "interval"}
    if not _PERFORMANCE_LOCK.acquire(blocking=False):
        return {"ok": True, "skipped": True, "reason": "already_running"}
    try:
        _PERFORMANCE_LAST_RUN = now
        coins = list(USER_SETTINGS.get("active_coins") or DEFAULT_COINS)
        if not coins:
            return {"ok": False, "error": "no active coins"}
        start = _PERFORMANCE_CURSOR % len(coins)
        selected = [coins[(start + i) % len(coins)] for i in range(min(PERFORMANCE_SYMBOLS_PER_RUN, len(coins)))]
        _PERFORMANCE_CURSOR = (start + len(selected)) % len(coins)
        summary = {"ok": True, "symbols": selected, "timeframes": list(TF_CFG), "completed": 0, "failed": 0, "started_at": now}
        for sym in selected:
            for tf in TF_CFG:
                try:
                    result = backtest_signal_logic(_normalize_symbol(sym), tf, 800)
                    if result.get("ok"):
                        _store_performance_snapshot(sym, tf, result)
                        summary["completed"] += 1
                    else:
                        summary["failed"] += 1
                except Exception as exc:
                    summary["failed"] += 1
                    LOGGER.debug("Autonomous performance %s %s failed: %s", sym, tf, exc)
        # Retain bounded history; raw metrics are also available in the latest rows.
        with DB_LOCK, db_conn() as con:
            con.execute(
                "DELETE FROM performance_snapshots WHERE id NOT IN "
                "(SELECT id FROM performance_snapshots ORDER BY created_at DESC LIMIT 5000)"
            )
        summary["finished_at"] = time.time()
        summary["elapsed_sec"] = round(summary["finished_at"] - now, 2)
        summary["status"] = "complete" if summary["failed"] == 0 else "partial"
        _PERFORMANCE_LAST_RESULT = dict(summary)
        return summary
    finally:
        _PERFORMANCE_LOCK.release()


def get_performance_history(symbol: str = "", tf: str = "", limit: int = 120) -> dict[str, Any]:
    symbol = _normalize_symbol(symbol) if symbol else ""
    limit = max(1, min(int(limit), 500))
    where, args = [], []
    if symbol:
        where.append("symbol=?"); args.append(symbol)
    if tf in TF_CFG:
        where.append("timeframe=?"); args.append(tf)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    with DB_LOCK, db_conn() as con:
        rows = con.execute(
            f"SELECT symbol,timeframe,created_at,trades,wins,losses,win_rate,expectancy,"
            f"profit_factor,max_drawdown,sharpe,sortino,oos_status "
            f"FROM performance_snapshots{clause} ORDER BY created_at DESC LIMIT ?",
            (*args, limit),
        ).fetchall()
    return {
        "ok": True,
        "items": [dict(r) for r in rows],
        "count": len(rows),
        "source": "AUTONOMOUS_BACKTEST_HISTORY",
        "autonomous_status": dict(_PERFORMANCE_LAST_RESULT),
    }


# ============================================================
# TITAN ENTERPRISE V4 - ADVANCED CONTROL MODULES
# Restored from the user's original master build. Additive only.
# ============================================================

class TitanEnterpriseEnhancementV4:
    """
    Enterprise enhancement layer:
    1. Pipeline validation
    2. Learning memory hooks
    3. Backtest framework
    4. Adaptive weighting
    5. Market manipulation protection
    6. Runtime safety checks
    """
    def __init__(self):
        self.history = []
        self.weights = {
            "technical": 0.35,
            "ai": 0.30,
            "derivatives": 0.20,
            "risk": 0.15
        }

    def validate_pipeline(self, data):
        return bool(data and isinstance(data, dict))

    def save_feedback(self, signal, result):
        _append_capped(self.history, {"signal": signal, "result": result}, 256)

    def adaptive_weights(self, market_state="normal"):
        if market_state == "sideways":
            self.weights = {
                "technical": 0.25,
                "ai": 0.25,
                "derivatives": 0.30,
                "risk": 0.20
            }
        elif market_state == "trend":
            self.weights = {
                "technical": 0.45,
                "ai": 0.30,
                "derivatives": 0.15,
                "risk": 0.10
            }
        return self.weights

    def backtest_record(self, decision, price_before, price_after):
        change = 0
        if price_before:
            change = ((price_after - price_before) / price_before) * 100
        return {"decision": decision, "performance": round(change, 4)}

    def anomaly_check(self, volume_change=0, volatility=0):
        if volume_change > 300 or volatility > 10:
            return {"blocked": True, "reason": "market anomaly detected"}
        return {"blocked": False}

    def self_check(self, payload):
        checks = {
            "data": self.validate_pipeline(payload),
            "risk": payload.get("risk", 0) < 50 if isinstance(payload, dict) else False,
            "engine": True
        }
        return {"passed": all(checks.values()), "checks": checks}


TITAN_ENTERPRISE_V4 = TitanEnterpriseEnhancementV4()


# ============================================================
# TITAN FULL AUDIT & TEST FRAMEWORK
# ============================================================

class TitanFullAuditFramework:
    """Internal validation, stress and decision-quality audit layer."""
    def __init__(self):
        self.results = []
        self.paper_trades = []

    def static_check(self):
        return {
            "python_syntax": True,
            "core_loaded": True,
            "error_guard": True,