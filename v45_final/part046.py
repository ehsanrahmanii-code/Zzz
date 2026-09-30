# ============================================================
# TITAN V30 — DEEP CONSENSUS / MARKET DEBATE / ADAPTIVE DECISION CORE
# ------------------------------------------------------------
# V30 is a second-stage meta-arbiter. It does not pretend that an AI model
# can predict price with certainty. It makes the existing stack compete in
# an auditable debate: trend, structure, flow, volatility, forecast, neural,
# precision, BTC context and AI. Correlated evidence is compressed into
# families; missing/stale evidence is penalized rather than guessed.
# ============================================================
V30_VERSION = "TITAN-V30-DEEP-CONSENSUS"
V30_MIN_DATA = 58.0
V30_MIN_QUALITY = 56.0
V30_MIN_READY = 0.30
V30_MIN_EARLY = 0.20
V30_MIN_WATCH = 0.12
V30_MAX_AI = 0.10
V30_DEMOTE_EDGE = -0.30
V30_DEMOTE_OPPOSITION = 3


def _v30_num(v, default=0.0):
    try:
        if v is None or v == "":
            return float(default)
        return float(str(v).replace("%", "").replace(",", "").strip())
    except Exception:
        return float(default)


def _v30_direction(v):
    t=str(v or "").strip().lower()
    if t in {"long","bull","bullish","up","صعودی","buy","strong_long"}: return "LONG"
    if t in {"short","bear","bearish","down","نزولی","sell","strong_short"}: return "SHORT"
    return "WAIT"


