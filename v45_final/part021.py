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