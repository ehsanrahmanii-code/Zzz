                break
        if rs:
            means.append(float(np.mean(rs)))
    return means


def _v45_trade_metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    net = [t["net_pct"] for t in trades]
    m = _safe_return_series(net, return_unit="pct")
    rs = np.asarray([t["r_net"] for t in trades], dtype=float) if trades else np.asarray([], dtype=float)
    gw = sum(1 for t in trades if t["gross_pct"] > 0)
    m["gross_win_rate"] = round(gw / len(trades) * 100, 2) if trades else 0.0
    m["expectancy_r"] = round(float(rs.mean()), 4) if rs.size else 0.0
    m["expectancy_r_se"] = round(float(rs.std(ddof=1) / math.sqrt(rs.size)), 4) if rs.size > 1 else None
    m["avg_cost_r"] = round(float(np.mean([t["cost_r"] for t in trades])), 3) if trades else 0.0
    m["avg_bars_held"] = round(float(np.mean([t["bars"] for t in trades])), 2) if trades else 0.0
    m["tp1_hits"] = sum(1 for t in trades if t["outcome"] == "TP1")
    m["sl_hits"] = sum(1 for t in trades if t["outcome"] == "SL")
    m["time_exits"] = sum(1 for t in trades if t["outcome"] == "TIME")
    return m


def _v45_verdict(metrics: dict[str, Any], rnd_pct: Optional[float], oos: dict[str, Any]) -> str:
    """EDGE_SUPPORTED needs: >=30 trades, PF>=1.1, positive OOS expectancy, expectancy lower bound (1.64 SE) > 0
    and, when a random-entry baseline exists, >=90th percentile of it. Anything weaker is never called an edge."""
    n = int(metrics.get("trades") or 0)
    if n < 30:
        return "INSUFFICIENT_SAMPLE"
    exp_r = safe_float(metrics.get("expectancy_r"), 0.0)
    se = metrics.get("expectancy_r_se")
    lcb = exp_r - 1.64 * safe_float(se, 9.0)
    pf = safe_float(metrics.get("profit_factor"), 0.0)
    oos_e = safe_float((oos or {}).get("oos_expectancy"), 0.0)
    rnd_ok = True if rnd_pct is None else rnd_pct >= 90
    if exp_r > 0 and lcb > 0 and pf >= 1.1 and oos_e > 0 and rnd_ok:
        return "EDGE_SUPPORTED"
    if exp_r > 0 and (rnd_pct is None or rnd_pct >= 75):
        return "WEAK_POSITIVE_UNPROVEN"
    return "NO_EDGE_PROVEN"


