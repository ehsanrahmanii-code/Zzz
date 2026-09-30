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