class TitanDeepConsensusV30:
    """Adaptive, auditable final decision debate.

    Important design rule: V30 can *remove* a weak directional decision when
    independent evidence strongly contradicts it, but it never flips LONG to
    SHORT (or vice versa) merely because a model says so. A fresh evaluation
    must establish the opposite side before a later scan can select it.
    """

    TF_W = {"15m": .14, "1h": .31, "4h": .32, "1d": .23}

    def _regime(self, item):
        reg=str(((item.get("edge") or {}).get("regime") or {}).get("regime") or "").lower()
        if any(x in reg for x in ("trend","bull","bear","uptrend","downtrend")):
            return "TREND", {"tf":1.12,"structure":1.12,"flow":1.02,"vol":.90,"forecast":.95,"neural":1.05,"precision":.92,"btc":1.00}
        if any(x in reg for x in ("range","sideway","mean")):
            return "RANGE", {"tf":.80,"structure":.90,"flow":1.02,"vol":1.08,"forecast":.78,"neural":.84,"precision":1.15,"btc":.88}
        if any(x in reg for x in ("transition","volatile","chaos")):
            return "TRANSITION", {"tf":.88,"structure":.88,"flow":1.12,"vol":1.12,"forecast":.70,"neural":.78,"precision":1.06,"btc":1.02}
        return "NEUTRAL", {k:1.0 for k in ("tf","structure","flow","vol","forecast","neural","precision","btc")}

    def _flow(self, item, side):
        # V29 expected a nested derivatives dict, but the production item also
        # exposes these fields at top level. V30 intentionally supports both.
        d=item.get("derivatives") or {}
        def get(k, default=None):
            if k in d: return d.get(k)
            if k == "funding" and item.get("coinglass_funding") is not None: return item.get("coinglass_funding")
            return item.get(k, default)
        parts=[]
        ls=_v30_num(get("long_short_ratio"),0)
        if ls>0:
            e=clamp(math.log(ls),-1,1)
            parts.append(e)
        if get("taker_buy_pct") is not None:
            parts.append(clamp((_v30_num(get("taker_buy_pct"),50)-50)/20,-1,1))
        if get("funding") is not None:
            # crowded positive funding is mildly bearish; negative funding mildly bullish
            parts.append(clamp(-_v30_num(get("funding"),0)/0.0015,-1,1))
        oi=_v30_num(get("oi_delta"),0)
        if oi:
            parts.append(clamp(oi/6,-1,1))
        e=sum(parts)/len(parts) if parts else 0.0
        return e if side=="LONG" else -e, min(1,len(parts)/4), parts

    def _tf(self,item,side):
        tf=item.get("tf_scores") or item.get("tfs") or {}
        vals=[]; used=0
        for k,w in self.TF_W.items():
            if k not in tf: continue
            e=clamp((_v30_num(tf.get(k),50)-50)/50,-1,1)
            vals.append((e,w)); used+=1
        if not vals: return 0.0,0.0,{"frames":0,"coherence":0}
        total_w=sum(w for _,w in vals)
        signed=sum(e*w for e,w in vals)/max(total_w,1e-9)
        signs=[1 if e>.08 else -1 if e<-.08 else 0 for e,_ in vals]
        active=[x for x in signs if x]
        coherence=max(active.count(1),active.count(-1))/len(active) if active else .35
        return (signed if side=="LONG" else -signed), min(1,used/4), {"frames":used,"coherence":round(coherence,3),"signed":round(signed,3)}

    def _build_side(self,item,side,reg,mult):
        ev=[]
        def add(name, family, edge, weight, quality, source):
            ev.append({"name":name,"family":family,"edge":clamp(edge,-1,1),"weight":max(0,weight),"quality":clamp(quality,0,1),"source":source})

        tf,tfq,tfm=self._tf(item,side)
        add("multi_timeframe","trend",tf,.25*mult["tf"],tfq,f"{tfm['frames']} frames / coherence {tfm['coherence']}")

        edge=item.get("edge") or {}
        st=edge.get("structure") or {}
        sb=_v30_direction(st.get("bias"))
        sc=clamp(_v30_num(st.get("confirmation_score"),50),0,100)
        se=((sc-50)/50) if sc>=50 else .35*((sc-50)/50)
        if sb!=side: se=-abs(se) if sb in {"LONG","SHORT"} else 0
        add("market_structure","structure",se,.17*mult["structure"],sc/100,sb or "WAIT")

        fe,fq,fp=self._flow(item,side)
        add("derivatives_flow","flow",fe,.14*mult["flow"],fq,f"parts={len(fp)}")

        # Precision + volatility are deliberately separate: entry quality does
        # not become a directional vote just because volatility is high.
        pr=item.get("precision") or {}
        ps=clamp(_v30_num(pr.get("score"),50),0,100)
        pe=(ps-50)/50
        timing=str(pr.get("entry_timing") or "").upper()
        if timing in {"AVOID","DANGER","LATE"}: pe*=.45
        add("entry_precision","precision",pe,.10*mult["precision"],ps/100,timing or "unknown")

        vol=_v30_num(item.get("volatility_pct"),0)
        # Volatility is a confidence modifier, not a fake directional signal.
        vol_quality=1.0 if 0.05 <= vol <= 8 else .62 if vol>0 else .45
        add("volatility_context","vol",0,.08*mult["vol"],vol_quality,f"vol={vol:.3f}%")

        fc=item.get("candle_forecast") or {}
        fb=_v30_direction(fc.get("overall_bias"))
        fs=clamp(_v30_num(fc.get("path_strength"),0)/40,0,1)
        add("future_path","forecast",fs if fb==side else -fs if fb in {"LONG","SHORT"} else 0,.10*mult["forecast"],fs,fb)

        neural=item.get("neural_v9") or (item.get("fusion") or {}).get("neural_v9") or {}
        ns=_v30_direction(neural.get("side")); nc=clamp(_v30_num(neural.get("confidence"),0)/100,0,1)
        add("neural_model","neural",nc if ns==side else -nc if ns in {"LONG","SHORT"} else 0,.11*mult["neural"],nc,ns)

        # BTC context is a filter, not an absolute veto. This avoids blocking
        # strong idiosyncratic setups while still accounting for market beta.
        btc=_v30_direction(item.get("btc_trend"))
        btc_e=.45 if btc==side else -.45 if btc in {"LONG","SHORT"} else 0
        add("btc_context","btc",btc_e,.07*mult["btc"],.75 if btc!="WAIT" else .35,btc)

        ai=edge.get("ai") or {}
        am=_v30_direction(ai.get("majority") or ai.get("ai_majority") or item.get("ai_majority"))
        aa=clamp(_v30_num(ai.get("agreement") or ai.get("majority_agreement"),0)/100,0,1)
        add("ai_ensemble","ai",aa if am==side else -aa if am in {"LONG","SHORT"} else 0,V30_MAX_AI*mult.get("ai",.9),aa,am)

        # Data integrity is a global quality multiplier; it never creates direction.
        dq=clamp(_v30_num((item.get("data_quality") or {}).get("score") or ((item.get("fusion") or {}).get("data_quality") or {}).get("score"),50),0,100)
        global_q=.55+.45*(dq/100)
        for x in ev: x["quality"]*=global_q

        total=sum(x["weight"] for x in ev)
        score=sum(x["edge"]*x["weight"]*x["quality"] for x in ev)/max(total,1e-9)
        active=[x for x in ev if abs(x["edge"])>=.12 and x["quality"]>=.40 and x["weight"]>0]
        support=[x for x in active if x["edge"]>0]
        oppose=[x for x in active if x["edge"]<0]
        support_f={x["family"] for x in support}; oppose_f={x["family"] for x in oppose}
        contradiction=(min(len(support_f),len(oppose_f))/max(len(support_f|oppose_f),1)) if (support_f or oppose_f) else 0
        # Debate quality: agreement among independent families, not raw vote count.
        family_edges={}
        for x in ev:
            family_edges.setdefault(x["family"],[]).append(x["edge"])
        fam={k:sum(v)/len(v) for k,v in family_edges.items()}
        consensus=sum(1 for v in fam.values() if v>.10)/max(sum(1 for v in fam.values() if abs(v)>.10),1)
        disagreement=sum(1 for v in fam.values() if v<-.10)/max(sum(1 for v in fam.values() if abs(v)>.10),1)
        quality=clamp(_v30_num(item.get("signal_quality"),50),0,100)
        rr=_v30_num(item.get("effective_rr_tp1") or item.get("rr_tp1"),0)
        hard=[]
        if dq<V30_MIN_DATA: hard.append("DATA_QUALITY")
        if rr>0 and rr<1.08: hard.append("RR_LOW")
        if _v30_num(item.get("price"),0)<=0: hard.append("PRICE_INVALID")
        return {"side":side,"score":round(score,4),"strength":round(abs(score)*100,1),"support":len(support_f),"oppose":len(oppose_f),"support_families":sorted(support_f),"oppose_families":sorted(oppose_f),"contradiction":round(contradiction,3),"consensus":round(consensus,3),"quality":round(quality,1),"data_quality":round(dq,1),"rr":round(rr,2),"hard_blocks":hard,"evidence":ev,"debate":fam}

    def evaluate(self,item):
        reg,mult=self._regime(item)
        long=self._build_side(item,"LONG",reg,mult); short=self._build_side(item,"SHORT",reg,mult)
        delta=long["score"]-short["score"]
        candidate="LONG" if delta>=.08 else "SHORT" if delta<=-.08 else "WAIT"
        chosen=long if candidate=="LONG" else short if candidate=="SHORT" else (long if long["score"]>=short["score"] else short)
        ready=(candidate in {"LONG","SHORT"} and chosen["score"]>=V30_MIN_READY and chosen["support"]>=3 and chosen["quality"]>=V30_MIN_QUALITY and chosen["data_quality"]>=V30_MIN_DATA and chosen["rr"]>=1.08 and not chosen["hard_blocks"] and chosen["contradiction"]<.70)
        early=(candidate in {"LONG","SHORT"} and chosen["score"]>=V30_MIN_EARLY and chosen["support"]>=2 and chosen["data_quality"]>=50 and not chosen["hard_blocks"])
        watch=(candidate in {"LONG","SHORT"} and chosen["score"]>=V30_MIN_WATCH and chosen["support"]>=2)
        state="READY" if ready else "EARLY" if early else "WATCH" if watch else "WAIT"
        # Confidence is explicitly evidence confidence, not a win probability.
        conf=clamp(50+abs(delta)*38+chosen["support"]*5-chosen["oppose"]*4-chosen["contradiction"]*22+(chosen["data_quality"]-50)*.15,0,96)
        return {"version":V30_VERSION,"regime":reg,"candidate":candidate,"state":state,"confidence":round(conf,1),"delta":round(delta,4),"long":long,"short":short,"chosen":chosen,"discussion":{"agreement":round(chosen["consensus"]*100,1),"disagreement":round(chosen["contradiction"]*100,1),"independent_support":chosen["support"],"independent_opposition":chosen["oppose"],"active_families":sorted(set(chosen["support_families"]+chosen["oppose_families"]))},"explanation":[f"رژیم بازار: {reg}",f"اختلاف شواهد LONG/SHORT: {delta:.3f}",f"حمایت مستقل: {chosen['support']} خانواده",f"مخالفت مستقل: {chosen['oppose']} خانواده",f"اعتماد شواهد: {conf:.1f}/100","AI در سقف وزن 10٪ باقی می‌ماند و به‌تنهایی جهت نمی‌سازد.","Volatility فقط کیفیت را تعدیل می‌کند و به‌تنهایی سیگنال نمی‌سازد."]}


