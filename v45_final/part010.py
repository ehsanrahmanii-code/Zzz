

def _adx_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder-style ADX without external dependencies."""
    if df is None or df.empty or len(df) < period + 3:
        return pd.Series(dtype=float)
    high, low, close = df["high"].astype(float), df["low"].astype(float), df["close"].astype(float)
    up = high.diff(); down = -low.diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    tr = pd.concat([(high-low), (high-close.shift()).abs(), (low-close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    pdi = 100 * plus_dm.ewm(alpha=1/period, adjust=False, min_periods=period).mean() / atr.replace(0, np.nan)
    mdi = 100 * minus_dm.ewm(alpha=1/period, adjust=False, min_periods=period).mean() / atr.replace(0, np.nan)
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1/period, adjust=False, min_periods=period).mean().fillna(0.0)


def _rolling_trend_stability(close: pd.Series, lookback: int = 20) -> tuple[float, float]:
    """Return (signed stability, consistency) from closed-candle returns.

    Stability is the average sign agreement of returns, scaled by direction.
    Consistency is the fraction of returns agreeing with the dominant direction.
    """
    r = pd.to_numeric(close, errors="coerce").pct_change().dropna().tail(lookback)
    if len(r) < max(8, lookback // 2):
        return 0.0, 0.0
    pos = float((r > 0).mean()); neg = float((r < 0).mean())
    consistency = max(pos, neg)
    signed = (pos - neg) * consistency
    return float(clamp(signed, -1.0, 1.0)), float(clamp(consistency, 0.0, 1.0))


def _candle_pressure(df: pd.DataFrame, lookback: int = 12) -> dict[str, float]:
    """Measure body dominance and directional close location, not raw volume prediction."""
    if df is None or df.empty:
        return {"pressure": 0.0, "body_quality": 0.0, "close_location": 0.5}
    x = df.tail(lookback).copy()
    rng = (x["high"] - x["low"]).replace(0, np.nan)
    body = (x["close"] - x["open"]).abs() / rng
    loc = (x["close"] - x["low"]) / rng
    signed_body = np.sign(x["close"] - x["open"]) * body.fillna(0)
    weights = np.linspace(0.5, 1.0, len(x))
    pressure = float(np.average(signed_body.fillna(0), weights=weights)) if len(x) else 0.0
    return {
        "pressure": round(clamp(pressure, -1.0, 1.0), 4),
        "body_quality": round(clamp(float(body.fillna(0).mean()), 0.0, 1.0), 4),
        "close_location": round(clamp(float(loc.fillna(0.5).tail(3).mean()), 0.0, 1.0), 4),
    }


def _precision_engine_snapshot(
    df15: pd.DataFrame,
    df1h: pd.DataFrame,
    price: float,
    atr: float,
    rsi: float,
    vwap: float,
    ema20: float,
    ema50: float,
    direction: str,
    volume_spike: bool,
    structure: dict[str, Any],
    regime: dict[str, Any],
    derivatives: dict[str, Any],
) -> dict[str, Any]:
    """Precision gate: entry timing, trend stability, stretch and market-quality filters.

    This is deliberately a gate/diagnostic, not a promise of predictive accuracy.
    """
    try:
        adx_s = _adx_series(df1h)
        adx = float(adx_s.iloc[-1]) if not adx_s.empty else 0.0
        signed_stability, consistency = _rolling_trend_stability(df1h["close"], 20)
        cp = _candle_pressure(df15, 12)
        atr_safe = max(float(atr), price * 0.0001, 1e-12)
        stretch_vwap = abs(price - vwap) / atr_safe if vwap > 0 else 0.0
        stretch_ema = abs(price - ema20) / atr_safe if ema20 > 0 else 0.0
        trend_up = ema20 > ema50
        trend_dir = 1 if trend_up else -1
        wanted = 1 if direction in {"صعودی", "LONG", "LONG/BUY"} else -1 if direction in {"نزولی", "SHORT", "SHORT/SELL"} else 0
        trend_alignment = trend_dir * wanted if wanted else 0
        structure_score = safe_float((structure or {}).get("confirmation_score"), 50)
        regime_name = str((regime or {}).get("regime", "unknown")).lower()
        trend_regime = any(k in regime_name for k in ("trend", "bull", "bear"))
        oi_delta = safe_float((derivatives or {}).get("oi_delta"), 0)
        funding = safe_float((derivatives or {}).get("funding"), 0)

        # ADX: low trend strength is a common source of false breakout-style entries.
        adx_score = clamp((adx - 12.0) / 28.0 * 100.0, 0, 100)
        stability_score = clamp(consistency * 100.0, 0, 100)
        direction_consistency = clamp((0.5 + 0.5 * signed_stability * wanted) * 100.0, 0, 100) if wanted else 50
        stretch_penalty = 0.0
        if stretch_vwap > 2.8: stretch_penalty += min(25.0, (stretch_vwap - 2.8) * 9.0)
        if stretch_ema > 3.2: stretch_penalty += min(20.0, (stretch_ema - 3.2) * 7.0)
        rsi_penalty = 0.0
        if wanted > 0 and rsi > 74: rsi_penalty = min(18.0, (rsi - 74) * 1.8)
        if wanted < 0 and rsi < 26: rsi_penalty = min(18.0, (26 - rsi) * 1.8)
        body_score = cp["body_quality"] * 100.0
        candle_direction = cp["pressure"] * wanted
        candle_score = clamp(50.0 + candle_direction * 45.0 + (body_score - 50.0) * 0.25, 0, 100)
        derivative_alignment = 50.0
        if wanted:
            # OI confirmation is supportive only when it points with price direction; funding is a softer input.
            if wanted > 0 and oi_delta > 0: derivative_alignment += min(18.0, oi_delta * 2.0)
            if wanted < 0 and oi_delta < 0: derivative_alignment += min(18.0, abs(oi_delta) * 2.0)
            if wanted > 0 and funding < -0.0002: derivative_alignment += 5.0
            if wanted < 0 and funding > 0.0002: derivative_alignment += 5.0
        derivative_alignment = clamp(derivative_alignment, 0, 100)

        precision = (
            0.24 * adx_score
            + 0.22 * stability_score
            + 0.18 * direction_consistency
            + 0.14 * candle_score
            + 0.12 * clamp(structure_score, 0, 100)
            + 0.10 * derivative_alignment
        ) - stretch_penalty - rsi_penalty
        if trend_alignment < 0:
            precision -= 12.0
        if not trend_regime and adx < 16:
            precision -= 8.0
        precision = float(clamp(precision, 0, 100))

        hard_blocks = []
        if price <= 0 or atr <= 0: hard_blocks.append("invalid_price_or_atr")
        if adx < 11 and consistency < 0.58: hard_blocks.append("low_trend_strength")
        if stretch_vwap > 4.0 or stretch_ema > 4.5: hard_blocks.append("overextended_entry")
        if wanted and direction_consistency < 34: hard_blocks.append("directional_instability")
        return {
            "score": round(precision, 1), "adx": round(adx, 2),
            "trend_stability": round(signed_stability, 4), "consistency": round(consistency, 4),
            "direction_consistency": round(direction_consistency, 1),
            "stretch_vwap_atr": round(stretch_vwap, 2), "stretch_ema_atr": round(stretch_ema, 2),
            "candle_pressure": cp["pressure"], "body_quality": cp["body_quality"],
            "candle_score": round(candle_score, 1), "derivative_alignment": round(derivative_alignment, 1),
            "trend_alignment": trend_alignment, "hard_blocks": hard_blocks,
            "entry_timing": "GOOD" if precision >= 72 and not hard_blocks else "WAIT" if precision < 56 or hard_blocks else "CAUTIOUS",
        }
    except Exception as exc:
        LOGGER.debug("precision engine failed: %s", exc)
        return {"score": 50.0, "entry_timing": "CAUTIOUS", "hard_blocks": [], "error": str(exc)}


def _friction_adjusted_rr(entry: float, sl: float, tp: float) -> float:
    risk = abs(entry - sl)
    reward = abs(tp - entry)
    friction = max(entry * TOTAL_ENTRY_BUFFER, 1e-12)
    return float(reward / max(risk + friction, 1e-12))



# ============================================================
# TITAN V9 — NEURAL SYNAPSE (central nervous system)
# Connects: TF scores · structure · regime · confluence · precision ·
# patterns · forecast path · derivatives · AI ensemble · DQ · ladder ·
# calibration · portfolio. Produces one coherent decision + confidence.
# Analysis-only. Never invents edge — only fuses existing evidence.
# ============================================================

class TitanNeuralSynapseV9:
    """Advanced multi-layer fusion with explainable weighted synapses."""

    # Layer weights (sum ≈ 1.0) — tuned for reliability over aggressiveness
    W = {
        # V28 tuned: stronger TF spine + precision + calibration for reliable edges
        "tf_spine": 0.20,       # multi-TF weighted score
        "structure": 0.11,      # market structure HH/HL
        "regime": 0.08,         # trend/vol regime
        "confluence": 0.11,     # multi-factor confluence
        "precision": 0.12,      # entry timing / ADX / stretch
        "pattern": 0.06,        # chart patterns
        "forecast": 0.07,       # probabilistic path (self-weighted)
        "derivatives": 0.08,    # funding / OI / L-S / taker
        "ai": 0.09,             # AI ensemble
        "calibration": 0.08,    # historical success calibration
    }

    def _side_from_score(self, sc: float) -> str:
        # Tuned V28: 54/46 — fewer missed edges than 56/44, still avoids noise
        if sc >= 54:
            return "LONG"
        if sc <= 46:
            return "SHORT"
        return "WAIT"

    def _tf_vector(self, tf_scores: dict) -> tuple[float, str, float]:
        if not tf_scores:
            return 50.0, "WAIT", 0.0
        weights = {"15m": 0.18, "1h": 0.30, "4h": 0.28, "1d": 0.24}  # V28 balanced actionable
        keys = [k for k in weights if k in tf_scores]
        if not keys:
            vals = list(tf_scores.values())
            avg = float(sum(vals) / len(vals))
            return avg, self._side_from_score(avg), abs(avg - 50.0)
        wsum = sum(weights[k] for k in keys)
        avg = sum(safe_float(tf_scores[k], 50) * weights[k] for k in keys) / max(wsum, 1e-9)
        # agreement among TFs
        sides = [self._side_from_score(safe_float(tf_scores[k], 50)) for k in keys]
        maj = max(set(sides), key=sides.count)
        agree = sides.count(maj) / len(sides)
        return float(avg), maj, float(agree * abs(avg - 50.0))

    def _pattern_signal(self, patterns: dict) -> tuple[float, str]:
        primary = (patterns or {}).get("primary") or {}
        if not primary:
            return 50.0, "WAIT"
        bias = str((primary.get("guide") or {}).get("bias", "خنثی"))
        conf = safe_float(primary.get("confidence"), 50) / 100.0
        if bias == "صعودی":
            return 50.0 + 18.0 * conf, "LONG"
        if bias == "نزولی":
            return 50.0 - 18.0 * conf, "SHORT"
        return 50.0, "WAIT"

    def _forecast_signal(self, forecast: dict, path_stats: dict) -> tuple[float, str]:
        if not forecast or not forecast.get("ok"):
            return 50.0, "WAIT"
        overall = str(forecast.get("overall_bias", "خنثی"))
        move = safe_float(forecast.get("expected_move_pct"), 0)
        strength = safe_float(forecast.get("path_strength"), 0)
        scale = safe_float((path_stats or {}).get("weight_scale"), 0.35)
        # damp by historical path accuracy
        tilt = float(np.clip(move * 2.5 + strength * 0.15, -18, 18)) * scale
        sc = 50.0 + tilt
        side = "LONG" if overall == "صعودی" and sc >= 53 else "SHORT" if overall == "نزولی" and sc <= 47 else "WAIT"
        return float(clamp(sc, 5, 95)), side

    def _deriv_signal(self, derivatives: dict, wanted_hint: int = 0) -> tuple[float, str]:
        sc = 50.0
        funding = derivatives.get("funding_value")
        oi_d = safe_float(derivatives.get("oi_delta"), 0)
        ls_ratio = safe_float(derivatives.get("long_short_ratio"), 1.0)
        taker_buy = safe_float(derivatives.get("taker_buy_pct"), 50)
        if funding is not None:
            f = safe_float(funding, 0)
            # extreme funding is contrarian
            if f >= 0.06:
                sc -= 6
            elif f <= -0.06:
                sc += 6
            elif f >= 0.025:
                sc -= 2.5
            elif f <= -0.025:
                sc += 2.5
        if oi_d > 1.5:
            sc += 3.0 if wanted_hint >= 0 else -3.0
        elif oi_d < -1.5:
            sc -= 2.0 if wanted_hint >= 0 else 2.0
        # crowding
        if ls_ratio >= 1.6:
            sc -= 5  # long crowded → short bias
        elif ls_ratio <= 0.65:
            sc += 5
        # taker flow
        sc += float(np.clip((taker_buy - 50) * 0.12, -5, 5))
        sc = float(clamp(sc, 10, 90))
        return sc, self._side_from_score(sc)

    def _ai_signal(self, fusion: dict, ai_opinions: dict) -> tuple[float, str, float]:
        maj = str((fusion or {}).get("ai_majority") or "WAIT")
        agree = safe_float((fusion or {}).get("ai_agreement"), 0)
        if maj not in {"LONG", "SHORT", "WAIT"}:
            # parse from opinions if needed
            votes = []
            for key in ("gemini", "openai", "grok", "claude", "deepseek", "internal"):
                text = str((ai_opinions or {}).get(key) or "")
                if not text:
                    continue
                v = extract_structured_ai_vote(text)
                votes.append(v.get("side", "WAIT"))
            if votes:
                maj = max(set(votes), key=votes.count)
                agree = votes.count(maj) / len(votes) * 100.0
        if maj == "LONG":
            sc = 50.0 + min(28.0, agree * 0.28)
        elif maj == "SHORT":
            sc = 50.0 - min(28.0, agree * 0.28)
        else:
            sc = 50.0
        return float(clamp(sc, 15, 85)), maj if maj in {"LONG", "SHORT", "WAIT"} else "WAIT", float(agree)

    def fuse(self, *, tf_scores: dict, structure: dict, regime: dict, confluence: dict,
             precision: dict, patterns: dict, forecast: dict, path_stats: dict,
             derivatives: dict, fusion: dict, ai_opinions: dict,
             data_quality: dict, ladder: dict, calib: dict,
             quant_bias: str, quant_score: float) -> dict:
        """Full neural fuse → side, confidence, layer map, vetoes."""
        layers: dict[str, Any] = {}
        reasons: list[str] = []
        vetoes: list[str] = []

        tf_sc, tf_side, tf_agree_mag = self._tf_vector(tf_scores or {})
        layers["tf_spine"] = {"score": round(tf_sc, 1), "side": tf_side, "weight": self.W["tf_spine"]}

        struct_bias = str((structure or {}).get("bias", "خنثی"))
        struct_conf = safe_float((structure or {}).get("confirmation_score"), 50)
        if struct_bias == "صعودی":
            st_sc = 50 + min(22, struct_conf * 0.25)
            st_side = "LONG"