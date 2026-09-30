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
            "decision": x.get("decision_tag","WAIT"),
            "side": o.get("candidate_side","WAIT"),
            "state": o.get("opportunity_state","NO_EDGE"),
            "score": o.get("opportunity_score",0),
            "margin": o.get("margin",0),
            "ai": o.get("ai",{}),
            "learning": o.get("learning",{}),
            "reasons": o.get("reason_tree",[]),
            "vetoes": o.get("hard_vetoes",[]),
        })
    rows.sort(key=lambda r: safe_float(r.get("score"),0), reverse=True)
    return jsonify({
        "ok": True,
        "version": V22_VERSION,
        "rows": rows,
        "summary": {
            "ready": sum(1 for r in rows if r["decision"] in {"LONG","SHORT"}),
            "early": sum(1 for r in rows if str(r["state"]).startswith("EARLY")),
            "watch": sum(1 for r in rows if str(r["state"]).startswith("WATCH")),
            "no_edge": sum(1 for r in rows if r["state"] == "NO_EDGE"),
        },
        "macro": macro or {},
    })



# ============================================================
# TITAN V29 — EVIDENCE FUSION / "MAGIC" ARBITRATOR
# ------------------------------------------------------------
# This is deliberately NOT a mystical predictor. "Magic" means that the
# engine combines independent evidence, regime-aware weights, uncertainty,
# contradiction detection, hysteresis and hard data gates in one auditable
# final pass. It can surface a strong opportunity hidden by a soft WAIT, but
# it cannot manufacture a trade from missing data or from AI text alone.
# ============================================================
V29_VERSION = "TITAN-V29-EVIDENCE-FUSION-MAGIC"
V29_MIN_DQ = 52.0
V29_MIN_QUALITY = 54.0
V29_MIN_RR = 1.08
V29_PROMOTE_SCORE = 0.34
V29_EARLY_SCORE = 0.25
V29_WATCH_SCORE = 0.18
V29_MIN_INDEPENDENT = 3
V29_AI_MAX_WEIGHT = 0.12
V29_HARD_CONTRADICTION = 0.82


def _v29_side_value(value: Any, side: str, positive_words=(), negative_words=()) -> float:
    """Return signed evidence in [-1,1] without guessing on unknown values."""
    if isinstance(value, (int, float)):
        return clamp(float(value), -1.0, 1.0)
    text = str(value or "").strip().lower()
    if not text:
        return 0.0
    if side == "LONG":
        if text in {"صعودی", "bull", "bullish", "up", "long", "buy", "strong_long"} or any(w in text for w in positive_words):
            return 1.0
        if text in {"نزولی", "bear", "bearish", "down", "short", "sell", "strong_short"} or any(w in text for w in negative_words):
            return -1.0
    else:
        if text in {"نزولی", "bear", "bearish", "down", "short", "sell", "strong_short"} or any(w in text for w in positive_words):
            return 1.0
        if text in {"صعودی", "bull", "bullish", "up", "long", "buy", "strong_long"} or any(w in text for w in negative_words):
            return -1.0
    return 0.0


