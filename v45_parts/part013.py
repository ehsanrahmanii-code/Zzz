            item["signal_quality"] = int(clamp(
                safe_float(item.get("signal_quality"), 0), 0, 92
            ))

        _v12_persist_ai_votes(symbol, item)

        return item

    except Exception as exc:
        LOGGER.exception("V12 CNS arbitration failed for %s: %s", symbol, exc)
        item["decision_integrity"] = {
            "version": "V12-CNS-PRO-MAX",
            "applied": False,
            "reason": "CNS failure; original core decision retained",
        }
        item["cognitive_nexus"] = {
            "version": CNS_VERSION,
            "action": item.get("decision_tag", "WAIT"),
            "confidence": 0,
            "reason": "CNS unavailable; core decision retained",
        }
        return item



# ============================================================
# TITAN V21 TRUST MAX
# Data Integrity + Regime Intelligence + Memory + AI Reliability
# + Probability Calibration + Walk-Forward Audit + Risk Governor
#
# This layer is deliberately additive: the existing V12 dashboard/theme/API
# remain intact. The engine gains a closed-loop audit and trust architecture.
# ============================================================

V21_VERSION = "TITAN-V21-TRUST-MAX-BALANCED"
V21_MIN_DATA_TRUST = 50.0
V21_MIN_SIGNAL_TRUST = 46.0
V21_MIN_HISTORY_SAMPLES = 6
V21_CALIBRATION_MIN_SAMPLES = 10
V21_WALK_FORWARD_MIN_SAMPLES = 16
V21_MAX_STALE_SEC = 60.0
V21_HISTORY_DECAY_DAYS = 45.0


def _v21_now_ts() -> float:
    return time.time()


def _v21_num(x: Any, default: float = 0.0) -> float:
    return safe_float(x, default)


def _v21_direction(x: Any) -> str:
    s = str(x or "").upper().strip()
    return s if s in {"LONG", "SHORT", "WAIT"} else "WAIT"


def _v21_nested(obj: Any, *keys: str, default: Any = None) -> Any:
    cur = obj
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return default if cur is None else cur


class TitanDataIntegrityV21:
    """Independent data-trust gate.

    It never fabricates missing market data. Missing evidence reduces trust and
    can veto a directional decision.
    """

    def evaluate(self, item: dict[str, Any]) -> dict[str, Any]:
        checks = {}
        price = _v21_num(item.get("price"))
        checks["price"] = price > 0

        dq = _v21_num(item.get("data_quality"), 0)
        if dq == 0:
            dq = _v21_num(item.get("data_quality_score"), 0)
        checks["reported_quality"] = dq >= MIN_DATA_QUALITY_SCORE

        # Missing age is unknown, not fresh. Treating it as age=0 silently
        # converted stale/missing live prices into trusted data.
        raw_age = item.get("price_age_sec")
        age = _v21_num(raw_age, -1.0)
        checks["price_fresh"] = 0 <= age <= V21_MAX_STALE_SEC

        tf_scores = item.get("tf_scores") or {}
        valid_tfs = []
        for tf in ("15m", "1h", "4h", "1d"):
            v = _v21_num(tf_scores.get(tf), -1)
            if 0 <= v <= 100:
                valid_tfs.append(tf)
        checks["multi_tf"] = len(valid_tfs) >= 3

        forecast = item.get("candle_forecast") or item.get("forecast") or {}
        checks["forecast"] = bool(forecast.get("ok", False)) and bool(
            forecast.get("candles") or forecast.get("overall_bias") or forecast.get("expected_move_pct") is not None
        )

        derivatives = item.get("derivatives") or {}
        checks["derivatives"] = bool(derivatives) or bool(item.get("oi_delta") is not None)

        passed = sum(bool(v) for v in checks.values())
        completeness = passed / max(len(checks), 1) * 100.0

        # Quality is not allowed to exceed the evidence actually present.
        trust = 0.55 * completeness + 0.45 * min(max(dq, 0), 100)
        trust = clamp(trust, 0, 100)

        hard_fail = []
        if not checks["price"]:
            hard_fail.append("invalid_price")
        if not checks["multi_tf"]:
            hard_fail.append("insufficient_timeframes")
        if age >= 0 and age > V21_MAX_STALE_SEC:
            hard_fail.append("stale_price")
        elif age < 0:
            # Closed-candle price is still real market data; absence of a live
            # tick lowers completeness/trust but is not an invented price.
            pass

        return {
            "version": V21_VERSION,
            "trust": round(trust, 1),
            "completeness": round(completeness, 1),
            "checks": checks,
            "valid_timeframes": valid_tfs,
            "hard_fail": hard_fail,
            "passed": not hard_fail and trust >= V21_MIN_DATA_TRUST,
        }


