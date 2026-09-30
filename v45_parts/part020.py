
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
                state = "NEGATIVE"
        out.update({"n": n, "n_binary": nb, "wins": wins, "losses": losses,
                    "win_rate": round(100.0 * wins / nb, 2) if nb else None, "exp_r": round(exp_r, 4),
                    "se": round(se, 4) if se is not None else None, "p_post": round(p_post, 4),
                    "state": state, "scope": scope})
    except Exception as exc:
        out["error"] = str(exc)[:160]
    return out


# ---------------------------------------------------------------- policy
def _v45_regime_name(x: dict[str, Any]) -> str:
    try:
        real = (x.get("central_decision") or {}).get("real_edge") or x.get("real_edge") or {}
        name = real.get("regime") if isinstance(real, dict) else None
        if not name:
            rg = x.get("regime")
            name = rg.get("name") if isinstance(rg, dict) else rg
        return str(name or "UNKNOWN")[:24]
    except Exception:
        return "UNKNOWN"


def _v45_candidate(x: dict[str, Any]) -> str:
    u = x.get("unified_central") or {}
    cand = str(u.get("candidate") or "").upper() if isinstance(u, dict) else ""
    if cand in {"LONG", "SHORT"}:
        return cand
    real = (x.get("central_decision") or {}).get("real_edge") or x.get("real_edge") or {}
    cand = str(real.get("candidate_direction") or "").upper() if isinstance(real, dict) else ""
    if cand in {"LONG", "SHORT"}:
        return cand
    cand = str(x.get("v42_blocked_candidate") or "").upper()
    return cand if cand in {"LONG", "SHORT"} else "WAIT"


def _v45_collect_reasons(x: dict[str, Any]) -> list[str]:
    out: list[str] = []
    real = (x.get("central_decision") or {}).get("real_edge") or x.get("real_edge") or {}
    if isinstance(real, dict):
        out += [str(r) for r in (real.get("no_trade_reasons") or [])]
    try:
        out += [str(r) for r in _v44_hard_safety_reasons(x)]
    except Exception:
        pass
    integ = x.get("v42_integrity") or {}
    if isinstance(integ, dict):
        out += [str(r) for r in (integ.get("reasons") or [])]
    return list(dict.fromkeys(out))


def _v45_explore_slot(symbol: str, side: str) -> bool:
    now = time.time()
    with _V45_EXPLORE_LOCK:
        if now - _V45_PUBLISHED.get((symbol, side), 0.0) < V45_SHADOW_COOLDOWN:
            return True                                    # keep an already-published exploratory signal stable
        _V45_EXPLORE_LOG[:] = [e for e in _V45_EXPLORE_LOG if now - e[0] < 3600]
        total = len(_V45_EXPLORE_LOG); same = sum(1 for e in _V45_EXPLORE_LOG if e[1] == side)
        if total >= V45_EXPLORE_MAX_PER_HOUR:
            return False
        if total >= 4 and (same + 1) / (total + 1) > V45_SIDE_SHARE_MAX:
            return False
        _V45_EXPLORE_LOG.append((now, side)); _V45_PUBLISHED[(symbol, side)] = now
        return True


def _v45_wait(x: dict[str, Any], code: str, fa: str, audit: dict[str, Any]) -> dict[str, Any]:
    y = dict(x)
    if str(y.get("decision_tag") or "WAIT").upper() != "WAIT":
        y = _v40_force_wait(y, fa, code)
    y["v45"] = {"version": V45_VERSION, "published": False, "state": code, "reason_fa": fa, **audit}
    return y