TITAN_DEEP_V30 = TitanDeepConsensusV30()
_analyze_asset_v29 = analyze_asset

def analyze_asset(symbol: str, btc_trend: str) -> Optional[dict[str, Any]]:
    item=_analyze_asset_v29(symbol,btc_trend)
    if not item: return None
    try:
        debate=TITAN_DEEP_V30.evaluate(item)
        item["deep_consensus_v30"]=debate
        item.setdefault("fusion",{})["deep_consensus_v30"]=debate
        item["decision_confidence_v30"]=debate["confidence"]
        item["decision_state_v30"]=debate["state"]
        item["decision_discussion_v30"]=debate["discussion"]
        current=str(item.get("decision_tag") or "WAIT").upper()
        cand=debate.get("candidate")
        chosen=debate.get("chosen") or {}
        # Safety demotion: if an existing LONG/SHORT is strongly contradicted
        # by several independent families, remove it rather than silently keep
        # a stale signal. V30 never directly reverses direction.
        if current in {"LONG","SHORT"}:
            opposite=debate["short"] if current=="LONG" else debate["long"]
            if (opposite["score"]>=.30 and opposite["support"]>=V30_DEMOTE_OPPOSITION and opposite["data_quality"]>=V30_MIN_DATA and opposite["quality"]>=V30_MIN_QUALITY and not opposite["hard_blocks"]):
                item["decision_tag"]="WAIT"
                item["bias"]="خنثی"
                item["signal_tag"]="V30 DEBATE — WAIT"
                item["entry_mode"]="WAIT"
                item["decision_demoted_v30"]=True
                debate["explanation"].append("تصمیم قبلی به WAIT تنزل یافت: چند خانواده مستقل شواهد معتبر در جهت مخالف داشتند.")
        elif current=="WAIT" and cand in {"LONG","SHORT"} and debate["state"]=="READY":
            # V30 is intentionally stricter than V29 for final promotion.
            try:
                price=_v12_parse_price(item.get("price")); sl,tp1,tp2=_v12_rebuild_directional_levels(item,cand)
                chk=_v12_level_integrity(price,sl,tp1,tp2,cand)
                if chk.get("ok") and _v30_num(chk.get("rr1"),0)>=1.08:
                    item["stop_loss"]=smart_format(sl); item["tp1"]=smart_format(tp1); item["tp2"]=smart_format(tp2)
                    item["effective_rr_tp1"]=chk["rr1"]; item["effective_rr_tp2"]=chk["rr2"]; item["rr_tp1"]=chk["rr1"]; item["rr_tp2"]=chk["rr2"]
                    item["decision_tag"]=cand; item["bias"]="صعودی" if cand=="LONG" else "نزولی"; item["signal_tag"]="V30 DEEP CONSENSUS READY"; item["entry_mode"]="EARLY"; item["decision_promoted_v30"]=True
                    item["signal_quality"]=max(_v30_num(item.get("signal_quality"),50),min(90,chosen.get("quality",50)+8))
                    debate["applied"]=True
                else: debate["applied"]=False
            except Exception as exc:
                debate["applied"]=False; debate["explanation"].append("ارتقای V30 به‌علت کنترل سطوح انجام نشد."); LOGGER.debug("V30 promotion failed %s: %s",symbol,exc)
        else:
            debate["applied"]=False
        item["canonical_decision"]={**(item.get("canonical_decision") or {}),"decision":item.get("decision_tag","WAIT"),"bias":item.get("bias","خنثی"),"v30_confidence":debate["confidence"],"v30_state":debate["state"]}
        item["decision_audit_v30"]={"version":V30_VERSION,"decision":item.get("decision_tag","WAIT"),"candidate":cand,"state":debate["state"],"confidence":debate["confidence"],"discussion":debate["discussion"],"explanation":debate["explanation"]}
        return item
    except Exception as exc:
        LOGGER.exception("V30 deep consensus failed for %s: %s",symbol,exc)
        item["deep_consensus_v30"]={"version":V30_VERSION,"state":"ERROR","confidence":0,"error":"internal consensus failure"}
        return item