class TitanRegimeIntelligenceV21:
    """Market-regime classifier using existing item evidence.

    Regime is descriptive; it does not directly force a direction.
    """

    def evaluate(self, item: dict[str, Any]) -> dict[str, Any]:
        tf = item.get("tf_scores") or {}
        vals = [_v21_num(tf.get(k), 50) for k in ("15m", "1h", "4h", "1d")]
        spread = max(vals) - min(vals) if vals else 0
        avg = sum(vals) / max(len(vals), 1)

        edge = item.get("edge") or {}
        regime_obj = edge.get("regime") or {}
        name = str(regime_obj.get("regime") or regime_obj.get("name") or "").lower()

        if "trend" in name or "bull" in name or "bear" in name:
            regime = "TREND"
        elif "range" in name or "side" in name:
            regime = "RANGE"
        elif "break" in name:
            regime = "BREAKOUT"
        elif spread >= 28:
            regime = "TRANSITION"
        elif 43 <= avg <= 57:
            regime = "RANGE"
        else:
            regime = "TREND"

        coherence = 100.0 - clamp(spread * 2.0, 0, 75)
        if regime == "TRANSITION":
            coherence *= 0.75

        return {
            "version": V21_VERSION,
            "regime": regime,
            "tf_average": round(avg, 1),
            "tf_spread": round(spread, 1),
            "coherence": round(coherence, 1),
        }


class TitanHistoricalMemoryV21:
    """Outcome memory with recency weighting and regime/direction separation."""

    def _rows(self, symbol: str, direction: str, limit: int = 400):
        try:
            with DB_LOCK, db_conn() as con:
                return con.execute(
                    "SELECT created_at, outcome, timeframe FROM forecasts "
                    "WHERE symbol=? AND direction=? AND outcome IN ('WIN','LOSS') "
                    "ORDER BY created_at DESC LIMIT ?",
                    (symbol, direction, limit),
                ).fetchall()
        except Exception as exc:
            LOGGER.debug("V21 memory read failed %s: %s", symbol, exc)
            return []

    def evaluate(self, symbol: str, direction: str) -> dict[str, Any]:
        direction = _v21_direction(direction)
        if direction not in {"LONG", "SHORT"}:
            return {"samples": 0, "win_rate": 50.0, "recent_win_rate": 50.0, "confidence": 0, "status": "NEUTRAL"}

        rows = self._rows(symbol, direction)
        if not rows:
            return {"samples": 0, "win_rate": 50.0, "recent_win_rate": 50.0, "confidence": 0, "status": "NO_HISTORY"}

        now = _v21_now_ts()
        weighted_wins = weighted_total = 0.0
        wins = 0
        for row in rows:
            try:
                ts = float(row[0])
            except Exception:
                ts = now
            age_days = max(0.0, (now - ts) / 86400.0) if ts > 1_000_000_000 else 0.0
            w = math.exp(-age_days / V21_HISTORY_DECAY_DAYS)
            outcome = str(row[1] or "").upper()
            weighted_total += w
            if outcome == "WIN":
                weighted_wins += w
                wins += 1

        n = len(rows)
        # Beta(2,2) shrinkage protects against tiny samples.
        posterior = (weighted_wins + 2.0) / (weighted_total + 4.0) if weighted_total else 0.5
        recent = rows[:min(20, n)]
        recent_wins = sum(1 for r in recent if str(r[1]).upper() == "WIN")
        recent_wr = recent_wins / len(recent) if recent else 0.5

        confidence = clamp(
            25.0 + min(55.0, n * 3.0) + abs(posterior - 0.5) * 80.0,
            0, 95
        )
        return {
            "samples": n,
            "wins": wins,
            "losses": n - wins,
            "win_rate": round(posterior * 100, 1),
            "recent_win_rate": round(recent_wr * 100, 1),
            "confidence": round(confidence, 1),
            "status": "ESTABLISHED" if n >= V21_MIN_HISTORY_SAMPLES else "LIMITED",
        }


class TitanAICredibilityV21:
    """Provider-specific historical reliability.

    AI output is evidence, never an unconditional override.
    """

    def evaluate(self, symbol: str, titan_direction: str) -> dict[str, Any]:
        titan_direction = _v21_direction(titan_direction)
        if titan_direction not in {"LONG", "SHORT"}:
            return {"samples": 0, "agreement": 50.0, "providers": {}, "status": "NEUTRAL"}

        try:
            with DB_LOCK, db_conn() as con:
                rows = con.execute(
                    "SELECT provider, direction, aligned FROM ai_votes "
                    "WHERE symbol=? ORDER BY created_at DESC LIMIT 500",
                    (symbol,),
                ).fetchall()
        except Exception as exc:
            LOGGER.debug("V21 AI history failed %s: %s", symbol, exc)
            rows = []

        providers = {}
        total = aligned = 0
        for provider, direction, _stored_titan_direction, is_aligned, _created_at in rows:
            p = str(provider or "").strip().lower()
            if not p:
                continue
            bucket = providers.setdefault(p, {"samples": 0, "aligned": 0})
            bucket["samples"] += 1
            bucket["aligned"] += int(bool(is_aligned))
            total += 1
            aligned += int(bool(is_aligned))

        return {
            "samples": total,
            "agreement": round(aligned / total * 100, 1) if total else 50.0,
            "providers": providers,
            "status": "ESTABLISHED" if total >= V21_MIN_HISTORY_SAMPLES else "LIMITED",
        }


