        try:
            _save_json(self.memory_path, self.memory)
        except Exception as exc:
            LOGGER.debug("Professional edge memory save skipped: %s", exc)

    # 1) Signal Confluence Engine
    def signal_confluence(self, *, score=50, alignment=50, rsi=50, price=0, vwap=0,
                          ema20=0, ema50=0, volume_spike=False, derivatives=None,
                          structure=None, regime="unknown"):
        derivatives = derivatives or {}
        structure = structure or {}
        checks = []
        points = []
        if score >= 60:
            checks.append(("momentum", 1)); points.append("مومنتوم صعودی")
        elif score <= 40:
            checks.append(("momentum", 1)); points.append("مومنتوم نزولی")
        else:
            checks.append(("momentum", 0))
        checks.append(("mtf", clamp(alignment / 100.0, 0, 1)))
        if price and vwap:
            checks.append(("vwap", 1 if (score >= 60 and price >= vwap) or (score <= 40 and price <= vwap) else 0.35))
        if ema20 and ema50:
            ema_ok = 1 if (score >= 60 and ema20 >= ema50) or (score <= 40 and ema20 <= ema50) else 0.25
            checks.append(("trend", ema_ok))
        checks.append(("volume", 1.0 if volume_spike else 0.4))
        oi = safe_float(derivatives.get("oi_delta"), 0)
        funding = safe_float(derivatives.get("funding_value"), 0)
        oi_score = 0.55
        if score >= 60 and oi > 0: oi_score = 0.9
        elif score <= 40 and oi > 0: oi_score = 0.8
        elif oi < 0: oi_score = 0.4
        checks.append(("open_interest", oi_score))
        structure_score = safe_float(structure.get("confirmation_score"), 50) / 100.0
        checks.append(("structure", clamp(structure_score, 0, 1)))
        regime_bonus = 1.0 if regime not in {"range", "unknown"} else 0.65
        checks.append(("regime", regime_bonus))
        raw = sum(v for _, v in checks) / max(1, len(checks))
        confluence = int(round(clamp(35 + raw * 65, 0, 100)))
        disagreement = [name for name, val in checks if val < 0.5]
        return {"score": confluence, "components": {k: round(float(v), 3) for k, v in checks},
                "disagreements": disagreement, "label": "STRONG CONFLUENCE" if confluence >= 80 else "CONFIRMED" if confluence >= 68 else "WATCH"}

    # 2) Regime Detection Engine
    def regime_detection(self, df, atr=None, score=50):
        try:
            close = df["close"].astype(float)
            if len(close) < 60: return {"regime": "unknown", "confidence": 0, "features": {}}
            ret20 = float(close.iloc[-1] / close.iloc[-21] - 1) if len(close) > 21 else 0.0
            ret5 = float(close.iloc[-1] / close.iloc[-6] - 1) if len(close) > 6 else 0.0
            atr_pct = float(atr / close.iloc[-1] * 100) if atr is not None and close.iloc[-1] else 0.0
            ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
            ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
            slope = abs(ret20) * 100
            if atr_pct >= 4.5:
                regime = "high_volatility"
            elif ret20 > 0.05 and ema20 > ema50 and slope > 1.5:
                regime = "trend_up"
            elif ret20 < -0.05 and ema20 < ema50 and slope > 1.5:
                regime = "trend_down"
            elif abs(ret5) > 0.02 and abs(ret20) < 0.04:
                regime = "breakout_watch"
            elif atr_pct < 1.2 and abs(ret20) < 0.025:
                regime = "range"
            else:
                regime = "transition"
            score_fit = 100 - min(80, abs((score - 50) - (20 if "up" in regime else -20 if "down" in regime else 0)) * 1.8)
            return {"regime": regime, "confidence": int(round(clamp(score_fit, 20, 95))),
                    "features": {"ret5_pct": round(ret5*100,3), "ret20_pct": round(ret20*100,3), "atr_pct": round(atr_pct,3), "ema_spread_pct": round((ema20/ema50-1)*100,3) if ema50 else 0}}
        except Exception as exc:
            LOGGER.debug("Regime detection failed: %s", exc)
            return {"regime": "unknown", "confidence": 0, "features": {}}

    # 3) Liquidity / Order-Flow Proxy
    def liquidity_map(self, df, current_price):
        try:
            data = df.tail(60).copy()
            price = float(current_price)
            if data.empty or price <= 0: raise ValueError("invalid liquidity input")
            vol = pd.to_numeric(data["vol"], errors="coerce").fillna(0)
            high_vol = data.loc[vol.nlargest(min(8, len(vol))).index]
            upper = float(high_vol["high"].median()) if not high_vol.empty else price
            lower = float(high_vol["low"].median()) if not high_vol.empty else price
            ranges = {"upper_pool": round(upper, 8), "lower_pool": round(lower, 8),
                      "upper_distance_pct": round((upper/price-1)*100,3),
                      "lower_distance_pct": round((lower/price-1)*100,3)}
            if upper > price * 1.003 and lower < price * 0.997:
                state = "balanced_liquidity"
            elif upper > price * 1.01:
                state = "overhead_liquidity"
            elif lower < price * 0.99:
                state = "downside_liquidity"
            else:
                state = "compressed"
            # buy/sell pressure proxy from candle location + volume
            clv = ((data["close"] - data["low"]) - (data["high"] - data["close"])) / (data["high"] - data["low"]).replace(0, np.nan)
            pressure = float((clv.fillna(0) * vol).sum() / max(float(vol.sum()), 1.0))
            return {"state": state, "pressure": round(pressure, 3), "map": ranges,
                    "liquidity_bias": "buying" if pressure > 0.12 else "selling" if pressure < -0.12 else "balanced"}
        except Exception as exc:
            LOGGER.debug("Liquidity map failed: %s", exc)
            return {"state": "unavailable", "pressure": 0, "map": {}, "liquidity_bias": "unknown"}

    # 4) Market Structure Engine
    def market_structure(self, df):
        try:
            d = df.tail(80).copy()
            highs = d["high"].rolling(5, center=True).max()
            lows = d["low"].rolling(5, center=True).min()
            swing_highs = d.loc[(d["high"] == highs).fillna(False), "high"].tail(6).tolist()
            swing_lows = d.loc[(d["low"] == lows).fillna(False), "low"].tail(6).tolist()
            last = float(d["close"].iloc[-1])
            recent_high = max(swing_highs[-3:]) if swing_highs else float(d["high"].tail(20).max())
            recent_low = min(swing_lows[-3:]) if swing_lows else float(d["low"].tail(20).min())
            prev_high = swing_highs[-4] if len(swing_highs) >= 4 else recent_high
            prev_low = swing_lows[-4] if len(swing_lows) >= 4 else recent_low
            higher_high = recent_high > prev_high
            higher_low = recent_low > prev_low
            lower_high = recent_high < prev_high
            lower_low = recent_low < prev_low
            if last > recent_high * 1.001:
                event = "BOS_UP"
            elif last < recent_low * 0.999:
                event = "BOS_DOWN"
            elif higher_high and higher_low:
                event = "BULL_STRUCTURE"
            elif lower_high and lower_low:
                event = "BEAR_STRUCTURE"
            else:
                event = "RANGE_STRUCTURE"
            confirmation = 80 if event in {"BOS_UP", "BOS_DOWN"} else 72 if event in {"BULL_STRUCTURE", "BEAR_STRUCTURE"} else 48
            return {"event": event, "last": round(last, 8), "swing_high": round(recent_high, 8), "swing_low": round(recent_low, 8), "confirmation_score": confirmation,
                    "bias": "صعودی" if event in {"BOS_UP", "BULL_STRUCTURE"} else "نزولی" if event in {"BOS_DOWN", "BEAR_STRUCTURE"} else "خنثی"}
        except Exception as exc:
            LOGGER.debug("Market structure failed: %s", exc)
            return {"event": "UNKNOWN", "confirmation_score": 0, "bias": "خنثی"}

    # 5) Walk-forward / OOS validation helper
    def out_of_sample_check(self, returns, min_samples=30, return_unit="pct"):
        arr = np.asarray(returns, dtype=float)
        arr = arr[np.isfinite(arr)]
        if arr.size < min_samples:
            return {"samples": int(arr.size), "oos_expectancy": 0.0, "oos_win_rate": 0.0,
                    "train_expectancy": 0.0, "status": "insufficient", "min_samples": int(min_samples),
                    "return_unit": return_unit}
        split = min(max(int(arr.size * 0.7), 10), arr.size - 10)
        train, test = arr[:split], arr[split:]
        decisive = test[test != 0]
        wins = int((decisive > 0).sum()); losses = int((decisive < 0).sum())
        return {"samples": int(test.size), "oos_expectancy": round(float(test.mean()), 4),
                "oos_win_rate": round(wins / (wins + losses) * 100, 2) if wins + losses else 0.0,
                "train_expectancy": round(float(train.mean()), 4), "status": "ok",
                "min_samples": int(min_samples), "return_unit": return_unit}

    # 6) Strategy Laboratory
    def strategy_lab(self, df, horizon=3, min_signals=30):
        strategies = {}
        try:
            close = pd.to_numeric(df["close"], errors="coerce")
            ema20 = close.ewm(span=20, adjust=False).mean(); ema50 = close.ewm(span=50, adjust=False).mean()
            rsi = wilder_rsi(close)
            signal_map = {
                "trend": np.where(ema20 > ema50, 1, np.where(ema20 < ema50, -1, 0)),
                "momentum": np.where(rsi > 55, 1, np.where(rsi < 45, -1, 0)),
                "breakout": np.where(close > close.rolling(20).max().shift(1), 1, np.where(close < close.rolling(20).min().shift(1), -1, 0)),
                "mean_reversion": np.where(rsi < 30, 1, np.where(rsi > 70, -1, 0)),
            }
            for name, signal in signal_map.items():
                sig = pd.Series(signal, index=df.index).fillna(0).astype(float)
                future = close.shift(-horizon) / close - 1.0
                raw = (future * sig * 100.0) - (TOTAL_ENTRY_BUFFER * 2.0 * 100.0)
                valid = raw[(sig != 0) & future.notna()].replace([np.inf, -np.inf], np.nan).dropna()
                metrics = _safe_return_series(valid.tolist(), return_unit="pct")
                strategies[name] = {
                    "signals": int((sig != 0).sum()), "complete_signals": int(valid.size),
                    "win_rate": metrics["win_rate"], "loss_rate": metrics["loss_rate"],
                    "expectancy_pct": metrics["expectancy"], "profit_factor": metrics["profit_factor"],
                    "max_drawdown_pct": metrics["max_drawdown"], "max_losing_streak": metrics["max_losing_streak"],
                }
            eligible = [(n,v) for n,v in strategies.items() if v["complete_signals"] >= min_signals]
            leader = max(eligible, key=lambda kv: kv[1]["expectancy_pct"], default=(None, {}))
            return {"strategies": strategies, "leader": leader[0], "leader_expectancy_pct": leader[1].get("expectancy_pct",0),
                    "horizon_bars": int(horizon), "min_signals": int(min_signals), "cost_model": "round_trip_fee+spread+slippage"}
        except Exception as exc:
            LOGGER.debug("Strategy lab failed: %s", exc)
            return {"strategies": {}, "leader": None, "leader_expectancy_pct": 0, "horizon_bars": int(horizon), "min_signals": int(min_signals)}

    # 7) Meta-Labeling
    def meta_label(self, confluence, quality, historical_win_rate=0):
        base = 0.45 * confluence + 0.35 * quality + 0.20 * clamp(historical_win_rate, 0, 100)
        probability = clamp(base, 0, 100)
        label = "ACCEPT" if probability >= 72 else "WATCH" if probability >= 58 else "REJECT"
        return {"probability": round(probability,2), "label": label}

    # 8) Adaptive Risk Engine
    def adaptive_risk(self, base_risk=1.0, volatility_pct=1.0, confidence=50, regime="unknown", drawdown_pct=0):
        factor = 1.0
        if volatility_pct > 4: factor *= 0.55
        elif volatility_pct > 2.5: factor *= 0.75
        elif volatility_pct < 0.8: factor *= 1.05
        if confidence < 60: factor *= 0.75
        elif confidence > 80: factor *= 1.05
        if regime in {"high_volatility", "transition"}: factor *= 0.75
        if drawdown_pct > 10: factor *= 0.45
        elif drawdown_pct > 5: factor *= 0.65
        return {"base_risk_pct": round(base_risk,3), "risk_pct": round(clamp(base_risk*factor,0.1,2.5),3), "factor": round(factor,3)}

    # 9) Drawdown Governor
    def drawdown_governor(self, values, unit="r"):
        arr = np.asarray(values, dtype=float); arr = arr[np.isfinite(arr)]
        if arr.size == 0:
            return {"state": "NORMAL", "drawdown_pct": 0.0, "risk_multiplier": 1.0, "unit": unit, "observations": 0}
        account_returns = arr / 100.0 if unit == "pct" else arr * 0.01
        account_returns = np.clip(account_returns, -0.999, 10.0)
        equity = np.cumprod(1.0 + account_returns)
        peak = np.maximum.accumulate(equity)
        dd_pct = float(np.max((peak - equity) / np.maximum(peak, 1e-12)) * 100.0)
        if dd_pct >= 15: state, mult = "DEFENSIVE", 0.35
        elif dd_pct >= 10: state, mult = "REDUCED", 0.55
        elif dd_pct >= 5: state, mult = "CAUTIOUS", 0.75
        else: state, mult = "NORMAL", 1.0
        return {"state": state, "drawdown_pct": round(dd_pct,3), "risk_multiplier": mult, "unit": unit, "observations": int(arr.size)}

    # 10) AI Ensemble Consensus
    def ai_ensemble(self, ai_opinions, titan_bias):
        mapping = {"صعودی": "LONG", "نزولی": "SHORT", "خنثی": "WAIT"}
        target = mapping.get(titan_bias, "WAIT")
        votes = []; providers = []; details = {}
        import re
        final_re = re.compile(r"نتیجه\s*نهایی\s*[:：-]?\s*(صعودی|نزولی|انتظار|خنثی)", re.I)
        for provider, raw_text in (ai_opinions or {}).items():
            if provider in {"ai_status", "providers", "internal", "titan"} or not isinstance(raw_text, str):
                continue
            text = raw_text.strip(); t = text.lower()
            if not text:
                continue
            # Prefer the explicitly requested final label. Keyword fallback only uses the
            # tail of the answer, reducing false votes when both bull/bear risks are discussed.
            matches = final_re.findall(text)
            if matches:
                lab = matches[-1]
                vote = "LONG" if lab == "صعودی" else "SHORT" if lab == "نزولی" else "WAIT"
            else:
                tail = t[-320:]
                long_hits = sum(tail.count(k) for k in ("صعودی", "bull", "long", "خرید"))
                short_hits = sum(tail.count(k) for k in ("نزولی", "bear", "short", "فروش"))
                vote = "LONG" if long_hits > short_hits else "SHORT" if short_hits > long_hits else "WAIT"
            votes.append(vote); providers.append(provider)
            details[provider] = {"vote": vote, "snippet": (text[:180] + "…") if len(text) > 180 else text}
        total = len(votes)
        agree = sum(v == target for v in votes)
        long_n = votes.count("LONG"); short_n = votes.count("SHORT"); wait_n = votes.count("WAIT")
        majority = "LONG" if long_n > short_n and long_n > wait_n else "SHORT" if short_n > long_n and short_n > wait_n else "WAIT"
        majority_n = max(long_n, short_n, wait_n) if total else 0
        return {
            "target": target, "votes": dict(zip(providers, votes)), "details": details,
            "agreement": round(agree / total * 100, 1) if total else 0.0,
            "majority_agreement": round(majority_n / total * 100, 1) if total else 0.0,
            "providers": total, "tally": {"LONG": long_n, "SHORT": short_n, "WAIT": wait_n},
            "majority": majority,
            "status": "CONSENSUS" if total and majority_n / total >= 0.66 else "MIXED" if total else "NO_AI_DATA",
        }

    # 11) Counterfactual Engine
    def counterfactual(self, price, sl, tp1, tp2, direction, future_prices):
        result = {"path": "NONE", "bars_to_tp1": None, "bars_to_tp2": None, "bars_to_sl": None, "mae_pct": 0.0, "mfe_pct": 0.0}
        try:
            future = [float(x) for x in future_prices if float(x) > 0]
            if not future or price <= 0: return result
            signed = [((x-price)/price*100) * (1 if direction != "نزولی" else -1) for x in future]
            result["mfe_pct"] = round(max(signed), 3); result["mae_pct"] = round(min(signed), 3)
            tp1_hit = (tp1 > price and any(x >= tp1 for x in future)) if direction != "نزولی" else any(x <= tp1 for x in future)
            tp2_hit = (tp2 > price and any(x >= tp2 for x in future)) if direction != "نزولی" else any(x <= tp2 for x in future)
            sl_hit = any(x <= sl for x in future) if direction != "نزولی" else any(x >= sl for x in future)
            if tp2_hit: result["path"] = "TP2"
            elif tp1_hit: result["path"] = "TP1"
            elif sl_hit: result["path"] = "SL"
            if tp1_hit:
                result["bars_to_tp1"] = next(i+1 for i,x in enumerate(future) if (x >= tp1 if direction != "نزولی" else x <= tp1))
            if tp2_hit:
                result["bars_to_tp2"] = next(i+1 for i,x in enumerate(future) if (x >= tp2 if direction != "نزولی" else x <= tp2))
            if sl_hit:
                result["bars_to_sl"] = next(i+1 for i,x in enumerate(future) if (x <= sl if direction != "نزولی" else x >= sl))
            return result
        except Exception:
            return result

    # 12) Decision Terminal
    def decision_terminal(self, item):
        edge = item.get("edge") or {}
        return {
            "symbol": item.get("symbol"), "price": item.get("price"), "bias": item.get("bias"),
            "decision_tag": item.get("decision_tag") or edge.get("decision_tag") or "WAIT",
            "regime": (edge.get("regime") or {}).get("regime", "unknown"),
            "market_risk": (edge.get("risk") or {}).get("risk_pct", 0),
            "liquidity": (edge.get("liquidity") or {}).get("state", "unknown"),
            "structure": (edge.get("structure") or {}).get("event", "unknown"),
            "structure_bias": (edge.get("structure") or {}).get("bias", "خنثی"),
            "confluence": (edge.get("confluence") or {}).get("score", 0),
            "confluence_label": (edge.get("confluence") or {}).get("label", ""),
            "meta_probability": (edge.get("meta") or {}).get("probability", 0),
            "meta_label": (edge.get("meta") or {}).get("label", "WATCH"),
            "ai_consensus": (edge.get("ai") or {}).get("agreement", 0),
            "ai_status": (edge.get("ai") or {}).get("status", "NO_AI_DATA"),
            "risk_reward_1": item.get("rr_tp1"), "risk_reward_2": item.get("rr_tp2"),
            "setup_quality": item.get("signal_quality"), "signal_tag": item.get("signal_tag"),
            "governor": (edge.get("governor") or {}).get("state", "NORMAL"),
            "final_state": (edge.get("meta") or {}).get("label", "WATCH"),
        }

    def register_observation(self, item):
        try:
            key = str(item.get("symbol"))
            bucket = self.memory.setdefault("symbols", {}).setdefault(key, {"observations":0,"quality_sum":0.0,"wins":0,"losses":0})
            bucket["observations"] += 1
            bucket["quality_sum"] += safe_float(item.get("signal_quality"), 0)
            self._save_memory()
        except Exception:
            pass

    def historical_win_rate_for_item(self, item):
        try:
            with DB_LOCK, db_conn() as con:
                row = con.execute("SELECT trades,wins FROM setup_stats WHERE setup_key LIKE ? ORDER BY trades DESC LIMIT 1", (f"%{item.get('bias')}%",)).fetchone()
            if row and row[0]: return float(row[1]/row[0]*100)
        except Exception:
            pass
        return 0.0