class TitanEvidenceFusionV29:
    """Final auditable evidence arbiter.

    Core principles:
      * no evidence is treated as neutral, never as bullish/bearish;
      * AI is capped and cannot manufacture a direction;
      * correlated indicators are grouped so five indicators do not count as
        five independent confirmations;
      * regime changes weights rather than changing the underlying evidence;
      * a direction needs both edge and independent confirmation;
      * confidence is evidence quality, not a guaranteed probability.
    """

    def _regime_profile(self, item: dict[str, Any]) -> tuple[str, dict[str, float]]:
        reg = str(((item.get("edge") or {}).get("regime") or {}).get("regime") or "").lower()
        if any(k in reg for k in ("trend", "bull", "bear", "uptrend", "downtrend")):
            return "TREND", {"tf":1.10,"structure":1.08,"flow":1.00,"forecast":0.92,"precision":0.90,"neural":1.05,"ai":0.90}
        if any(k in reg for k in ("range", "sideway", "mean")):
            return "RANGE", {"tf":0.78,"structure":0.88,"flow":1.00,"forecast":0.75,"precision":1.15,"neural":0.82,"ai":0.82}
        if any(k in reg for k in ("transition", "volatile", "chaos")):
            return "TRANSITION", {"tf":0.92,"structure":0.92,"flow":1.10,"forecast":0.70,"precision":1.05,"neural":0.78,"ai":0.72}
        return "NEUTRAL", {"tf":1.0,"structure":1.0,"flow":1.0,"forecast":0.9,"precision":1.0,"neural":0.9,"ai":0.82}

    def _build(self, item: dict[str, Any], side: str) -> dict[str, Any]:
        tf = item.get("tf_scores") or item.get("tfs") or {}
        edge = item.get("edge") or {}
        structure = edge.get("structure") or {}
        regime = edge.get("regime") or {}
        precision = item.get("precision") or edge.get("precision") or {}
        neural = (item.get("neural_v9") or (item.get("fusion") or {}).get("neural_v9") or {})
        forecast = item.get("candle_forecast") or {}
        derivatives = item.get("derivatives") or {}
        # Production payload also exposes derivatives at top level. Merge them so
        # V29 never loses live flow evidence simply because the transport shape changed.
        if not derivatives:
            derivatives = {k: item.get(k) for k in ("long_short_ratio","taker_buy_pct","taker_sell_pct","funding","coinglass_funding","oi_delta") if item.get(k) is not None}
        if "funding" not in derivatives and item.get("coinglass_funding") is not None:
            derivatives["funding"] = item.get("coinglass_funding")
        ai = edge.get("ai") or {}
        fusion = item.get("fusion") or {}
        profile, mult = self._regime_profile(item)

        ev=[]
        def add(name, group, raw, weight, quality=1.0, note=""):
            ev.append({"name":name,"group":group,"raw":clamp(raw,-1,1),"weight":max(0.0,weight),"quality":clamp(quality,0,1),"note":note})

        # Multi-timeframe spine: one independent group, not four votes.
        vals=[]
        tf_used=0.0
        for tf_name, w in (("15m",.16),("1h",.30),("4h",.30),("1d",.24)):
            if tf_name in tf:
                vals.append((safe_float(tf.get(tf_name),50)-50)/50*w)
                tf_used += w
        tf_edge=sum(vals)/max(tf_used,1e-9) if vals else 0.0
        add("multi_tf","tf",tf_edge,.23*mult["tf"],min(1,tf_used/.99),f"frames={len(vals)}")

        sb=str(structure.get("bias") or "")
        sc=clamp(safe_float(structure.get("confirmation_score"),50),0,100)
        st=_v29_side_value(sb,side)
        add("structure","structure",st*((sc-50)/50 if sc>=50 else 0.35*((sc-50)/50)),.17*mult["structure"],sc/100,sb or "neutral")

        # Flow/derivatives group. Use explicit directional ratios when available.
        ls=safe_float(derivatives.get("long_short_ratio"),0)
        taker_buy=safe_float(derivatives.get("taker_buy_pct"),50)
        funding=safe_float(derivatives.get("funding"),0)
        flow=0.0
        flow_parts=0
        if ls>0:
            # ratio >1 is long-heavy; map smoothly and symmetrically.
            flow += clamp(math.log(ls),-1,1); flow_parts += 1
        if "taker_buy_pct" in derivatives:
            flow += clamp((taker_buy-50)/20,-1,1); flow_parts += 1
        if "funding" in derivatives:
            # Positive funding is crowded long; therefore mildly bearish, and vice versa.
            flow += clamp(-funding/0.0015,-1,1); flow_parts += 1
        flow = flow/max(flow_parts,1)
        add("market_flow","flow",flow,.13*mult["flow"],min(1,flow_parts/3),f"parts={flow_parts}")

        # Precision/entry location group.
        timing=str(precision.get("entry_timing") or "").upper()
        pscore=clamp(safe_float(precision.get("score"),50),0,100)
        pe=(pscore-50)/50
        if timing in {"AVOID","DANGER","LATE"}: pe*=0.55
        add("entry_precision","precision",pe,.14*mult["precision"],pscore/100,timing or "unknown")

        # Forecast group: only count it when an actual directional path exists.
        fb=str(forecast.get("overall_bias") or "")
        fs=clamp(safe_float(forecast.get("path_strength"),0)/40,0,1)
        add("future_path","forecast",_v29_side_value(fb,side)*fs,.10*mult["forecast"],fs,fb or "neutral")

        # Neural group.
        ns=str(neural.get("side") or "WAIT").upper()
        nc=clamp(safe_float(neural.get("confidence"),0)/100,0,1)
        add("neural","neural",(1 if ns==side else -1 if ns in {"LONG","SHORT"} else 0)*nc,.13*mult["neural"],nc,ns)

        # AI group is deliberately capped. AI text can enrich evidence but cannot
        # override market data or hard safety gates.
        am=str(ai.get("majority") or ai.get("ai_majority") or fusion.get("ai_majority") or "WAIT").upper()
        aa=clamp(safe_float(ai.get("agreement") or ai.get("majority_agreement") or fusion.get("ai_agreement"),0)/100,0,1)
        add("ai_ensemble","ai",(1 if am==side else -1 if am in {"LONG","SHORT"} else 0)*aa,V29_AI_MAX_WEIGHT*mult["ai"],aa,am)

        total_w=sum(x["weight"] for x in ev)
        weighted=sum(x["raw"]*x["weight"]*x["quality"] for x in ev)
        score=weighted/max(total_w,1e-9)
        # Contradiction is group-level, so correlated indicators cannot inflate it.
        active=[x for x in ev if abs(x["raw"])>=0.22 and x["quality"]>=0.45]
        support=[x for x in active if x["raw"]>0]
        oppose=[x for x in active if x["raw"]<0]
        contradiction=(min(len(support),len(oppose))/max(len(active),1)) if active else 0.0
        independent_support=len({x["group"] for x in support})
        independent_oppose=len({x["group"] for x in oppose})
        margin=abs(score)
        quality=clamp(safe_float(item.get("signal_quality"),50),0,100)
        dq=clamp(safe_float((item.get("data_quality") or {}).get("score") or (fusion.get("data_quality") or {}).get("score"),50),0,100)
        rr= safe_float(item.get("effective_rr_tp1") or item.get("rr_tp1"),0)
        hard=[]
        if dq < V29_MIN_DQ: hard.append("DATA_QUALITY")
        if rr > 0 and rr < V29_MIN_RR: hard.append("RR_LOW")
        if price_invalid := (safe_float(str(item.get("price")).replace(",",""),0) <= 0): hard.append("PRICE_INVALID")
        if contradiction>=V29_HARD_CONTRADICTION: hard.append("EVIDENCE_CONTRADICTION")
        return {
            "version":V29_VERSION,"regime":profile,"score":round(score,4),
            "strength":round(margin*100,1),"independent_support":independent_support,
            "independent_oppose":independent_oppose,"contradiction":round(contradiction,3),
            "quality":round(quality,1),"data_quality":round(dq,1),"rr":round(rr,2),
            "hard_blocks":list(dict.fromkeys(hard)),"evidence":ev,
            "support_groups":sorted({x["group"] for x in support}),
            "oppose_groups":sorted({x["group"] for x in oppose}),
            "regime": profile,
        }

    def evaluate(self,item:dict[str,Any])->dict[str,Any]:
        long=self._build(item,"LONG"); short=self._build(item,"SHORT")
        # Choose the side by absolute evidence edge. Near ties remain neutral.
        side="LONG" if long["score"]-short["score"]>=0.10 else "SHORT" if short["score"]-long["score"]>=0.10 else "WAIT"
        chosen=long if side=="LONG" else short if side=="SHORT" else {"score":0,"strength":0,"independent_support":0,"hard_blocks":list(dict.fromkeys(long["hard_blocks"]+short["hard_blocks"])),"contradiction":max(long["contradiction"],short["contradiction"]),"quality":max(long["quality"],short["quality"]),"data_quality":min(long["data_quality"],short["data_quality"]),"rr":max(long["rr"],short["rr"]),"support_groups":[],"oppose_groups":[]}
        current=str(item.get("decision_tag") or "WAIT").upper()
        candidate=side
        # Independent evidence is the key anti-noise mechanism.
        promote=(
            candidate in {"LONG","SHORT"}
            and chosen["score"]>=V29_PROMOTE_SCORE
            and chosen["independent_support"]>=V29_MIN_INDEPENDENT
            and chosen["quality"]>=V29_MIN_QUALITY
            and chosen["data_quality"]>=V29_MIN_DQ
            and chosen["rr"]>=V29_MIN_RR
            and not chosen["hard_blocks"]
        )
        early=(candidate in {"LONG","SHORT"} and chosen["score"]>=V29_EARLY_SCORE and chosen["independent_support"]>=2 and not chosen["hard_blocks"])
        watch=(candidate in {"LONG","SHORT"} and chosen["score"]>=V29_WATCH_SCORE and chosen["independent_support"]>=2)
        if promote: state="MAGIC_READY"
        elif early: state="MAGIC_EARLY_"+candidate
        elif watch: state="MAGIC_WATCH_"+candidate
        else: state="MAGIC_NO_EDGE"
        confidence=clamp(50 + chosen["strength"]*0.42 + max(0,chosen["independent_support"]-1)*5 - chosen["contradiction"]*28,0,96)
        return {"version":V29_VERSION,"candidate":candidate,"current":current,"promote":promote,"state":state,"confidence":round(confidence,1),"long":long,"short":short,"chosen":chosen,"explanation":[
            f"رژیم: {chosen.get('regime','—')}",
            f"لبه خالص: {chosen.get('strength',0):.1f}%",
            f"شواهد مستقل هم‌جهت: {chosen.get('independent_support',0)} گروه",
            f"تناقض گروهی: {chosen.get('contradiction',0)*100:.1f}%",
            f"اعتماد شواهد: {confidence:.1f}/100",
            "AI فقط نقش تقویتی محدود دارد و جایگزین داده بازار نیست.",
        ]}


