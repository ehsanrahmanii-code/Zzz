            tp2 = safe_float(row["tp2"], np.nan)
            decision = str(row["decision"] or "")
            if entry <= 0 or not (math.isfinite(sl) and sl > 0) or not (math.isfinite(tp1) and tp1 > 0):
                with DB_LOCK, db_conn() as con:
                    con.execute(
                        "UPDATE paper_trades SET status='CLOSED',exit_price=?,pnl_pct=0,r_multiple=0,closed_at=?,reason=? WHERE id=?",
                        (entry, now, "INVALID_LEVELS", row["id"]),
                    )
                continue
            start_ms = int(float(row["created_at"]) * 1000)
            df = fetch_klines(row["symbol"], "15m", 1000, start_ms=start_ms)
            window = df[df["t"] >= start_ms]
            outcome, hit, exit_price = _first_touch_ohlc(window, decision, sl, tp1, tp2)
            if outcome not in {"WIN", "LOSS"}:
                created = safe_float(row["created_at"], now)
                if now >= created + 240 * 60 and not window.empty:
                    outcome, hit = "TIME_EXIT", "TIME_EXIT"
                    exit_price = safe_float(window["close"].iloc[-1], entry)
                else:
                    continue
            exit_price = safe_float(exit_price, 0.0)
            if exit_price <= 0 or not math.isfinite(exit_price):
                exit_price = safe_float(window["close"].iloc[-1], entry) if not window.empty else entry
                hit = "INVALID_EXIT_RECOVERED"
            pnl_pct = ((exit_price - entry) / entry) * 100.0 if entry else 0.0
            if decision in {"نزولی", "SHORT"}:
                pnl_pct *= -1
            pnl_pct -= TOTAL_ENTRY_BUFFER * 2.0 * 100.0
            risk_per_unit = abs(entry - sl)
            if risk_per_unit <= 0:
                r_multiple = 0.0
            elif decision in {"صعودی", "LONG"}:
                r_multiple = (exit_price - entry) / risk_per_unit
            else:
                r_multiple = (entry - exit_price) / risk_per_unit
            r_multiple -= (TOTAL_ENTRY_BUFFER * 2.0 * entry / risk_per_unit) if risk_per_unit else 0.0
            r_multiple = float(clamp(r_multiple, -5.0, 5.0))
            pnl_pct = float(clamp(pnl_pct, -25.0, 25.0))
            with DB_LOCK, db_conn() as con:
                con.execute(
                    "UPDATE paper_trades SET status='CLOSED',exit_price=?,pnl_pct=?,r_multiple=?,closed_at=?,reason=? WHERE id=?",
                    (exit_price, pnl_pct, r_multiple, now, hit, row["id"]),
                )
        except Exception as exc:
            LOGGER.warning("Paper evaluation failed #%s: %s", row["id"], exc)

def store_forecasts(market_data: list[dict[str, Any]]) -> None:
    """Store one independent directional forecast per symbol/cooldown window.

    This avoids inflating sample size by inserting essentially the same signal every
    dashboard refresh. WAIT/neutral rows are not used as pseudo-trades.
    """
    now = time.time()
    with DB_LOCK, db_conn() as con:
        for item in market_data:
            decision = str(item.get("decision_tag") or (item.get("edge") or {}).get("decision_tag") or "WAIT")
            direction = "صعودی" if decision == "LONG" else "نزولی" if decision == "SHORT" else "خنثی"
            if decision not in {"LONG", "SHORT"} or safe_float(item.get("signal_quality"), 0) < MIN_DIRECTIONAL_QUALITY:
                continue
            _g = str(item.get("grade") or (item.get("signal_grade") or {}).get("grade") or "")
            if _g in {"D", "F"}:
                continue
            recent = con.execute(
                "SELECT 1 FROM forecasts WHERE symbol=? AND timeframe='1h' AND direction=? AND created_at>=? LIMIT 1",
                (item["symbol"], direction, now - SIGNAL_COOLDOWN_SECONDS),
            ).fetchone()
            if recent:
                continue
            fusion = (item.get("titan_analysis") or {}).get("fusion") or item.get("fusion") or {}
            edge_ai = (item.get("edge") or {}).get("ai") or {}
            ai_maj = str(fusion.get("ai_majority") or edge_ai.get("majority") or "")
            ai_ag = safe_float(fusion.get("ai_agreement") or edge_ai.get("majority_agreement") or edge_ai.get("agreement"), 0)
            fused = safe_float(fusion.get("fused_score"), 0); succ = safe_float(fusion.get("success_probability"), 0)
            forecast_obj = item.get("candle_forecast") or {}
            predicted_move = safe_float(forecast_obj.get("expected_move_pct"), 0.0)
            con.execute(
                "INSERT INTO forecasts(symbol,timeframe,created_at,direction,score,alignment,price,sl,tp1,tp2,horizon_minutes,source,ai_majority,ai_agreement,fused_score,success_prob,predicted_move_pct) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (item["symbol"], "1h", now, direction, item["score"], item["alignment"],
                 safe_float(str(item.get("price", "0")).replace(",", "")),
                 safe_float(str(item.get("stop_loss", "0")).replace(",", "")),
                 safe_float(str(item.get("tp1", "0")).replace(",", "")),
                 safe_float(str(item.get("tp2", "0")).replace(",", "")),
                 240, "quant+ai-fusion-v5-audited", ai_maj, ai_ag, fused, succ, predicted_move),
            )

