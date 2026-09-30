    """Soft portfolio resonance: same-side cluster reduces edge quality."""
    if decision not in {"LONG", "SHORT"} or not cache_rows:
        return {"same_side": 0, "penalty": 0.0, "note": ""}
    majors = {"BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT"}
    sym = _normalize_symbol(symbol)
    same = 0
    for row in cache_rows:
        other = _normalize_symbol(row.get("symbol") or "")
        if other == sym:
            continue
        od = str(row.get("decision_tag") or row.get("decision") or "").upper()
        if od == decision:
            same += 1
    penalty = 0.0
    note = ""
    if same >= 6:
        penalty = 10.0
        note = f"رزونانس سبد: {same} سیگنال هم‌جهت فعال"
    elif same >= 4:
        penalty = 5.0
        note = f"فشار خوشه‌ای: {same} سیگنال هم‌جهت"
    if sym in majors and same >= 3:
        penalty = max(penalty, 4.0)
    return {"same_side": same, "penalty": penalty, "note": note}


def _v36_apply(item: dict[str, Any], cache_rows: Optional[list] = None) -> dict[str, Any]:
    """Quantum Resonance final polish — demote on drift, modest boost on pure agreement."""
    try:
        decision = str(item.get("decision_tag") or item.get("decision") or "WAIT").upper()
        agree = _v36_horizon_agreement(item)
        drift = _v36_price_drift_gate(item)
        resonance = _v36_cross_asset_resonance(
            str(item.get("symbol") or ""), decision, list(cache_rows or [])
        )
        killed = False
        boosted = False
        notes: list[str] = []

        if decision in {"LONG", "SHORT"} and drift.get("kill"):
            item["decision_tag"] = "WAIT"
            item["decision"] = "WAIT"
            item["bias"] = "خنثی"
            item["entry_mode"] = "WAIT"
            item["signal_tag"] = "V36 RESONANCE WAIT — PRICE DRIFT"
            item["central_reason_fa"] = (
                f"قیمت از اسنپ‌شات سیگنال بیش از حد فاصله گرفته ({drift.get('reason')}); "
                "سیگنال جهت‌دار باطل شد."
            )
            killed = True
            notes.append(str(drift.get("reason") or "drift_kill"))

        if not killed and decision in {"LONG", "SHORT"}:
            if (
                agree.get("direction") in {"LONG", "SHORT"}
                and agree.get("direction") != decision
                and agree.get("agreement", 0) >= 0.55
            ):
                item["decision_tag"] = "WAIT"
                item["decision"] = "WAIT"
                item["bias"] = "خنثی"
                item["entry_mode"] = "WAIT"
                item["signal_tag"] = "V36 RESONANCE WAIT — HORIZON DISCORD"
                item["central_reason_fa"] = "اجماع افق‌های زمانی با جهت سیگنال در تضاد است."
                killed = True
                notes.append("horizon_discord")
            elif agree.get("aligned_with_decision") and agree.get("agreement", 0) >= V36_RESONANCE_BOOST_MIN:
                conf = safe_float(item.get("decision_confidence"), 50.0)
                boost = min(V36_MAX_CONF_BOOST, (agree["agreement"] - V36_RESONANCE_BOOST_MIN) * 18.0)
                boost = max(0.0, boost - safe_float(resonance.get("penalty"), 0.0) * 0.35)
                if boost >= 1.0:
                    item["decision_confidence"] = round(clamp(conf + boost, 0.0, 96.0), 1)
                    boosted = True
                    notes.append(f"resonance_boost_+{boost:.1f}")
            if resonance.get("penalty", 0) >= 8 and not killed:
                conf = safe_float(item.get("decision_confidence"), 50.0)
                item["decision_confidence"] = round(max(35.0, conf - resonance["penalty"]), 1)
                notes.append(resonance.get("note") or "cluster_pressure")

        item["v36_resonance"] = {
            "version": V36_VERSION,
            "horizon_agreement": agree,
            "price_drift": drift,
            "cross_asset": resonance,
            "killed": killed,
            "boosted": boosted,
            "notes": notes,
        }
        item.setdefault("fusion", {})["v36_resonance"] = item["v36_resonance"]
        arch = item.get("decision_architecture") if isinstance(item.get("decision_architecture"), dict) else {}
        arch = dict(arch)
        arch["resonance_layer"] = V36_VERSION
        arch["final_decision"] = item.get("decision_tag", "WAIT")
        item["decision_architecture"] = arch
        return item
    except Exception as exc:
        LOGGER.debug("V36 resonance failed: %s", exc)
        item["v36_resonance"] = {"version": V36_VERSION, "error": str(exc)[:180]}
        return item