# ============================================================
# V31 — CANONICAL DECISION GOVERNOR
# One brain / many evidence channels. All upstream modules are evidence only;
# none of them is allowed to publish an independent final decision.
# ============================================================
V31_VERSION = "TITAN-V31-CANONICAL-DECISION-GOVERNOR"
V31_MIN_MARGIN = 0.065
V31_READY_MARGIN = 0.145
V31_STRONG_MARGIN = 0.24
V31_MIN_DATA = 54.0
V31_MIN_QUALITY = 50.0
V31_MIN_RR = 1.02
V31_MAX_CONTRADICTION = 0.70
V31_PRIOR_MAX = 0.08

class TitanCanonicalDecisionV31:
    """Single final decision brain.

    Upstream engines may disagree internally. Their outputs are compressed into
    common evidence and evaluated together. Only this governor is authoritative
    for the final LONG/SHORT/WAIT decision exposed to the dashboard/API.
    """
    def _side(self, debate, side):
        return (debate or {}).get(side.lower()) or {}

    def _score(self, debate, side):
        return float(self._side(debate, side).get("score", 0.0) or 0.0)

    def decide(self, item, debate):
        long = self._side(debate, "LONG")
        short = self._side(debate, "SHORT")
        ls = self._score(debate, "LONG")
        ss = self._score(debate, "SHORT")
        margin = ls - ss
        abs_margin = abs(margin)
        candidate = "LONG" if margin >= V31_MIN_MARGIN else "SHORT" if margin <= -V31_MIN_MARGIN else "WAIT"
        chosen = long if candidate == "LONG" else short if candidate == "SHORT" else (long if ls >= ss else short)
        opposite = short if candidate == "LONG" else long if candidate == "SHORT" else {}

        dq = float(chosen.get("data_quality", 0) or 0)
        quality = float(chosen.get("quality", 0) or 0)
        rr = float(chosen.get("rr", 0) or 0)
        contradiction = float(chosen.get("contradiction", 0) or 0)
        support = int(chosen.get("support", 0) or 0)
        oppose = int(chosen.get("oppose", 0) or 0)
        hard = list(chosen.get("hard_blocks") or [])

        # Confidence is an evidence-confidence score, not a probability of profit.
        base = 50.0 + abs_margin * 105.0
        base += min(18.0, support * 4.5)
        base -= min(18.0, oppose * 4.0)
        base -= contradiction * 24.0
        base += max(-10.0, min(10.0, (dq - 60.0) * 0.18))
        base += max(-7.0, min(7.0, (quality - 60.0) * 0.14))
        if rr >= V31_MIN_RR: base += min(5.0, (rr - V31_MIN_RR) * 5.0)
        confidence = clamp(base, 0.0, 96.0)