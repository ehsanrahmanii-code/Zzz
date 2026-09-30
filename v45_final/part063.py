    done = 0
    try:
        with DB_LOCK, db_conn() as con:
            rows = con.execute(
                """SELECT p.id,p.created_at,p.symbol,p.decision,p.outcome,p.return_pct,p.confidence,p.margin,p.reasons_json,
                          m.regime
                   FROM central_predictions p LEFT JOIN central_trade_metrics m ON m.prediction_id=p.id
                   WHERE p.outcome IN ('WIN','LOSS','TIME_EXIT','AMBIGUOUS')
                     AND NOT EXISTS (SELECT 1 FROM central_learning_events e WHERE e.prediction_id=p.id)
                   ORDER BY p.evaluated_at LIMIT 250"""
            ).fetchall()
        for row in rows:
            rid, created, symbol, direction, outcome, ret, conf, margin, reasons_json, regime = row
            try:
                reasons = json.loads(reasons_json or "[]")
            except Exception:
                reasons = []
            if outcome == "WIN":
                error_class = "NONE"
                lesson = "تصمیم تحقق‌یافته موفق بود؛ وزن شواهد هم‌جهت حفظ و فقط در صورت تکرار تقویت شود."
            elif outcome == "LOSS":
                error_class = "FALSE_DIRECTION"
                lesson = "تصمیم اشتباه بود؛ عوامل هم‌جهت با تصمیم باید در نمونه‌های بعدی وزن کمتری بگیرند و شرایط شکست بررسی شود."
            elif outcome == "TIME_EXIT":
                error_class = "NO_RESOLUTION"
                lesson = "حرکت کافی برای تحقق هدف/حدضرر رخ نداد؛ این نمونه برای کالیبراسیون باینری ضعیف است و نباید برد محسوب شود."
            else:
                error_class = "AMBIGUOUS_PATH"
                lesson = "ترتیب لمس سطوح نامشخص بود؛ نمونه از یادگیری برد/باخت حذف می‌شود."
            with DB_LOCK, db_conn() as con:
                con.execute(
                    """INSERT OR IGNORE INTO central_learning_events(
                       prediction_id,created_at,symbol,direction,outcome,return_pct,error_class,lesson,regime,confidence,edge,margin,policy_edge,policy_margin,policy_trust,learned_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (rid,created, symbol,direction,outcome,safe_float(ret,0),error_class,lesson,regime,
                     safe_float(conf,0),0.0,safe_float(margin,0),V44_BASE_EDGE,V44_BASE_MARGIN,V44_BASE_TRUST,time.time())
                )
                con.commit()
            done += 1
        # Persist current bounded policy for global/LONG/SHORT and symbols with data.
        scopes = [("GLOBAL", ""), ("LONG", "LONG"), ("SHORT", "SHORT")]
        try:
            with DB_LOCK, db_conn() as con:
                syms = [r[0] for r in con.execute("SELECT DISTINCT symbol FROM central_predictions WHERE symbol IS NOT NULL LIMIT 200").fetchall()]
        except Exception:
            syms = []
        for scope, direction in scopes + [(f"SYMBOL:{s}", "") for s in syms]:
            sym = scope.split(":",1)[1] if scope.startswith("SYMBOL:") else ""
            st = _v44_policy_stats(sym, direction)
            th = st.get("thresholds") or {}
            with DB_LOCK, db_conn() as con:
                con.execute(
                    """INSERT INTO central_policy_state(scope,samples,wins,losses,time_exits,avg_return,win_rate,edge_threshold,margin_threshold,trust_threshold,last_update,lesson)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(scope) DO UPDATE SET samples=excluded.samples,wins=excluded.wins,losses=excluded.losses,time_exits=excluded.time_exits,
                       avg_return=excluded.avg_return,win_rate=excluded.win_rate,edge_threshold=excluded.edge_threshold,margin_threshold=excluded.margin_threshold,
                       trust_threshold=excluded.trust_threshold,last_update=excluded.last_update,lesson=excluded.lesson""",
                    (scope,st.get("samples",0),st.get("wins",0),st.get("losses",0),st.get("time_exits",0),st.get("avg_return",0),st.get("win_rate",50),
                     safe_float(th.get("edge"),V44_BASE_EDGE),safe_float(th.get("margin"),V44_BASE_MARGIN),safe_float(th.get("trust"),V44_BASE_TRUST),time.time(),
                     "bounded adaptive policy from realized outcomes"),
                )
                con.commit()
        return done
    except Exception as exc:
        LOGGER.debug("V44 learner: %s", exc)
        return done


# Wrap the existing evaluator so realized outcomes automatically feed the
# adaptive policy without changing its careful chronological first-touch logic.
_V44_PREV_EVALUATE_PENDING = _central_evaluate_pending

def _central_evaluate_pending() -> dict[str, Any]:
    result = _V44_PREV_EVALUATE_PENDING()
    try:
        learned = _v44_learn_realized_outcomes()
        if isinstance(result, dict):
            result = dict(result)
            result["v44_learning_events"] = learned
    except Exception:
        pass
    return result


# Final public gateway: V43 remains the one-brain evidence arbiter; V44 only
# recovers high-quality soft WAITs and can never bypass V42 hard integrity.
_V44_PREV_ANALYZE = analyze_asset

def analyze_asset(symbol: str, btc_trend: str) -> Optional[dict[str, Any]]:
    x = _V44_PREV_ANALYZE(symbol, btc_trend)
    if not x:
        return x
    out = _v44_apply_opportunity_policy(x)
    try:
        _central_record_prediction(out)
    except Exception:
        pass
    return out


@app.get("/api/adaptive-learning")
def api_adaptive_learning():
    try:
        global_stats = _v44_policy_stats()
        long_stats = _v44_policy_stats(direction="LONG")
        short_stats = _v44_policy_stats(direction="SHORT")
        with DB_LOCK, db_conn() as con:
            lessons = con.execute(
                "SELECT symbol,direction,outcome,error_class,lesson,confidence,created_at,learned_at FROM central_learning_events ORDER BY learned_at DESC LIMIT 100"
            ).fetchall()
        return jsonify({
            "ok": True, "version": V44_VERSION,
            "global": global_stats, "long": long_stats, "short": short_stats,
            "lessons": [dict(symbol=r[0],direction=r[1],outcome=r[2],error_class=r[3],lesson=r[4],confidence=r[5],created_at=r[6],learned_at=r[7]) for r in lessons],
            "policy": {"soft_wait_recovery": True, "hard_safety_override": False,
                       "bounded_adaptation": True, "zero_error_claim": False},
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)[:240]}), 500


# ============================================================
# TITAN V45 — COHERENT VALIDATED DECISIONS · HONEST BACKTEST · SHADOW LEARNING
# ------------------------------------------------------------
# Root causes fixed here (found by auditing V44 against the live WAL log):
#  1. WAIT candidates were judged with NEUTRAL symmetric SL/TP (RR≈1.0, and
#     inverted levels for SHORT), so `weak_rr` / `invalid_levels` fired on every
#     candidate and V44 promotion could never succeed.  V45 rebuilds levels
#     for the candidate side before judging it.
#  2. Learning deadlock: WAIT never produced samples, so policy stayed at
#     0 samples / default 50 %.  V45 records every directional candidate as a
#     SHADOW sample (no capital), evaluates it with chronological first-touch,
#     and feeds the result back into the gate.
#  3. Backtest held 1 bar with no SL/TP and ignored that costs (0.16 %) eat
#     more than half of a 1h move.  V45 simulates the SAME ATR levels the live
#     system publishes, reports gross vs net, one-trade-at-a-time, a random-entry
#     baseline and train-only walk-forward with abstention.
#  4. Duplicate arbiter/overlap log rows (same symbol, same second).
# Nothing here can guarantee profit.  V45 only publishes a directional signal
# when evidence, costs, levels and learned outcomes are mutually consistent.
# ============================================================
V45_VERSION = "TITAN-V45-COHERENT-VALIDATED-LEARNING"
V45_FRICTION_PCT = TOTAL_ENTRY_BUFFER * 2.0 * 100.0     # round-trip fee+spread+slippage, in %
V45_SL_ATR = 1.5
V45_RR1 = 1.6
V45_RR2 = 2.8
V45_MIN_RISK_ATR = 1.0
V45_MAX_RISK_ATR = 2.4
V45_MAX_COST_R = 0.35            # cost must stay below 0.35R, otherwise the trade is not worth its friction
V45_TF_MAX_HOLD = {"1m": 60, "5m": 48, "15m": 32, "30m": 24, "1h": 16, "4h": 10, "1d": 7}
V45_SHADOW_HORIZON_MIN = 240
V45_SHADOW_COOLDOWN = 2700
V45_MIN_VALIDATED_N = 20
V45_PRIOR_P = 0.45               # deliberately below a coin flip: no edge is assumed
V45_PRIOR_STRENGTH = 12.0
V45_TIER_A_MAX_SOFT = 0.5
V45_TIER_B_MAX_SOFT = 1.5
V45_EXPLORE_MAX_SOFT = 1.0
V45_EXPLORE_MAX_PER_HOUR = 6
V45_SIDE_SHARE_MAX = 0.70
V45_SOFT_WEIGHTS = {
    "regime_conflict": 1.0, "structure_not_confirmed": 1.0, "structure_confidence_low": 0.5,
    "regime_confidence_low": 0.5, "mtf_alignment_low": 0.75, "liquidity_flow_conflict": 1.0,
    "entry_quality_low": 0.75,
}
V45_LEVEL_REASONS = {"weak_rr", "invalid_levels", "rr1_below_floor", "rr2_below_floor",
                     "invalid_directional_levels", "stop_distance_extreme"}
V45_META_REASONS = {"REAL_EDGE_FINAL_GATE"}

_V45_EXPLORE_LOCK = threading.Lock()
_V45_EXPLORE_LOG: list[tuple[float, str]] = []
_V45_PUBLISHED: dict[tuple[str, str], float] = {}
_V45_EVAL_STATE = {"last": 0.0}


# ---------------------------------------------------------------- levels / simulation
def _v45_rr_levels(price: float, atr: float, side: str, anchor: Optional[float] = None,
                   rr1: float = V45_RR1, rr2: float = V45_RR2) -> Optional[dict[str, float]]:
    """Oriented ATR levels for the candidate side (pure price levels; costs are charged separately)."""
    try:
        price = float(price); atr = float(atr)
    except (TypeError, ValueError):
        return None
    if side not in {"LONG", "SHORT"} or not (price > 0 and atr > 0 and math.isfinite(price) and math.isfinite(atr)):
        return None
    risk = V45_SL_ATR * atr
    if anchor and anchor > 0:
        dist = (price - anchor) if side == "LONG" else (anchor - price)
        if dist > 0:
            risk = clamp(dist + 0.25 * atr, V45_MIN_RISK_ATR * atr, V45_MAX_RISK_ATR * atr)
    sgn = 1.0 if side == "LONG" else -1.0
    sl = price - sgn * risk
    tp1 = price + sgn * rr1 * risk
    tp2 = price + sgn * rr2 * risk
    if sl <= 0:
        return None
    risk_pct = risk / price * 100.0
    return {"sl": sl, "tp1": tp1, "tp2": tp2, "risk": risk, "risk_pct": risk_pct,
            "rr1": rr1, "rr2": rr2, "cost_r": V45_FRICTION_PCT / max(risk_pct, 1e-9)}


def _v45_sim_trade(arr: dict[str, Any], i: int, side: str, max_hold: int,
                   anchor: Optional[float] = None) -> Optional[dict[str, Any]]:
    """Signal at close of bar i -> enter at OPEN of bar i+1; SL/TP1 on high/low; same-bar tie = SL (conservative)."""
    o, h, l, c, atr = arr["o"], arr["h"], arr["l"], arr["c"], arr["atr"]
    n = len(c)
    if i + 1 >= n:
        return None
    entry = float(o[i + 1])
    lv = _v45_rr_levels(entry, float(atr[i]), side, anchor)
    if not lv:
        return None
    sl, tp1 = lv["sl"], lv["tp1"]
    last = min(n - 1, i + max_hold)
    exit_px, outcome, exit_idx = float(c[last]), "TIME", last
    for j in range(i + 1, last + 1):
        hi, lo, op = float(h[j]), float(l[j]), float(o[j])
        if side == "LONG":
            if op <= sl:
                exit_px, outcome, exit_idx = op, "SL", j; break
            sl_hit, tp_hit = lo <= sl, hi >= tp1
        else:
            if op >= sl:
                exit_px, outcome, exit_idx = op, "SL", j; break
            sl_hit, tp_hit = hi >= sl, lo <= tp1
        if sl_hit:
            exit_px, outcome, exit_idx = sl, "SL", j; break
        if tp_hit:
            exit_px, outcome, exit_idx = tp1, "TP1", j; break
    gross = ((exit_px - entry) / entry * 100.0) if side == "LONG" else ((entry - exit_px) / entry * 100.0)
    net = gross - V45_FRICTION_PCT
    return {"i": int(i), "side": side, "entry": entry, "exit": exit_px, "outcome": outcome,
            "gross_pct": gross, "net_pct": net, "r_net": net / max(lv["risk_pct"], 1e-9),
            "risk_pct": lv["risk_pct"], "cost_r": lv["cost_r"], "exit_idx": int(exit_idx),
            "bars": int(exit_idx - i)}


def _v45_arrays(df: "pd.DataFrame") -> dict[str, Any]:
    return {"o": df["open"].astype(float).to_numpy(), "h": df["high"].astype(float).to_numpy(),
            "l": df["low"].astype(float).to_numpy(), "c": df["close"].astype(float).to_numpy(),
            "atr": calc_atr(df).astype(float).to_numpy()}


def _v45_signal_table(df: "pd.DataFrame", warmup: int = 60, window: int = 200) -> list[tuple]:
    """Causal per-bar forecast table computed once and reused across the whole parameter grid."""
    rows: list[tuple] = []
    for i in range(warmup, len(df) - 2):
        sample = df.iloc[max(0, i + 1 - window): i + 1]
        direction, score, meta = _tf_forecast(sample)
        m = meta or {}
        rows.append((i, direction, float(score), safe_float(m.get("rsi"), 50.0), safe_float(m.get("ema_gap"), 0.0),
                     safe_float(m.get("momentum"), 0.0), safe_float(m.get("adx"), 20.0)))
    return rows


def _v45_pick_side(row: tuple, p: dict[str, float]) -> Optional[str]:
    _, direction, score, rsi_v, gap, mom, adx = row
    if adx < p.get("adx_min", 0):
        return None
    if direction == "صعودی" and score >= p["long_thr"] and gap >= -0.15:
        return "LONG"
    if (direction == "نزولی" and score <= p["short_thr"] and gap <= 0.10 and mom <= 0.15
            and not (rsi_v < 22 and mom > -0.5)):
        return "SHORT"
    return None


def _v45_run_sim(arr: dict[str, Any], table: list[tuple], p: dict[str, float], start: int, end: int,
                 max_hold: int) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    busy = -1
    for row in table:
        i = row[0]
        if i < start or i >= end or i <= busy:
            continue
        side = _v45_pick_side(row, p)
        if not side:
            continue
        t = _v45_sim_trade(arr, i, side, max_hold)
        if t:
            trades.append(t); busy = t["exit_idx"]
    return trades


def _v45_random_baseline(arr: dict[str, Any], n_trades: int, long_frac: float, max_hold: int,
                         start: int, end: int, iters: int = 300, seed: int = 11) -> list[float]:
    rng = np.random.default_rng(seed)
    means: list[float] = []
    if n_trades < 5 or end - start < 20:
        return means
    for _ in range(iters):
        idx = np.sort(rng.integers(start, end, size=n_trades * 3))
        busy = -1; rs: list[float] = []
        for i in idx:
            if i <= busy:
                continue
            t = _v45_sim_trade(arr, int(i), "LONG" if rng.random() < long_frac else "SHORT", max_hold)
            if t:
                rs.append(t["r_net"]); busy = t["exit_idx"]
            if len(rs) >= n_trades: