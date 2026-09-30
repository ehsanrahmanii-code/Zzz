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