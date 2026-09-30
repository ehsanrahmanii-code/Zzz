
        reasons=[]
        if candidate == "WAIT": reasons.append("اختلاف LONG و SHORT برای تصمیم جهت‌دار کافی نیست.")
        if dq < V31_MIN_DATA: reasons.append("کیفیت/اعتبار داده برای تصمیم جهت‌دار کافی نیست.")
        if quality < V31_MIN_QUALITY: reasons.append("کیفیت سیگنال ترکیبی پایین‌تر از حد لازم است.")
        if rr and rr < V31_MIN_RR: reasons.append("نسبت ریسک به بازده مؤثر کافی نیست.")
        if contradiction >= V31_MAX_CONTRADICTION: reasons.append("بین خانواده‌های مستقل شواهد تضاد معنادار وجود دارد.")
        if hard: reasons.append("یک یا چند کنترل سخت کیفیت/ریسک فعال است.")
        if support < 2 and candidate != "WAIT": reasons.append("پشتیبانی مستقل برای جهت انتخابی محدود است.")

        # A direction becomes authoritative only when the combined evidence is
        # coherent. No individual model, indicator, or AI provider can promote it.
        directional_ok = (
            candidate in {"LONG","SHORT"}
            and abs_margin >= V31_MIN_MARGIN
            and dq >= V31_MIN_DATA
            and quality >= V31_MIN_QUALITY
            and rr >= V31_MIN_RR
            and support >= 1
            and contradiction < V31_MAX_CONTRADICTION
            and not hard
        )

        if not directional_ok:
            final = "WAIT"
            state = "WAIT"
        elif abs_margin >= V31_STRONG_MARGIN and support >= 3 and quality >= 60 and dq >= 62:
            final = candidate
            state = "STRONG"
        elif abs_margin >= V31_READY_MARGIN and support >= 2:
            final = candidate
            state = "READY"
        else:
            final = candidate
            state = "EARLY"

        # Hysteresis: an existing valid direction may survive a small temporary
        # margin loss, but it cannot survive a clear opposite consensus.
        prior = str(item.get("decision_tag") or "WAIT").upper()
        if final == "WAIT" and prior in {"LONG","SHORT"}:
            prior_side = self._side(debate, prior)
            prior_score = float(prior_side.get("score",0) or 0)
            opp_score = float((short if prior=="LONG" else long).get("score",0) or 0)
            prior_valid = (
                prior_score >= 0.16 and dq >= V31_MIN_DATA and quality >= V31_MIN_QUALITY
                and rr >= V31_MIN_RR and int(prior_side.get("support",0) or 0) >= 1
                and float(prior_side.get("contradiction",0) or 0) < V31_MAX_CONTRADICTION
                and not (prior_side.get("hard_blocks") or [])
            )
            clear_opposite = (opp_score - prior_score) >= V31_READY_MARGIN and int((short if prior=="LONG" else long).get("support",0) or 0) >= 3
            if prior_valid and not clear_opposite:
                final = prior
                state = "HOLDING"
                reasons.append("تصمیم قبلی فقط به‌عنوان hysteresis معتبر حفظ شد؛ هیچ موتور مستقلی تصمیم را تحمیل نکرد.")

        if not reasons:
            reasons.append("تصمیم از ادغام واحد همه خانواده‌های شواهد حاصل شد.")

        return {
            "version": V31_VERSION,
            "decision": final,
            "state": state,
            "candidate": candidate,
            "confidence": round(confidence,1),
            "margin": round(margin,4),
            "long_score": round(ls,4),
            "short_score": round(ss,4),
            "support": support,
            "opposition": oppose,
            "data_quality": round(dq,1),
            "signal_quality": round(quality,1),
            "rr": round(rr,2),
            "contradiction": round(contradiction,3),
            "authoritative": True,
            "reason": reasons,
            "architecture": "ONE_BRAIN_MANY_EVIDENCE_CHANNELS",
        }

TITAN_CANONICAL_V31 = TitanCanonicalDecisionV31()
_analyze_asset_v30 = analyze_asset