def evaluate_pending_forecasts() -> None:
    now = time.time()
    with DB_LOCK, db_conn() as con:
        rows = con.execute("SELECT * FROM forecasts WHERE outcome='PENDING' AND created_at <= ? LIMIT 100", (now,)).fetchall()
    learned_any = False
    for row in rows:
        horizon_end = float(row["created_at"]) + int(row["horizon_minutes"]) * 60
        if now < horizon_end:
            continue
        try:
            start_ms = int(float(row["created_at"]) * 1000)
            end_ms = int(horizon_end * 1000)
            bars_needed = max(20, min(1000, int(math.ceil(int(row["horizon_minutes"]) / 15)) + 4))
            df = fetch_klines(row["symbol"], "15m", bars_needed, start_ms=start_ms, end_ms=end_ms)
            window = df[(df["t"] >= start_ms) & (df["t"] <= end_ms)]
            if window.empty:
                continue
            direction = str(row["direction"])
            outcome, hit_type, _ = _first_touch_ohlc(
                window, direction, safe_float(row["sl"], np.nan), safe_float(row["tp1"], np.nan), safe_float(row["tp2"], np.nan)
            )
            with DB_LOCK, db_conn() as con:
                con.execute("UPDATE forecasts SET outcome=?, evaluated_at=?, hit_type=? WHERE id=?", (outcome, now, hit_type, row["id"]))
            learned_any = learned_any or outcome in {"WIN", "LOSS"}
            # Track realized path vs predicted direction for forecast self-weighting
            try:
                entry_px = safe_float(row["price"], 0)
                last_px = float(window["close"].iloc[-1]) if len(window) else 0.0
                if entry_px > 0 and last_px > 0:
                    actual_move = (last_px / entry_px - 1.0) * 100.0
                    pred_bias = str(row["direction"])
                    if pred_bias in {"LONG", "صعودی"}:
                        pred_bias = "صعودی"
                    elif pred_bias in {"SHORT", "نزولی"}:
                        pred_bias = "نزولی"
                    record_forecast_path_outcome(
                        str(row["symbol"]), pred_bias,
                        predicted_move_pct=safe_float(row["predicted_move_pct"], 0.0),
                        actual_move_pct=actual_move,
                    )
            except Exception:
                pass
        except Exception as exc:
            LOGGER.warning("Forecast evaluation failed #%s: %s", row["id"], exc)
    # Rebuild adaptive state from authoritative DB once, preventing duplicate learning.
    if learned_any:
        try:
            TITAN_ADAPTIVE.refresh_from_db()
        except Exception as learn_exc:
            LOGGER.debug("adaptive refresh skip: %s", learn_exc)