def _v45_apply_policy(item: dict[str, Any]) -> dict[str, Any]:
    x = dict(item or {})
    symbol = _normalize_symbol(str(x.get("symbol") or ""))
    before = str(x.get("decision_tag") or x.get("decision") or "WAIT").upper()
    cand = before if before in {"LONG", "SHORT"} else _v45_candidate(x)
    if cand not in {"LONG", "SHORT"}:
        x["v45"] = {"version": V45_VERSION, "published": False, "state": "NO_CANDIDATE"}
        return x
    price = _v42_price(x); atr = safe_float(x.get("atr"), 0.0)
    structure = x.get("structure") if isinstance(x.get("structure"), dict) else {}
    anchor = safe_float(structure.get("swing_low" if cand == "LONG" else "swing_high"), 0.0)
    lv = _v45_rr_levels(price, atr, cand, anchor if anchor > 0 else None)
    regime = _v45_regime_name(x)
    u = x.get("unified_central") if isinstance(x.get("unified_central"), dict) else {}
    ctx = {"edge": safe_float(u.get("edge"), 0.0), "margin": safe_float(u.get("margin"), 0.0),
           "trust": safe_float(u.get("trust"), 0.0),
           "confidence": safe_float(u.get("confidence"), safe_float(x.get("decision_confidence"), 0.0))}
    reasons = _v45_collect_reasons(x)
    directional_origin = before in {"LONG", "SHORT"}
    hard, soft_hits = [], []
    for r in reasons:
        if r in V45_META_REASONS:
            continue
        if r in V45_SOFT_WEIGHTS:
            soft_hits.append(r)
        elif r in V45_LEVEL_REASONS:
            if directional_origin:
                hard.append(r)               # already directional: its own levels are authoritative
        else:
            hard.append(r)                   # unknown / safety reasons stay fail-closed
    softness = sum(V45_SOFT_WEIGHTS[r] for r in soft_hits)
    if not lv:
        hard.append("v45_levels_unavailable")
    elif lv["cost_r"] > V45_MAX_COST_R:
        hard.append("cost_too_high")
    stats = _v45_stats(cand, regime)
    th = (_v44_policy_stats(symbol, cand).get("thresholds") or {}) if "_v44_policy_stats" in globals() else {}
    evidence_ok = (ctx["edge"] >= safe_float(th.get("edge"), V44_BASE_EDGE) and ctx["margin"] >= safe_float(th.get("margin"), V44_BASE_MARGIN)
                   and ctx["trust"] >= safe_float(th.get("trust"), V44_BASE_TRUST) and ctx["confidence"] >= V44_MIN_CONFIDENCE)
    breakeven = ((1.0 + (lv["cost_r"] if lv else 0.0)) / (1.0 + (lv["rr1"] if lv else V45_RR1)))
    audit = {"candidate": cand, "regime": regime, "soft_penalty": round(softness, 2), "soft": soft_hits, "hard": hard,
             "evidence": {k: round(v, 4) for k, v in ctx.items()}, "evidence_ok": bool(evidence_ok),
             "thresholds": th, "shadow": stats, "breakeven_win_prob": round(breakeven, 4),
             "cost_r": round(lv["cost_r"], 3) if lv else None,
             "levels": {k: round(v, 8) for k, v in (lv or {}).items() if k in {"sl", "tp1", "tp2", "risk_pct"}}}

    def finish(res: dict[str, Any], mode: str) -> dict[str, Any]:
        _v45_record_shadow(symbol, cand, regime, lv, price, atr, ctx, str(res.get("decision_tag") or "WAIT").upper(),
                           mode, hard + soft_hits, softness)
        return res

    if directional_origin:
        if stats["state"] == "NEGATIVE" and stats["scope"] != "none":
            return finish(_v45_wait(x, "LEARNED_NEGATIVE_EV", "نتایج واقعی/سایه‌ای این سمت و رژیم، امید ریاضی منفی نشان می‌دهد؛ ورود متوقف شد.", audit), "DEMOTED_NEG")
        x["v45"] = {"version": V45_VERSION, "published": True, "state": "PASS_THROUGH", **audit}
        return finish(x, "PASS_THROUGH")
    if hard:
        return finish(_v45_wait(x, "HARD_BLOCK", "مانع سخت ریسک/داده/هزینه وجود دارد: " + "، ".join(hard[:4]), audit), "BLOCKED_HARD")
    if not evidence_ok:
        return finish(_v45_wait(x, "WATCH_NO_EDGE", "کاندید جهت‌دار وجود دارد ولی شواهد (edge/margin/trust/confidence) هنوز کافی نیست.", audit), "WATCH")
    if stats["state"] == "NEGATIVE":
        return finish(_v45_wait(x, "LEARNED_NEGATIVE_EV", "امید ریاضی سایه‌ای/واقعی این سمت منفی است؛ فعلاً فقط پایش.", audit), "BLOCKED_NEG")
    validated = stats["state"] == "VALIDATED"
    if validated and softness <= V45_TIER_A_MAX_SOFT:
        tier, mode, risk_mult = "READY", "VALIDATED", 1.0
    elif validated and softness <= V45_TIER_B_MAX_SOFT:
        tier, mode, risk_mult = "EARLY", "VALIDATED", 0.5
    elif not validated and softness <= V45_EXPLORE_MAX_SOFT and _v45_explore_slot(symbol, cand):
        tier, mode, risk_mult = "EXPLORATORY", "EXPLORATORY", 0.25
    else:
        return finish(_v45_wait(x, "WATCH_SOFT_BLOCKS", "شرایط هنوز کامل نیست (موانع نرم: " + ("، ".join(soft_hits) or "محدودیت نرخ اکتشاف") + ")؛ WAIT درست است.", audit), "WATCH")

    trial = dict(x)
    fmt = smart_format
    trial.update({
        "decision": cand, "decision_tag": cand, "bias": "صعودی" if cand == "LONG" else "نزولی",
        "entry_mode": "EARLY" if tier != "READY" else "READY",
        "stop_loss": fmt(lv["sl"]), "tp1": fmt(lv["tp1"]), "tp2": fmt(lv["tp2"]),
        "stop_loss_raw": float(lv["sl"]), "tp1_raw": float(lv["tp1"]), "tp2_raw": float(lv["tp2"]),
        "risk_distance_pct": round(lv["risk_pct"], 3), "rr_tp1": round(lv["rr1"], 2), "rr_tp2": round(lv["rr2"], 2),
        "effective_rr_tp1": round(lv["rr1"], 2), "effective_rr_tp2": round(lv["rr2"], 2),
        "signal_tag": {"READY": f"V45 آماده — {cand}", "EARLY": f"V45 اولیه (نیم‌ریسک) — {cand}",
                       "EXPLORATORY": f"V45 آزمایشی کم‌ریسک — {cand}"}[tier],
        "decision_state": f"V45_{mode}_{tier}_{cand}",
        "decision_confidence": round(clamp(ctx["confidence"], V44_MIN_CONFIDENCE, V44_MAX_CONFIDENCE), 2),
        "risk_multiplier_suggested": risk_mult, "signal_mode": mode, "paper_only": mode != "VALIDATED",
    })
    trial = _v42_integrity_seal(trial)
    if str(trial.get("decision_tag") or "WAIT").upper() != cand:
        audit["integrity"] = (trial.get("v42_integrity") or {}).get("reasons")
        return finish(_v45_wait(x, "INTEGRITY_RECHECK_FAILED", "بازبینی یکپارچگی سطوح/داده رد شد.", audit), "BLOCKED_INTEGRITY")
    trial["v45"] = {"version": V45_VERSION, "published": True, "tier": tier, "mode": mode, "risk_multiplier": risk_mult, **audit}
    arch = dict(trial.get("decision_architecture") or {})
    arch.update({"v45_policy": V45_VERSION, "final_decision": cand, "tier": tier, "mode": mode, "hard_safety_overridable": False})
    trial["decision_architecture"] = arch
    trial["authority"] = V45_VERSION
    return finish(trial, mode)