def analyze_asset(symbol: str, btc_trend: str) -> Optional[dict[str, Any]]:
    """Public analyzer: exactly one authoritative final decision."""
    item = _analyze_asset_v30(symbol, btc_trend)
    if not item:
        return None
    try:
        debate = item.get("deep_consensus_v30") or TITAN_DEEP_V30.evaluate(item)
        canonical = TITAN_CANONICAL_V31.decide(item, debate)

        # Preserve every upstream analysis as evidence/audit, but overwrite the
        # public decision fields from ONE canonical governor only.
        decision = canonical["decision"]
        item["decision_tag"] = decision
        item["bias"] = "صعودی" if decision == "LONG" else "نزولی" if decision == "SHORT" else "خنثی"
        item["entry_mode"] = "EARLY" if decision in {"LONG","SHORT"} else "WAIT"
        item["decision_confidence"] = canonical["confidence"]
        item["decision_state"] = canonical["state"]
        item["signal_tag"] = f"V31 CANONICAL — {decision}"
        item["canonical_decision"] = {
            **(item.get("canonical_decision") or {}),
            "decision": decision,
            "bias": item["bias"],
            "confidence": canonical["confidence"],
            "state": canonical["state"],
            "version": V31_VERSION,
            "authoritative": True,
        }
        item["decision_audit_v31"] = canonical
        item.setdefault("fusion", {})["canonical_decision_v31"] = canonical

        # Explicitly mark upstream outputs as evidence, preventing downstream UI
        # code from treating them as separate final decisions.
        item["decision_architecture"] = {
            "type": "ONE_BRAIN_MANY_EVIDENCE_CHANNELS",
            "authoritative_source": V31_VERSION,
            "upstream_are_evidence_only": True,
            "final_decision": decision,
        }
        return item
    except Exception as exc:
        LOGGER.exception("V31 canonical governor failed for %s: %s", symbol, exc)
        # Fail closed: never invent a directional signal when the single
        # authoritative governor cannot complete.
        item["decision_tag"] = "WAIT"
        item["bias"] = "خنثی"
        item["entry_mode"] = "WAIT"
        item["decision_confidence"] = 0.0
        item["decision_state"] = "ERROR_SAFE_WAIT"
        item["signal_tag"] = "V31 CANONICAL — WAIT"
        item["canonical_decision"] = {
            "decision":"WAIT","state":"ERROR_SAFE_WAIT","confidence":0.0,
            "version":V31_VERSION,"authoritative":True,
            "reason":["موتور تصمیم واحد با خطای داخلی متوقف شد؛ fail-closed به WAIT انجام شد."]
        }
        return item



# ============================================================
# TITAN V32 — CONTINUOUS PERFORMANCE / TIMEFRAME LEARNING / SCAN TELEMETRY
# ---------------------------------------------------------------------------
# V32 does NOT create a second decision brain. It supplies a measured,
# outcome-based historical calibration evidence channel to the single V31
# governor, while separately auditing every canonical forecast by symbol and
# timeframe. This makes the system learn from realized outcomes without
# pretending that a tiny sample is proof.
# ============================================================
V32_VERSION = "TITAN-V32-CONTINUOUS-LEARNING-AUDIT"
V32_TFS = ("15m", "1h", "4h", "1d")
V32_HORIZON_MIN = {"15m": 60, "1h": 240, "4h": 960, "1d": 2880}
V32_COOLDOWN_MIN = {"15m": 20, "1h": 75, "4h": 300, "1d": 1500}
V32_MIN_LEARN_SAMPLES = 12
V32_LEARN_CAP = 0.10
V32_WAIT_MOVE_THRESHOLD = 0.0035


def _tf_minutes(tf: str) -> int:
    return {"15m":15,"1h":60,"4h":240,"1d":1440}.get(str(tf),60)