def backtest_signal_logic(symbol: str, tf: str = "1h", limit: int = 1000) -> dict[str, Any]:  # noqa: F811 (V45 override)
    """Honest proxy backtest: the SAME ATR SL/TP1 levels V45 publishes, first-touch on OHLC, entry at next open,
    one trade at a time, costs charged once, gross vs net, random-entry baseline. Still technical-only
    (no historical AI/derivatives) — that limitation is stated in the output."""
    limit = min(max(int(limit), 100), MAX_BACKTEST_CANDLES)
    try:
        df = fetch_klines(symbol, tf, limit)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "symbol": symbol, "timeframe": tf}
    if df is None or len(df) < 120:
        return {"ok": False, "error": "داده تاریخی کافی نیست", "symbol": symbol, "timeframe": tf}
    df = df.reset_index(drop=True)
    max_hold = V45_TF_MAX_HOLD.get(str(tf), 12)
    arr = _v45_arrays(df)
    table = _v45_signal_table(df)
    params = {"long_thr": 58.0, "short_thr": 40.0, "adx_min": 0.0}
    trades = _v45_run_sim(arr, table, params, 60, len(df) - 2, max_hold)
    longs = [t for t in trades if t["side"] == "LONG"]
    shorts = [t for t in trades if t["side"] == "SHORT"]
    m = _v45_trade_metrics(trades)
    long_m, short_m = _v45_trade_metrics(longs), _v45_trade_metrics(shorts)
    returns = [t["net_pct"] for t in trades]
    oos = TITAN_EDGE_SUITE.out_of_sample_check(returns, return_unit="pct")
    governor = TITAN_EDGE_SUITE.drawdown_governor(returns, unit="pct")
    strategies = TITAN_EDGE_SUITE.strategy_lab(df)
    rnd = _v45_random_baseline(arr, len(trades), (len(longs) / len(trades)) if trades else 0.5, max_hold, 60, len(df) - 2)
    actual_r = m["expectancy_r"]
    rnd_pct = round(100.0 * sum(1 for x in rnd if x < actual_r) / len(rnd), 1) if rnd else None
    verdict = _v45_verdict(m, rnd_pct, oos)
    paths = {"TP1": m["tp1_hits"], "TP2": 0, "SL": m["sl_hits"], "NONE": m["time_exits"]}
    bh = round((float(arr["c"][-1]) / float(arr["c"][0]) - 1.0) * 100.0, 2)
    return {
        "ok": True, "symbol": symbol, "timeframe": tf, "candles": len(df), "metrics": m,
        "validation_scope": "technical_proxy_only_no_historical_ai_or_derivatives",
        "long_metrics": long_m, "short_metrics": short_m,
        "long_signals": len(longs), "short_signals": len(shorts), "directional_signals": len(trades),
        "from": float(df["t"].iloc[0]), "to": float(df["t"].iloc[-1]),
        "return_series_pct": [round(float(x), 6) for x in returns[-1500:]],
        "filters": {"long": "score>=58 + ema_gap>=-0.15", "short": "score<=40 + ema_gap<=0.10 + momentum<=0.15 + not panic-oversold trap",
                    "note": "SL/TP1 = ATR levels identical to live V45; one trade at a time; entry at next open"},
        "v45": {
            "version": V45_VERSION, "verdict": verdict, "max_hold_bars": max_hold,
            "entry_model": "next_bar_open", "same_bar_sl_tp_rule": "SL_FIRST_CONSERVATIVE",
            "round_trip_cost_pct": round(V45_FRICTION_PCT, 4),
            "gross_win_rate": m["gross_win_rate"], "net_win_rate": m["win_rate"],
            "expectancy_r_net": m["expectancy_r"], "avg_cost_r": m["avg_cost_r"],
            "random_entry_percentile": rnd_pct, "random_entry_mean_r": round(float(np.mean(rnd)), 4) if rnd else None,
            "buy_and_hold_pct": bh,
            "reading": ("تا وقتی verdict برابر EDGE_SUPPORTED نشده، این منطق لبه‌ی اثبات‌شده ندارد؛ "
                        "win rate بدون در نظر گرفتن R و هزینه معنا ندارد."),
        },
        "professional": {
            "oos": oos, "drawdown_governor": governor,
            "counterfactual": {"paths": paths, "sample": len(trades)},
            "strategy_lab": strategies,
            "meta_labeling_reference": "V45 shadow outcomes + OOS + side-split",
        },
    }


def walk_forward_backtest(symbol: str, tf: str = "1h", limit: int = 1200, train: int = 300, test: int = 100) -> dict[str, Any]:  # noqa: F811
    """Train-only selection by lower-confidence-bound expectancy (R), purge = max hold, and ABSTAIN when no
    parameter set shows a positive lower bound in training (a selective system should be allowed to say 'no trade')."""
    limit = min(max(int(limit), train + test + 100), MAX_BACKTEST_CANDLES)
    try:
        df = fetch_klines(symbol, tf, limit)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    if df is None or len(df) < train + test + 100:
        return {"ok": False, "error": "داده تاریخی کافی نیست"}
    df = df.reset_index(drop=True)
    max_hold = V45_TF_MAX_HOLD.get(str(tf), 12)
    arr = _v45_arrays(df); table = _v45_signal_table(df)
    grid = [{"long_thr": float(lt), "short_thr": float(st), "adx_min": float(ax)}
            for lt in (58, 62, 66) for st in (42, 38, 34) for ax in (0, 20)]
    purge = max_hold
    windows, chosen = [], []
    all_test: list[dict[str, Any]] = []
    i = 60
    while i + train + purge + test <= len(df) - 2:
        tr_end = i + train - max_hold
        scored = []
        for p in grid:
            tr = _v45_run_sim(arr, table, p, i, tr_end, max_hold)
            if len(tr) < 10:
                continue
            rs = np.asarray([t["r_net"] for t in tr], dtype=float)
            lcb = float(rs.mean() - rs.std(ddof=1) / math.sqrt(len(rs)))
            scored.append((lcb, p, len(tr), float(rs.mean())))
        te_start = i + train + purge
        if scored:
            best = max(scored, key=lambda z: z[0])
        else:
            best = None
        abstain = best is None or best[0] <= -0.05
        if abstain:
            te = []
            chosen.append(None)
        else:
            te = _v45_run_sim(arr, table, best[1], te_start, te_start + test, max_hold)
            chosen.append(best[1])
        wm = _v45_trade_metrics(te)
        wm["abstained"] = bool(abstain)
        wm["selected_params"] = None if abstain else best[1]
        wm["train_lcb_r"] = None if best is None else round(best[0], 4)
        wm["train_trades"] = 0 if best is None else best[2]
        windows.append(wm); all_test.extend(te)
        i += test
    agg = _v45_trade_metrics(all_test)
    longs = [t for t in all_test if t["side"] == "LONG"]; shorts = [t for t in all_test if t["side"] == "SHORT"]
    used = [p for p in chosen if p]
    stability = {}
    for name in ("long_thr", "short_thr", "adx_min"):
        vals = [p[name] for p in used]
        if vals:
            stability[name] = {"min": min(vals), "max": max(vals), "mean": round(float(np.mean(vals)), 3), "unique": len(set(vals))}
    returns = [t["net_pct"] for t in all_test]
    oos_pro = TITAN_EDGE_SUITE.out_of_sample_check(returns, return_unit="pct")
    abst = sum(1 for p in chosen if p is None)
    return {
        "ok": True, "symbol": symbol, "timeframe": tf, "windows": len(windows), "aggregate": agg,
        "long_aggregate": _v45_trade_metrics(longs), "short_aggregate": _v45_trade_metrics(shorts),
        "window_metrics": windows, "purge_candles": purge,
        "validation_scope": "technical_proxy_v45_train_only_LCB_selection_purged_with_abstention",
        "parameter_stability": stability, "selected_parameters_history": chosen,
        "abstained_windows": abst, "abstained_share": round(abst / len(windows), 3) if windows else None,
        "verdict": _v45_verdict(agg, None, oos_pro),
        "professional": {"out_of_sample": oos_pro,
                         "drawdown_governor": TITAN_EDGE_SUITE.drawdown_governor(returns, unit="pct"),
                         "strategy_lab": TITAN_EDGE_SUITE.strategy_lab(df)},
    }