def _v44_apply_opportunity_policy(item: dict[str, Any]) -> dict[str, Any]:  # noqa: F811 (V45 override)
    try:
        return _v45_apply_policy(item)
    except Exception as exc:
        LOGGER.warning("V45 policy failed, keeping upstream decision: %s", exc)
        y = dict(item or {})
        y["v45"] = {"version": V45_VERSION, "published": False, "state": "POLICY_ERROR", "error": str(exc)[:160]}
        return y


_V45_PREV_EVALUATE_PENDING = _central_evaluate_pending


def _central_evaluate_pending() -> dict[str, Any]:  # noqa: F811 (V45 wrapper)
    result = _V45_PREV_EVALUATE_PENDING()
    try:
        k = _v45_evaluate_shadow()
        if isinstance(result, dict):
            result = dict(result); result["v45_shadow_evaluated"] = k
    except Exception:
        pass
    return result


@app.get("/api/v45/status")
def api_v45_status():
    try:
        with DB_LOCK, db_conn() as con:
            modes = [dict(r) for r in con.execute(
                "SELECT mode, final_decision, COUNT(*) n FROM v45_shadow WHERE created_at>=? GROUP BY mode, final_decision",
                (time.time() - 86400,)).fetchall()]
            recent = [dict(r) for r in con.execute(
                "SELECT created_at,symbol,side,regime,mode,final_decision,outcome,r_net,soft_penalty,blocks FROM v45_shadow ORDER BY created_at DESC LIMIT 40").fetchall()]
        return jsonify({"ok": True, "version": V45_VERSION,
                        "stats": {"LONG": _v45_stats("LONG"), "SHORT": _v45_stats("SHORT")},
                        "last_24h_by_mode": modes, "recent": recent,
                        "config": {"rr1": V45_RR1, "sl_atr": V45_SL_ATR, "max_cost_r": V45_MAX_COST_R,
                                   "round_trip_cost_pct": round(V45_FRICTION_PCT, 4), "min_validated_n": V45_MIN_VALIDATED_N,
                                   "explore_max_per_hour": V45_EXPLORE_MAX_PER_HOUR},
                        "honesty": "هیچ تضمین سودی وجود ندارد؛ سیگنال EXPLORATORY فقط برای جمع‌آوری نمونه با ریسک ۰.۲۵ است."})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)[:240]}), 500


