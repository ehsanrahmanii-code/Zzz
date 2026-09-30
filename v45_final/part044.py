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
            "ai": {"majority": ai_side, "agreement": round(ai_agree, 1), "bonus": round(ai_bonus, 2)},
            "learning": {
                "chosen_side": prof,
                "global": global_prof,
                "threshold": round(promote_threshold, 1),
            },
            "persistence": persistence,
            "hard_vetoes": list(dict.fromkeys(hard_vetoes)),
            "promoted": promoted,
            "reason_tree": reasons,
            "balance": {
                "actionable": action in {"LONG", "SHORT"},
                "opportunity_visible": state != "NO_EDGE",
                "false_signal_protection": bool(hard_vetoes or not promoted),
            },
        }


class TitanDecisionAuditV22:
    """Persistent decision ledger and self-review metrics."""

    def record(self, item: dict[str, Any], opp: dict[str, Any]) -> None:
        try:
            now = time.time()
            symbol = str(item.get("symbol") or "")
            with DB_LOCK, db_conn() as con:
                recent = con.execute(
                    "SELECT 1 FROM decision_journal_v22 WHERE symbol=? AND created_at>? LIMIT 1",
                    (symbol, now - V22_JOURNAL_COOLDOWN),
                ).fetchone()
                if recent:
                    return
                fusion = item.get("fusion") or {}
                con.execute(
                    "INSERT INTO decision_journal_v22("
                    "created_at,symbol,decision,candidate_side,opportunity_state,opportunity_score,"
                    "trust,quality,ai_majority,ai_agreement,regime,reason_json,outcome"
                    ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        now, symbol, str(item.get("decision_tag") or "WAIT"),
                        opp.get("candidate_side","WAIT"),
                        opp.get("opportunity_state","NO_EDGE"),
                        safe_float(opp.get("opportunity_score"),0),
                        safe_float((item.get("trust_max_v21") or {}).get("trust"),0),
                        safe_float(item.get("signal_quality"),0),
                        str((opp.get("ai") or {}).get("majority","WAIT")),
                        safe_float((opp.get("ai") or {}).get("agreement"),0),
                        str((opp.get("regime") or {}).get("regime") or (item.get("trust_max_v21") or {}).get("regime",{}).get("regime","")),
                        json.dumps({"reasons": opp.get("reason_tree",[]), "edges": opp.get("edges",{}), "learning": opp.get("learning",{})}, ensure_ascii=False),
                        "PENDING",
                    ),
                )
        except Exception as exc:
            LOGGER.debug("V22 journal write failed %s: %s", item.get("symbol"), exc)

    def summary(self) -> dict[str, Any]:
        try:
            with DB_LOCK, db_conn() as con:
                rows = con.execute(
                    "SELECT opportunity_state,decision,outcome,opportunity_score,trust,quality,ai_majority,ai_agreement "
                    "FROM decision_journal_v22 ORDER BY created_at DESC LIMIT 1000"
                ).fetchall()
            total = len(rows)
            ready = sum(1 for r in rows if str(r["decision"]) in {"LONG","SHORT"})
            visible = sum(1 for r in rows if str(r["opportunity_state"]) != "NO_EDGE")
            pending = sum(1 for r in rows if str(r["outcome"]) == "PENDING")
            return {
                "journal_rows": total,
                "directional_decisions": ready,
                "opportunities_visible": visible,
                "pending_reviews": pending,
                "coverage_pct": round(visible / total * 100, 1) if total else 0.0,
            }
        except Exception:
            return {"journal_rows": 0, "directional_decisions": 0, "opportunities_visible": 0, "pending_reviews": 0, "coverage_pct": 0.0}


TITAN_LEARNING_V22 = TitanLearningEngineV22()
TITAN_OPPORTUNITY_V22 = TitanOpportunityEngineV22()
TITAN_AUDIT_V22 = TitanDecisionAuditV22()


_analyze_asset_v21 = analyze_asset