def _safe_return_series(values: list[float], return_unit: str = "pct") -> dict[str, Any]:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return {"trades": 0, "decisive_trades": 0, "neutral_trades": 0, "win_rate": 0.0, "loss_rate": 0.0,
                "profit_factor": None, "expectancy": 0.0, "max_drawdown": 0.0, "sharpe": 0.0, "sortino": 0.0,
                "avg_win": 0.0, "avg_loss": 0.0, "max_losing_streak": 0, "return_unit": return_unit}
    wins, losses = arr[arr > 0], arr[arr < 0]
    neutral = int((arr == 0).sum()); decisive = int(wins.size + losses.size)
    gross_loss = abs(float(losses.sum())); mean = float(arr.mean())
    account_returns = arr / 100.0 if return_unit == "pct" else arr * 0.01
    account_returns = np.clip(account_returns, -0.999, 10.0)
    equity = np.cumprod(1.0 + account_returns)
    peak = np.maximum.accumulate(equity)
    drawdowns = (peak - equity) / np.maximum(peak, 1e-12) * 100.0
    std = float(arr.std(ddof=1)) if arr.size > 1 else 0.0
    downside = np.minimum(arr, 0.0)
    downside_dev = float(np.sqrt(np.mean(np.square(downside)))) if arr.size else 0.0
    streak = max_streak = 0
    for x in arr:
        if x < 0: streak += 1; max_streak = max(max_streak, streak)
        elif x > 0: streak = 0
    return {
        "trades": int(arr.size), "wins": int(wins.size), "losses": int(losses.size), "decisive_trades": decisive, "neutral_trades": neutral,
        "win_rate": round(wins.size / decisive * 100, 2) if decisive else 0.0,
        "loss_rate": round(losses.size / decisive * 100, 2) if decisive else 0.0,
        "profit_factor": round(float(wins.sum() / gross_loss), 3) if gross_loss > 0 else None,
        "expectancy": round(mean, 4), "max_drawdown": round(float(drawdowns.max()), 4),
        "sharpe": round(mean / std, 3) if std else 0.0,
        "sortino": round(mean / downside_dev, 3) if downside_dev else 0.0,
        "avg_win": round(float(wins.mean()), 4) if wins.size else 0.0,
        "avg_loss": round(float(losses.mean()), 4) if losses.size else 0.0,
        "max_losing_streak": int(max_streak), "return_unit": return_unit,
    }


def get_audit_stats() -> dict[str, Any]:
    """Multi-tier historical accuracy: overall + LONG vs SHORT split + grade."""
    with DB_LOCK, db_conn() as con:
        evaluated = con.execute("SELECT COUNT(*) FROM forecasts WHERE outcome IN ('WIN','LOSS','MISS','NEUTRAL','AMBIGUOUS')").fetchone()[0]
        wins = con.execute("SELECT COUNT(*) FROM forecasts WHERE outcome='WIN'").fetchone()[0]
        losses = con.execute("SELECT COUNT(*) FROM forecasts WHERE outcome='LOSS'").fetchone()[0]
        neutral = con.execute("SELECT COUNT(*) FROM forecasts WHERE outcome IN ('MISS','NEUTRAL')").fetchone()[0]
        ambiguous = con.execute("SELECT COUNT(*) FROM forecasts WHERE outcome='AMBIGUOUS'").fetchone()[0]
        tp_hits = con.execute("SELECT COUNT(*) FROM forecasts WHERE hit_type IN ('TP1','TP2')").fetchone()[0]
        sl_hits = con.execute("SELECT COUNT(*) FROM forecasts WHERE hit_type='SL'").fetchone()[0]
        long_w = con.execute("SELECT COUNT(*) FROM forecasts WHERE outcome='WIN' AND direction IN ('صعودی','LONG')").fetchone()[0]
        long_l = con.execute("SELECT COUNT(*) FROM forecasts WHERE outcome='LOSS' AND direction IN ('صعودی','LONG')").fetchone()[0]
        short_w = con.execute("SELECT COUNT(*) FROM forecasts WHERE outcome='WIN' AND direction IN ('نزولی','SHORT')").fetchone()[0]
        short_l = con.execute("SELECT COUNT(*) FROM forecasts WHERE outcome='LOSS' AND direction IN ('نزولی','SHORT')").fetchone()[0]
    decisive = wins + losses
    wr = round(wins / decisive * 100, 1) if decisive else 0.0
    long_dec = long_w + long_l
    short_dec = short_w + short_l
    long_wr = round(long_w / long_dec * 100, 1) if long_dec else 0.0
    short_wr = round(short_w / short_dec * 100, 1) if short_dec else 0.0
    # Accuracy tier without relying on prior predictions: pure outcome grade
    if decisive < 8:
        tier, tier_label = "C", "نمونه ناکافی"
    elif wr >= 62 and tp_hits >= sl_hits:
        tier, tier_label = "A", "دقت بالا"
    elif wr >= 52:
        tier, tier_label = "B", "دقت قابل قبول"
    elif wr >= 42:
        tier, tier_label = "C", "دقت متوسط"
    else:
        tier, tier_label = "D", "نیاز به بازتنظیم"
    # Wilson lower bound communicates uncertainty better than raw win-rate alone.
    if decisive:
        z = 1.96; phat = wins / decisive
        denom = 1 + z*z/decisive
        centre = phat + z*z/(2*decisive)
        margin = z * math.sqrt((phat*(1-phat) + z*z/(4*decisive))/decisive)
        wr_lower95 = max(0.0, (centre - margin) / denom * 100.0)
    else:
        wr_lower95 = 0.0
    resolution_rate = (decisive / evaluated * 100.0) if evaluated else 0.0
    return {
        "evaluated": int(evaluated), "wins": int(wins), "losses": int(losses),
        "neutral": int(neutral), "ambiguous": int(ambiguous),
        "win_rate": wr, "tp_hits": int(tp_hits), "sl_hits": int(sl_hits),
        "long_win_rate": long_wr, "short_win_rate": short_wr,
        "long_trades": int(long_dec), "short_trades": int(short_dec),
        "win_rate_lower_95": round(wr_lower95, 1), "resolution_rate": round(resolution_rate, 1),
        "tier": tier, "tier_label": tier_label,
        "label": "Historical first-touch audit · deduplicated directional signals · uncertainty-aware",
        "probability_calibration": _probability_calibration(),
    }