# ---------------------------------------------------------------- shadow learning store
def _v45_init_tables() -> None:
    try:
        with DB_LOCK, db_conn() as con:
            con.execute("""CREATE TABLE IF NOT EXISTS v45_shadow(
                id INTEGER PRIMARY KEY AUTOINCREMENT, created_at REAL NOT NULL, symbol TEXT NOT NULL, side TEXT NOT NULL,
                regime TEXT DEFAULT '', price REAL, sl REAL, tp1 REAL, tp2 REAL, atr REAL, rr1 REAL, cost_r REAL,
                edge REAL, margin REAL, trust REAL, confidence REAL, soft_penalty REAL, blocks TEXT DEFAULT '',
                final_decision TEXT DEFAULT 'WAIT', mode TEXT DEFAULT '', outcome TEXT DEFAULT 'PENDING',
                hit_type TEXT DEFAULT '', r_net REAL, evaluated_at REAL, UNIQUE(symbol, side, created_at))""")
            con.execute("CREATE INDEX IF NOT EXISTS idx_v45_pending ON v45_shadow(outcome, created_at)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_v45_scope ON v45_shadow(side, regime, outcome, created_at)")
            con.commit()
    except Exception as exc:
        LOGGER.debug("V45 schema: %s", exc)


_v45_init_tables()


def _v45_record_shadow(symbol: str, side: str, regime: str, lv: Optional[dict[str, float]], price: float, atr: float,
                       ctx: dict[str, Any], final: str, mode: str, blocks: list[str], soft: float) -> None:
    if not lv or side not in {"LONG", "SHORT"}:
        return
    now = time.time()
    try:
        with DB_LOCK, db_conn() as con:
            if con.execute("SELECT 1 FROM v45_shadow WHERE symbol=? AND side=? AND created_at>=? LIMIT 1",
                           (symbol, side, now - V45_SHADOW_COOLDOWN)).fetchone():
                return
            con.execute(
                "INSERT OR IGNORE INTO v45_shadow(created_at,symbol,side,regime,price,sl,tp1,tp2,atr,rr1,cost_r,edge,margin,trust,confidence,soft_penalty,blocks,final_decision,mode) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (now, symbol, side, regime, price, lv["sl"], lv["tp1"], lv["tp2"], atr, lv["rr1"], lv["cost_r"],
                 safe_float(ctx.get("edge"), 0), safe_float(ctx.get("margin"), 0), safe_float(ctx.get("trust"), 0),
                 safe_float(ctx.get("confidence"), 0), soft, ",".join(blocks)[:400], final, mode))
            con.commit()
    except Exception as exc:
        LOGGER.debug("V45 shadow record: %s", exc)