TITAN_MAGIC_V29 = TitanEvidenceFusionV29()

# Preserve V22 as the complete prior pipeline, then put one transparent final
# arbitration layer above it. This avoids touching the dashboard contract.
_analyze_asset_v22 = analyze_asset

def analyze_asset(symbol: str, btc_trend: str) -> Optional[dict[str, Any]]:
    item = _analyze_asset_v22(symbol, btc_trend)
    if not item:
        return None
    try:
        magic = TITAN_MAGIC_V29.evaluate(item)
        item["magic_v29"] = magic
        item.setdefault("fusion", {})["magic_v29"] = magic
        item["magic_confidence"] = magic.get("confidence", 0)
        item["magic_state"] = magic.get("state", "MAGIC_NO_EDGE")

        current=str(item.get("decision_tag") or "WAIT").upper()
        candidate=str(magic.get("candidate") or "WAIT").upper()
        chosen=magic.get("chosen") or {}
        # A promotion is allowed only for a current WAIT and only when V29 has
        # enough independent evidence. If levels cannot be made valid, it stays WAIT.
        if current=="WAIT" and magic.get("promote") and candidate in {"LONG","SHORT"}:
            try:
                price=_v12_parse_price(item.get("price"))
                sl,tp1,tp2=_v12_rebuild_directional_levels(item,candidate)
                chk=_v12_level_integrity(price,sl,tp1,tp2,candidate)
                if chk.get("ok") and safe_float(chk.get("rr1"),0)>=V29_MIN_RR:
                    item["stop_loss"]=smart_format(sl); item["tp1"]=smart_format(tp1); item["tp2"]=smart_format(tp2)
                    item["effective_rr_tp1"]=chk["rr1"]; item["effective_rr_tp2"]=chk["rr2"]
                    item["rr_tp1"]=chk["rr1"]; item["rr_tp2"]=chk["rr2"]
                    item["decision_tag"]=candidate
                    item["bias"]="صعودی" if candidate=="LONG" else "نزولی"
                    item["signal_tag"]="V29 MAGIC READY"
                    item["entry_mode"]="EARLY"
                    item["signal_quality"]=max(safe_float(item.get("signal_quality"),50),min(86,safe_float(chosen.get("quality"),50)+8))
                    magic["applied"]=True
                else:
                    magic["applied"]=False
                    magic["explanation"].append("ارتقای V29 لغو شد: سطوح نهایی یا RR معتبر نبود.")
            except Exception as exc:
                magic["applied"]=False
                magic["explanation"].append("ارتقای V29 به‌دلیل خطای کنترل سطوح انجام نشد.")
                LOGGER.debug("V29 promotion failed for %s: %s",symbol,exc)
        elif current in {"LONG","SHORT"}:
            # Existing directional decisions are never flipped by the magic layer.
            magic["applied"]=False
            magic["explanation"].append("تصمیم جهت‌دار موجود حفظ شد؛ V29 فقط آن را ممیزی کرد.")
        else:
            magic["applied"]=False

        # Final consistency fields for dashboard/API consumers.
        item["canonical_decision"]={**(item.get("canonical_decision") or {}),"decision":item.get("decision_tag","WAIT"),"bias":item.get("bias","خنثی"),"magic_confidence":magic.get("confidence",0),"magic_state":magic.get("state")}
        item["decision_audit_v29"]={
            "decision":item.get("decision_tag","WAIT"),"candidate":candidate,
            "state":magic.get("state"),"confidence":magic.get("confidence",0),
            "independent_support":chosen.get("independent_support",0),
            "contradiction":chosen.get("contradiction",0),
            "hard_blocks":chosen.get("hard_blocks",[]),
            "explanation":magic.get("explanation",[]),
        }
        return item
    except Exception as exc:
        LOGGER.exception("V29 magic arbitration failed for %s: %s",symbol,exc)
        item["magic_v29"]={"version":V29_VERSION,"state":"ERROR","confidence":0,"error":"internal arbitration failure"}
        return item