# ============================================================
# TITAN V40 — FIVE HARD FIXES IN ONE LAYER
# 1) Precision thresholds already applied globally
# 2) Paper integrity already applied
# 3) DB self-heal on startup (corrupt paper + stuck PENDING)
# 4) Unified maintenance brain (central/v32/forecast/journal/paper)
# 5) Final precision gate (history ban + confluence + integrity)
# ============================================================
V40_VERSION = "TITAN-V41-BALANCED-OPPORTUNITY"
V40_MIN_LIVE_AGE = 12.0
V40_MIN_RR1 = 1.10
V40_MIN_RR2 = 1.40
V40_MIN_CONF = 52.0
V40_MIN_AGREE = 0.38
V40_BAN_WR = 30.0
V40_BAN_N = 8
V40_SOFT_WR = 40.0
V40_GLOBAL_SHORT_WR = 35.0
V40_GLOBAL_SHORT_N = 20
V40_LOOKBACK = 250
_V40_HIST: dict[str, Any] = {"ts": 0.0, "by_key": {}, "g_short": {}, "g_long": {}}
_V40_HIST_LOCK = threading.RLock()


def _v40_db_self_heal() -> dict[str, Any]:
    """One-shot hygiene: close corrupt papers, expire impossible PENDING rows."""
    report = {"paper_invalid": 0, "paper_absurd_r": 0, "forecast_expired": 0,
              "v32_expired": 0, "journal_expired": 0, "central_forced": 0}
    now = time.time()
    try:
        with DB_LOCK, db_conn() as con:
            # Corrupt closed papers with exit=0 or |R|>20
            cur = con.execute(
                "SELECT id, entry, exit_price, r_multiple, tp1, sl FROM paper_trades WHERE status='CLOSED'"
            ).fetchall()
            for row in cur:
                rid = row[0]
                entry = safe_float(row[1], 0)
                exit_px = safe_float(row[2], 0)
                r_mult = safe_float(row[3], 0)
                tp1 = safe_float(row[4], 0)
                sl = safe_float(row[5], 0)
                bad = False
                reason = None
                if tp1 <= 0 or sl <= 0 or entry <= 0:
                    bad, reason = True, "INVALID_LEVELS_HEALED"
                elif exit_px <= 0:
                    bad, reason = True, "INVALID_EXIT_HEALED"
                elif abs(r_mult) > 8:
                    bad, reason = True, "ABSURD_R_HEALED"
                if bad:
                    con.execute(
                        "UPDATE paper_trades SET pnl_pct=0, r_multiple=0, reason=?, exit_price=? WHERE id=?",
                        (reason, entry if exit_px <= 0 else exit_px, rid),
                    )
                    report["paper_absurd_r" if "R" in (reason or "") else "paper_invalid"] += 1
            # Open papers with invalid levels
            for row in con.execute("SELECT id, entry, sl, tp1 FROM paper_trades WHERE status='OPEN'").fetchall():
                if safe_float(row[1], 0) <= 0 or safe_float(row[2], 0) <= 0 or safe_float(row[3], 0) <= 0:
                    con.execute(
                        "UPDATE paper_trades SET status='CLOSED', exit_price=?, pnl_pct=0, r_multiple=0, closed_at=?, reason=? WHERE id=?",
                        (safe_float(row[1], 0), now, "INVALID_LEVELS", row[0]),
                    )
                    report["paper_invalid"] += 1
            # Forecasts stuck PENDING past horizon+1h → MISS
            for row in con.execute(
                "SELECT id, created_at, horizon_minutes FROM forecasts WHERE outcome='PENDING'"
            ).fetchall():
                end = safe_float(row[1], 0) + int(row[2] or 240) * 60 + 3600
                if now >= end:
                    con.execute(
                        "UPDATE forecasts SET outcome='MISS', evaluated_at=?, hit_type='HEALED_EXPIRE' WHERE id=?",
                        (now, row[0]),
                    )
                    report["forecast_expired"] += 1
            # V32 audit stuck past horizon+2h
            try:
                for row in con.execute(
                    "SELECT id, created_at, horizon_minutes FROM v32_forecast_audit WHERE outcome='PENDING'"
                ).fetchall():
                    end = safe_float(row[1], 0) + int(row[2] or 240) * 60 + 7200
                    if now >= end:
                        con.execute(
                            "UPDATE v32_forecast_audit SET outcome='EXPIRED', evaluated_at=?, return_pct=0 WHERE id=?",
                            (now, row[0]),
                        )
                        report["v32_expired"] += 1
            except Exception:
                pass
            # V22 journal PENDING older than 6h → EXPIRED
            try:
                for row in con.execute(
                    "SELECT id, created_at FROM decision_journal_v22 WHERE outcome='PENDING'"
                ).fetchall():
                    if now - safe_float(row[1], 0) > 6 * 3600:
                        con.execute(
                            "UPDATE decision_journal_v22 SET outcome='EXPIRED' WHERE id=?",
                            (row[0],),
                        )
                        report["journal_expired"] += 1
            except Exception:
                pass
            con.commit()
    except Exception as exc:
        LOGGER.warning("V40 DB self-heal failed: %s", exc)
        report["error"] = str(exc)[:200]
    LOGGER.info("V40 DB self-heal: %s", report)
    return report