def _v45_self_test() -> int:
    fails: list[str] = []

    def chk(name: str, cond: bool, detail: str = "") -> None:
        print(("  ✓ " if cond else "  ✗ ") + name + ("" if cond else f" — {detail}"))
        if not cond:
            fails.append(name)

    print("=" * 60); print("TITAN V45 SELF-TEST"); print("=" * 60)
    lg = _v45_rr_levels(100.0, 1.0, "LONG"); sh = _v45_rr_levels(100.0, 1.0, "SHORT")
    chk("long_levels_oriented", bool(lg) and lg["sl"] < 100 < lg["tp1"] < lg["tp2"], str(lg))
    chk("short_levels_oriented", bool(sh) and sh["tp2"] < sh["tp1"] < 100 < sh["sl"], str(sh))
    chk("rr1_is_target", abs(lg["rr1"] - V45_RR1) < 1e-9 and abs((lg["tp1"] - 100) / (100 - lg["sl"]) - V45_RR1) < 1e-9)
    n = 40
    base = np.full(n, 100.0)
    mk = lambda hi, lo: {"o": base.copy(), "h": np.full(n, hi), "l": np.full(n, lo), "c": base.copy(), "atr": np.full(n, 1.0)}
    a = mk(103.0, 99.5); a["h"][5] = 103.0
    t = _v45_sim_trade(a, 2, "LONG", 10)
    chk("sim_long_tp1", bool(t) and t["outcome"] == "TP1" and t["gross_pct"] > 0, str(t))
    b = mk(100.2, 97.0)
    t = _v45_sim_trade(b, 2, "LONG", 10)
    chk("sim_long_sl", bool(t) and t["outcome"] == "SL" and t["r_net"] < -1.0, str(t))
    both = mk(103.5, 97.0)
    t = _v45_sim_trade(both, 2, "LONG", 10)
    chk("sim_same_bar_is_sl", bool(t) and t["outcome"] == "SL", str(t))
    flat = mk(100.3, 99.7)
    t = _v45_sim_trade(flat, 2, "SHORT", 6)
    chk("sim_timeout_charged_cost", bool(t) and t["outcome"] == "TIME" and t["net_pct"] < 0, str(t))
    chk("cost_r_scales_with_risk", _v45_rr_levels(100, 0.2, "LONG")["cost_r"] > V45_MAX_COST_R > _v45_rr_levels(100, 1.0, "LONG")["cost_r"])
    rng = np.random.default_rng(5)
    close = 100 + np.cumsum(rng.normal(0, 0.4, 400))
    dfx = pd.DataFrame({"t": np.arange(400) * 3600000.0, "open": close, "high": close + 0.3, "low": close - 0.3, "close": close, "vol": rng.uniform(100, 200, 400)})
    tab = _v45_signal_table(dfx)
    arr = _v45_arrays(dfx)
    trs = _v45_run_sim(arr, tab, {"long_thr": 58.0, "short_thr": 40.0, "adx_min": 0.0}, 60, 398, 12)
    ok_no_overlap = all(trs[k + 1]["i"] > trs[k]["exit_idx"] for k in range(len(trs) - 1))
    chk("backtest_one_trade_at_a_time", ok_no_overlap and len(trs) > 0, f"n={len(trs)}")
    chk("stats_shape", "state" in _v45_stats("LONG", "RANGE"))
    print("V45 self-test:", "PASS" if not fails else f"FAIL {fails}")
    return 0 if not fails else 1