# ============================================================
# TITAN ADAPTIVE INTELLIGENCE — self-correcting weights & fusion
# Learns from forecast outcomes + AI disagreement patterns.
# ============================================================

class TitanAdaptiveIntelligence:
    """Professional calibration layer.

    Goals:
    - Reduce LONG/SHORT mismatch between quant core and AI ensemble
    - Raise success rate by demanding multi-layer agreement
    - Learn from past WIN/LOSS and shift weights so repeated mistakes fade
    - Never invent edge: disagreement → WAIT unless history strongly favors one side
    """

    def __init__(self):
        self.path = MEMORY_DIR / "adaptive_calibration.json"
        self.state = self._load()

    def _default(self) -> dict[str, Any]:
        return {
            "version": 4,
            "updated_at": 0.0,
            "global": {
                "long_wins": 0, "long_losses": 0,
                "short_wins": 0, "short_losses": 0,
                "ai_agree_wins": 0, "ai_agree_losses": 0,
                "ai_disagree_wins": 0, "ai_disagree_losses": 0,
            },
            "weights": {
                "quant": 0.24,
                "structure": 0.16,
                "regime": 0.12,
                "confluence": 0.14,
                "ai": 0.28,
                "history": 0.06,
            },
            "thresholds": {
                "long_score": 54.0,
                "short_score": 46.0,
                "min_alignment": 50.0,
                "min_confluence": 54.0,
                "ai_consensus_pct": 55.0,
                "promote_score_buffer": 6.0,
            },
            "symbols": {},
            "error_patterns": {
                "false_long": 0,
                "false_short": 0,
                "ignored_ai_long": 0,
                "ignored_ai_short": 0,
            },
        }

    def _load(self) -> dict[str, Any]:
        data = _load_json(self.path, {})
        base = self._default()
        if not isinstance(data, dict):
            return base
        for k, v in base.items():
            if k not in data:
                data[k] = v
            elif isinstance(v, dict) and isinstance(data.get(k), dict):
                for kk, vv in v.items():
                    data[k].setdefault(kk, vv)
        return data

    def _save(self) -> None:
        try:
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
        if rel["long_samples"] >= 6 and rel["long_wr"] > 60:
            long_barrier = max(54.0, long_barrier - 2)
        if rel["short_samples"] >= 6 and rel["short_wr"] > 60:
            short_barrier = min(46.0, short_barrier + 2)

        explanation: list[str] = []
        explanation.append(f"هم‌جوشی={fused:+.2f} · وزن AI={w['ai']:.0%} · وزن کمی={w['quant']:.0%}")

        # --- AI alignment gates ---
        quant_side = "LONG" if quant_bias == "صعودی" or score >= 54 else "SHORT" if quant_bias == "نزولی" or score <= 46 else "WAIT"
        ai_conflict = False
        if ai_providers >= 1 and ai_majority in {"LONG", "SHORT"} and quant_side in {"LONG", "SHORT"}:
            if ai_majority != quant_side:
                ai_conflict = True
                explanation.append(f"اختلاف TITAN({quant_side}) با اکثریت هوش‌مصنوعی({ai_majority})")

        # Base technical OK flags (balanced: real edge can pass without extreme fusion)
        long_ok = (
            fused >= 0.10
            and score >= long_barrier
            and alignment >= min_align - 4
            and conf >= min_conf - 12
            and quant_d >= -0.22
        )
        short_ok = (
            fused <= -0.10
            and score <= short_barrier
            and alignment >= min_align - 4
            and conf >= min_conf - 12
            and quant_d <= 0.22
        )

        # Graded AI interaction: AI is a decision partner, not an automatic veto.
        # A single disagreement must not erase a technically strong opportunity.
        # Only a strong AI consensus against a weak quant setup is allowed to veto.
        if ai_conflict and ai_providers >= 1:
            strong_quant_long = quant_side == "LONG" and fused >= 0.30 and conf >= 68 and struct_d >= 0
            strong_quant_short = quant_side == "SHORT" and fused <= -0.30 and conf >= 68 and struct_d <= 0
            hard_ai_veto = ai_agree >= 78 and fused < 0.22 if quant_side == "LONG" else ai_agree >= 78 and fused > -0.22 if quant_side == "SHORT" else False
            if hard_ai_veto and not (strong_quant_long or strong_quant_short):
                if quant_side == "LONG": long_ok = False
                if quant_side == "SHORT": short_ok = False
                explanation.append("اجماع قوی AI خلاف setup ضعیف → عدم ورود")
            else:
                # Keep the quant opportunity alive, but reduce conviction slightly.
                explanation.append("اختلاف AI/TITAN → رأی AI به‌عنوان جریمه وزن‌دار لحاظ شد، نه وتوی کامل")

        # AI majority veto of weak quant
        if ai_providers >= 1 and ai_majority == "SHORT" and ai_agree >= ai_need:
            if long_ok and fused < 0.40:
                long_ok = False
                explanation.append("وتوی فروش هوش مصنوعی روی خرید ضعیف")
        if ai_providers >= 1 and ai_majority == "LONG" and ai_agree >= ai_need:
            if short_ok and fused > -0.40:
                short_ok = False
                explanation.append("وتوی خرید هوش مصنوعی روی فروش ضعیف")

        # AI promotion of borderline setups (only same direction)
        if ai_providers >= 1 and ai_agree >= ai_need:
            if ai_majority == "LONG" and not long_ok:
                if (
                    score >= long_barrier - max(5.0, promote_buf)
                    and alignment >= min_align - 7
                    and fused >= 0.08
                    and struct_d >= -0.10
                    and conf >= 53
                ):
                    long_ok = True
                    explanation.append("ارتقای مرزی خرید با اجماع هوش مصنوعی")
            if ai_majority == "SHORT" and not short_ok:
                if (
                    score <= short_barrier + max(5.0, promote_buf)
                    and alignment >= min_align - 7
                    and fused <= -0.08
                    and struct_d <= 0.10
                    and conf >= 53
                ):
                    short_ok = True
                    explanation.append("ارتقای مرزی فروش با اجماع هوش مصنوعی")

        # Meta-label gate
        if meta_label == "REJECT":
            long_ok = False
            short_ok = False
            explanation.append("متا-برچسب رد → انتظار")

        # Success probability model (0-100)
        base_succ = 50.0
        base_succ += abs(fused) * 22.0
        base_succ += (alignment - 50) * 0.25
        base_succ += (conf - 50) * 0.20
        base_succ += (meta_prob - 50) * 0.15
        if ai_providers >= 1:
            if not ai_conflict:
                base_succ += min(12.0, ai_agree * 0.12)
            else:
                base_succ -= min(15.0, 8 + (100 - ai_agree) * 0.05)
        # Historical calibration is sample-size weighted and Bayesian-shrunk.
        # `success_probability` remains an estimate, not a guaranteed/calibrated market probability.
        side_wr = 50.0; side_n = 0
        if long_ok:
            side_wr, side_n = rel["long_wr"], rel["long_samples"]
        elif short_ok:
            side_wr, side_n = rel["short_wr"], rel["short_samples"]
        hist_weight = min(0.35, max(0.0, side_n) / 60.0 * 0.35)
        base_succ = (1.0 - hist_weight) * base_succ + hist_weight * side_wr
        certainty_cap = 72.0 if side_n < 8 else 80.0 if side_n < 20 else 88.0
        if ai_providers == 0:
            certainty_cap = min(certainty_cap, 76.0)
        success_probability = float(clamp(base_succ, 5, certainty_cap))
        cal_dir = "LONG" if long_ok else "SHORT" if short_ok else ""
        calibration = _probability_calibration(symbol, cal_dir, success_probability)
        calibrated_probability = float(calibration.get("calibrated", success_probability))
        # Blend only partially so sparse historical data cannot dominate the live model.
        if calibration.get("samples", 0) >= 12:
            success_probability = float(clamp(0.55 * success_probability + 0.45 * calibrated_probability, 5, certainty_cap))

        # Hard floor: no directional call without enough estimated success score
        # Opportunity-aware floor: strong multi-factor technical setups can fire even
        # when AI confidence is imperfect. This avoids an always-WAIT system while
        # keeping a minimum quality floor.
        technical_edge = abs(fused) >= 0.28 and alignment >= (min_align - 4) and conf >= (min_conf - 5)
        min_succ = 54.0 if technical_edge else (56.0 if ai_providers >= 1 else 53.0)
        if success_probability < min_succ and not (technical_edge and success_probability >= 52.0):
            if long_ok or short_ok:
                explanation.append(f"احتمال موفقیت {success_probability:.0f}% زیر کف {min_succ:.0f} → انتظار")
            long_ok = False
            short_ok = False

        if long_ok and short_ok:
            decision, final_bias = "WAIT", "خنثی"
            explanation.append("تعارض دوطرفه → انتظار")
        elif long_ok:
            decision, final_bias = "LONG", "صعودی"
            explanation.append(f"تأیید خرید · احتمال≈{success_probability:.0f}%")
        elif short_ok:
            decision, final_bias = "SHORT", "نزولی"
            explanation.append(f"تأیید فروش · احتمال≈{success_probability:.0f}%")
        else:
            decision, final_bias = "WAIT", "خنثی"
            explanation.append("شرایط برای سیگنال جهتی کافی نیست")

        if fc.get("ok") and fc_d != 0:
            agree = (decision == "LONG" and fc_d > 0) or (decision == "SHORT" and fc_d < 0)
            explanation.append(
                f"مسیر {fc.get('horizon', 12)} کندلی: {fc.get('overall_bias')} · "
                f"{'هم‌راستا' if agree else 'ناهم‌راستا'} با تصمیم · قدرت مسیر {safe_float(fc.get('path_strength'), 0):.0f}"
            )
        if primary:
            explanation.append(
                f"الگوی «{primary.get('id')}» (اطمینان {safe_float(primary.get('confidence'), 0):.0f}%) · سوگیری {(primary.get('guide') or {}).get('bias', '—')}"
            )

        return {
            "decision": decision,
            "bias": final_bias,
            "fused_score": round(fused, 4),
            "success_probability": round(success_probability, 1),
            "probability_calibration": calibration,
            "weights": {k: round(v, 4) for k, v in w.items()},
            "thresholds": {
                "long_score": long_barrier,
                "short_score": short_barrier,
                "min_alignment": min_align,
                "min_confluence": min_conf,
                "min_success": min_succ,
            },
            "reliability": rel,
            "ai_majority": ai_majority,
            "ai_agreement": ai_agree,
            "ai_target_agreement": ai_target_agree,
            "ai_conflict": ai_conflict,
            "explanation": explanation,
            "tally": tally,
            "quant_side": quant_side,
        }



