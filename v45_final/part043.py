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