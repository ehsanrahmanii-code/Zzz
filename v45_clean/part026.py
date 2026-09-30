
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