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