# ============================================================
# BACKTEST / WALK FORWARD - FIXED HORIZON LOGIC
# ============================================================


def backtest_signal_logic(symbol: str, tf: str = "1h", limit: int = 1000) -> dict[str, Any]:
    """Technical-proxy backtest with separate Long/Short metrics.

    Important: this validates the deterministic single-timeframe technical core only;
    it does NOT pretend to reproduce live AI/derivatives/adaptive fusion historically.

    LONG: score >= 58 + EMA structure lean
    SHORT: score <= 40 + stricter filter (RSI not deeply oversold bounce zone) + stronger score edge
    Costs include round-trip fee+spread+slippage.
    """
    limit = min(max(int(limit), 100), MAX_BACKTEST_CANDLES)
    try:
        df = fetch_klines(symbol, tf, limit)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "symbol": symbol, "timeframe": tf}
    if len(df) < 80:
        return {"ok": False, "error": "داده تاریخی کافی نیست", "symbol": symbol, "timeframe": tf}
    unit = str(tf)[-1]; n = int(str(tf)[:-1] or "1"); minutes = n * {"m": 1, "h": 60, "d": 1440}.get(unit, 60)
    hold_bars = 1 if minutes >= 60 else max(1, math.ceil(60 / minutes))
    returns: list[float] = []; decisions: list[str] = []
    long_returns: list[float] = []; short_returns: list[float] = []
    cf_records = []
    friction = TOTAL_ENTRY_BUFFER * 2.0
    for i in range(60, len(df) - hold_bars):
        sample = df.iloc[:i + 1].copy()
        direction, score, meta = _tf_forecast(sample)
        entry = float(sample["close"].iloc[-1])
        future = float(df["close"].iloc[i + hold_bars])
        rsi_v = safe_float((meta or {}).get("rsi"), 50)
        ema_gap = safe_float((meta or {}).get("ema_gap"), 0)
        mom = safe_float((meta or {}).get("momentum"), 0)

        take_long = direction == "صعودی" and score >= 58 and ema_gap >= -0.15
        # Short is stricter: need deeper bear lean, avoid catching falling knives in extreme oversold without momentum
        take_short = (
            direction == "نزولی"
            and score <= 40
            and ema_gap <= 0.10
            and mom <= 0.15
            and not (rsi_v < 22 and mom > -0.5)  # skip pure panic bounce traps
        )

        if take_long:
            pnl = ((future - entry) / entry) * 100 - friction * 100
            returns.append(pnl); long_returns.append(pnl); decisions.append("LONG")
            side = "صعودی"
        elif take_short:
            pnl = ((entry - future) / entry) * 100 - friction * 100
            returns.append(pnl); short_returns.append(pnl); decisions.append("SHORT")
            side = "نزولی"
        else:
            continue

        future_prices = df["close"].iloc[i + 1:min(len(df), i + 13)].tolist()
        cf_records.append(TITAN_EDGE_SUITE.counterfactual(
            entry,
            entry * (1 - 0.01) if side == "صعودی" else entry * (1 + 0.01),
            entry * (1 + 0.015) if side == "صعودی" else entry * (1 - 0.015),
            entry * (1 + 0.025) if side == "صعودی" else entry * (1 - 0.025),
            side, future_prices,
        ))

    metrics = _safe_return_series(returns, return_unit="pct")
    long_m = _safe_return_series(long_returns, return_unit="pct")
    short_m = _safe_return_series(short_returns, return_unit="pct")
    oos = TITAN_EDGE_SUITE.out_of_sample_check(returns, return_unit="pct")
    governor = TITAN_EDGE_SUITE.drawdown_governor(returns, unit="pct")
    paths = {p: sum(1 for x in cf_records if x.get("path") == p) for p in ("TP1", "TP2", "SL", "NONE")}
    strategies = TITAN_EDGE_SUITE.strategy_lab(df)
    return {
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