def _v32_init_tables() -> None:
    try:
        with DB_LOCK, db_conn() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS v32_forecast_audit(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    decision TEXT NOT NULL,
                    confidence REAL DEFAULT 0,
                    price REAL NOT NULL,
                    horizon_minutes INTEGER NOT NULL,
                    outcome TEXT DEFAULT 'PENDING',
                    return_pct REAL,
                    max_favorable_pct REAL,
                    max_adverse_pct REAL,
                    evaluated_at REAL,
                    reason TEXT DEFAULT '',
                    UNIQUE(symbol,timeframe,created_at)
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS idx_v32_pending ON v32_forecast_audit(outcome,created_at)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_v32_perf ON v32_forecast_audit(symbol,timeframe,outcome,created_at)")
            con.execute("""
                CREATE TABLE IF NOT EXISTS v32_learning_state(
                    key TEXT PRIMARY KEY,
                    updated_at REAL NOT NULL,
                    payload TEXT NOT NULL
                )
            """)
    except Exception as exc:
        LOGGER.warning("V32 table initialization failed: %s", exc)


_v32_init_tables()


def _v32_tf_price_direction(df: pd.DataFrame, decision: str, entry: float) -> tuple[str, float, float, float]:
    if df is None or df.empty or entry <= 0:
        return "PENDING", 0.0, 0.0, 0.0
    close = pd.to_numeric(df.get("close"), errors="coerce").dropna()
    high = pd.to_numeric(df.get("high"), errors="coerce").dropna()
    low = pd.to_numeric(df.get("low"), errors="coerce").dropna()
    if close.empty:
        return "PENDING", 0.0, 0.0, 0.0
    final_px = float(close.iloc[-1])
    ret = (final_px / entry - 1.0) if entry else 0.0
    if decision == "SHORT":
        ret = -ret
        favorable = max(0.0, (entry - float(low.min())) / entry) if not low.empty else max(0.0, ret)
        adverse = max(0.0, (float(high.max()) - entry) / entry) if not high.empty else 0.0
    elif decision == "LONG":
        favorable = max(0.0, (float(high.max()) - entry) / entry) if not high.empty else max(0.0, ret)
        adverse = max(0.0, (entry - float(low.min())) / entry) if not low.empty else 0.0
    else:
        favorable = adverse = abs(ret)
    # A directional forecast is correct only if price moved beyond a friction/
    # noise band in the predicted direction. Small moves are NEUTRAL, not wins.
    if decision in {"LONG", "SHORT"}:
        if ret > V32_WAIT_MOVE_THRESHOLD:
            outcome = "WIN"
        elif ret < -V32_WAIT_MOVE_THRESHOLD:
            outcome = "LOSS"
        else:
            outcome = "NEUTRAL"
    else:
        outcome = "WAIT_CORRECT" if abs(ret) <= V32_WAIT_MOVE_THRESHOLD else "WAIT_MISSED"
    return outcome, ret * 100.0, favorable * 100.0, adverse * 100.0


def v32_record_scan_predictions(market_data: list[dict[str, Any]]) -> None:
    """Record one *timeframe-specific* prediction per symbol.

    The previous implementation wrote the same canonical decision into all four
    timeframe rows. That made the performance matrix look like 15m/1h/4h/1d
    were independently tested when they were not. Here each row is derived from
    that timeframe's own score; the canonical multi-TF decision remains separate.
    """
    now = time.time()
    if not market_data:
        return
    with DB_LOCK, db_conn() as con:
        for item in market_data:
            symbol = _normalize_symbol(item.get("symbol", ""))
            price = safe_float(str(item.get("live_price") or item.get("price") or "0").replace(",", ""), 0.0)
            tf_scores = item.get("tf_scores") or {}
            if not symbol or price <= 0:
                continue
            for tf in V32_TFS:
                score = safe_float(tf_scores.get(tf), 50.0)
                if score >= 55.0:
                    decision = "LONG"
                elif score <= 45.0:
                    decision = "SHORT"
                else:
                    decision = "WAIT"
                confidence = clamp(50.0 + abs(score - 50.0) * 2.0, 50.0, 90.0)
                cooldown = V32_COOLDOWN_MIN[tf] * 60
                recent = con.execute(
                    "SELECT 1 FROM v32_forecast_audit WHERE symbol=? AND timeframe=? AND created_at>=? LIMIT 1",
                    (symbol, tf, now - cooldown),
                ).fetchone()
                if recent:
                    continue
                con.execute(
                    """INSERT OR IGNORE INTO v32_forecast_audit(
                        symbol,timeframe,created_at,decision,confidence,price,horizon_minutes,outcome
                    ) VALUES(?,?,?,?,?,?,?,'PENDING')""",
                    (symbol, tf, now, decision, confidence, price, V32_HORIZON_MIN[tf]),
                )


def v32_evaluate_pending() -> int:
    """Resolve historical predictions from actual Binance OHLC, never from later model output."""
    now = time.time(); learned = 0
    with DB_LOCK, db_conn() as con:
        rows = con.execute("SELECT * FROM v32_forecast_audit WHERE outcome='PENDING' AND created_at <= ? ORDER BY created_at LIMIT 250", (now,)).fetchall()
    for row in rows:
        end = float(row["created_at"]) + int(row["horizon_minutes"]) * 60
        if now < end:
            continue
        try:
            tf = str(row["timeframe"]); symbol = str(row["symbol"]); decision = str(row["decision"])
            start_ms = int(float(row["created_at"]) * 1000); end_ms = int(end * 1000)
            # Small bounded pull: enough bars for the horizon, with no look-ahead
            # beyond the evaluation endpoint.
            bars = max(12, min(1000, int(math.ceil(row["horizon_minutes"] / max(1, _tf_minutes(tf)))) + 4))
            df = fetch_klines(symbol, tf, bars, start_ms=start_ms, end_ms=end_ms)
            window = df[(df["t"] >= start_ms) & (df["t"] <= end_ms)] if df is not None and not df.empty else pd.DataFrame()
            outcome, ret, fav, adv = _v32_tf_price_direction(window, decision, safe_float(row["price"], 0.0))
            if outcome == "PENDING":
                continue
            with DB_LOCK, db_conn() as con:
                con.execute("UPDATE v32_forecast_audit SET outcome=?,return_pct=?,max_favorable_pct=?,max_adverse_pct=?,evaluated_at=? WHERE id=?",
                            (outcome, ret, fav, adv, now, row["id"]))
            if outcome in {"WIN", "LOSS"}:
                learned += 1
        except Exception as exc: