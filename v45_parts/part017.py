            except Exception as exc:
                LOGGER.debug("central horizon fetch failed #%s: %s", rid, exc)
                continue

            # Chronological barrier evaluation.  If SL and TP are both inside
            # one OHLC candle, ordering is unknowable at this timeframe; do not
            # manufacture a WIN/LOSS sample from ambiguous data.
            touch, hit_type, exit_px = _first_touch_ohlc(
                window, decision,
                safe_float(sl, np.nan),
                safe_float(tp1, np.nan),
                safe_float(tp2, np.nan),
            )

            last = safe_float(window["close"].iloc[-1], entry)
            if decision == "LONG":
                ret = (last / entry - 1.0) * 100.0
            else:
                ret = (entry / last - 1.0) * 100.0 if last > 0 else 0.0

            if touch == "WIN":
                outcome = "WIN"
            elif touch == "LOSS":
                outcome = "LOSS"
            elif touch == "AMBIGUOUS":
                outcome = "AMBIGUOUS"
            else:
                # No barrier was touched inside the declared horizon.  This is
                # a time-expiry observation, not a binary WIN/LOSS training label.
                outcome = "TIME_EXIT"

            lesson = {
                "WIN": "اولین لمس هدف داخل پنجره پیش‌بینی رخ داد.",
                "LOSS": "اولین لمس حد ضرر داخل پنجره پیش‌بینی رخ داد.",
                "AMBIGUOUS": "حد ضرر و هدف در یک کندل لمس شدند؛ ترتیب قابل تشخیص نیست.",
                "TIME_EXIT": "هیچ سطحی تا پایان افق لمس نشد؛ نمونه برای یادگیری دودویی استفاده نمی‌شود.",
            }.get(outcome, "")

            # Edge Lab telemetry: MAE/MFE, time-to-event, realized regime and friction-aware R.
            regime_name, vol_pct, trend_strength = _edge_regime_from_window(window)
            mae_pct = mfe_pct = 0.0
            try:
                highs = window["high"].astype(float); lows = window["low"].astype(float)
                if decision == "LONG":
                    mae_pct = (float(lows.min()) / entry - 1.0) * 100.0
                    mfe_pct = (float(highs.max()) / entry - 1.0) * 100.0
                else:
                    mae_pct = (entry / float(highs.max()) - 1.0) * 100.0
                    mfe_pct = (entry / float(lows.min()) - 1.0) * 100.0
            except Exception:
                pass
            touch_d, touch_px, touch_ts = _edge_first_touch_detail(window, decision, safe_float(sl,np.nan), safe_float(tp1,np.nan), safe_float(tp2,np.nan))
            event_time = ((touch_ts - created) / 60.0) if touch_ts is not None else float(horizon)
            friction_pct = TOTAL_ENTRY_BUFFER * 2.0 * 100.0
            gross_ret = ret
            net_ret = gross_ret - friction_pct if math.isfinite(gross_ret) else gross_ret
            risk_dist = abs(entry - safe_float(sl, entry))
            r_mult = ((touch_px-entry)/max(risk_dist,1e-12) if decision=="LONG" and touch_px else (entry-touch_px)/max(risk_dist,1e-12) if decision=="SHORT" and touch_px else net_ret/max((risk_dist/max(entry,1e-12))*100.0,1e-12))
            entry_quality = clamp(50.0 + abs(safe_float(prediction_confidence,50.0)-50.0)*0.6 + trend_strength*0.2, 0.0, 100.0)
            directional_bias = 100.0 if decision=="LONG" else -100.0
            with DB_LOCK, db_conn() as con:
                con.execute("INSERT OR REPLACE INTO central_trade_metrics(prediction_id,regime,volatility_pct,trend_strength,mae_pct,mfe_pct,time_to_event_min,exit_price,net_return_pct,r_multiple,entry_quality,directional_bias,ambiguity,friction_pct,evaluated_at,param_version,edge_lab_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (rid,regime_name,vol_pct,trend_strength,mae_pct,mfe_pct,event_time,touch_px or last,net_ret,r_mult,entry_quality,directional_bias,1 if outcome=="AMBIGUOUS" else 0,friction_pct,now,TITAN_PARAM_VERSION,EDGE_LAB_VERSION))
                con.commit()

            try:
                comps = json.loads(comp_json or "[]")
            except Exception:
                comps = []

            # Only unambiguous barrier outcomes are allowed to change weights.
            if outcome in {"WIN", "LOSS"} and isinstance(comps, list):
                for c in comps:
                    name = str(c.get("component") or "")
                    if not name or name not in _CENTRAL_WEIGHTS_DEFAULT:
                        continue
                    side = str(c.get("side") or "WAIT")
                    aligned = side == decision
                    win = outcome == "WIN"
                    reward = (
                        1.0 if (win and aligned)
                        else 0.5 if ((not win) and side in {"LONG", "SHORT"} and not aligned)
                        else 0.0
                    )
                    penalty = (
                        1.0 if ((not win) and aligned)
                        else 0.5 if (win and side in {"LONG", "SHORT"} and not aligned)
                        else 0.0
                    )
                    with DB_LOCK, db_conn() as con:
                        con.execute(
                            """INSERT INTO central_component_stats(
                               component,samples,wins,losses,reward_sum,penalty_sum,weight,updated_at)
                               VALUES(?,?,?,?,?,?,?,?)
                               ON CONFLICT(component) DO UPDATE SET
                                 samples=samples+1,
                                 wins=wins+excluded.wins,
                                 losses=losses+excluded.losses,
                                 reward_sum=reward_sum+excluded.reward_sum,
                                 penalty_sum=penalty_sum+excluded.penalty_sum,
                                 updated_at=excluded.updated_at""",
                            (
                                name, 1,
                                1 if (win and aligned) else 0,
                                1 if ((not win) and aligned) else 0,
                                reward, penalty,
                                safe_float(_CENTRAL_WEIGHTS_DEFAULT.get(name), 1.0),
                                now,
                            ),
                        )

            with DB_LOCK, db_conn() as con:
                con.execute(
                    """UPDATE central_predictions
                       SET outcome=?,evaluated_at=?,return_pct=?,lesson=?
                       WHERE id=?""",
                    (outcome, now, ret, lesson, rid),
                )
                con.commit()
            done += 1

        if done:
            _central_load_weights()
        return {"ok": True, "evaluated": done}
    except Exception as exc:
        LOGGER.debug("central evaluate: %s", exc)
        return {"ok": False, "error": str(exc)[:200]}

def _emergency_live_cards(coins: list | None = None) -> list[dict[str, Any]]:
    """Never leave Android dashboard blank — live prices + WAIT."""
    coins = list(coins or USER_SETTINGS.get("active_coins") or DEFAULT_COINS)
    cards: list[dict[str, Any]] = []
    prices: dict[str, float] = {}
    try:
        prices = dict(_fetch_live_prices(list(coins)) or {})
    except Exception as exc:
        LOGGER.warning("emergency prices: %s", exc)
    now = time.time()
    for sym in coins:
        px = safe_float(prices.get(sym), 0.0)
        if px <= 0:
            for k, v in prices.items():
                if _normalize_symbol(k) == _normalize_symbol(sym):
                    px = safe_float(v, 0.0)
                    break
        if px <= 0:
            continue
        base = sym.split("/")[0] if "/" in sym else sym
        meta = COIN_META.get(base, (base, ""))
        cards.append({
            "symbol": sym, "name": meta[0], "icon": meta[1] if len(meta) > 1 else "",
            "price": smart_format(px), "price_raw": px, "live_price": px,
            "entry_raw": px, "entry_valid": smart_format(px),
            "decision": "WAIT", "decision_tag": "WAIT", "bias": "خنثی",
            "score": 50, "score_color": "#94a3b8", "signal_quality": 0,
            "success_probability": 50, "success_prob": 50, "trust_index": 40,
            "stop_loss": "—", "tp1": "—", "tp2": "—", "rr_tp1": "—",
            "authority": TITAN_CENTRAL_VERSION,
            "signal_tag": "LIVE-PRICE ONLY · WAIT",
            "central_reason_fa": "اسکن کامل در حال اجرا؛ فقط قیمت زنده",
            "scan_timestamp": now, "emergency_card": True,
        })
    return cards



# ============================================================
# TITAN V31 ADVANCED EDGE SUITE — 21 production modules
# Research/decision-support only. No order execution.
# ============================================================
V31_EDGE_VERSION = "TITAN-V31-21-EDGE-SUITE"
_V31_MEMORY = {}
_V31_LOCK = threading.RLock()


def _v31_num(x, default=0.0):
    try:
        v=float(x)
        return default if not math.isfinite(v) else v
    except Exception:
        return default


def _v31_side(item):
    d=str(item.get("decision_tag") or item.get("decision") or "WAIT").upper()
    return d if d in {"LONG","SHORT"} else "WAIT"

# 1) Signal DNA: immutable snapshot of the setup, so every realized result is attributable.
def _v31_signal_dna(item):
    side=_v31_side(item); r=_v31_num(item.get("rsi"),50); score=_v31_num(item.get("score"),50)
    return {"side":side,"score":round(score,2),"rsi":round(r,2),
            "regime":(item.get("regime") or item.get("market_regime") or "unknown"),
            "structure":(item.get("structure") or {}).get("bias", item.get("structure_bias","unknown")) if isinstance(item.get("structure"),dict) else item.get("structure_bias","unknown"),
            "entry":_v31_num(item.get("price") or item.get("entry_raw")),
            "rr1":_v31_num(item.get("rr_tp1")),"rr2":_v31_num(item.get("rr_tp2")),
            "quality":_v31_num(item.get("signal_quality"),0),"timestamp":time.time()}

# 2) Evidence fusion: correlated evidence is discounted; independent evidence is rewarded.
def _v31_evidence_fusion(item):
    dna=_v31_signal_dna(item); side=dna["side"]
    raw=[]
    for k,v in ((item.get("fusion") or {}).items() if isinstance(item.get("fusion"),dict) else []):
        if isinstance(v,(int,float)): raw.append((k,float(v)))
    support=[]
    if side=="LONG": support=[_v31_num(item.get("score"),50)/100,_v31_num(item.get("alignment"),50)/100]
    elif side=="SHORT": support=[1-_v31_num(item.get("score"),50)/100,1-_v31_num(item.get("alignment"),50)/100]
    else: support=[.5]
    # two strong but dependent price-derived signals never count as two full independent votes.
    independent=min(1.0,0.55*max(support)+0.45*(sum(support)/len(support)))
    return {"independence_score":round(independent,4),"raw_components":len(raw),"discount":round(1.0-0.35*max(0,len(raw)-3)/max(1,len(raw)),4)}

# 3) Counterfactual engine: explicit reasons the thesis can fail.
def _v31_counterfactual(item):
    side=_v31_side(item); score=_v31_num(item.get("score"),50); rr=_v31_num(item.get("rr_tp1"),0)
    risks=[]
    if side=="LONG" and score<55: risks.append("جهت صعودی ضعیف")
    if side=="SHORT" and score>45: risks.append("جهت نزولی ضعیف")
    if rr and rr<0.9: risks.append("R/R ضعیف")
    if str(item.get("regime") or "").lower() in {"transition","shock","unknown"}: risks.append("رژیم ناپایدار")
    return {"failure_risks":risks,"counterfactual_score":round(max(0,100-20*len(risks)),1),"thesis_fragile":len(risks)>=2}

# 4) Adversarial robustness: deterministic perturbation envelope, not a fake Monte-Carlo forecast.
def _v31_adversarial(item):
    q=_v31_num(item.get("signal_quality"),50); rr=_v31_num(item.get("rr_tp1"),1.0); side=_v31_side(item)
    if side=="WAIT": return {"robustness":50.0,"stress_cases":0,"failures":0}
    cases=[q-5,q-10,q-15, q-(2 if rr<1.2 else 0)]
    failures=sum(x<45 for x in cases)
    return {"robustness":round(max(0,min(100,100-15*failures-5*max(0,1.0-rr))),1),"stress_cases":len(cases),"failures":failures}

# 5) Entry stability: small price perturbations must not flip the thesis.
def _v31_entry_stability(item):
    p=_v31_num(item.get("price") or item.get("entry_raw")); sl=_v31_num(item.get("stop_loss")); tp=_v31_num(item.get("tp1")); side=_v31_side(item)
    if not p or side=="WAIT": return {"score":50.0,"band_pct":0.0}
    band=0.0025; vals=[]
    for f in (1-band,1-band/2,1,1+band/2,1+band):
        ep=p*f
        if side=="LONG": vals.append(float(sl<p and ep>sl and (not tp or ep<tp)))
        else: vals.append(float(sl>p and ep<sl and (not tp or ep>tp)))
    return {"score":round(100*sum(vals)/len(vals),1),"band_pct":band*100}

# 6) Exit intelligence: structure/risk/time/liquidity aware exit mode.
def _v31_exit_intelligence(item):
    side=_v31_side(item); rr1=_v31_num(item.get("rr_tp1"),0); rr2=_v31_num(item.get("rr_tp2"),0)
    regime=str(item.get("regime") or "").lower(); mode="HOLD_TO_TARGET"
    if side=="WAIT": mode="NONE"
    elif "shock" in regime: mode="DEFENSIVE_REDUCE"
    elif rr1<1.0: mode="EARLY_EXIT_BIAS"
    elif rr2>=1.8: mode="RUNNER_TO_TP2"
    return {"mode":mode,"rr_tp1":rr1,"rr_tp2":rr2,"invalidation":"structure_break_or_SL"}

# 7) Confidence decay: stale evidence loses weight with time.
def _v31_confidence_decay(item):
    ts=_v31_num(item.get("scan_timestamp"),time.time()); age=max(0,time.time()-ts); half=900.0
    decay=math.exp(-math.log(2)*age/half)
    return {"age_sec":round(age,1),"decay":round(decay,4),"effective_quality":round(_v31_num(item.get("signal_quality"),0)*decay,2)}

# 8) Market shock detector: uses available live/quality features conservatively.
def _v31_shock(item):
    atr=_v31_num(item.get("atr")); vol=bool(item.get("volume_spike")); spread=_v31_num(item.get("spread_pct"),0)
    flags=[]
    if vol: flags.append("volume_spike")
    if spread>0.25: flags.append("wide_spread")
    if atr<=0: flags.append("atr_missing")
    return {"mode":"SHOCK" if len(flags)>=2 else "NORMAL","flags":flags,"severity":min(1.0,len(flags)/3)}

# 9) Asset personality: persistent in-process profile, updated from each signal DNA.
def _v31_personality(item):
    sym=str(item.get("symbol") or "UNKNOWN"); side=_v31_side(item)
    with _V31_LOCK:
        st=_V31_MEMORY.setdefault(sym,{"samples":0,"long":0,"short":0,"quality_sum":0.0})
        st["samples"]+=1; st["long"]+=int(side=="LONG"); st["short"]+=int(side=="SHORT"); st["quality_sum"]+=_v31_num(item.get("signal_quality"),0)
        return {"samples":st["samples"],"long_share":round(st["long"]/st["samples"],3),"avg_quality":round(st["quality_sum"]/st["samples"],2)}

# 10) Session intelligence: UTC session bucket is deterministic and timezone-safe.
def _v31_session(item):
    h=datetime.now(timezone.utc).hour
    bucket="ASIA" if h<8 else "EUROPE" if h<13 else "US" if h<21 else "LATE"
    return {"session":bucket,"utc_hour":h}

# 11) Regime transition detector: disagreement between current regime and prior regime is a warning.
def _v31_transition(item):
    sym=str(item.get("symbol") or "UNKNOWN"); regime=str(item.get("regime") or item.get("market_regime") or "unknown")
    with _V31_LOCK:
        prev=_V31_MEMORY.setdefault("_regime",{}).get(sym); _V31_MEMORY["_regime"][sym]=regime
    return {"transition":bool(prev and prev!=regime),"previous":prev,"current":regime}

# 12) Dead-signal detector: no meaningful movement/evidence means WAIT rather than forced action.
def _v31_dead_signal(item):
    side=_v31_side(item); q=_v31_num(item.get("signal_quality"),0); score=_v31_num(item.get("score"),50)
    dead=side=="WAIT" or q<35 or abs(score-50)<3
    return {"dead":dead,"reason":"insufficient_edge" if dead else "active_edge"}

# 13) Internal prediction market: component probabilities are combined by independent strength.
def _v31_prediction_market(item):
    score=_v31_num(item.get("score"),50)/100; align=_v31_num(item.get("alignment"),50)/100
    side=_v31_side(item)
    probs=[score,align] if side=="LONG" else [1-score,1-align] if side=="SHORT" else [.5]
    return {"probability_proxy":round(100*sum(probs)/len(probs),2),"components":len(probs),"side":side}

# 14) Bayesian updating: conservative Beta posterior from realized central samples.
def _v31_bayes(item):
    sym=str(item.get("symbol") or ""); side=_v31_side(item); wins=losses=0
    try:
        if sym and side in {"LONG","SHORT"}:
            with DB_LOCK, db_conn() as con:
                # central_predictions stores English decision tags (LONG/SHORT), not Persian bias labels.
                row=con.execute(
                    "SELECT SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END), "
                    "SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) "
                    "FROM central_predictions WHERE symbol=? AND decision=? AND outcome IN ('WIN','LOSS')",
                    (sym, side),
                ).fetchone()
                wins=int(row[0] or 0); losses=int(row[1] or 0)
    except Exception: pass
    post=(wins+2)/(wins+losses+4)
    return {"wins":wins,"losses":losses,"posterior_pct":round(100*post,2)}

# 15) Uncertainty engine: probability and uncertainty are separate outputs.
def _v31_uncertainty(parts):
    vals=[_v31_num(parts.get("robustness"),50),_v31_num(parts.get("entry_stability"),50),_v31_num(parts.get("evidence_independence"),50)]
    uncertainty=100-sum(vals)/len(vals)
    return {"uncertainty":round(max(0,min(100,uncertainty)),2),"confidence_band":"LOW" if uncertainty<20 else "MEDIUM" if uncertainty<40 else "HIGH"}

# 16) Multi-dimensional confidence vector.
def _v31_confidence(item, parts):
    q=_v31_num(item.get("signal_quality"),0)
    return {"direction":round(abs(_v31_num(item.get("score"),50)-50)*2,1),"structure":q,"entry_quality":parts["entry_stability"],"regime":100 if not parts["transition"] else 45,"robustness":parts["robustness"],"uncertainty":parts["uncertainty"]}

# 17) Explainability: machine-readable WHY / WHY-NOT trail.
def _v31_explain(item, parts):
    why=[]; why_not=[]; side=_v31_side(item)
    if side in {"LONG","SHORT"}: why.append(f"direction={side}")
    if parts["robustness"]>=70: why.append("robust_under_stress")
    if parts["entry_stability"]>=80: why.append("stable_entry")
    if parts["transition"]: why_not.append("regime_transition")
    if parts["counterfactual"]<60: why_not.append("fragile_thesis")
    if parts["uncertainty"]>40: why_not.append("high_uncertainty")
    return {"why":why,"why_not":why_not}

# 18) Self-destruct threshold: invalidate thesis when core assumptions collapse.
def _v31_self_destruct(item, parts):
    trigger=(parts["counterfactual"]<40 or parts["robustness"]<40 or parts["dead"])
    return {"invalidate":bool(trigger),"reason":"core_edge_collapsed" if trigger else "thesis_intact"}

# 19) Data quality gate: missing core values reduce authority rather than being fabricated.
def _v31_data_quality(item):
    keys=("price","rsi","atr","score")
    missing=[k for k in keys if item.get(k) in (None,"","—")]
    score=max(0,100-20*len(missing))
    return {"score":score,"missing":missing,"gate":"PASS" if score>=80 else "DEGRADED" if score>=50 else "FAIL"}

# 20) Research lab: rolling attribution by asset/side from realized central outcomes.
def _v31_research(item):
    out={"samples":0,"wins":0,"losses":0,"win_rate":None}
    try:
        sym=str(item.get("symbol") or "")
        if sym:
            with DB_LOCK, db_conn() as con:
                r=con.execute("SELECT COUNT(*),SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END),SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) FROM central_predictions WHERE symbol=? AND outcome!='PENDING'",(sym,)).fetchone()
            n=int(r[0] or 0); w=int(r[1] or 0); l=int(r[2] or 0)
            out={"samples":n,"wins":w,"losses":l,"win_rate":round(100*w/n,2) if n else None}
    except Exception: pass
    return out

# 21) Champion/challenger: keep the current governor authoritative; compare challengers only as audit metrics.
def _v31_champion_challenger(item, parts):
    champion=float(_v31_num(item.get("signal_quality"),0)); challenger=float((parts["robustness"]+parts["entry_stability"]+parts["counterfactual"])/3)
    return {"champion":round(champion,2),"challenger":round(challenger,2),"challenger_wins":bool(challenger>champion),"action":"AUDIT_ONLY"}


def _v31_apply(item):
    """Run all 21 modules. The suite is a safety/audit layer; it never fabricates probabilities."""
    try:
        dna=_v31_signal_dna(item); ev=_v31_evidence_fusion(item); cf=_v31_counterfactual(item); adv=_v31_adversarial(item)
        ent=_v31_entry_stability(item); ex=_v31_exit_intelligence(item); decay=_v31_confidence_decay(item); shock=_v31_shock(item)
        personality=_v31_personality(item); session=_v31_session(item); transition=_v31_transition(item); dead=_v31_dead_signal(item)
        market=_v31_prediction_market(item); bayes=_v31_bayes(item)
        unc=_v31_uncertainty({"robustness":adv["robustness"],"entry_stability":ent["score"],"evidence_independence":ev["independence_score"]*100})
        conf=_v31_confidence(item,{"entry_stability":ent["score"],"robustness":adv["robustness"],"transition":transition["transition"],"uncertainty":unc["uncertainty"]})
        explain=_v31_explain(item,{"robustness":adv["robustness"],"entry_stability":ent["score"],"transition":transition["transition"],"counterfactual":cf["counterfactual_score"],"uncertainty":unc["uncertainty"]})
        sd=_v31_self_destruct(item,{"counterfactual":cf["counterfactual_score"],"robustness":adv["robustness"],"dead":dead["dead"]})
        dq=_v31_data_quality(item); research=_v31_research(item); cc=_v31_champion_challenger(item,{"robustness":adv["robustness"],"entry_stability":ent["score"],"counterfactual":cf["counterfactual_score"]})
        # Only hard safety failures can force WAIT. This does not create a new trade signal.
        original=_v31_side(item); forced_wait=sd["invalidate"] or dq["gate"]=="FAIL" or shock["mode"]=="SHOCK"
        if forced_wait and original in {"LONG","SHORT"}:
            item["decision_tag"]="WAIT"; item["decision"]="WAIT"; item["advanced_override"]="SAFETY_WAIT"
        item["v31_edge_suite"]={"version":V31_EDGE_VERSION,"signal_dna":dna,"evidence_fusion":ev,"counterfactual":cf,"adversarial":adv,"entry_stability":ent,"exit_intelligence":ex,"confidence_decay":decay,"shock":shock,"personality":personality,"session":session,"regime_transition":transition,"dead_signal":dead,"prediction_market":market,"bayesian":bayes,"uncertainty":unc,"confidence_vector":conf,"explainability":explain,"self_destruct":sd,"data_quality":dq,"research_lab":research,"champion_challenger":cc,"safety_wait":forced_wait}
        return item
    except Exception as exc:
        LOGGER.exception("V31 edge suite failed: %s",exc)
        item["v31_edge_suite"]={"version":V31_EDGE_VERSION,"error":str(exc)[:240]}
        return item


# ============================================================
# TITAN V34 — ADAPTIVE TRUST / OPPORTUNITY / CALIBRATION CORE
# ------------------------------------------------------------
# Additive evidence layer. It does not execute trades and does not invent
# probabilities. It learns only from realized outcomes already stored by TITAN.
# Goals:
#   1) distinguish "not enough evidence" from "almost actionable"
#   2) reduce unnecessary WAIT near a coherent edge
#   3) calibrate trust using realized history with Bayesian shrinkage
#   4) adapt evidence weight by symbol/direction without overfitting
#   5) expose a transparent scorecard for performance and audit
# ============================================================
V34_VERSION = "TITAN-V34-ADAPTIVE-TRUST-OPPORTUNITY"
V34_MIN_MARGIN = 0.07
V34_PROMOTE_SCORE = 70.0
V34_MIN_DQ = 52.0
V34_MIN_QUALITY = 50.0
V34_MIN_RR = 1.10
V34_MAX_CONTRADICTION = 0.68
V34_MIN_HISTORY = 12
V34_HISTORY_SHRINK = 10.0


def _v34_history(symbol: str, side: str) -> dict[str, Any]:
    """Outcome history with Bayesian shrinkage; tiny samples never dominate."""
    wins = losses = 0
    try:
        with DB_LOCK, db_conn() as con:
            row = con.execute(
                """SELECT
                     SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END),
                     SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END)
                   FROM central_predictions
                   WHERE symbol=? AND decision=? AND outcome IN ('WIN','LOSS')""",
                (symbol, side),
            ).fetchone()
            wins = int(row[0] or 0)
            losses = int(row[1] or 0)
    except Exception:
        pass
    n = wins + losses
    # Beta(2,2) prior: stable at small samples and converges toward reality.
    posterior = (wins + 2.0) / (n + 4.0) if n else 0.5
    raw_wr = 100.0 * wins / n if n else 50.0
    return {
        "wins": wins, "losses": losses, "samples": n,
        "raw_win_rate": round(raw_wr, 2),
        "posterior_win_rate": round(100.0 * posterior, 2),
        "reliable": n >= V34_MIN_HISTORY,
    }


def _v34_opportunity(item: dict[str, Any]) -> dict[str, Any]:
    """Score a near-actionable WAIT without pretending it is a profit probability."""
    debate = item.get("deep_consensus_v30") or {}
    long = debate.get("long") or {}
    short = debate.get("short") or {}
    ls = safe_float(long.get("score"), 0.0)
    ss = safe_float(short.get("score"), 0.0)
    margin = ls - ss
    side = "LONG" if margin >= V34_MIN_MARGIN else "SHORT" if margin <= -V34_MIN_MARGIN else "WAIT"
    chosen = long if side == "LONG" else short if side == "SHORT" else {}
    if not chosen:
        return {"version": V34_VERSION, "state": "NO_EDGE", "score": 0.0, "candidate": "WAIT"}

    dq = safe_float(chosen.get("data_quality"), 0.0)
    quality = safe_float(chosen.get("quality"), 0.0)
    rr = safe_float(chosen.get("rr"), 0.0)
    contradiction = safe_float(chosen.get("contradiction"), 1.0)
    support = int(chosen.get("support", 0) or 0)
    oppose = int(chosen.get("oppose", 0) or 0)
    hard = list(chosen.get("hard_blocks") or [])
    history = _v34_history(_normalize_symbol(item.get("symbol") or ""), side)

    # Each component is bounded. This is an evidence score, not win probability.
    margin_score = clamp((abs(margin) - V34_MIN_MARGIN) / 0.14 * 100.0, 0.0, 100.0)
    dq_score = clamp((dq - V34_MIN_DQ) / 35.0 * 100.0, 0.0, 100.0)
    quality_score = clamp((quality - V34_MIN_QUALITY) / 35.0 * 100.0, 0.0, 100.0)
    rr_score = clamp((rr - V34_MIN_RR) / 0.90 * 100.0, 0.0, 100.0)
    support_score = clamp(support * 25.0 - oppose * 15.0, 0.0, 100.0)
    contradiction_score = clamp((V34_MAX_CONTRADICTION - contradiction) / V34_MAX_CONTRADICTION * 100.0, 0.0, 100.0)
    history_score = history["posterior_win_rate"] if history["reliable"] else 50.0

    score = (
        margin_score * 0.25 + quality_score * 0.20 + dq_score * 0.15 +
        support_score * 0.15 + rr_score * 0.10 + contradiction_score * 0.10 +
        history_score * 0.05
    )
    safety_block = (
        bool(hard) or dq < V34_MIN_DQ or quality < V34_MIN_QUALITY or
        rr < V34_MIN_RR or contradiction >= V34_MAX_CONTRADICTION
    )
    promote = side in {"LONG", "SHORT"} and score >= V34_PROMOTE_SCORE and not safety_block
    return {
        "version": V34_VERSION,
        "state": "PROMOTE_EARLY" if promote else "WATCH",
        "candidate": side,
        "score": round(clamp(score, 0.0, 100.0), 1),
        "margin": round(margin, 4),
        "data_quality": round(dq, 1),
        "signal_quality": round(quality, 1),
        "rr": round(rr, 2),
        "support": support,
        "opposition": oppose,
        "contradiction": round(contradiction, 3),
        "history": history,
        "safety_block": safety_block,
        "components": {
            "margin": round(margin_score, 1), "quality": round(quality_score, 1),
            "data": round(dq_score, 1), "support": round(support_score, 1),
            "rr": round(rr_score, 1), "contradiction": round(contradiction_score, 1),
            "history": round(history_score, 1),
        },
        "note": "Evidence score only; not a guaranteed probability of profit.",
    }


def _v34_apply(item: dict[str, Any]) -> dict[str, Any]:
    """Final opportunity layer above the canonical evidence stack."""
    try:
        opp = _v34_opportunity(item)
        item["v34_opportunity"] = opp
        item.setdefault("fusion", {})["v34_opportunity"] = opp
        current = str(item.get("decision_tag") or item.get("decision") or "WAIT").upper()
        # Only promote a WAIT that is already supported by the existing central
        # debate. Never flip a valid LONG/SHORT and never bypass hard safety blocks.
        if current == "WAIT" and opp.get("state") == "PROMOTE_EARLY":
            decision = str(opp.get("candidate") or "WAIT")
            item["decision_tag"] = decision
            item["decision"] = decision
            item["bias"] = "صعودی" if decision == "LONG" else "نزولی"
            item["entry_mode"] = "EARLY"
            item["decision_state"] = "CENTRAL_V34_EARLY"
            item["signal_tag"] = f"CENTRAL V34 OPPORTUNITY — {decision}"
            # Confidence is increased modestly by evidence quality, never to 100.
            old = safe_float(item.get("decision_confidence"), 50.0)
            boost = min(8.0, max(2.0, (safe_float(opp.get("score"), 66.0) - 60.0) * 0.20))
            item["decision_confidence"] = round(clamp(max(old, 50.0) + boost, 0.0, 96.0), 1)
            item["central_reason_fa"] = "فرصت نزدیک به فعال‌شدن با اجماع شواهد، کیفیت داده و RR معتبر؛ V34 آن را از WAIT به EARLY ارتقا داد."
            item["v34_promoted"] = True
        else:
            item["v34_promoted"] = False
        item["decision_architecture"] = {
            "type": "SINGLE_CENTRAL_GOVERNOR_WITH_ADAPTIVE_EVIDENCE",
            "authoritative_source": TITAN_CENTRAL_VERSION,
            "opportunity_layer": V34_VERSION,
            "final_decision": item.get("decision_tag", "WAIT"),
            "legacy_engines_are_evidence_only": True,
        }
        return item
    except Exception as exc:
        LOGGER.debug("V34 adaptive trust failed: %s", exc)
        item["v34_opportunity"] = {"version": V34_VERSION, "state": "DEGRADED", "score": 0.0}
        item["v34_promoted"] = False
        return item

# ============================================================
# TITAN V35 — CANONICAL LIVE-PRICE / LEVEL SYNCHRONIZATION
# ------------------------------------------------------------
# One authoritative spot snapshot is used for the public dashboard price,
# entry, SL/TP, RR, forecast anchor and live-price metadata. Closed-candle
# indicators remain based on closed OHLCV; only price-dependent outputs are
# re-anchored. No signal is fabricated when a fresh live price is unavailable.
# ============================================================
V35_VERSION = "TITAN-V35-CANONICAL-LIVE-SNAPSHOT"
V35_MAX_LIVE_AGE_SEC = 8.0
V35_REBASE_MAX_AGE_SEC = 12.0


def _v35_get_live_snapshot(symbol: str, max_age: float = V35_MAX_LIVE_AGE_SEC) -> dict[str, Any]:
    """Return the freshest available Binance spot snapshot for one symbol."""
    sym = _normalize_symbol(symbol)
    now = time.time()
    with LIVE_LOCK:
        info = dict(LIVE_PRICES.get(sym) or {})
    px = safe_float(info.get("price"), 0.0)
    ts = safe_float(info.get("ts"), 0.0)
    age = now - ts if ts > 0 else float("inf")
    if px > 0 and age <= float(max_age):
        return {"price": px, "ts": ts, "age_sec": max(0.0, age),
                "source": info.get("source") or "Binance"}

    # The background live engine normally keeps this hot. A direct refresh is
    # the fail-safe for a slow/stopped worker, and is limited to this symbol.
    try:
        fresh = _fetch_live_prices([sym])
        px = safe_float(fresh.get(sym), 0.0)
        if px > 0:
            _register_live_price(sym, px, "REST-direct")
            with LIVE_LOCK:
                info = dict(LIVE_PRICES.get(sym) or {})
            ts = safe_float(info.get("ts"), time.time())
            return {"price": px, "ts": ts,
                    "age_sec": max(0.0, time.time() - ts),
                    "source": info.get("source") or "REST-direct"}
    except Exception as exc:
        LOGGER.debug("V35 direct live snapshot failed %s: %s", sym, exc)

    return {"price": px, "ts": ts, "age_sec": age,
            "source": info.get("source") or "cache", "fresh": False}


def _v35_rebase_price_dependent_outputs(item: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """Make all public price/entry/exit outputs coherent with one live price."""
    if not item or not snapshot:
        return item
    live = safe_float(snapshot.get("price"), 0.0)
    if live <= 0:
        item["live_sync"] = False
        item["live_sync_reason"] = "fresh_live_price_unavailable"
        return item

    now = time.time()
    old = _v29_num_price(item.get("price_raw") or item.get("price"))
    if old <= 0:
        old = live
    ratio = live / old if old > 0 else 1.0

    item.setdefault("signal_snapshot", {})
    if "price" not in item["signal_snapshot"]:
        item["signal_snapshot"]["price"] = old
        item["signal_snapshot"]["timestamp"] = item.get("scan_timestamp", now)

    item["price_raw"] = live
    item["live_price"] = live
    item["entry_raw"] = live
    item["price"] = smart_format(live)
    item["entry_valid"] = smart_format(live)

    # Directional exits are percentage-rebased from the exact signal snapshot.
    # If a final direction was promoted after the original levels were built,
    # rebuild them from the current price and validate orientation/RR first.
    decision = str(item.get("decision_tag") or item.get("decision") or "WAIT").upper()
    if decision in {"LONG", "SHORT"}:
        for key in ("stop_loss", "tp1", "tp2"):
            if key in item:
                item[key] = _v29_shift_price_field(item.get(key), ratio)

        sl = _v29_num_price(item.get("stop_loss"))
        tp1 = _v29_num_price(item.get("tp1"))
        tp2 = _v29_num_price(item.get("tp2"))
        check = _v12_level_integrity(live, sl, tp1, tp2, decision)
        if not check.get("ok"):
            rsl, rtp1, rtp2 = _v12_rebuild_directional_levels(item, decision)
            check2 = _v12_level_integrity(live, rsl, rtp1, rtp2, decision)
            if check2.get("ok"):
                sl, tp1, tp2 = rsl, rtp1, rtp2
                check = check2
                item["level_rebased_by_v35"] = True
            else:
                # Never expose a directional signal with invalid levels.
                item["decision_tag"] = "WAIT"
                item["decision"] = "WAIT"
                item["bias"] = "خنثی"
                item["entry_mode"] = "WAIT"
                item["signal_tag"] = "V35 SAFETY WAIT — LIVE LEVELS INVALID"
                item["level_rebased_by_v35"] = False
                item["live_sync_reason"] = "directional_levels_invalid_after_live_rebase"
                sl = tp1 = tp2 = 0.0
        if sl > 0 and tp1 > 0 and tp2 > 0:
            item["stop_loss_raw"] = float(sl)
            item["tp1_raw"] = float(tp1)
            item["tp2_raw"] = float(tp2)
            item["stop_loss"] = smart_format(sl)
            item["tp1"] = smart_format(tp1)
            item["tp2"] = smart_format(tp2)
            item["rr_tp1"] = check.get("rr1", 0.0)
            item["rr_tp2"] = check.get("rr2", 0.0)
            item["effective_rr_tp1"] = item["rr_tp1"]
            item["effective_rr_tp2"] = item["rr_tp2"]
    else:
        # WAIT has no actionable exit levels. Its entry anchor is always live.
        item["entry_raw"] = live
        item["entry_valid"] = smart_format(live)

    sl = _v29_num_price(item.get("stop_loss"))
    tp1 = _v29_num_price(item.get("tp1"))
    tp2 = _v29_num_price(item.get("tp2"))
    if sl > 0:
        risk = abs(live - sl)
        item["risk_distance_pct"] = round(risk / live * 100.0, 3)
        if risk > 0 and tp1 > 0:
            item["rr_tp1"] = round(abs(tp1 - live) / risk, 3)
            item["effective_rr_tp1"] = item["rr_tp1"]
        if risk > 0 and tp2 > 0:
            item["rr_tp2"] = round(abs(tp2 - live) / risk, 3)
            item["effective_rr_tp2"] = item["rr_tp2"]

    # Keep scenario prices anchored to exactly the same live reference.
    fc = item.get("candle_forecast")
    if isinstance(fc, dict):
        fc["last_price"] = round(live, 8)
        if old > 0 and math.isfinite(ratio) and ratio > 0:
            for candle in fc.get("candles", []) or []:
                if isinstance(candle, dict):
                    for key in ("open", "high", "low", "close", "mid", "band_low", "band_high"):
                        if key in candle:
                            try:
                                candle[key] = round(float(candle[key]) * ratio, 8)
                            except Exception:
                                pass

    age = max(0.0, now - safe_float(snapshot.get("ts"), now))
    item["live_price_source"] = snapshot.get("source") or "Binance"
    item["live_price_ts"] = safe_float(snapshot.get("ts"), now)
    item["live_price_age_sec"] = round(age, 3)
    item["live_sync"] = bool(age <= V35_MAX_LIVE_AGE_SEC)
    item["price_delta_from_scan_pct"] = round((live / old - 1.0) * 100.0, 4) if old > 0 else 0.0
    item["price_sync_version"] = V35_VERSION
    item["price_sync"] = {
        "authoritative_price": live,
        "source": item["live_price_source"],
        "timestamp": item["live_price_ts"],
        "age_sec": item["live_price_age_sec"],
        "entry_anchor": live,
        "levels_rebased": bool(item.get("level_rebased_by_v35", False) or decision in {"LONG", "SHORT"}),
        "single_price_source_for_public_outputs": True,
    }
    return item



# ============================================================
# TITAN V36 — QUANTUM RESONANCE EDGE (magical upgrade layer)
# ------------------------------------------------------------
# Cross-asset resonance, drift-aware confidence decay, and
# multi-horizon agreement score. Analysis-only; never invents
# win probability. Can only demote unsafe signals or modestly
# boost a coherent multi-horizon edge that is already present.
# ============================================================
V36_VERSION = "TITAN-V36-QUANTUM-RESONANCE-EDGE"
V36_DRIFT_KILL_PCT = 1.85
V36_RESONANCE_BOOST_MIN = 0.62
V36_MAX_CONF_BOOST = 6.0
_V36_RESONANCE_CACHE: dict[str, Any] = {"ts": 0.0, "matrix": {}}
_V36_RESONANCE_LOCK = threading.RLock()


def _v36_horizon_agreement(item: dict[str, Any]) -> dict[str, Any]:
    """Score agreement across HTF/MTF/LTF + forecast path + structure."""
    tf = item.get("tf_scores") or item.get("tfs") or {}
    s15 = safe_float(tf.get("15m"), 50.0)
    s1h = safe_float(tf.get("1h"), 50.0)
    s4h = safe_float(tf.get("4h"), 50.0)
    s1d = safe_float(tf.get("1d"), 50.0)
    decision = str(item.get("decision_tag") or item.get("decision") or "WAIT").upper()

    def lean(sc: float) -> float:
        return clamp((sc - 50.0) / 50.0, -1.0, 1.0)

    leans = [lean(s15), lean(s1h), lean(s4h), lean(s1d)]
    fc = item.get("candle_forecast") or {}
    fc_bias = str(fc.get("overall_bias") or "")
    if fc_bias == "صعودی":
        leans.append(0.45)
    elif fc_bias == "نزولی":
        leans.append(-0.45)
    struct = item.get("structure") if isinstance(item.get("structure"), dict) else {}
    sb = str(struct.get("bias") or item.get("structure_bias") or "")
    if sb == "صعودی":
        leans.append(0.40)
    elif sb == "نزولی":
        leans.append(-0.40)

    if not leans:
        return {"agreement": 0.0, "direction": "WAIT", "n": 0}
    mean = sum(leans) / len(leans)
    var = sum((x - mean) ** 2 for x in leans) / max(1, len(leans))
    cohesion = float(clamp(1.0 - (var ** 0.5) * 1.8, 0.0, 1.0))
    magnitude = abs(mean)
    agreement = float(clamp(cohesion * (0.45 + 0.55 * magnitude), 0.0, 1.0))
    direction = "LONG" if mean > 0.08 else "SHORT" if mean < -0.08 else "WAIT"
    aligned = direction == decision if decision in {"LONG", "SHORT"} else False
    return {
        "agreement": round(agreement, 4),
        "mean_lean": round(mean, 4),
        "cohesion": round(cohesion, 4),
        "direction": direction,
        "aligned_with_decision": aligned,
        "n": len(leans),
    }


def _v36_price_drift_gate(item: dict[str, Any]) -> dict[str, Any]:
    """Kill directional signals when live price has run away from the scan snapshot."""
    snap = item.get("signal_snapshot") if isinstance(item.get("signal_snapshot"), dict) else {}
    snap_px = safe_float(snap.get("price"), 0.0)
    live = safe_float(item.get("price_raw") or item.get("live_price"), 0.0)
    decision = str(item.get("decision_tag") or item.get("decision") or "WAIT").upper()
    if snap_px <= 0 or live <= 0 or decision not in {"LONG", "SHORT"}:
        return {"drift_pct": 0.0, "kill": False, "reason": ""}
    drift = (live / snap_px - 1.0) * 100.0
    adverse = (decision == "LONG" and drift > V36_DRIFT_KILL_PCT) or (
        decision == "SHORT" and drift < -V36_DRIFT_KILL_PCT
    )
    extreme = abs(drift) > V36_DRIFT_KILL_PCT * 1.6
    kill = bool(adverse or extreme)
    reason = ""
    if adverse:
        reason = f"adverse_drift_{drift:+.2f}%"
    elif extreme:
        reason = f"extreme_drift_{drift:+.2f}%"
    return {"drift_pct": round(drift, 3), "kill": kill, "reason": reason, "snap": snap_px, "live": live}


def _v36_cross_asset_resonance(symbol: str, decision: str, cache_rows: list) -> dict[str, Any]:
    """Soft portfolio resonance: same-side cluster reduces edge quality."""
    if decision not in {"LONG", "SHORT"} or not cache_rows:
        return {"same_side": 0, "penalty": 0.0, "note": ""}
    majors = {"BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT"}
    sym = _normalize_symbol(symbol)
    same = 0
    for row in cache_rows:
        other = _normalize_symbol(row.get("symbol") or "")
        if other == sym:
            continue
        od = str(row.get("decision_tag") or row.get("decision") or "").upper()
        if od == decision:
            same += 1
    penalty = 0.0
    note = ""
    if same >= 6:
        penalty = 10.0
        note = f"رزونانس سبد: {same} سیگنال هم‌جهت فعال"
    elif same >= 4:
        penalty = 5.0
        note = f"فشار خوشه‌ای: {same} سیگنال هم‌جهت"
    if sym in majors and same >= 3:
        penalty = max(penalty, 4.0)
    return {"same_side": same, "penalty": penalty, "note": note}


def _v36_apply(item: dict[str, Any], cache_rows: Optional[list] = None) -> dict[str, Any]:
    """Quantum Resonance final polish — demote on drift, modest boost on pure agreement."""
    try:
        decision = str(item.get("decision_tag") or item.get("decision") or "WAIT").upper()
        agree = _v36_horizon_agreement(item)
        drift = _v36_price_drift_gate(item)
        resonance = _v36_cross_asset_resonance(
            str(item.get("symbol") or ""), decision, list(cache_rows or [])
        )
        killed = False
        boosted = False
        notes: list[str] = []

        if decision in {"LONG", "SHORT"} and drift.get("kill"):
            item["decision_tag"] = "WAIT"
            item["decision"] = "WAIT"
            item["bias"] = "خنثی"
            item["entry_mode"] = "WAIT"
            item["signal_tag"] = "V36 RESONANCE WAIT — PRICE DRIFT"
            item["central_reason_fa"] = (
                f"قیمت از اسنپ‌شات سیگنال بیش از حد فاصله گرفته ({drift.get('reason')}); "
                "سیگنال جهت‌دار باطل شد."
            )
            killed = True
            notes.append(str(drift.get("reason") or "drift_kill"))

        if not killed and decision in {"LONG", "SHORT"}:
            if (
                agree.get("direction") in {"LONG", "SHORT"}
                and agree.get("direction") != decision
                and agree.get("agreement", 0) >= 0.55
            ):
                item["decision_tag"] = "WAIT"
                item["decision"] = "WAIT"
                item["bias"] = "خنثی"
                item["entry_mode"] = "WAIT"
                item["signal_tag"] = "V36 RESONANCE WAIT — HORIZON DISCORD"
                item["central_reason_fa"] = "اجماع افق‌های زمانی با جهت سیگنال در تضاد است."
                killed = True
                notes.append("horizon_discord")
            elif agree.get("aligned_with_decision") and agree.get("agreement", 0) >= V36_RESONANCE_BOOST_MIN:
                conf = safe_float(item.get("decision_confidence"), 50.0)
                boost = min(V36_MAX_CONF_BOOST, (agree["agreement"] - V36_RESONANCE_BOOST_MIN) * 18.0)
                boost = max(0.0, boost - safe_float(resonance.get("penalty"), 0.0) * 0.35)
                if boost >= 1.0:
                    item["decision_confidence"] = round(clamp(conf + boost, 0.0, 96.0), 1)
                    boosted = True
                    notes.append(f"resonance_boost_+{boost:.1f}")
            if resonance.get("penalty", 0) >= 8 and not killed:
                conf = safe_float(item.get("decision_confidence"), 50.0)
                item["decision_confidence"] = round(max(35.0, conf - resonance["penalty"]), 1)
                notes.append(resonance.get("note") or "cluster_pressure")

        item["v36_resonance"] = {
            "version": V36_VERSION,
            "horizon_agreement": agree,
            "price_drift": drift,
            "cross_asset": resonance,
            "killed": killed,
            "boosted": boosted,
            "notes": notes,
        }
        item.setdefault("fusion", {})["v36_resonance"] = item["v36_resonance"]
        arch = item.get("decision_architecture") if isinstance(item.get("decision_architecture"), dict) else {}
        arch = dict(arch)
        arch["resonance_layer"] = V36_VERSION
        arch["final_decision"] = item.get("decision_tag", "WAIT")
        item["decision_architecture"] = arch
        return item
    except Exception as exc:
        LOGGER.debug("V36 resonance failed: %s", exc)
        item["v36_resonance"] = {"version": V36_VERSION, "error": str(exc)[:180]}
        return item



# ============================================================
# TITAN V40 — FIVE HARD FIXES IN ONE LAYER
# 1) Precision thresholds already applied globally
# 2) Paper integrity already applied
# 3) DB self-heal on startup (corrupt paper + stuck PENDING)
# 4) Unified maintenance brain (central/v32/forecast/journal/paper)
# 5) Final precision gate (history ban + confluence + integrity)
# ============================================================
V40_VERSION = "TITAN-V41-BALANCED-OPPORTUNITY"
V40_MIN_LIVE_AGE = 12.0
V40_MIN_RR1 = 1.10
V40_MIN_RR2 = 1.40
V40_MIN_CONF = 52.0
V40_MIN_AGREE = 0.38
V40_BAN_WR = 30.0
V40_BAN_N = 8
V40_SOFT_WR = 40.0
V40_GLOBAL_SHORT_WR = 35.0
V40_GLOBAL_SHORT_N = 20
V40_LOOKBACK = 250
_V40_HIST: dict[str, Any] = {"ts": 0.0, "by_key": {}, "g_short": {}, "g_long": {}}
_V40_HIST_LOCK = threading.RLock()


def _v40_db_self_heal() -> dict[str, Any]:
    """One-shot hygiene: close corrupt papers, expire impossible PENDING rows."""
    report = {"paper_invalid": 0, "paper_absurd_r": 0, "forecast_expired": 0,
              "v32_expired": 0, "journal_expired": 0, "central_forced": 0}
    now = time.time()
    try:
        with DB_LOCK, db_conn() as con:
            # Corrupt closed papers with exit=0 or |R|>20
            cur = con.execute(
                "SELECT id, entry, exit_price, r_multiple, tp1, sl FROM paper_trades WHERE status='CLOSED'"
            ).fetchall()
            for row in cur:
                rid = row[0]
                entry = safe_float(row[1], 0)
                exit_px = safe_float(row[2], 0)
                r_mult = safe_float(row[3], 0)
                tp1 = safe_float(row[4], 0)
                sl = safe_float(row[5], 0)
                bad = False
                reason = None
                if tp1 <= 0 or sl <= 0 or entry <= 0:
                    bad, reason = True, "INVALID_LEVELS_HEALED"
                elif exit_px <= 0:
                    bad, reason = True, "INVALID_EXIT_HEALED"
                elif abs(r_mult) > 8:
                    bad, reason = True, "ABSURD_R_HEALED"
                if bad:
                    con.execute(
                        "UPDATE paper_trades SET pnl_pct=0, r_multiple=0, reason=?, exit_price=? WHERE id=?",
                        (reason, entry if exit_px <= 0 else exit_px, rid),
                    )
                    report["paper_absurd_r" if "R" in (reason or "") else "paper_invalid"] += 1
            # Open papers with invalid levels
            for row in con.execute("SELECT id, entry, sl, tp1 FROM paper_trades WHERE status='OPEN'").fetchall():
                if safe_float(row[1], 0) <= 0 or safe_float(row[2], 0) <= 0 or safe_float(row[3], 0) <= 0:
                    con.execute(
                        "UPDATE paper_trades SET status='CLOSED', exit_price=?, pnl_pct=0, r_multiple=0, closed_at=?, reason=? WHERE id=?",
                        (safe_float(row[1], 0), now, "INVALID_LEVELS", row[0]),
                    )
                    report["paper_invalid"] += 1
            # Forecasts stuck PENDING past horizon+1h → MISS
            for row in con.execute(
                "SELECT id, created_at, horizon_minutes FROM forecasts WHERE outcome='PENDING'"
            ).fetchall():
                end = safe_float(row[1], 0) + int(row[2] or 240) * 60 + 3600
                if now >= end:
                    con.execute(
                        "UPDATE forecasts SET outcome='MISS', evaluated_at=?, hit_type='HEALED_EXPIRE' WHERE id=?",
                        (now, row[0]),
                    )
                    report["forecast_expired"] += 1
            # V32 audit stuck past horizon+2h
            try:
                for row in con.execute(
                    "SELECT id, created_at, horizon_minutes FROM v32_forecast_audit WHERE outcome='PENDING'"
                ).fetchall():
                    end = safe_float(row[1], 0) + int(row[2] or 240) * 60 + 7200
                    if now >= end:
                        con.execute(
                            "UPDATE v32_forecast_audit SET outcome='EXPIRED', evaluated_at=?, return_pct=0 WHERE id=?",
                            (now, row[0]),
                        )
                        report["v32_expired"] += 1
            except Exception:
                pass
            # V22 journal PENDING older than 6h → EXPIRED
            try:
                for row in con.execute(
                    "SELECT id, created_at FROM decision_journal_v22 WHERE outcome='PENDING'"
                ).fetchall():
                    if now - safe_float(row[1], 0) > 6 * 3600:
                        con.execute(
                            "UPDATE decision_journal_v22 SET outcome='EXPIRED' WHERE id=?",
                            (row[0],),