TITAN_ADAPTIVE = TitanAdaptiveIntelligence()
try:
    TITAN_ADAPTIVE.refresh_from_db()
except Exception:
    pass



TITAN_EDGE_SUITE = TitanProfessionalEdgeSuite()

def _first_touch_ohlc(window: pd.DataFrame, direction: str, sl: float, tp1: float, tp2: float | None = None) -> tuple[str, str, float | None]:
    """Chronological barrier evaluator using OHLC.

    If SL and TP are both inside the same candle, ordering is unknowable at that
    granularity, so the result is AMBIGUOUS rather than silently choosing a winner.
    """
    if window is None or window.empty or not np.isfinite(sl) or not np.isfinite(tp1):
        return "MISS", "NONE", None
    is_long = direction in {"صعودی", "LONG", "long"}
    is_short = direction in {"نزولی", "SHORT", "short"}
    if not (is_long or is_short):
        return "NEUTRAL", "NONE", None
    for _, bar in window.sort_values("t").iterrows():
        high = safe_float(bar.get("high"), np.nan); low = safe_float(bar.get("low"), np.nan)
        if not (np.isfinite(high) and np.isfinite(low)):
            continue
        sl_hit = low <= sl if is_long else high >= sl
        tp1_hit = high >= tp1 if is_long else low <= tp1
        tp2_hit = False
        if tp2 is not None and np.isfinite(tp2):
            tp2_hit = high >= tp2 if is_long else low <= tp2
        if sl_hit and (tp1_hit or tp2_hit):
            return "AMBIGUOUS", "BOTH_SAME_BAR", None
        if sl_hit:
            return "LOSS", "SL", float(sl)
        if tp2_hit:
            return "WIN", "TP2", float(tp2)
        if tp1_hit:
            return "WIN", "TP1", float(tp1)
    return "MISS", "NONE", None