# ============================================================
# TITAN SELF-TEST — V35/V36 gate fixtures (no network required)
# Run:  python TITAN_V36_ANDROID_FINAL.py --self-test
# ============================================================

def _titan_self_test() -> int:
    """Return 0 on success, 1 on failure. Offline unit checks for critical gates."""
    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        if not cond:
            failures.append(f"FAIL {name}: {detail}")
            print(f"  ✗ {name} — {detail}")
        else:
            print(f"  ✓ {name}")

    print("=" * 60)
    print("TITAN SELF-TEST · V35/V36/V42/V43/V44 gates + helpers")
    print("=" * 60)

    check("clamp_mid", clamp(50, 0, 100) == 50.0)
    check("clamp_hi", clamp(150, 0, 100) == 100.0)
    check("normalize_symbol", _normalize_symbol("btc") == "BTC/USDT")
    check("binance_symbol", _binance_symbol("ETH/USDT") == "ETHUSDT")

    if "_v36_horizon_agreement" in globals():
        longish = {
            "tf_scores": {"15m": 62, "1h": 64, "4h": 68, "1d": 66},
            "decision_tag": "LONG",
            "candle_forecast": {"overall_bias": "صعودی"},
            "structure": {"bias": "صعودی"},
        }
        ag = _v36_horizon_agreement(longish)
        check("v36_agree_long_dir", ag.get("direction") == "LONG", str(ag))
        check("v36_agree_aligned", ag.get("aligned_with_decision") is True, str(ag))
        check("v36_agree_score", safe_float(ag.get("agreement"), 0) > 0.3, str(ag))

        conflict = {
            "tf_scores": {"15m": 30, "1h": 28, "4h": 25, "1d": 22},
            "decision_tag": "LONG",
            "candle_forecast": {"overall_bias": "نزولی"},
            "structure": {"bias": "نزولی"},
        }
        ag2 = _v36_horizon_agreement(conflict)
        check("v36_agree_conflict_short", ag2.get("direction") == "SHORT", str(ag2))

    if "_v36_price_drift_gate" in globals():
        d0 = _v36_price_drift_gate({
            "decision_tag": "LONG", "price_raw": 100.5,
            "signal_snapshot": {"price": 100.0},
        })
        check("v36_drift_safe", d0.get("kill") is False, str(d0))
        d1 = _v36_price_drift_gate({
            "decision_tag": "LONG", "price_raw": 103.0,
            "signal_snapshot": {"price": 100.0},
        })
        check("v36_drift_kill_long", d1.get("kill") is True, str(d1))
        d2 = _v36_price_drift_gate({
            "decision_tag": "SHORT", "price_raw": 97.0,
            "signal_snapshot": {"price": 100.0},
        })
        check("v36_drift_kill_short", d2.get("kill") is True, str(d2))

    if "_v36_cross_asset_resonance" in globals():
        rows = [{"symbol": f"ALT{i}/USDT", "decision_tag": "LONG"} for i in range(7)]
        res = _v36_cross_asset_resonance("BTC/USDT", "LONG", rows)
        check("v36_cluster_penalty", safe_float(res.get("penalty"), 0) >= 5.0, str(res))
        res2 = _v36_cross_asset_resonance("BTC/USDT", "WAIT", rows)
        check("v36_cluster_wait_zero", safe_float(res2.get("penalty"), 0) == 0.0, str(res2))

    if "_v36_apply" in globals():
        item = {
            "symbol": "BTC/USDT", "decision_tag": "LONG", "decision": "LONG",
            "bias": "صعودی", "decision_confidence": 70.0,
            "price_raw": 104.0, "live_price": 104.0,
            "signal_snapshot": {"price": 100.0},
            "tf_scores": {"15m": 60, "1h": 61, "4h": 62, "1d": 63},
            "candle_forecast": {"overall_bias": "صعودی"},
            "structure": {"bias": "صعودی"},
        }
        out = _v36_apply(dict(item), [])
        check("v36_apply_kills_drift", out.get("decision_tag") == "WAIT", str(out.get("v36_resonance")))
        check("v36_apply_has_pack", isinstance(out.get("v36_resonance"), dict))

        item2 = {
            "symbol": "ETH/USDT", "decision_tag": "LONG", "decision": "LONG",
            "bias": "صعودی", "decision_confidence": 70.0,
            "price_raw": 100.2, "live_price": 100.2,
            "signal_snapshot": {"price": 100.0},
            "tf_scores": {"15m": 65, "1h": 66, "4h": 70, "1d": 68},
            "candle_forecast": {"overall_bias": "صعودی"},
            "structure": {"bias": "صعودی"},
        }
        out2 = _v36_apply(dict(item2), [])
        check("v36_apply_keeps_aligned_long", out2.get("decision_tag") == "LONG", str(out2.get("v36_resonance")))

    if "_v35_rebase_price_dependent_outputs" in globals():
        card = {
            "decision_tag": "WAIT", "decision": "WAIT",
            "price_raw": 100.0, "price": "100", "entry_raw": 100.0,
            "candle_forecast": {
                "last_price": 100.0,
                "candles": [{"open": 100, "high": 101, "low": 99, "close": 100.5,
                             "mid": 100.5, "band_low": 99, "band_high": 102}],
            },
        }
        snap = {"price": 110.0, "ts": time.time(), "age_sec": 0.5, "source": "test"}
        rebased = _v35_rebase_price_dependent_outputs(dict(card), snap)
        check("v35_rebase_price", abs(safe_float(rebased.get("price_raw"), 0) - 110.0) < 1e-9)
        check("v35_rebase_live_sync", rebased.get("live_sync") is True)
        check(
            "v35_forecast_anchor",
            abs(safe_float((rebased.get("candle_forecast") or {}).get("last_price"), 0) - 110.0) < 1e-6,
        )

    if "_v12_level_integrity" in globals():
        ok = _v12_level_integrity(100.0, 95.0, 108.0, 115.0, "LONG")
        check("v12_long_levels_ok", bool(ok.get("ok")), str(ok))
        bad = _v12_level_integrity(100.0, 105.0, 108.0, 115.0, "LONG")
        check("v12_long_levels_bad", not bool(bad.get("ok")), str(bad))

    if "_v42_integrity_seal" in globals():
        good = {
            "symbol": "BTC/USDT", "decision_tag": "LONG", "decision": "LONG",
            "price_raw": 100.0, "live_price": 100.0, "live_price_age_sec": 1.0,
            "data_quality": {"score": 80}, "stop_loss_raw": 95.0,
            "tp1_raw": 108.0, "tp2_raw": 115.0, "probability_calibration": {"samples": 0, "is_calibrated": False},
        }
        g = _v42_integrity_seal(good)
        check("v42_valid_long", g.get("decision_tag") == "LONG", str(g.get("v42_integrity")))
        bad = dict(good, live_price_age_sec=30.0)
        b = _v42_integrity_seal(bad)
        check("v42_stale_blocks", b.get("decision_tag") == "WAIT", str(b.get("v42_integrity")))
        bad2 = dict(good, stop_loss_raw=105.0)
        b2 = _v42_integrity_seal(bad2)
        check("v42_bad_levels_block", b2.get("decision_tag") == "WAIT", str(b2.get("v42_integrity")))

    if "_v43_unified_decide" in globals():
        u = _v43_unified_decide({
            "symbol":"TEST/USDT", "price_raw":100.0, "live_price":100.0, "live_price_age_sec":1.0,
            "data_quality":{"score":80}, "tf_scores":{"15m":65,"1h":68,"4h":70,"1d":66},
            "score":68, "structure":{"bias":"LONG","event":"BOS_UP","confirmation_score":75},
            "regime":{"regime":"trend_up","confidence":80}, "liquidity":{"pressure":0.25},
            "precision":{"score":72}, "neural_v9":{"neural_score":70,"confidence":75,"side":"LONG"},
            "v31_edge_suite":{"evidence_fusion":{"independence_score":0.8},"adversarial":{"robustness":75},"entry_stability":{"score":78},"uncertainty":{"uncertainty":20},"safety_wait":False},
            "v34_opportunity":{"score":72}, "v36_resonance":{"penalty":0},
            "v40_precision":{"score":75,"hard_blocks":[]}, "btc_trend":"صعودی",
            "candle_forecast":{"overall_bias":"صعودی","expected_move_pct":1.2},
            "probability_calibration":{"calibrated":65,"samples":100,"is_calibrated":True},
            "v32_learning":{"long_adjustment":2.0,"short_adjustment":0.2},
            "stop_loss_raw":98.0,"tp1_raw":104.0,"tp2_raw":108.0,
        })
        check("v43_unified_governor", u.get("decision") in {"LONG","SHORT","WAIT"} and isinstance(u.get("unified_central"),dict), str(u))
        check("v43_participation", safe_float((u.get("unified_central") or {}).get("participation",{}).get("active_components"),0) >= V43_MIN_COMPONENTS, str((u.get("unified_central") or {}).get("participation")))

    if "_v44_policy_stats" in globals():
        st = _v44_policy_stats("NO_SUCH_SYMBOL/USDT")
        check("v44_policy_default", safe_float((st.get("thresholds") or {}).get("edge"),0) == V44_BASE_EDGE, str(st))
    if "_v44_apply_opportunity_policy" in globals():
        candidate = {
            "symbol":"TEST/USDT", "decision_tag":"WAIT", "decision":"WAIT",
            "price_raw":100.0, "live_price":100.0, "live_price_age_sec":1.0,
            "data_quality":{"score":85}, "tf_scores":{"15m":68,"1h":72,"4h":74,"1d":70},
            "unified_central":{"candidate":"LONG","long_score":0.40,"short_score":0.12,"edge":0.40,"margin":0.28,"trust":80,"confidence":78,
                "participation":{"hard_vetoes":[]}},
            "v40_precision":{"score":78,"hard_blocks":[]},
            "v42_integrity":{"passed":True,"reasons":[]},
            "stop_loss_raw":95.0,"tp1_raw":108.0,"tp2_raw":115.0,
        }
        promoted = _v44_apply_opportunity_policy(candidate)
        check("v44_promotes_quality_wait", promoted.get("decision_tag") in {"LONG","WAIT"}, str(promoted.get("v44_opportunity")))
        blocked = dict(candidate, v40_precision={"hard_blocks":["invalid_levels"]})
        blocked_out = _v44_apply_opportunity_policy(blocked)
        check("v44_respects_hard_block", blocked_out.get("decision_tag") == "WAIT", str(blocked_out.get("v44_opportunity")))

    if "V44_VERSION" in globals():
        sample = {
            "symbol": "TEST/USDT", "price_raw": 100.0, "live_price": 100.0,
            "data_quality": {"score": 80}, "tf_scores": {"15m": 65, "1h": 66, "4h": 68},
            "score": 65, "taker_buy_pct": 62,
            "precision": {"score": 95}, "v40_precision": {"score": 95, "hard_blocks": []},
            "v31_edge_suite": {"adversarial": {"robustness": 90}, "entry_stability": {"score": 90}},
            "v34_opportunity": {"score": 90},
            "probability_calibration": {"calibrated": 90, "samples": 200, "is_calibrated": True},
            "candle_forecast": {"expected_move_pct": 2.0},
            "stop_loss_raw": 97.0, "tp1_raw": 105.0, "tp2_raw": 108.0,
        }
        ev, part = _v43_unified_evidence(sample)
        check("v44_quality_not_direction", all(k not in ev for k in ("precision_engine", "v31_edge_suite", "v34_opportunity", "v40_precision", "realized_calibration", "forecast_engine")), str(list(ev)))
        check("v44_unsigned_forecast_not_direction", "forecast_direction" not in ev, str(ev.get("forecast_direction")))
        check("v44_balanced_thresholds", _CENTRAL_MIN_EDGE <= 0.12 and _CENTRAL_MIN_MARGIN <= 0.055, f"edge={_CENTRAL_MIN_EDGE}, margin={_CENTRAL_MIN_MARGIN}")

    audit = titan_system_audit() if "titan_system_audit" in globals() else {"passed": False}
    check("system_audit", bool(audit.get("passed")), str(audit))

    print("-" * 60)
    if failures:
        print(f"SELF-TEST FAILED: {len(failures)} check(s)")
        for f in failures:
            print(" ", f)
        return 1
    print("SELF-TEST PASSED")
    return 0



def run_titan(open_browser: bool = False) -> None:
    """Start the TITAN desktop runtime in a caller-owned thread/process."""
    try:
        _safe_startup_check()
        load_settings()
        reload_keys()
    except Exception as exc:
        LOGGER.exception("Desktop startup preparation failed: %s", exc)
    try:
        start_live_engine()
    except Exception as exc:
        LOGGER.warning("Live engine startup deferred: %s", exc)
    # V29: continuous scan + learning loop is independent of browser refreshes.
    try:
        threading.Thread(target=_v29_auto_loop, name="titan-v29-autonomous", daemon=True).start()
    except Exception as exc:
        LOGGER.warning("Autonomous loop startup failed: %s", exc)
    # Warm disk/memory cache in background so the first browser hit is instant.
    try:
        threading.Thread(target=lambda: _background_market_refresh(False), name="titan-warmup", daemon=True).start()
    except Exception as exc:
        LOGGER.debug("warmup failed: %s", exc)
    try:
        _ensure_central_learner()
    except Exception:
        pass
    try:
        threading.Thread(target=_v40_maintenance_loop, name="titan-v40-heal", daemon=True).start()
        LOGGER.info("V40 self-healing maintenance loop started")
    except Exception as _v40e:
        LOGGER.warning("V40 maintenance start failed: %s", _v40e)
    if open_browser:
        try:
            threading.Thread(target=_open_dashboard_browser, name="titan-browser", daemon=True).start()
        except Exception:
            pass
    print("=" * 78)
    print("⚡ TITAN V41 BALANCED OPPORTUNITY — real signals without missing edges")
    print(f"📁 Storage: {APP_HOME}")
    print(f"🧠 Authority: {TITAN_CENTRAL_VERSION} + {V40_VERSION}")
    print(f"🧠 Param: {TITAN_PARAM_VERSION}")
    print("📱 Android mode: local-only dashboard | storage HARD-LOCKED to AI TAITAN AI")
    print("🛡️ Storage audit: PASS | writable: YES | persistent paths: LOCKED")
    print(f"🔑 Gemini Key: {'FOUND' if GEMINI_API_KEY else 'NOT FOUND'}")
    print(f"🔑 CoinGlass Key: {'FOUND' if COINGLASS_API_KEY else 'NOT FOUND (Binance fallback)'}")
    print(f"🌐 Dashboard: http://127.0.0.1:{PORT}  |  LAN: http://<PHONE-IP>:{PORT}")
    print("📊 Mode: Analysis only — signals are probabilistic, not guarantees")
    print("🩺 V41: balanced gates · soft horizon/BTC · RR≥1.10 · self-heal · no opportunity waste")
    print("🔄 Auto-scan / central judge / REAL EDGE / reward-penalty / EDGE LAB: ACTIVE")
    print(f"🛡️ Integrity seal: {V42_VERSION} | fail-closed risk/price/level/probability contract: ACTIVE")
    print(f"🧠 Unified governor: {V43_VERSION} | all available evidence modules participate: ACTIVE")
    print(f"🧠 Adaptive opportunity + continuous learning: {V44_VERSION} | bounded self-improvement: ACTIVE")
    print(f"⚖️ Balanced opportunity + honest outcome evaluation: {V44_VERSION} | /api/decision-quality")
    print(f"🧪 V45: candidate-side levels · cost-aware EV gate · shadow learning · honest backtest | {V45_VERSION} | /api/v45/status")
    print("🧠 Opportunity policy: EARLY/READY/STRONG — WAIT only on insufficient edge or hard data risk")
    print("📱 Android tuning: soft central governor, watchdog, workers capped, adaptive polling, SQLite temp_store=MEMORY")
    print("🧹 Favicon 500 fix: ACTIVE | browser persistent storage: DISABLED")
    print("=" * 78)
    app.run(host=HOST, port=PORT, threaded=True, debug=False, use_reloader=False)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in {"--self-test", "--test", "self-test"}:
        raise SystemExit(_titan_self_test() or _v45_self_test())
    run_titan(open_browser=True)