class TitanProbabilityCalibrationV21:
    """Converts historical forecast outcomes into a conservative calibration layer."""

    def evaluate(self, item: dict[str, Any], direction: str) -> dict[str, Any]:
        raw = _v21_num(item.get("success_probability"), 50.0)
        raw = clamp(raw, 1, 99)

        hist = TITAN_MEMORY_V21.evaluate(str(item.get("symbol", "")), direction)
        n = int(hist.get("samples", 0))
        if n < V21_CALIBRATION_MIN_SAMPLES:
            calibrated = 0.70 * raw + 0.30 * 50.0
            status = "INSUFFICIENT_HISTORY"
        else:
            empirical = _v21_num(hist.get("win_rate"), 50.0)
            calibrated = 0.55 * raw + 0.45 * empirical
            status = "CALIBRATED"

        # Never let a small historical sample create extreme certainty.
        cap = 78.0 if n < 30 else 88.0
        calibrated = clamp(calibrated, 22.0, cap)
        return {
            "raw": round(raw, 1),
            "calibrated": round(calibrated, 1),
            "samples": n,
            "status": status,
        }


class TitanWalkForwardAuditV21:
    """Lightweight outcome audit.

    It does not optimize parameters on the same observations it evaluates.
    It reports sample sufficiency rather than pretending a tiny backtest is proof.
    """

    def evaluate(self, symbol: str, direction: str, limit: int = 300) -> dict[str, Any]:
        direction = _v21_direction(direction)
        if direction not in {"LONG", "SHORT"}:
            return {"status": "NEUTRAL", "samples": 0}

        try:
            with DB_LOCK, db_conn() as con:
                rows = con.execute(
                    "SELECT outcome FROM forecasts WHERE symbol=? AND direction=? "
                    "AND outcome IN ('WIN','LOSS') ORDER BY created_at ASC LIMIT ?",
                    (symbol, direction, limit),
                ).fetchall()
        except Exception as exc:
            LOGGER.debug("V21 walk-forward audit failed %s", symbol)
            rows = []

        n = len(rows)
        if n < V21_WALK_FORWARD_MIN_SAMPLES:
            return {
                "status": "INSUFFICIENT",
                "samples": n,
                "oos_win_rate": None,
                "max_losing_streak": None,
            }

        outcomes = [str(r[0]).upper() for r in rows]
        split = max(10, int(n * 0.70))
        test = outcomes[split:]
        wins = sum(1 for x in test if x == "WIN")
        wr = wins / max(len(test), 1) * 100

        streak = best = 0
        for x in test:
            if x == "LOSS":
                streak += 1
                best = max(best, streak)
            else:
                streak = 0

        return {
            "status": "AUDITED",
            "samples": n,
            "train_samples": split,
            "oos_samples": len(test),
            "oos_win_rate": round(wr, 1),
            "max_losing_streak": best,
        }


class TitanRiskGovernorV21:
    """Final independent governor.

    It can downgrade a proposed signal but never upgrades it by itself.
    """

    def evaluate(self, item: dict[str, Any], cns: dict[str, Any],
                 data: dict[str, Any], regime: dict[str, Any],
                 calibration: dict[str, Any], wf: dict[str, Any]) -> dict[str, Any]:
        proposed = _v21_direction(cns.get("action"))
        reasons = []
        score = 100.0

        if data.get("trust", 0) < V21_MIN_DATA_TRUST:
            reasons.append("DATA_TRUST_LOW")
            score -= 35

        if data.get("hard_fail"):
            reasons.extend(data["hard_fail"])
            score -= 30

        if regime.get("regime") == "TRANSITION":
            score -= 10
            reasons.append("REGIME_TRANSITION")

        if proposed in {"LONG", "SHORT"}:
            rr = _v21_num(item.get("effective_rr_tp1"), 0)
            if rr < MIN_EFFECTIVE_RR:
                score -= 30
                reasons.append("RR_LOW")

            cal = _v21_num(calibration.get("calibrated"), 50)
            if cal < 52:
                score -= 20
                reasons.append("CALIBRATION_WEAK")

            if wf.get("status") == "AUDITED" and _v21_num(wf.get("oos_win_rate"), 50) < 45:
                score -= 15
                reasons.append("OOS_WEAK")

        score = clamp(score, 0, 100)
        action = proposed
        if proposed in {"LONG", "SHORT"} and score < V21_MIN_SIGNAL_TRUST:
            action = "WAIT"

        return {
            "version": V21_VERSION,
            "action": action,
            "trust": round(score, 1),
            "reasons": reasons,
            "governed": action != proposed,
        }