# ============================================================
# PAPER / FORECAST / METRICS
# ============================================================


def _record_setup_outcome(item: dict[str, Any], pnl_r: float) -> None:
    key = "|".join([str(item.get("bias")), str(item.get("signal_tag")), str(item.get("tfs", {}).get("1h", "")), str(item.get("tfs", {}).get("4h", ""))])
    with DB_LOCK, db_conn() as con:
        row = con.execute("SELECT trades,wins,losses,pnl_r FROM setup_stats WHERE setup_key=?", (key,)).fetchone()
        trades, wins, losses, pnl = tuple(row) if row else (0, 0, 0, 0.0)
        trades += 1
        wins += int(pnl_r > 0); losses += int(pnl_r < 0); pnl += pnl_r
        con.execute("INSERT OR REPLACE INTO setup_stats(setup_key,trades,wins,losses,pnl_r,updated_at) VALUES(?,?,?,?,?,?)", (key, trades, wins, losses, pnl, time.time()))


def calculate_position_size(account_size: float, risk_pct: float, entry: float, stop: float) -> dict[str, float]:
    account = max(0.0, float(account_size)); risk = clamp(float(risk_pct), 0.01, 20.0); distance = abs(entry - stop)
    risk_cash = account * risk / 100.0; quantity = risk_cash / distance if distance > 0 else 0.0
    return {"risk_cash": round(risk_cash, 4), "quantity": round(quantity, 8), "notional": round(quantity * max(entry, 0), 4)}


