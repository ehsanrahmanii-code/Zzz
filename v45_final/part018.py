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