                    ),
                )

            # Learning samples must represent distinct setups, not scan frequency.
            if decision not in {"LONG", "SHORT"}:
                con.commit()
                return

            recent = con.execute(
                """SELECT 1 FROM central_predictions
                   WHERE symbol=? AND created_at>=?
                   LIMIT 1""",
                (symbol, now - SIGNAL_COOLDOWN_SECONDS),
            ).fetchone()
            if recent:
                con.commit()
                return

            con.execute(
                """INSERT INTO central_predictions(
                    created_at,symbol,decision,bias,price,stop_loss,tp1,tp2,confidence,score,margin,
                    reasons_json,components_json,weights_json,horizon_minutes,outcome,version)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    now,
                    symbol,
                    decision,
                    item.get("bias"),
                    safe_float(item.get("price_raw"), safe_float(str(item.get("price") or "0").replace(",", ""), 0.0)),
                    safe_float(item.get("stop_loss_raw"), safe_float(str(item.get("stop_loss") or "0").replace(",", ""), 0.0)) or None,
                    safe_float(item.get("tp1_raw"), safe_float(str(item.get("tp1") or "0").replace(",", ""), 0.0)) or None,
                    safe_float(item.get("tp2_raw"), safe_float(str(item.get("tp2") or "0").replace(",", ""), 0.0)) or None,
                    safe_float(meta.get("confidence"), 0.0),
                    safe_float(item.get("score"), 50.0),
                    safe_float(meta.get("margin"), 0.0),
                    json.dumps(meta.get("reasons") or [], ensure_ascii=False),
                    json.dumps(meta.get("components") or [], ensure_ascii=False, default=str),
                    json.dumps(meta.get("weights") or {}, ensure_ascii=False),
                    240,
                    "PENDING",
                    TITAN_CENTRAL_VERSION,
                ),
            )
            con.commit()
    except Exception as exc:
        LOGGER.debug("central record: %s", exc)


def _central_evaluate_pending() -> dict[str, Any]:
    """Evaluate predictions only inside their original, exact forward horizon.

    The old evaluator fetched the latest candles after the horizon and therefore
    could accidentally judge a 4-hour prediction using price action from much
    later.  It also used max/min over the whole window, which cannot tell which
    barrier was touched first.  This version uses a bounded OHLC window and the
    same chronological first-touch logic used by paper trades.
    """
    done = 0
    try:
        now = time.time()
        with DB_LOCK, db_conn() as con:
            rows = con.execute(
                """SELECT id,created_at,symbol,decision,price,stop_loss,tp1,tp2,
                          horizon_minutes,components_json,confidence
                   FROM central_predictions
                   WHERE outcome='PENDING' AND created_at<=?
                   ORDER BY created_at LIMIT 200""",
                (now - 60,),
            ).fetchall()

        for row in rows:
            (rid, created, symbol, decision, entry, sl, tp1, tp2,
             horizon, comp_json, prediction_confidence) = row
            created = float(created)
            horizon = int(horizon or 240)
            horizon_end = created + horizon * 60.0
            if now < horizon_end:
                continue

            entry = safe_float(entry, 0.0)
            if entry <= 0 or decision not in {"LONG", "SHORT"}:
                continue

            start_ms = int(created * 1000)
            end_ms = int(horizon_end * 1000)

            try:
                bars_needed = max(20, min(1000, int(math.ceil(horizon / 15.0)) + 4))
                df = fetch_klines(
                    str(symbol), "15m", bars_needed,
                    start_ms=start_ms, end_ms=end_ms,
                )
                if df is None or df.empty or "t" not in df.columns:
                    continue
                window = df[
                    (df["t"].astype(float) >= start_ms) &
                    (df["t"].astype(float) < end_ms)
                ].sort_values("t")
                if window.empty:
                    continue
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