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