def analyze_asset(symbol: str, btc_trend: str) -> Optional[dict[str, Any]]:
    item = _analyze_asset_v21(symbol, btc_trend)
    if not item:
        return None
    try:
        opp = TITAN_OPPORTUNITY_V22.evaluate(item, TITAN_LEARNING_V22)

        # If V22 legitimately promotes a WAIT, rebuild levels before exposing it.
        if opp.get("promoted") and opp.get("action") in {"LONG", "SHORT"} and item.get("decision_tag") == "WAIT":
            sl, tp1, tp2 = _v12_rebuild_directional_levels(item, opp["action"])
            price = _v12_parse_price(item.get("price"))
            chk = _v12_level_integrity(price, sl, tp1, tp2, opp["action"])
            if chk.get("ok"):
                item["stop_loss"] = smart_format(sl)
                item["tp1"] = smart_format(tp1)
                item["tp2"] = smart_format(tp2)
                item["effective_rr_tp1"] = chk["rr1"]
                item["effective_rr_tp2"] = chk["rr2"]
                item["rr_tp1"] = chk["rr1"]
                item["rr_tp2"] = chk["rr2"]
                item["decision_tag"] = opp["action"]
                item["bias"] = "صعودی" if opp["action"] == "LONG" else "نزولی"
                item["signal_tag"] = "V22 ADAPTIVE OPPORTUNITY"
                item["entry_mode"] = "EARLY"
                item.setdefault("fusion", {})["v22_promotion"] = True
                opp["level_integrity"] = chk
            else:
                opp["promoted"] = False
                opp["action"] = "WAIT"
                opp["level_integrity"] = chk
                opp["reason_tree"].append("ارتقا لغو شد چون SL/TP/RR نهایی معتبر نبود")

        # If V22 does not promote, preserve the real V21 decision but expose
        # the opportunity state so a strong setup is not hidden as a blank WAIT.
        item["opportunity_v22"] = opp
        item.setdefault("fusion", {})["opportunity_v22"] = opp
        item["decision_audit_v22"] = {
            "decision": item.get("decision_tag","WAIT"),
            "core_decision": opp.get("core_action","WAIT"),
            "candidate_side": opp.get("candidate_side","WAIT"),
            "state": opp.get("opportunity_state","NO_EDGE"),
            "score": opp.get("opportunity_score",0),
            "margin": opp.get("margin",0),
            "reasons": opp.get("reason_tree",[]),
            "learning": opp.get("learning",{}),
            "ai": opp.get("ai",{}),
        }
        item["opportunity_score"] = opp.get("opportunity_score",0)
        item["opportunity_state"] = opp.get("opportunity_state","NO_EDGE")
        item["opportunity_side"] = opp.get("candidate_side","WAIT")
        item["decision_reason"] = " | ".join(opp.get("reason_tree",[])[:12])

        # Final integrity: bias ↔ decision_tag ↔ grade stay coherent for the UI
        dec = str(item.get("decision_tag") or "WAIT").upper()
        if dec == "LONG":
            item["bias"] = "صعودی"
        elif dec == "SHORT":
            item["bias"] = "نزولی"
        elif dec == "WAIT":
            if item.get("bias") in {"صعودی", "نزولی"} and safe_float(item.get("opportunity_score"), 0) < 48:
                item["bias"] = "خنثی"
        # Ensure grade string is always present for templates
        if not item.get("grade"):
            sg = item.get("signal_grade") or {}
            item["grade"] = sg.get("grade") or "—"
            item["trust_index"] = item.get("trust_index") or sg.get("trust_index") or 0
        # Clamp display probability
        try:
            item["success_probability"] = round(float(clamp(safe_float(item.get("success_probability"), 50), 1, 95)), 1)
        except Exception:
            item["success_probability"] = 50.0
        item["param_version"] = TITAN_PARAM_VERSION

        TITAN_AUDIT_V22.record(item, opp)
        return item
    except Exception as exc:
        LOGGER.exception("V22 adaptive opportunity failed for %s: %s", symbol, exc)
        item["opportunity_v22"] = {
            "version": V22_VERSION,
            "action": item.get("decision_tag","WAIT"),
            "opportunity_state": "UNKNOWN",
            "opportunity_score": 0,
            "reason_tree": ["V22 خطا داد؛ تصمیم هسته بدون تغییر حفظ شد"],
        }
        return item


@app.get("/api/trust-max")
def api_trust_max():
    data, _summary, _macro = _fast_market_snapshot()
    return jsonify({
        "ok": True,
        "version": V22_VERSION,
        "summary": TITAN_AUDIT_V22.summary(),
        "learning": TITAN_LEARNING_V22.global_profile(),
        "items": [
            {
                "symbol": x.get("symbol"),
                "decision": x.get("decision_tag","WAIT"),
                "opportunity": x.get("opportunity_v22") or {},
                "audit": x.get("decision_audit_v22") or {},
            }
            for x in (data or [])
        ],
    })


@app.get("/api/opportunities")
def api_v22_opportunities():
    data, _summary, macro = _fast_market_snapshot()
    rows = []
    for x in data or []:
        o = x.get("opportunity_v22") or {}
        rows.append({
            "symbol": x.get("symbol"),