def paper_open_signal(item: dict[str, Any], account_size: float = 10000.0, risk_pct: float = 1.0) -> bool:
    """Open paper only with valid oriented levels — never store tp=0 or inverted SL/TP."""
    try:
        entry = safe_float(str(item.get("price", "0")).replace(",", ""))
        sl = safe_float(str(item.get("stop_loss", "0")).replace(",", ""))
        tp1 = safe_float(str(item.get("tp1", "0")).replace(",", ""))
        tp2 = safe_float(str(item.get("tp2", "0")).replace(",", ""))
        bias = str(item.get("bias") or "")
        decision = str(item.get("decision_tag") or item.get("decision") or "")
        if decision in {"LONG", "SHORT"}:
            side = decision
        elif bias in {"صعودی", "LONG"}:
            side = "LONG"
        elif bias in {"نزولی", "SHORT"}:
            side = "SHORT"
        else:
            return False
        if entry <= 0 or sl <= 0 or tp1 <= 0:
            return False
        if side == "LONG" and not (sl < entry < tp1):
            return False
        if side == "SHORT" and not (tp1 < entry < sl):
            return False
        risk = abs(entry - sl)
        if risk <= entry * 0.0005 or abs(tp1 - entry) / risk < MIN_EFFECTIVE_RR:
            return False
        size = calculate_position_size(account_size, risk_pct, entry, sl)
        pred_prob = float(clamp(safe_float(
            item.get("success_probability", item.get("success_prob", item.get("decision_confidence", 50.0))), 50.0
        ), 1.0, 85.0))
        with DB_LOCK, db_conn() as con:
            if con.execute("SELECT 1 FROM paper_trades WHERE symbol=? AND status='OPEN' LIMIT 1", (item["symbol"],)).fetchone():
                return False
            if con.execute("SELECT 1 FROM paper_trades WHERE symbol=? AND created_at>=? LIMIT 1",
                           (item["symbol"], time.time() - SIGNAL_COOLDOWN_SECONDS)).fetchone():
                return False
            con.execute(
                "INSERT INTO paper_trades(symbol,timeframe,created_at,decision,entry,sl,tp1,tp2,quantity,risk_pct,status,success_prob) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (item["symbol"], "1h", time.time(), side, entry, sl, tp1, tp2 if tp2 > 0 else tp1,
                 size["quantity"], risk_pct, "OPEN", pred_prob),
            )
        return True
    except Exception as exc:
        LOGGER.warning("Paper signal failed: %s", exc)
        return False


def evaluate_paper_trades() -> None:
    """Chronological first-touch; guards against exit_price=0 and invalid levels."""
    now = time.time()
    with DB_LOCK, db_conn() as con:
        rows = con.execute("SELECT * FROM paper_trades WHERE status='OPEN' ORDER BY created_at LIMIT 200").fetchall()
    for row in rows:
        try:
            entry = safe_float(row["entry"], 0)
            sl = safe_float(row["sl"], np.nan)
            tp1 = safe_float(row["tp1"], np.nan)