def _v40_unified_maintenance() -> dict[str, Any]:
    """Always-on evaluation brain so PENDING does not rot and learning continues."""
    out: dict[str, Any] = {}
    try:
        out["central"] = _central_evaluate_pending() if "_central_evaluate_pending" in globals() else {}
    except Exception as exc:
        out["central_err"] = str(exc)[:120]
    try:
        if "v32_evaluate_pending" in globals():
            out["v32"] = v32_evaluate_pending()
    except Exception as exc:
        out["v32_err"] = str(exc)[:120]
    try:
        evaluate_pending_forecasts()
        out["forecasts"] = "ok"
    except Exception as e:
        out["forecasts_err"] = str(e)[:120]
    try:
        evaluate_paper_trades()
        out["paper"] = "ok"
    except Exception as e:
        out["paper_err"] = str(e)[:120]
    try:
        _central_load_weights()
        out["weights_reloaded"] = True
    except Exception:
        pass
    try:
        with _V40_HIST_LOCK:
            _V40_HIST["ts"] = 0.0  # force hist refresh next gate
    except Exception:
        pass
    return out


def _v40_maintenance_loop() -> None:
    """Dedicated self-healing loop — independent of scan success."""
    # Initial heal once storage is ready
    try:
        _v40_db_self_heal()
    except Exception as exc:
        LOGGER.debug("initial heal: %s", exc)
    while not LIVE_STOP.is_set():
        try:
            _v40_unified_maintenance()
        except Exception as exc:
            LOGGER.debug("V40 maintenance: %s", exc)
        LIVE_STOP.wait(35)


def _v40_refresh_hist(force: bool = False) -> dict[str, Any]:
    now = time.time()
    with _V40_HIST_LOCK:
        if not force and _V40_HIST["ts"] and now - _V40_HIST["ts"] < 45:
            return _V40_HIST
    by_key: dict[str, dict[str, float]] = {}
    g_short = {"wins": 0.0, "losses": 0.0}
    g_long = {"wins": 0.0, "losses": 0.0}
    try:
        with DB_LOCK, db_conn() as con:
            rows = con.execute(
                """SELECT symbol, decision, outcome FROM central_predictions
                   WHERE outcome IN ('WIN','LOSS') AND decision IN ('LONG','SHORT')
                   ORDER BY id DESC LIMIT ?""",
                (V40_LOOKBACK,),
            ).fetchall()
        for r in rows:
            sym = _normalize_symbol(r[0] if not isinstance(r, sqlite3.Row) else r["symbol"])
            side = str((r[1] if not isinstance(r, sqlite3.Row) else r["decision"]) or "").upper()
            outc = str((r[2] if not isinstance(r, sqlite3.Row) else r["outcome"]) or "").upper()
            key = f"{sym}|{side}"
            st = by_key.setdefault(key, {"wins": 0.0, "losses": 0.0})
            if outc == "WIN":
                st["wins"] += 1
                (g_short if side == "SHORT" else g_long)["wins"] += 1
            else:
                st["losses"] += 1
                (g_short if side == "SHORT" else g_long)["losses"] += 1
        for st in by_key.values():
            n = st["wins"] + st["losses"]
            st["samples"] = n
            st["wr"] = 100.0 * st["wins"] / n if n else 50.0
        for g in (g_short, g_long):
            n = g["wins"] + g["losses"]
            g["samples"] = n
            g["wr"] = 100.0 * g["wins"] / n if n else 50.0
    except Exception as exc:
        LOGGER.debug("V40 hist: %s", exc)