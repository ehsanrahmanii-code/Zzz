            self.state["updated_at"] = time.time()
            _save_json(self.path, self.state)
        except Exception as exc:
            LOGGER.debug("adaptive save skipped: %s", exc)

    def _wr(self, wins: float, losses: float) -> float:
        # Beta(2,2) shrinkage prevents 1-3 lucky outcomes from becoming 0%/100% reliability.
        wins = max(0.0, float(wins)); losses = max(0.0, float(losses))
        return ((wins + 2.0) / (wins + losses + 4.0)) * 100.0

    def refresh_from_db(self) -> None:
        """Rebuild calibration memory from DB exactly once per stored outcome.

        The previous implementation reset global counters but kept per-symbol buckets,
        causing the same history to be counted again on every restart/refresh.
        """
        try:
            with DB_LOCK, db_conn() as con:
                rows = con.execute(
                    "SELECT symbol,direction,outcome,ai_majority FROM forecasts "
                    "WHERE outcome IN ('WIN','LOSS') ORDER BY id DESC LIMIT 400"
                ).fetchall()
            self.state["global"] = dict(self._default()["global"])
            self.state["symbols"] = {}
            self.state["error_patterns"] = dict(self._default()["error_patterns"])
            g = self.state["global"]
            for row in rows:
                direction = str(row["direction"]); outcome = str(row["outcome"]); symbol = str(row["symbol"])
                ai_maj = str(row["ai_majority"] or "")
                is_long = direction in {"صعودی", "LONG", "long"}
                is_short = direction in {"نزولی", "SHORT", "short"}
                win = outcome == "WIN"
                if is_long:
                    g["long_wins" if win else "long_losses"] += 1
                elif is_short:
                    g["short_wins" if win else "short_losses"] += 1
                bucket = self.state["symbols"].setdefault(
                    symbol, {"long_wins": 0, "long_losses": 0, "short_wins": 0, "short_losses": 0}
                )
                if is_long:
                    bucket["long_wins" if win else "long_losses"] += 1
                elif is_short:
                    bucket["short_wins" if win else "short_losses"] += 1
                ai_long = ai_maj in {"LONG", "صعودی"}; ai_short = ai_maj in {"SHORT", "نزولی"}
                has_ai = ai_long or ai_short
                ai_agreed = has_ai and ((is_long and ai_long) or (is_short and ai_short))
                if has_ai:
                    g["ai_agree_wins" if (ai_agreed and win) else
                      "ai_agree_losses" if ai_agreed else
                      "ai_disagree_wins" if win else "ai_disagree_losses"] += 1
                    if not win and not ai_agreed:
                        if is_long: self.state["error_patterns"]["false_long"] += 1
                        if is_short: self.state["error_patterns"]["false_short"] += 1
            self._rebalance_weights()
            self._save()
        except Exception as exc:
            LOGGER.debug("adaptive refresh failed: %s", exc)

    def record_outcome(
        self,
        *,
        symbol: str,
        direction: str,
        outcome: str,
        ai_agreed: bool = True,
        quant_was_long: bool = False,
        quant_was_short: bool = False,
    ) -> None:
        g = self.state["global"]
        is_long = direction in {"صعودی", "LONG", "long"}
        is_short = direction in {"نزولی", "SHORT", "short"}
        win = outcome == "WIN"
        loss = outcome == "LOSS"
        if not (win or loss):
            return
        if is_long:
            g["long_wins" if win else "long_losses"] += 1
        elif is_short:
            g["short_wins" if win else "short_losses"] += 1
        if ai_agreed:
            g["ai_agree_wins" if win else "ai_agree_losses"] += 1
        else:
            g["ai_disagree_wins" if win else "ai_disagree_losses"] += 1
            if loss and is_long:
                self.state["error_patterns"]["false_long"] = int(self.state["error_patterns"].get("false_long", 0)) + 1
            if loss and is_short:
                self.state["error_patterns"]["false_short"] = int(self.state["error_patterns"].get("false_short", 0)) + 1
            # Track when quant ignored AI and lost
            if loss and quant_was_long and not is_long:
                pass
            if loss and not ai_agreed:
                if is_long:
                    self.state["error_patterns"]["ignored_ai_short"] = int(self.state["error_patterns"].get("ignored_ai_short", 0)) + 1
                if is_short:
                    self.state["error_patterns"]["ignored_ai_long"] = int(self.state["error_patterns"].get("ignored_ai_long", 0)) + 1
        bucket = self.state["symbols"].setdefault(
            symbol, {"long_wins": 0, "long_losses": 0, "short_wins": 0, "short_losses": 0}
        )
        if is_long:
            bucket["long_wins" if win else "long_losses"] += 1
        elif is_short:
            bucket["short_wins" if win else "short_losses"] += 1
        self._rebalance_weights()
        self._save()

    def _rebalance_weights(self) -> None:
        """Self-tune layer weights and thresholds from observed WIN/LOSS patterns."""
        g = self.state["global"]
        long_wr = self._wr(g["long_wins"], g["long_losses"])
        short_wr = self._wr(g["short_wins"], g["short_losses"])
        agree_n = g["ai_agree_wins"] + g["ai_agree_losses"]
        disagree_n = g["ai_disagree_wins"] + g["ai_disagree_losses"]
        agree_wr = self._wr(g["ai_agree_wins"], g["ai_agree_losses"])
        disagree_wr = self._wr(g["ai_disagree_wins"], g["ai_disagree_losses"])
        # Recompute from stable defaults; do not ratchet thresholds/weights merely because
        # this method is called repeatedly with the same observations.
        defaults = self._default()
        w = dict(defaults["weights"])
        th = dict(defaults["thresholds"])
        ep = self.state["error_patterns"]

        # When trades that agreed with AI win more → increase AI weight
        if agree_n >= 5 and agree_wr >= disagree_wr + 6:
            w["ai"] = min(0.38, float(w.get("ai", 0.26)) + 0.025)
            w["quant"] = max(0.16, float(w.get("quant", 0.26)) - 0.015)
            w["confluence"] = min(0.18, float(w.get("confluence", 0.14)) + 0.005)
        elif disagree_n >= 5 and disagree_wr > agree_wr + 8:
            # Rare: quant alone better — small quant bump but keep AI gate
            w["quant"] = min(0.32, float(w.get("quant", 0.26)) + 0.015)
            w["ai"] = max(0.18, float(w.get("ai", 0.26)) - 0.01)

        # False long epidemic → harder long threshold, more structure weight
        if ep.get("false_long", 0) >= 4 and long_wr < 48:
            th["long_score"] = min(70.0, float(th.get("long_score", 58)) + 1.2)
            th["min_confluence"] = min(78.0, float(th.get("min_confluence", 62)) + 1.0)
            w["structure"] = min(0.24, float(w.get("structure", 0.16)) + 0.01)
            w["quant"] = max(0.15, float(w.get("quant", 0.26)) - 0.01)
        if ep.get("false_short", 0) >= 4 and short_wr < 48:
            th["short_score"] = max(30.0, float(th.get("short_score", 42)) - 1.2)
            th["min_confluence"] = min(78.0, float(th.get("min_confluence", 62)) + 1.0)
            w["structure"] = min(0.24, float(w.get("structure", 0.16)) + 0.01)

        # Good side performance → slightly easier barriers
        if (g["long_wins"] + g["long_losses"]) >= 10 and long_wr >= 58:
            th["long_score"] = max(54.0, float(th.get("long_score", 58)) - 0.6)
        if (g["short_wins"] + g["short_losses"]) >= 10 and short_wr >= 58:
            th["short_score"] = min(46.0, float(th.get("short_score", 42)) + 0.6)

        # Normalize weights
        total = sum(float(v) for v in w.values()) or 1.0
        self.state["weights"] = {k: round(float(v) / total, 4) for k, v in w.items()}
        self.state["thresholds"] = th

    def side_reliability(self, symbol: str = "") -> dict[str, float]:
        g = self.state["global"]
        long_wr = self._wr(g["long_wins"], g["long_losses"])
        short_wr = self._wr(g["short_wins"], g["short_losses"])
        sym = self.state["symbols"].get(symbol) or {}
        if (sym.get("long_wins", 0) + sym.get("long_losses", 0)) >= 4:
            long_wr = 0.55 * long_wr + 0.45 * self._wr(sym["long_wins"], sym["long_losses"])
        if (sym.get("short_wins", 0) + sym.get("short_losses", 0)) >= 4:
            short_wr = 0.55 * short_wr + 0.45 * self._wr(sym["short_wins"], sym["short_losses"])
        return {
            "long_wr": round(long_wr, 2),
            "short_wr": round(short_wr, 2),
            "long_samples": int(g["long_wins"] + g["long_losses"]),
            "short_samples": int(g["short_wins"] + g["short_losses"]),
        }

    def fuse_decision(
        self,
        *,
        symbol: str,
        quant_bias: str,
        score: float,
        alignment: float,
        structure: dict[str, Any],
        regime: dict[str, Any],
        confluence: dict[str, Any],
        meta: dict[str, Any],
        ai_ensemble: dict[str, Any],
        forecast: Optional[dict[str, Any]] = None,
        patterns: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Professional multi-layer fusion — TITAN ↔ AI ↔ forecast ↔ patterns.

        Rules (priority):
        1) Strong AI↔quant disagreement → WAIT (do not force a side)
        2) AI consensus can promote borderline quant only with structure/confluence support
        3) Historical false-long / false-short raises the bar for that side
        4) Success probability must clear a floor before LONG/SHORT leaves WAIT
        5) Weights self-tune from past WIN/LOSS via _rebalance_weights
        6) 12-candle forecast path and chart patterns vote as soft directional layers
        """
        w = dict(self.state.get("weights") or {})
        th = dict(self.state.get("thresholds") or {})
        # Ensure weight keys exist and normalize
        for k, default in (("quant", 0.26), ("structure", 0.16), ("regime", 0.12),
                           ("confluence", 0.14), ("ai", 0.26), ("history", 0.06)):
            w[k] = float(w.get(k, default))
        ssum = sum(w.values()) or 1.0
        w = {k: v / ssum for k, v in w.items()}

        rel = self.side_reliability(symbol)
        struct_bias = str((structure or {}).get("bias", "خنثی"))
        regime_name = str((regime or {}).get("regime", "unknown"))
        conf = safe_float((confluence or {}).get("score"), 50)
        meta_prob = safe_float((meta or {}).get("probability"), 50)
        meta_label = str((meta or {}).get("label", "WATCH"))
        ai_majority = str((ai_ensemble or {}).get("majority", "WAIT"))
        ai_target_agree = safe_float((ai_ensemble or {}).get("agreement"), 0)
        ai_agree = safe_float((ai_ensemble or {}).get("majority_agreement"), ai_target_agree)
        ai_status = str((ai_ensemble or {}).get("status", "NO_AI_DATA"))
        ai_providers = int((ai_ensemble or {}).get("providers", 0) or 0)
        tally = (ai_ensemble or {}).get("tally") or {}
        errors = self.state.get("error_patterns") or {}

        def dir_score(label: str) -> float:
            lab = str(label or "")
            if lab in {"صعودی", "LONG", "trend_up", "BOS_UP", "BULL_STRUCTURE"} or "up" in lab.lower():
                return 1.0
            if lab in {"نزولی", "SHORT", "trend_down", "BOS_DOWN", "BEAR_STRUCTURE"} or "down" in lab.lower():
                return -1.0
            return 0.0

        quant_cont = clamp((float(score) - 50.0) / 50.0, -1.0, 1.0)
        quant_d = dir_score(quant_bias) if quant_bias != "خنثی" else quant_cont * 0.5
        struct_d = dir_score(struct_bias)
        regime_d = dir_score(regime_name)
        conf_d = quant_cont if conf >= 58 else quant_cont * 0.35
        ai_d = dir_score(ai_majority)

        hist_d = 0.0
        if rel["long_wr"] >= rel["short_wr"] + 8 and rel["long_samples"] >= 5:
            hist_d = 0.4
        elif rel["short_wr"] >= rel["long_wr"] + 8 and rel["short_samples"] >= 5:
            hist_d = -0.4
        elif rel["long_wr"] < 42 and rel["long_samples"] >= 8:
            hist_d = -0.25  # punish historically bad longs
        elif rel["short_wr"] < 42 and rel["short_samples"] >= 8:
            hist_d = 0.25

        # Forecast + pattern soft votes (do not dominate quant/AI)
        fc = forecast or {}
        fc_d = dir_score(str(fc.get("overall_bias") or ""))
        _fc_acc = forecast_path_accuracy_stats(symbol)
        _fc_scale = safe_float(_fc_acc.get("weight_scale"), 0.35)
        fc_w = (min(0.12, 0.04 + safe_float(fc.get("path_strength"), 0) / 400.0) * _fc_scale) if fc.get("ok") else 0.0
        pat = patterns or {}
        primary = pat.get("primary") or {}
        pat_d = dir_score(str((primary.get("guide") or {}).get("bias") or ""))
        pat_conf = safe_float(primary.get("confidence"), 0) / 100.0
        pat_w = min(0.10, 0.03 + pat_conf * 0.07) if primary else 0.0

        # Renormalize so total weight stays 1.0 after adding soft layers
        base_keys = ("quant", "structure", "regime", "confluence", "ai", "history")
        base_sum = sum(w[k] for k in base_keys) or 1.0
        soft = fc_w + pat_w
        scale = max(0.78, 1.0 - soft)
        for k in base_keys:
            w[k] = w[k] / base_sum * scale
        w["forecast"] = fc_w
        w["pattern"] = pat_w

        fused = (
            w["quant"] * quant_d
            + w["structure"] * struct_d
            + w["regime"] * regime_d
            + w["confluence"] * conf_d
            + w["ai"] * ai_d
            + w["history"] * hist_d
            + w["forecast"] * fc_d
            + w["pattern"] * pat_d
        )
        fused = float(clamp(fused, -1.0, 1.0))
        if fc_d != 0 and fc.get("ok"):
            # mild agreement note later via explanation
            pass

        # Adaptive barriers from learned thresholds + error patterns
        long_barrier = float(th.get("long_score", 58))
        short_barrier = float(th.get("short_score", 42))
        min_align = float(th.get("min_alignment", 58))
        min_conf = float(th.get("min_confluence", 62))
        ai_need = float(th.get("ai_consensus_pct", 55))
        promote_buf = float(th.get("promote_score_buffer", 4))

        # Raise bar if system keeps making false longs/shorts
        fl = int(errors.get("false_long", 0) or 0)
        fs = int(errors.get("false_short", 0) or 0)
        if fl >= 5:
            long_barrier = min(70.0, long_barrier + min(6.0, fl * 0.35))
        if fs >= 5:
            short_barrier = max(30.0, short_barrier - min(6.0, fs * 0.35))

        # Symbol-specific reliability adjusts barriers
        if rel["long_samples"] >= 6 and rel["long_wr"] < 45:
            long_barrier = min(72.0, long_barrier + 3)
        if rel["short_samples"] >= 6 and rel["short_wr"] < 45:
            short_barrier = max(28.0, short_barrier - 3)