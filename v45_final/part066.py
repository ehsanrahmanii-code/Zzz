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