class TitanTrustMaxV21:
    """Closed-loop final evidence graph."""

    def evaluate(self, item: dict[str, Any]) -> dict[str, Any]:
        symbol = str(item.get("symbol") or "")
        cns = item.get("cognitive_nexus") or {}
        proposed = _v21_direction(cns.get("action") or item.get("decision_tag"))

        data = TITAN_DATA_V21.evaluate(item)
        regime = TITAN_REGIME_V21.evaluate(item)
        direction = proposed if proposed in {"LONG", "SHORT"} else _v21_direction(item.get("decision_tag"))

        history = (
            TITAN_MEMORY_V21.evaluate(symbol, direction)
            if direction in {"LONG", "SHORT"}
            else {"samples": 0, "win_rate": 50.0, "confidence": 0, "status": "NEUTRAL"}
        )
        ai = TITAN_AI_CRED_V21.evaluate(symbol, direction)
        calibration = TITAN_CALIBRATION_V21.evaluate(item, direction)
        wf = TITAN_WF_V21.evaluate(symbol, direction)
        governor = TITAN_GOVERNOR_V21.evaluate(item, cns, data, regime, calibration, wf)

        # Trust is an evidence quality metric, not a guaranteed probability.
        trust = (
            0.28 * data["trust"]
            + 0.18 * regime["coherence"]
            + 0.18 * _v21_num(cns.get("confidence"), 0)
            + 0.16 * calibration["calibrated"]
            + 0.10 * _v21_num(history.get("confidence"), 0)
            + 0.10 * ai["agreement"]
        )
        trust = clamp(trust, 0, 100)

        final_action = governor["action"]
        if final_action in {"LONG", "SHORT"} and trust < V21_MIN_SIGNAL_TRUST:
            final_action = "WAIT"

        reasons = []
        if not data["passed"]:
            reasons.append("اعتماد داده کافی نیست")
        if governor["governed"]:
            reasons.extend(governor["reasons"])
        if regime["regime"] == "TRANSITION":
            reasons.append("رژیم بازار در حال انتقال است")

        return {
            "version": V21_VERSION,
            "action": final_action,
            "trust": round(trust, 1),
            "proposed_action": proposed,
            "data_integrity": data,
            "regime": regime,
            "historical_memory": history,
            "ai_credibility": ai,
            "calibration": calibration,
            "walk_forward": wf,
            "risk_governor": governor,
            "reasons": list(dict.fromkeys(reasons)),
            "audit_note": "Trust is evidence quality, not a profit guarantee.",
        }


TITAN_DATA_V21 = TitanDataIntegrityV21()
TITAN_REGIME_V21 = TitanRegimeIntelligenceV21()
TITAN_MEMORY_V21 = TitanHistoricalMemoryV21()
TITAN_AI_CRED_V21 = TitanAICredibilityV21()
TITAN_CALIBRATION_V21 = TitanProbabilityCalibrationV21()
TITAN_WF_V21 = TitanWalkForwardAuditV21()
TITAN_GOVERNOR_V21 = TitanRiskGovernorV21()
TITAN_TRUST_V21 = TitanTrustMaxV21()


# Preserve the V12 public analyzer and put Trust Max above it.
_analyze_asset_v12 = analyze_asset


def analyze_asset(symbol: str, btc_trend: str) -> Optional[dict[str, Any]]:
    item = _analyze_asset_v12(symbol, btc_trend)
    if not item:
        return None

    try:
        trust = TITAN_TRUST_V21.evaluate(item)
        item["trust_max_v21"] = trust
        item.setdefault("fusion", {})["trust_max_v21"] = trust

        # V21 is a governor. V28.4: only hard data failure kills direction;
        # otherwise keep LONG/SHORT and attach risk reasons.
        action = trust["action"]
        hard_data = bool((trust.get("data_integrity") or {}).get("hard_fail"))
        if action == "WAIT" and str(item.get("decision_tag")) in {"LONG", "SHORT"}:
            if hard_data or safe_float(trust.get("trust"), 100) < 35:
                item["decision_tag"] = "WAIT"
                item["bias"] = "خنثی"
                item["signal_tag"] = "V21 RISK GOVERNOR"
                item["entry_mode"] = "WAIT"
                item["fusion"]["v21_override"] = True
                item["fusion"]["v21_reason"] = trust["reasons"]
            else:
                item["fusion"]["v21_soft"] = True
                item["fusion"]["v21_reason"] = trust["reasons"]
                item["signal_tag"] = str(item.get("signal_tag") or "CONFIRMED SETUP")
                if item.get("signal_quality") is not None:
                    item["signal_quality"] = int(min(safe_float(item.get("signal_quality"), 50), 74))

        item["canonical_decision"] = {
            **(item.get("canonical_decision") or {}),
            "decision": item.get("decision_tag", "WAIT"),
            "bias": item.get("bias", "خنثی"),
            "trust_max": trust["trust"],
            "trust_version": V21_VERSION,
            "risk_governor": trust["risk_governor"],
            "data_integrity": trust["data_integrity"],
            "regime": trust["regime"],
            "calibration": trust["calibration"],
        }

        # Expose a compact audit object for the dashboard without changing the UI.
        item["decision_audit"] = {
            "final": item.get("decision_tag", "WAIT"),
            "trust": trust["trust"],
            "data_trust": trust["data_integrity"]["trust"],
            "regime": trust["regime"]["regime"],
            "calibrated_probability": trust["calibration"]["calibrated"],
            "history_samples": trust["historical_memory"].get("samples", 0),
            "oos_status": trust["walk_forward"].get("status"),
            "reasons": trust["reasons"],
        }

        return item
    except Exception as exc:
        LOGGER.exception("V21 Trust Max failed for %s: %s", symbol, exc)
        return item


# ============================================================
# TITAN V22 — ADAPTIVE OPPORTUNITY & SELF-LEARNING ENGINE
#
# Goal:
#   1) Avoid arbitrary WAIT.
#   2) Avoid arbitrary LONG/SHORT.
#   3) Preserve a real directional signal when evidence is sufficient.
#   4) Surface strong pre-trigger opportunities as EARLY/WATCH instead of
#      hiding them behind WAIT.
#   5) Learn from realized outcomes and recalibrate thresholds/AI influence.
#   6) Produce a complete reason tree for every final decision.
#
# This layer is analysis-only. It never executes orders and never invents
# market data, levels, or outcomes.
# ============================================================

V22_VERSION = "TITAN-V22-ADAPTIVE-OPPORTUNITY-BALANCED"
V22_JOURNAL_COOLDOWN = 90.0
V22_CANDIDATE_MEMORY_MINUTES = 24.0
V22_PROMOTE_SCORE = 56.0
V22_STRONG_TRIGGER_SCORE = 64.0
V22_EARLY_SCORE = 48.0
V22_WATCH_SCORE = 40.0
V22_MIN_DATA = 48.0
V22_MIN_QUALITY = 44.0
V22_MIN_NEURAL = 40.0
V22_MIN_RR = 1.02
V22_MIN_AI_AGREEMENT = 48.0
V22_MAX_AI_CONFLICT = 92.0
V22_MAX_HARD_VETOES = 1


