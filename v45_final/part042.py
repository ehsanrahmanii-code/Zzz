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