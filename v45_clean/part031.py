                edge_lab_version TEXT
            )""")
            con.execute("""CREATE TABLE IF NOT EXISTS central_model_registry(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_name TEXT NOT NULL,
                version TEXT NOT NULL,
                role TEXT NOT NULL,
                weights_json TEXT,
                sample_count INTEGER DEFAULT 0,
                win_rate REAL,
                expectancy_pct REAL,
                profit_factor REAL,
                status TEXT DEFAULT 'CANDIDATE',
                created_at REAL,
                promoted_at REAL,
                UNIQUE(model_name,version)
            )""")
            con.execute("""CREATE TABLE IF NOT EXISTS central_overlap_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at REAL,
                symbol TEXT,
                decision TEXT,
                blocked INTEGER,
                reason TEXT,
                pending_same_symbol INTEGER,
                pending_same_side INTEGER
            )""")
            con.execute("CREATE INDEX IF NOT EXISTS idx_ctm_regime ON central_trade_metrics(regime)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_ctm_eval ON central_trade_metrics(evaluated_at)")
            con.commit()
    except Exception as exc:
        LOGGER.debug("edge lab schema: %s", exc)


def _edge_regime_from_window(window) -> tuple[str, float, float]:
    """Derive a conservative realized regime from the exact evaluation window."""
    try:
        closes = window["close"].astype(float).dropna()
        if len(closes) < 4:
            return "unknown", 0.0, 0.0
        rets = closes.pct_change().dropna()
        vol_pct = float(np.std(rets) * math.sqrt(max(1, len(rets))) * 100.0)
        base = max(float(closes.iloc[0]), 1e-12)
        slope_pct = float((float(closes.iloc[-1]) / base - 1.0) * 100.0)
        if vol_pct >= 3.0:
            regime = "high_volatility"
        elif slope_pct >= 1.2:
            regime = "trend_up"
        elif slope_pct <= -1.2:
            regime = "trend_down"
        else:
            regime = "range"
        strength = clamp(abs(slope_pct) / max(vol_pct, 0.25) * 50.0, 0.0, 100.0)
        return regime, vol_pct, strength
    except Exception:
        return "unknown", 0.0, 0.0


def _edge_first_touch_detail(window, decision: str, sl: float, tp1: float, tp2: float):
    """Return first touch type/price/time; same conservative ambiguity rule."""
    for _, r in window.iterrows():
        hi = safe_float(r.get("high"), 0.0); lo = safe_float(r.get("low"), 0.0)
        ts = safe_float(r.get("t"), 0.0) / 1000.0
        if decision == "LONG":
            sl_hit = sl > 0 and lo <= sl
            tp_hit = tp1 > 0 and hi >= tp1
            if sl_hit and tp_hit:
                return "AMBIGUOUS", None, ts
            if sl_hit:
                return "LOSS", sl, ts
            if tp_hit:
                return "WIN", tp1, ts
        else:
            sl_hit = sl > 0 and hi >= sl
            tp_hit = tp1 > 0 and lo <= tp1
            if sl_hit and tp_hit:
                return "AMBIGUOUS", None, ts
            if sl_hit:
                return "LOSS", sl, ts
            if tp_hit:
                return "WIN", tp1, ts
    return "TIME_EXIT", None, None


def _edge_calibrate_central(raw_conf: float, direction: str = "", symbol: str = "") -> dict[str, Any]:
    """Calibrate central confidence only from already-realized historical central labels."""
    raw = float(clamp(raw_conf, 5.0, 95.0))
    pairs = []
    try:
        with DB_LOCK, db_conn() as con:
            rows = con.execute(
                "SELECT confidence,outcome FROM central_predictions "
                "WHERE outcome IN ('WIN','LOSS') AND confidence IS NOT NULL "
                "ORDER BY evaluated_at ASC,id ASC LIMIT 1200"
            ).fetchall()
        for conf, out in rows:
            pairs.append((clamp(safe_float(conf, 50.0)/100.0, 0.01, 0.99), 1.0 if out == "WIN" else 0.0))
    except Exception:
        pairs = []
    if len(pairs) < 20:
        return {"raw": round(raw,1), "calibrated": None, "samples": len(pairs),
                "method":"insufficient_history", "is_calibrated":False}
    probs=[x for x,_ in pairs]; labels=[y for _,y in pairs]
    platt=_platt_scale(probs, labels, raw/100.0)
    # 12-bin weighted isotonic estimate.
    bins=[]
    for k in range(12):
        lo=k/12; hi=(k+1)/12
        vals=[y for x,y in pairs if lo <= x < hi or (k==11 and lo <= x <= hi)]
        if vals:
            bins.append((lo+hi/2, (sum(vals)+2)/(len(vals)+4), len(vals)))
    iso=None
    if bins:
        xs=[b[0] for b in bins]; ys=[b[1] for b in bins]; ws=[b[2] for b in bins]
        iy=_pava_isotonic(xs,ys,ws)
        x=raw/100.0
        if x <= xs[0]: iso=iy[0]
        elif x >= xs[-1]: iso=iy[-1]
        else:
            for j in range(len(xs)-1):
                if xs[j] <= x <= xs[j+1]:
                    t=(x-xs[j])/max(xs[j+1]-xs[j],1e-12)
                    iso=iy[j]+t*(iy[j+1]-iy[j]); break
    vals=[v for v in (platt,iso) if v is not None]
    if not vals:
        return {"raw":round(raw,1),"calibrated":None,"samples":len(pairs),"method":"failed","is_calibrated":False}
    cal=clamp(float(np.mean(vals))*100.0, 5.0, 88.0)
    # Shrink extreme estimates until the sample is large enough.
    if len(pairs) < 60: cal=50.0+(cal-50.0)*0.70
    elif len(pairs) < 120: cal=50.0+(cal-50.0)*0.85
    return {"raw":round(raw,1),"calibrated":round(cal,1),"samples":len(pairs),
            "method":"platt+isotonic_online", "is_calibrated":True}


def _edge_overlap_gate(symbol: str, candidate: str) -> dict[str, Any]:
    """Block duplicate active setups and cap same-side portfolio concentration."""
    if candidate not in {"LONG","SHORT"}:
        return {"ok":True,"reason":"","same_symbol":0,"same_side":0}
    same_symbol=same_side=0
    try:
        with DB_LOCK, db_conn() as con:
            same_symbol=int(con.execute(
                "SELECT COUNT(*) FROM central_predictions WHERE outcome='PENDING' AND symbol=?",(symbol,)
            ).fetchone()[0])
            same_side=int(con.execute(
                "SELECT COUNT(*) FROM central_predictions WHERE outcome='PENDING' AND decision=?",(candidate,)
            ).fetchone()[0])
            blocked = same_symbol >= EDGE_MAX_PENDING_PER_SYMBOL or same_side >= EDGE_MAX_PENDING_SAME_SIDE
            reason = (f"سیگنال فعال تکراری برای {symbol}" if same_symbol >= EDGE_MAX_PENDING_PER_SYMBOL
                      else f"تراکم سیگنال {candidate}: {same_side} نمونه فعال" if same_side >= EDGE_MAX_PENDING_SAME_SIDE else "")
            if not con.execute("SELECT 1 FROM central_overlap_log WHERE symbol=? AND decision=? AND created_at>? LIMIT 1",
                               (symbol, candidate, time.time() - 30)).fetchone():
                con.execute("INSERT INTO central_overlap_log(created_at,symbol,decision,blocked,reason,pending_same_symbol,pending_same_side) VALUES(?,?,?,?,?,?,?)",
                            (time.time(),symbol,candidate,int(blocked),reason,same_symbol,same_side))
            con.commit()
            return {"ok":not blocked,"reason":reason,"same_symbol":same_symbol,"same_side":same_side}
    except Exception:
        return {"ok":True,"reason":"","same_symbol":0,"same_side":0}


def _edge_performance_report() -> dict[str, Any]:
    """Friction-aware expectancy/PF plus regime and attribution summaries."""
    out={"samples":0,"win_rate":None,"expectancy_pct":None,"profit_factor":None,"regimes":{},"components":{}}
    try:
        with DB_LOCK, db_conn() as con:
            rows=con.execute("SELECT outcome,net_return_pct,r_multiple,regime FROM central_trade_metrics JOIN central_predictions ON central_predictions.id=central_trade_metrics.prediction_id WHERE outcome IN ('WIN','LOSS') ORDER BY evaluated_at ASC").fetchall()
            out["samples"]=len(rows)
            rs=[safe_float(r[1],0) for r in rows]; rms=[safe_float(r[2],0) for r in rows]
            wins=[x for x in rs if x>0]; losses=[abs(x) for x in rs if x<0]
            out["win_rate"]=round(sum(1 for r in rows if r[0]=='WIN')/max(1,len(rows))*100,2)
            out["expectancy_pct"]=round(float(np.mean(rs)),4) if rs else None
            out["profit_factor"]=round(sum(wins)/max(sum(losses),1e-9),3) if losses else (None if not wins else 99.0)
            for regime in sorted({str(r[3] or 'unknown') for r in rows}):
                rr=[safe_float(r[1],0) for r in rows if str(r[3] or 'unknown')==regime]
                out["regimes"][regime]={"samples":len(rr),"expectancy_pct":round(float(np.mean(rr)),4) if rr else None,
                    "win_rate":round(sum(1 for x in rr if x>0)/max(1,len(rr))*100,2)}
            comp=con.execute("SELECT component,samples,wins,losses,reward_sum,penalty_sum,weight FROM central_component_stats ORDER BY component").fetchall()
            for r in comp:
                out["components"][r[0]]={"samples":r[1],"wins":r[2],"losses":r[3],"reward":round(safe_float(r[4]),3),"penalty":round(safe_float(r[5]),3),"weight":round(safe_float(r[6]),4)}
    except Exception as exc:
        out["error"]=str(exc)[:180]
    return out


def _edge_monte_carlo(runs: int = EDGE_MC_RUNS) -> dict[str, Any]:
    """Bootstrap/shuffle risk envelope from realized net R-multiples."""
    try:
        with DB_LOCK, db_conn() as con:
            vals=[safe_float(r[0]) for r in con.execute("SELECT r_multiple FROM central_trade_metrics WHERE r_multiple IS NOT NULL ORDER BY evaluated_at").fetchall()]
        vals=[v for v in vals if math.isfinite(v)]
        if len(vals)<20: return {"samples":len(vals),"runs":0,"status":"insufficient"}
        rng=np.random.default_rng(29)
        finals=[]; max_dd=[]
        for _ in range(int(max(100,min(runs,10000)))):
            seq=rng.choice(vals,size=len(vals),replace=True)
            eq=np.cumsum(seq); peak=np.maximum.accumulate(np.r_[0.0,eq]); dd=peak[1:]-eq
            finals.append(float(eq[-1])); max_dd.append(float(np.max(dd)) if len(dd) else 0.0)
        return {"samples":len(vals),"runs":len(finals),"status":"ok",
                "final_r_p50":round(float(np.percentile(finals,50)),3),
                "final_r_p05":round(float(np.percentile(finals,5)),3),
                "final_r_p95":round(float(np.percentile(finals,95)),3),
                "max_dd_r_p50":round(float(np.percentile(max_dd,50)),3),
                "max_dd_r_p95":round(float(np.percentile(max_dd,95)),3)}
    except Exception as exc:
        return {"status":"error","error":str(exc)[:180]}


def _edge_champion_challenger() -> dict[str, Any]:
    """Keep a reproducible registry; challenger never silently changes live weights."""
    report=_edge_performance_report(); now=time.time()
    try:
        with DB_LOCK, db_conn() as con:
            weights=json.dumps(_CENTRAL_WEIGHTS,ensure_ascii=False,sort_keys=True)
            con.execute("INSERT OR IGNORE INTO central_model_registry(model_name,version,role,weights_json,sample_count,win_rate,expectancy_pct,profit_factor,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        ("TITAN_CENTRAL","V29.5-LIVE","CHAMPION",weights,report.get("samples",0),report.get("win_rate"),report.get("expectancy_pct"),report.get("profit_factor"),"LIVE",now))
            con.execute("INSERT OR IGNORE INTO central_model_registry(model_name,version,role,weights_json,status,created_at) VALUES(?,?,?,?,?,?)",
                        ("TITAN_CENTRAL","V29.5-CHALLENGER","CHALLENGER",weights,"SHADOW",now))
            con.commit()
        return {"champion":"V29.5-LIVE","challenger":"V29.5-CHALLENGER","promotion":"manual_after_OOS_validation","metrics":report}
    except Exception as exc:
        return {"error":str(exc)[:180]}


def _edge_walk_forward_report(train_frac: float = 0.60, test_frac: float = 0.20,
                               embargo_minutes: int = 240) -> dict[str, Any]:
    """Chronological, purged/embargoed stability check on realized central trades.

    This does not pretend to be a full historical strategy backtest: it measures
    whether realized central outcomes remain stable when later observations are
    kept out of the earlier training window.
    """
    try:
        with DB_LOCK, db_conn() as con:
            rows=con.execute("SELECT p.created_at,p.outcome,m.net_return_pct,m.r_multiple,p.confidence "
                             "FROM central_predictions p JOIN central_trade_metrics m ON m.prediction_id=p.id "
                             "WHERE p.outcome IN ('WIN','LOSS') ORDER BY p.created_at ASC,p.id ASC").fetchall()
        n=len(rows)
        if n < 30:
            return {"status":"insufficient","samples":n,"minimum":30}
        cut1=max(10,int(n*train_frac)); cut2=min(n-10,int(n*(train_frac+test_frac)))
        if cut2<=cut1: return {"status":"insufficient","samples":n}
        train=list(rows[:cut1]); test=list(rows[cut2:])
        # Purge test observations too close to the end of training.
        train_end=safe_float(train[-1][0],0)
        test=[r for r in test if safe_float(r[0],0) >= train_end + embargo_minutes*60]
        def stats(rr):
            vals=[safe_float(r[2],0) for r in rr]
            if not vals:return {"samples":0,"expectancy_pct":None,"win_rate":None,"profit_factor":None}
            gains=sum(v for v in vals if v>0); losses=abs(sum(v for v in vals if v<0))
            return {"samples":len(vals),"expectancy_pct":round(float(np.mean(vals)),4),
                    "win_rate":round(sum(v>0 for v in vals)/len(vals)*100,2),
                    "profit_factor":round(gains/max(losses,1e-9),3) if losses else 99.0}
        return {"status":"ok","samples":n,"embargo_minutes":embargo_minutes,
                "train":stats(train),"test":stats(test),
                "purged":True,"note":"فقط برای سنجش پایداری realized outcomes؛ تضمین عملکرد آینده نیست."}
    except Exception as exc:
        return {"status":"error","error":str(exc)[:180]}


def _edge_api_report() -> dict[str, Any]:
    return {"ok":True,"version":EDGE_LAB_VERSION,"metrics":_edge_performance_report(),
            "monte_carlo":_edge_monte_carlo(),"governance":_edge_champion_challenger(),
            "walk_forward":_edge_walk_forward_report(),
            "friction":{"fee_rate":FEE_RATE,"spread_rate":SPREAD_RATE,"slippage_rate":SLIPPAGE_RATE,
                         "round_trip_pct":round(TOTAL_ENTRY_BUFFER*2*100,4)},
            "note":"کالیبراسیون و عملکرد فقط بر مبنای نمونه‌های realized گذشته است؛ پیش‌بینی تضمینی نیست."}


def _central_init_schema() -> None:
    try:
        with DB_LOCK, db_conn() as con:
            con.execute(
                """CREATE TABLE IF NOT EXISTS central_predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at REAL NOT NULL,
                    symbol TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    bias TEXT,
                    price REAL,
                    stop_loss REAL,
                    tp1 REAL,
                    tp2 REAL,
                    confidence REAL,
                    score REAL,
                    margin REAL,
                    reasons_json TEXT,
                    components_json TEXT,
                    weights_json TEXT,
                    horizon_minutes INTEGER DEFAULT 240,
                    outcome TEXT DEFAULT 'PENDING',
                    evaluated_at REAL,
                    return_pct REAL,
                    lesson TEXT,
                    version TEXT
                )"""
            )
            con.execute(
                """CREATE TABLE IF NOT EXISTS central_component_stats (
                    component TEXT PRIMARY KEY,
                    samples INTEGER DEFAULT 0,
                    wins INTEGER DEFAULT 0,
                    losses INTEGER DEFAULT 0,
                    reward_sum REAL DEFAULT 0,
                    penalty_sum REAL DEFAULT 0,
                    weight REAL DEFAULT 1.0,
                    updated_at REAL
                )"""
            )
            con.execute(
                """CREATE TABLE IF NOT EXISTS central_arbiter_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at REAL,
                    symbol TEXT,
                    decision TEXT,
                    verdict TEXT,
                    score REAL,
                    notes TEXT
                )"""
            )
            con.commit()
    except Exception as exc:
        LOGGER.debug("central schema: %s", exc)


def _central_load_weights() -> None:
    global _CENTRAL_WEIGHTS
    try:
        with DB_LOCK, db_conn() as con:
            rows = con.execute(
                "SELECT component,samples,wins,losses,reward_sum,penalty_sum,weight FROM central_component_stats"
            ).fetchall()
        weights = dict(_CENTRAL_WEIGHTS_DEFAULT)
        for row in rows:
            name, samples, wins, losses, reward, penalty, w = row
            # Ignore components from retired decision generations.  Otherwise an
            # old DB can silently resurrect removed/circular voters.
            if name not in _CENTRAL_WEIGHTS_DEFAULT:
                continue
            n = int(samples or 0)
            if n >= 12:
                wr = (wins or 0) / max(1, (wins or 0) + (losses or 0))
                reliability = clamp(0.55 + (wr - 0.5) * 1.4, 0.35, 1.55)
                # mild reward/penalty tilt
                tilt = 1.0 + 0.04 * safe_float(reward, 0) - 0.05 * safe_float(penalty, 0)
                w = clamp(safe_float(_CENTRAL_WEIGHTS_DEFAULT.get(name), 1.0) * reliability * tilt, 0.25, 2.4)
            else:
                w = safe_float(_CENTRAL_WEIGHTS_DEFAULT.get(name), 1.0)
            weights[name] = float(w)
        with _CENTRAL_WEIGHT_LOCK:
            _CENTRAL_WEIGHTS = weights
    except Exception as exc:
        LOGGER.debug("central weight load: %s", exc)


_central_init_schema()
_edge_lab_init_schema()
_central_load_weights()


def _central_votes(item: dict[str, Any]) -> dict[str, dict[str, Any]]:
    votes: dict[str, dict[str, Any]] = {}
    tf = item.get("tf_scores") or item.get("tfs") or {}
    s15 = safe_float(tf.get("15m"), 50.0)
    s1h = safe_float(tf.get("1h"), 50.0)
    s4h = safe_float(tf.get("4h"), 50.0)
    s1d = safe_float(tf.get("1d"), 50.0)
    htf = 0.55 * s4h + 0.45 * s1d
    mtf = s1h
    ltf = s15

    def _from_score(sc: float) -> tuple[float, float, str]:
        lean = clamp((sc - 50.0) / 50.0, -1.0, 1.0)
        conf = clamp(abs(sc - 50.0) / 50.0, 0.0, 1.0)
        side = "LONG" if lean > 0.08 else "SHORT" if lean < -0.08 else "WAIT"
        return lean, conf, side

    for key, sc, label in (
        ("htf_trend", htf, "روند کلان 4h/1d"),
        ("mtf_setup", mtf, "ستاپ 1h"),
        ("ltf_trigger", ltf, "تریگر 15m"),
    ):
        lean, conf, side = _from_score(sc)
        votes[key] = {"lean": lean, "confidence": conf, "side": side, "raw": sc, "label": label}

    score = safe_float(item.get("score"), 50.0)
    lean, conf, side = _from_score(score)
    votes["momentum"] = {"lean": lean, "confidence": conf, "side": side, "raw": score, "label": "مومنتوم هسته"}

    structure = item.get("structure") or {}
    sb = str(structure.get("bias") or item.get("structure_bias") or item.get("bias") or "")
    if sb in {"صعودی", "LONG"}:
        lean, conf = 0.55, 0.55
    elif sb in {"نزولی", "SHORT"}:
        lean, conf = -0.55, 0.55
    else:
        lean, conf = 0.0, 0.2
    votes["structure"] = {
        "lean": lean, "confidence": conf,
        "side": "LONG" if lean > 0 else "SHORT" if lean < 0 else "WAIT",
        "raw": sb or "خنثی", "label": "ساختار قیمت",
    }

    taker_buy = safe_float(item.get("taker_buy_pct"), 50.0)
    if taker_buy == 50 and isinstance(item.get("buy_sell"), dict):
        taker_buy = safe_float((item.get("buy_sell") or {}).get("buy_pct"), 50.0)
    vol_lean = clamp((taker_buy - 50.0) / 35.0, -1.0, 1.0)
    votes["volume_flow"] = {
        "lean": vol_lean,
        "confidence": clamp(abs(taker_buy - 50.0) / 35.0, 0.0, 1.0),
        "side": "LONG" if vol_lean > 0.12 else "SHORT" if vol_lean < -0.12 else "WAIT",
        "raw": taker_buy, "label": "جریان حجم",
    }

    deriv = item.get("derivatives") if isinstance(item.get("derivatives"), dict) else {}
    funding = safe_float(item.get("funding_value"), safe_float(deriv.get("funding_value"), 0.0))
    oi_delta = safe_float(item.get("oi_delta"), safe_float(deriv.get("oi_delta"), 0.0))
    fund_lean = clamp(-funding * 8.0, -1.0, 1.0)
    oi_lean = clamp(oi_delta / 8.0, -1.0, 1.0)
    d_lean = clamp(0.6 * fund_lean + 0.4 * oi_lean, -1.0, 1.0)
    votes["derivatives"] = {
        "lean": d_lean, "confidence": clamp(abs(d_lean), 0.0, 1.0),
        "side": "LONG" if d_lean > 0.12 else "SHORT" if d_lean < -0.12 else "WAIT",
        "raw": {"funding": funding, "oi_delta": oi_delta}, "label": "مشتقات",
    }

    patterns = item.get("patterns") or item.get("pattern_pack") or {}
    pbias = safe_float(patterns.get("score_bias") if isinstance(patterns, dict) else 0.0, safe_float(item.get("pattern_bias"), 0.0))
    p_lean = clamp(pbias / 4.0, -1.0, 1.0)
    votes["pattern"] = {
        "lean": p_lean, "confidence": clamp(abs(p_lean), 0.0, 1.0),
        "side": "LONG" if p_lean > 0.15 else "SHORT" if p_lean < -0.15 else "WAIT",
        "raw": pbias, "label": "الگوی نموداری",
    }

    fc = item.get("candle_forecast") or item.get("forecast") or {}
    fc_bias = str(fc.get("overall_bias") or "")
    if fc_bias == "صعودی":
        f_lean, f_conf = 0.45, 0.4
    elif fc_bias == "نزولی":
        f_lean, f_conf = -0.45, 0.4
    else:
        f_lean, f_conf = 0.0, 0.15
    path_strength = safe_float(fc.get("path_strength"), 0.0) / 40.0
    f_conf = clamp(f_conf + path_strength * 0.3, 0.0, 1.0)
    votes["forecast_path"] = {
        "lean": f_lean, "confidence": f_conf,
        "side": "LONG" if f_lean > 0 else "SHORT" if f_lean < 0 else "WAIT",
        "raw": fc_bias or "خنثی", "label": "مسیر پیش‌بینی",
    }

    # Do NOT vote the previous canonical decision back into the new canonical
    # decision.  It is derived from many of the same inputs and would create
    # circular reinforcement.  It remains available in the audit payload only.

    learning = item.get("v32_learning") or {}
    long_adj = safe_float(learning.get("long_adjustment"), 0.0)
    short_adj = safe_float(learning.get("short_adjustment"), 0.0)
    learn_lean = clamp((long_adj - short_adj) / 8.0, -1.0, 1.0)
    votes["learning_v32"] = {
        "lean": learn_lean,
        "confidence": clamp(abs(learn_lean), 0.0, 1.0),
        "side": "LONG" if learn_lean > 0.12 else "SHORT" if learn_lean < -0.12 else "WAIT",
        "raw": {"long_adj": long_adj, "short_adj": short_adj},
        "label": "یادگیری تاریخی",
    }

    ai = item.get("ai_ensemble") or item.get("ai_opinions") or (item.get("edge") or {}).get("ai") or {}
    ai_side = str(ai.get("majority") or ai.get("side") or item.get("ai_majority") or "WAIT").upper()
    if ai_side in {"صعودی", "BUY", "LONG"}:
        a_lean, a_side = 0.5, "LONG"
    elif ai_side in {"نزولی", "SELL", "SHORT"}:
        a_lean, a_side = -0.5, "SHORT"
    else:
        a_lean, a_side = 0.0, "WAIT"
    a_conf = clamp(safe_float(ai.get("agreement"), 0.0) / 100.0, 0.0, 1.0)
    votes["ai_vote"] = {
        "lean": a_lean, "confidence": max(a_conf, 0.15 if a_side != "WAIT" else 0.05),
        "side": a_side, "raw": ai_side, "label": "رأی AI",
    }

    dq = item.get("data_quality") or {}
    trust = safe_float(dq.get("score"), safe_float(item.get("data_trust"), safe_float(item.get("trust_index"), 70.0)))
    votes["data_trust"] = {
        "lean": 0.0, "confidence": clamp(trust / 100.0, 0.0, 1.0),
        "side": "WAIT", "raw": trust, "label": "اعتماد داده", "trust": trust,
    }
    return votes


def _central_decide(item: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    votes = _central_votes(item)
    with _CENTRAL_WEIGHT_LOCK:
        weights = dict(_CENTRAL_WEIGHTS)

    long_score = short_score = weight_sum = 0.0
    details = []
    for name, v in votes.items():
        if name == "data_trust":
            continue
        w = safe_float(weights.get(name), 1.0)