def _v22_init_tables() -> None:
    try:
        with DB_LOCK, db_conn() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS decision_journal_v22(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at REAL NOT NULL,
                    symbol TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    candidate_side TEXT DEFAULT 'WAIT',
                    opportunity_state TEXT DEFAULT 'NO_EDGE',
                    opportunity_score REAL DEFAULT 0,
                    trust REAL DEFAULT 0,
                    quality REAL DEFAULT 0,
                    ai_majority TEXT DEFAULT 'WAIT',
                    ai_agreement REAL DEFAULT 0,
                    regime TEXT DEFAULT '',
                    reason_json TEXT DEFAULT '{}',
                    outcome TEXT DEFAULT 'PENDING'
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS idx_v22_journal_symbol ON decision_journal_v22(symbol, created_at)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_v22_journal_outcome ON decision_journal_v22(outcome, created_at)")
            con.execute("""
                CREATE TABLE IF NOT EXISTS v22_learning_state(
                    state_key TEXT PRIMARY KEY,
                    updated_at REAL NOT NULL,
                    payload TEXT NOT NULL
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS v22_candidate_state(
                    symbol TEXT PRIMARY KEY,
                    side TEXT DEFAULT 'WAIT',
                    first_seen REAL DEFAULT 0,
                    last_seen REAL DEFAULT 0,
                    streak INTEGER DEFAULT 0,
                    best_score REAL DEFAULT 0,
                    last_reason TEXT DEFAULT ''
                )
            """)
    except Exception as exc:
        LOGGER.warning("V22 table initialization failed: %s", exc)


_v22_init_tables()


class TitanLearningEngineV22:
    """Outcome-driven calibration.

    It deliberately uses shrinkage and minimum samples. A tiny winning streak
    cannot make the engine aggressively lower its thresholds.
    """

    def _rows(self, symbol: str = "", direction: str = ""):
        sql = (
            "SELECT id,symbol,direction,outcome,score,alignment,ai_majority,"
            "ai_agreement,fused_score,success_prob,created_at "
            "FROM forecasts WHERE outcome IN ('WIN','LOSS')"
        )
        params = []
        if symbol:
            sql += " AND symbol=?"
            params.append(symbol)
        if direction:
            sql += " AND direction=?"
            params.append(direction)
        sql += " ORDER BY created_at DESC LIMIT 1200"
        try:
            with DB_LOCK, db_conn() as con:
                return con.execute(sql, params).fetchall()
        except Exception as exc:
            LOGGER.debug("V22 learning rows failed: %s", exc)
            return []

    @staticmethod
    def _beta(wins: float, losses: float) -> float:
        return (wins + 2.0) / (wins + losses + 4.0) * 100.0

    def side_profile(self, symbol: str, side: str) -> dict[str, Any]:
        db_side = "صعودی" if side == "LONG" else "نزولی"
        rows = self._rows(symbol, db_side)
        n = len(rows)
        wins = sum(1 for r in rows if str(r["outcome"]) == "WIN")
        losses = n - wins
        recent = rows[:20]
        rw = sum(1 for r in recent if str(r["outcome"]) == "WIN")
        wr = self._beta(wins, losses)
        recent_wr = self._beta(rw, max(0, len(recent) - rw))

        # Calibration: are high model probabilities actually associated with wins?
        high_p = [r for r in rows if safe_float(r["success_prob"], 0) >= 60]
        high_p_wr = (
            self._beta(
                sum(1 for r in high_p if str(r["outcome"]) == "WIN"),
                sum(1 for r in high_p if str(r["outcome"]) == "LOSS"),
            )
            if high_p else 50.0
        )

        # AI ensemble accuracy for this side.
        ai_rows = [
            r for r in rows
            if str(r["ai_majority"] or "").upper() in {side, "LONG" if side == "LONG" else "SHORT"}
        ]
        ai_w = sum(1 for r in ai_rows if str(r["outcome"]) == "WIN")
        ai_l = sum(1 for r in ai_rows if str(r["outcome"]) == "LOSS")
        ai_wr = self._beta(ai_w, ai_l) if ai_rows else 50.0

        # Stable adaptive threshold shift. Positive means be stricter.
        shift = 0.0
        if n >= 10:
            if recent_wr < 45:
                shift += min(4.0, (45.0 - recent_wr) * 0.18)
            elif recent_wr > 61:
                shift -= min(3.0, (recent_wr - 61.0) * 0.12)
            if high_p_wr < 45:
                shift += 1.5
            elif high_p_wr > 62:
                shift -= 1.0
        return {
            "samples": n,
            "wins": wins,
            "losses": losses,
            "win_rate": round(wr, 1),
            "recent_win_rate": round(recent_wr, 1),
            "high_probability_wr": round(high_p_wr, 1),
            "ai_aligned_wr": round(ai_wr, 1),
            "ai_samples": len(ai_rows),
            "threshold_shift": round(shift, 2),
            "confidence": round(min(1.0, n / 40.0), 3),
        }

    def global_profile(self) -> dict[str, Any]:
        rows = self._rows()
        n = len(rows)
        wins = sum(1 for r in rows if str(r["outcome"]) == "WIN")
        losses = n - wins
        ai_rows = [r for r in rows if str(r["ai_majority"] or "").upper() in {"LONG", "SHORT"}]
        ai_w = sum(1 for r in ai_rows if str(r["outcome"]) == "WIN")
        ai_l = sum(1 for r in ai_rows if str(r["outcome"]) == "LOSS")
        return {
            "samples": n,
            "win_rate": round(self._beta(wins, losses), 1),
            "ai_win_rate": round(self._beta(ai_w, ai_l), 1) if ai_rows else 50.0,
            "ai_samples": len(ai_rows),
        }


class TitanOpportunityEngineV22:
    """Balances action vs patience using a two-threshold + persistence model."""

    def _ai(self, item: dict[str, Any]) -> tuple[str, float]:
        edge_ai = (item.get("edge") or {}).get("ai") or {}
        fusion = item.get("fusion") or {}
        majority = str(
            edge_ai.get("majority")
            or edge_ai.get("ai_majority")
            or fusion.get("ai_majority")
            or "WAIT"
        ).upper()
        agreement = safe_float(
            edge_ai.get("majority_agreement")
            or edge_ai.get("agreement")
            or fusion.get("ai_agreement"),
            0,
        )
        return majority if majority in {"LONG", "SHORT", "WAIT"} else "WAIT", clamp(agreement, 0, 100)

    def _candidate_edges(self, item: dict[str, Any]) -> dict[str, float]:
        tf = item.get("tf_scores") or {}
        tf_long = tf_short = 0.0
        weights = {"15m": 0.18, "1h": 0.30, "4h": 0.28, "1d": 0.24}
        used = 0.0
        for k, w in weights.items():
            if k not in tf:
                continue
            e = (safe_float(tf.get(k), 50) - 50) / 50
            if e > 0:
                tf_long += e * w
            elif e < 0:
                tf_short += -e * w
            used += w
        if used:
            tf_long /= used
            tf_short /= used

        structure = (item.get("edge") or {}).get("structure") or {}
        confluence = (item.get("edge") or {}).get("confluence") or {}
        precision = item.get("precision") or {}
        neural = item.get("neural_v9") or {}
        fc = item.get("candle_forecast") or {}
        patterns = item.get("patterns") or {}
        primary = patterns.get("primary") or {}
        guide = primary.get("guide") or {}

        struct_side = str(structure.get("bias") or "")
        struct_sc = safe_float(structure.get("confirmation_score"), 50)
        conf_sc = safe_float(confluence.get("score"), 50)
        prec_sc = safe_float(precision.get("score"), 50)
        nside = str(neural.get("side") or "WAIT")
        nconf = safe_float(neural.get("confidence"), 0) / 100
        fb = str(fc.get("overall_bias") or "")
        fs = clamp(safe_float(fc.get("path_strength"), 0) / 40, 0, 1)
        pb = str(guide.get("bias") or "")
        pc = clamp(safe_float(primary.get("confidence"), 0) / 100, 0, 1)

        def side_score(side: str) -> float:
            s = 0.0
            # TF spine
            s += (tf_long if side == "LONG" else tf_short) * 100 * .25
            # Structure
            if (side == "LONG" and struct_side == "صعودی") or (side == "SHORT" and struct_side == "نزولی"):
                s += max(0, struct_sc - 50) * .18
            # Confluence follows current bias but is still a useful independent vote.
            current_bias = str(item.get("bias") or "")
            if (side == "LONG" and current_bias == "صعودی") or (side == "SHORT" and current_bias == "نزولی"):
                s += max(0, conf_sc - 50) * .14
            # Precision
            s += max(0, prec_sc - 50) * .10
            # Neural
            if nside == side:
                s += nconf * 12
            # Forecast
            if (side == "LONG" and fb == "صعودی") or (side == "SHORT" and fb == "نزولی"):
                s += fs * 8
            # Pattern
            if (side == "LONG" and pb == "صعودی") or (side == "SHORT" and pb == "نزولی"):
                s += pc * 5
            return clamp(s, 0, 100)

        return {"LONG": side_score("LONG"), "SHORT": side_score("SHORT")}

    def _persistence(self, symbol: str, side: str, score: float) -> dict[str, Any]:
        # WAIT is not a directional candidate and must not build persistence
        # that can later be mistaken for an entry setup.
        if side not in {"LONG", "SHORT"}:
            return {"streak": 0, "age_min": 0.0, "persistent": False}
        now = time.time()
        try:
            with DB_LOCK, db_conn() as con:
                row = con.execute(
                    "SELECT * FROM v22_candidate_state WHERE symbol=?",
                    (symbol,),
                ).fetchone()
                if not row:
                    con.execute(
                        "INSERT INTO v22_candidate_state(symbol,side,first_seen,last_seen,streak,best_score,last_reason) VALUES(?,?,?,?,?,?,?)",
                        (symbol, side, now, now, 1, score, ""),
                    )
                    return {"streak": 1, "age_min": 0.0, "persistent": False}
                old_side = str(row["side"] or "WAIT")
                last = safe_float(row["last_seen"], now)
                age_min = max(0.0, (now - last) / 60.0)
                if old_side == side and age_min <= V22_CANDIDATE_MEMORY_MINUTES:
                    streak = int(row["streak"] or 0) + 1
                    first = safe_float(row["first_seen"], now)
                else:
                    streak = 1
                    first = now
                con.execute(
                    "UPDATE v22_candidate_state SET side=?,first_seen=?,last_seen=?,streak=?,best_score=?,last_reason=? WHERE symbol=?",
                    (side, first, now, streak, max(score, safe_float(row["best_score"], 0)), "", symbol),
                )
                return {
                    "streak": streak,
                    "age_min": round((now - first) / 60.0, 1),
                    "persistent": streak >= 2 and (now - first) <= V22_CANDIDATE_MEMORY_MINUTES * 60,
                }
        except Exception as exc:
            LOGGER.debug("V22 persistence failed %s: %s", symbol, exc)
            return {"streak": 1, "age_min": 0.0, "persistent": False}

    def evaluate(self, item: dict[str, Any], learning: TitanLearningEngineV22) -> dict[str, Any]:
        symbol = str(item.get("symbol") or "")
        v21 = item.get("trust_max_v21") or {}
        data = v21.get("data_integrity") or {}
        regime = v21.get("regime") or {}
        cns = item.get("cognitive_nexus") or {}
        quality = safe_float(item.get("signal_quality"), 0)
        neural = item.get("neural_v9") or {}
        neural_conf = safe_float(neural.get("confidence"), 0)
        rr = safe_float(item.get("effective_rr_tp1"), safe_float(item.get("rr_tp1"), 0))
        ai_side, ai_agree = self._ai(item)
        edges = self._candidate_edges(item)

        # Add AI only as a weighted partner. Historical AI performance can move
        # this influence, but never above a bounded ceiling.
        prof_long = learning.side_profile(symbol, "LONG")
        prof_short = learning.side_profile(symbol, "SHORT")
        chosen = "LONG" if edges["LONG"] >= edges["SHORT"] else "SHORT"
        prof = prof_long if chosen == "LONG" else prof_short
        global_prof = learning.global_profile()

        ai_bonus = 0.0
        if ai_side == chosen:
            base_ai = 4.0 + ai_agree * 0.07
            if prof.get("ai_samples", 0) >= 8:
                ai_quality = prof.get("ai_aligned_wr", 50)
                base_ai *= clamp(0.75 + (ai_quality - 45) / 80.0, 0.65, 1.35)
            ai_bonus = min(10.0, base_ai)
        elif ai_side in {"LONG", "SHORT"} and ai_agree >= 65:
            ai_bonus = -min(9.0, ai_agree * 0.06)

        score = clamp(max(edges.values()) + ai_bonus, 0, 100)
        raw_margin = edges["LONG"] - edges["SHORT"]
        # Never resolve an exact/near tie into SHORT merely because of a Python
        # else branch. A direction requires a measurable edge over the other side.
        side = "LONG" if raw_margin >= 1.0 else "SHORT" if raw_margin <= -1.0 else "WAIT"
        margin = abs(raw_margin)

        history_shift = prof.get("threshold_shift", 0.0)
        promote_threshold = V22_PROMOTE_SCORE + history_shift
        if prof.get("samples", 0) >= 20 and prof.get("recent_win_rate", 50) >= 60:
            promote_threshold -= 2.0
        # Balanced band: allow real edges through; history can still raise the bar a bit.
        promote_threshold = clamp(promote_threshold, 52.0, 72.0)

        hard_vetoes = []
        hard_vetoes.extend(data.get("hard_fail") or [])
        # Soften: only keep the most severe CNS vetoes as hard blockers
        for v in (cns.get("vetoes") or []):
            if str(v) in {"data_quality", "ai_hard_conflict", "rr"}:
                hard_vetoes.append(v)
        if rr < V22_MIN_RR:
            hard_vetoes.append("RR")
        if ai_side in {"LONG", "SHORT"} and ai_side != side and ai_agree >= V22_MAX_AI_CONFLICT:
            hard_vetoes.append("AI_HARD_CONFLICT")
        # Allow at most V22_MAX_HARD_VETOES soft issues without killing the signal
        if len(hard_vetoes) > max(0, int(V22_MAX_HARD_VETOES)):
            pass  # keep list; trigger logic still checks emptiness for strongest path
        else:
            # With balanced mode, a single mild veto does not zero the opportunity
            hard_vetoes = [v for v in hard_vetoes if str(v) in {"data_quality", "AI_HARD_CONFLICT", "invalid_price"}]

        persistence = self._persistence(symbol, side, score)

        # A strong candidate can be promoted on the first scan; otherwise two
        # consecutive observations are required. This is the anti-noise hysteresis.
        strong_trigger = (
            side in {"LONG", "SHORT"}
            and score >= V22_STRONG_TRIGGER_SCORE
            and data.get("trust", 0) >= V22_MIN_DATA
            and quality >= V22_MIN_QUALITY
            and neural_conf >= V22_MIN_NEURAL
            and rr >= V22_MIN_RR
            and len(hard_vetoes) <= V22_MAX_HARD_VETOES
            and ai_agree < V22_MAX_AI_CONFLICT
        )
        stable_trigger = (
            side in {"LONG", "SHORT"}
            and score >= promote_threshold
            and margin >= 3.5
            and data.get("trust", 0) >= V22_MIN_DATA
            and quality >= V22_MIN_QUALITY
            and neural_conf >= V22_MIN_NEURAL
            and rr >= V22_MIN_RR
            and (persistence["persistent"] or score >= V22_STRONG_TRIGGER_SCORE - 2)
            and len(hard_vetoes) <= V22_MAX_HARD_VETOES
        )

        core_decision = _v21_direction(item.get("decision_tag"))
        action = core_decision
        promoted = False
        if core_decision == "WAIT" and (strong_trigger or stable_trigger):
            action = side
            promoted = True

        # If the core already has a directional decision, V22 never changes its
        # direction merely because AI is louder; it only verifies/grades it.
        if core_decision in {"LONG", "SHORT"}:
            side = core_decision

        if action in {"LONG", "SHORT"}:
            state = "READY" if (data.get("trust", 0) >= 80 and quality >= 72 and neural_conf >= 65 and rr >= 1.35) else "EARLY"
        elif side in {"LONG", "SHORT"} and score >= V22_EARLY_SCORE and not hard_vetoes:
            state = "EARLY_" + side
        elif side in {"LONG", "SHORT"} and score >= V22_WATCH_SCORE:
            state = "WATCH_" + side
        else:
            state = "NO_EDGE"

        # Complete reason tree — every positive/negative contribution is visible.
        reasons = []
        reasons.append(f"سمت کاندید: {side}")
        reasons.append(f"امتیاز فرصت: {score:.1f}/100")
        reasons.append(f"اختلاف دو سمت: {margin:.1f}")
        reasons.append(f"اعتماد داده: {safe_float(data.get('trust'),0):.1f}")
        reasons.append(f"کیفیت سیگنال: {quality:.1f}")
        reasons.append(f"اعتماد عصبی: {neural_conf:.1f}")
        reasons.append(f"RR1: {rr:.2f}")
        reasons.append(f"رأی AI: {ai_side} با توافق {ai_agree:.1f}%")
        reasons.append(f"پایداری کاندید: {persistence['streak']} اسکن / {persistence['age_min']:.1f} دقیقه")
        reasons.append(f"رژیم: {regime.get('regime','—')}")
        if hard_vetoes:
            reasons.append("موانع سخت: " + ", ".join(dict.fromkeys(hard_vetoes)))
        if promoted:
            reasons.append("فرصت WAIT به سیگنال ارتقا یافت چون آستانه فرصت + شواهد مستقل + پایداری/تریگر برقرار شد")
        elif core_decision == "WAIT" and state.startswith(("EARLY_", "WATCH_")):
            reasons.append("سیگنال نهایی هنوز WAIT است؛ فرصت پنهان نشده و به‌عنوان پیش‌هشدار ثبت شد")
        elif core_decision == "WAIT":
            reasons.append("شواهد برای جهت‌دهی نهایی کافی نیست")

        return {
            "version": V22_VERSION,
            "action": action,
            "core_action": core_decision,
            "candidate_side": side,
            "opportunity_state": state,
            "opportunity_score": round(score, 1),
            "margin": round(margin, 1),
            "edges": {k: round(v, 1) for k, v in edges.items()},