def _v45_evaluate_shadow(limit: int = 25) -> int:
    """Chronological first-touch evaluation of matured shadow samples (AMBIGUOUS is excluded from learning)."""
    now = time.time()
    if now - _V45_EVAL_STATE["last"] < 90:
        return 0
    _V45_EVAL_STATE["last"] = now
    done = 0
    try:
        with DB_LOCK, db_conn() as con:
            con.execute("UPDATE v45_shadow SET outcome='EXPIRED', evaluated_at=? WHERE outcome='PENDING' AND created_at<?",
                        (now, now - 3 * 86400))
            rows = con.execute("SELECT * FROM v45_shadow WHERE outcome='PENDING' AND created_at<=? ORDER BY created_at LIMIT ?",
                               (now - V45_SHADOW_HORIZON_MIN * 60, limit)).fetchall()
            con.commit()
    except Exception:
        return 0
    for row in rows:
        try:
            start_ms = int(float(row["created_at"]) * 1000)
            end_ms = int((float(row["created_at"]) + V45_SHADOW_HORIZON_MIN * 60) * 1000)
            df = fetch_klines(row["symbol"], "15m", int(V45_SHADOW_HORIZON_MIN / 15) + 6, start_ms=start_ms, end_ms=end_ms)
            window = df[(df["t"] >= start_ms) & (df["t"] <= end_ms)]
            if window.empty:
                continue
            side, price, sl, tp1 = str(row["side"]), float(row["price"]), float(row["sl"]), float(row["tp1"])
            outcome, hit, _ = _first_touch_ohlc(window, side, sl, tp1, None)
            risk_pct = abs(price - sl) / price * 100.0
            cost_r = V45_FRICTION_PCT / max(risk_pct, 1e-9)
            rr = abs(tp1 - price) / max(abs(price - sl), 1e-12)
            if outcome == "WIN":
                r = rr - cost_r
            elif outcome == "LOSS":
                r = -1.0 - cost_r
            elif outcome == "AMBIGUOUS":
                outcome, r = "AMBIGUOUS", None
            else:
                last = float(window["close"].iloc[-1])
                move = (last - price) / price * 100.0 if side == "LONG" else (price - last) / price * 100.0
                outcome, hit, r = "TIME_EXIT", "TIME", (move - V45_FRICTION_PCT) / max(risk_pct, 1e-9)
            with DB_LOCK, db_conn() as con:
                con.execute("UPDATE v45_shadow SET outcome=?, hit_type=?, r_net=?, evaluated_at=? WHERE id=?",
                            (outcome, hit, r, time.time(), row["id"]))
                con.commit()
            done += 1
        except Exception as exc:
            LOGGER.debug("V45 shadow eval #%s: %s", row["id"], exc)
    return done


def _v45_stats(side: str, regime: str = "", days: int = 30) -> dict[str, Any]:
    out = {"n": 0, "n_binary": 0, "wins": 0, "losses": 0, "win_rate": None, "exp_r": 0.0, "se": None,
           "p_post": V45_PRIOR_P, "state": "UNPROVEN", "scope": "none", "min_n": V45_MIN_VALIDATED_N}
    try:
        cutoff = time.time() - days * 86400

        def q(reg: str):
            sql = ("SELECT outcome, r_net FROM v45_shadow WHERE side=? AND outcome IN ('WIN','LOSS','TIME_EXIT') "
                   "AND r_net IS NOT NULL AND created_at>=?")
            args: list[Any] = [side, cutoff]
            if reg:
                sql += " AND regime=?"; args.append(reg)
            sql += " ORDER BY created_at DESC LIMIT 300"
            with DB_LOCK, db_conn() as con:
                return con.execute(sql, args).fetchall()

        rows = q(regime) if regime else []
        scope = f"{side}|{regime}" if regime else side
        if sum(1 for r in rows if r[0] in ("WIN", "LOSS")) < V45_MIN_VALIDATED_N:
            side_rows = q("")
            if len(side_rows) > len(rows):
                rows, scope = side_rows, side
        if not rows:
            return out
        wins = sum(1 for r in rows if r[0] == "WIN"); losses = sum(1 for r in rows if r[0] == "LOSS")
        nb = wins + losses
        rs = np.asarray([float(r[1]) for r in rows], dtype=float)
        n = int(rs.size)
        exp_r = float(rs.mean())
        se = float(rs.std(ddof=1) / math.sqrt(n)) if n > 1 else None
        p_post = (wins + V45_PRIOR_STRENGTH * V45_PRIOR_P) / (nb + V45_PRIOR_STRENGTH)
        state = "UNPROVEN"
        if nb >= V45_MIN_VALIDATED_N and se is not None:
            if exp_r - 0.5 * se > 0:
                state = "VALIDATED"
            elif exp_r + 0.5 * se < 0: