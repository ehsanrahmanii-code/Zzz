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