# ============================================================
# AUTONOMOUS PERFORMANCE SNAPSHOT ENGINE
# ============================================================

PERFORMANCE_AUTO_INTERVAL_SECONDS = 300
PERFORMANCE_SYMBOLS_PER_RUN = 3
_PERFORMANCE_LOCK = threading.Lock()
_PERFORMANCE_LAST_RUN = 0.0
_PERFORMANCE_CURSOR = 0
_PERFORMANCE_LAST_RESULT: dict[str, Any] = {"ok": True, "status": "never_run", "completed": 0, "failed": 0}


def _store_performance_snapshot(symbol: str, tf: str, result: dict[str, Any]) -> None:
    if not isinstance(result, dict) or not result.get("ok"):
        return
    m = result.get("metrics") or {}
    oos = (((result.get("professional") or {}).get("oos") or {}).get("status")
           or ((result.get("professional") or {}).get("out_of_sample") or {}).get("status") or "")
    payload = json.dumps(result, ensure_ascii=False, default=str)
    with DB_LOCK, db_conn() as con:
        con.execute(
            """INSERT INTO performance_snapshots(
                symbol,timeframe,created_at,trades,wins,losses,win_rate,expectancy,
                profit_factor,max_drawdown,sharpe,sortino,oos_status,metrics_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                _normalize_symbol(symbol), str(tf), time.time(),
                int(safe_float(m.get("trades"), 0)),
                int(safe_float(m.get("wins"), 0)),
                int(safe_float(m.get("losses"), 0)),
                safe_float(m.get("win_rate"), 0),
                safe_float(m.get("expectancy"), 0),
                safe_float(m.get("profit_factor"), 0) if m.get("profit_factor") is not None else None,
                safe_float(m.get("max_drawdown"), 0),
                safe_float(m.get("sharpe"), 0),
                safe_float(m.get("sortino"), 0),
                str(oos),
                payload[-120000:],
            ),
        )


def autonomous_performance_maintenance(force: bool = False) -> dict[str, Any]:
    """Continuously build auditable backtest history without browser interaction.

    This is deliberately throttled for Android: a small rotating subset of coins
    is evaluated each cycle, while all timeframes are covered for those coins.
    """
    global _PERFORMANCE_LAST_RUN, _PERFORMANCE_CURSOR, _PERFORMANCE_LAST_RESULT
    now = time.time()
    if not force and now - _PERFORMANCE_LAST_RUN < PERFORMANCE_AUTO_INTERVAL_SECONDS:
        return {"ok": True, "skipped": True, "reason": "interval"}
    if not _PERFORMANCE_LOCK.acquire(blocking=False):
        return {"ok": True, "skipped": True, "reason": "already_running"}
    try:
        _PERFORMANCE_LAST_RUN = now
        coins = list(USER_SETTINGS.get("active_coins") or DEFAULT_COINS)
        if not coins:
            return {"ok": False, "error": "no active coins"}
        start = _PERFORMANCE_CURSOR % len(coins)
        selected = [coins[(start + i) % len(coins)] for i in range(min(PERFORMANCE_SYMBOLS_PER_RUN, len(coins)))]
        _PERFORMANCE_CURSOR = (start + len(selected)) % len(coins)
        summary = {"ok": True, "symbols": selected, "timeframes": list(TF_CFG), "completed": 0, "failed": 0, "started_at": now}
        for sym in selected:
            for tf in TF_CFG:
                try:
                    result = backtest_signal_logic(_normalize_symbol(sym), tf, 800)
                    if result.get("ok"):
                        _store_performance_snapshot(sym, tf, result)
                        summary["completed"] += 1
                    else:
                        summary["failed"] += 1
                except Exception as exc:
                    summary["failed"] += 1
                    LOGGER.debug("Autonomous performance %s %s failed: %s", sym, tf, exc)
        # Retain bounded history; raw metrics are also available in the latest rows.
        with DB_LOCK, db_conn() as con:
            con.execute(
                "DELETE FROM performance_snapshots WHERE id NOT IN "
                "(SELECT id FROM performance_snapshots ORDER BY created_at DESC LIMIT 5000)"
            )
        summary["finished_at"] = time.time()
        summary["elapsed_sec"] = round(summary["finished_at"] - now, 2)
        summary["status"] = "complete" if summary["failed"] == 0 else "partial"
        _PERFORMANCE_LAST_RESULT = dict(summary)
        return summary
    finally:
        _PERFORMANCE_LOCK.release()


def get_performance_history(symbol: str = "", tf: str = "", limit: int = 120) -> dict[str, Any]:
    symbol = _normalize_symbol(symbol) if symbol else ""
    limit = max(1, min(int(limit), 500))
    where, args = [], []
    if symbol:
        where.append("symbol=?"); args.append(symbol)
    if tf in TF_CFG:
        where.append("timeframe=?"); args.append(tf)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    with DB_LOCK, db_conn() as con:
        rows = con.execute(
            f"SELECT symbol,timeframe,created_at,trades,wins,losses,win_rate,expectancy,"
            f"profit_factor,max_drawdown,sharpe,sortino,oos_status "
            f"FROM performance_snapshots{clause} ORDER BY created_at DESC LIMIT ?",
            (*args, limit),
        ).fetchall()
    return {
        "ok": True,
        "items": [dict(r) for r in rows],
        "count": len(rows),
        "source": "AUTONOMOUS_BACKTEST_HISTORY",
        "autonomous_status": dict(_PERFORMANCE_LAST_RESULT),
    }


# ============================================================
# TITAN ENTERPRISE V4 - ADVANCED CONTROL MODULES
# Restored from the user's original master build. Additive only.
# ============================================================

class TitanEnterpriseEnhancementV4:
    """
    Enterprise enhancement layer:
    1. Pipeline validation
    2. Learning memory hooks
    3. Backtest framework
    4. Adaptive weighting
    5. Market manipulation protection
    6. Runtime safety checks
    """
    def __init__(self):
        self.history = []
        self.weights = {
            "technical": 0.35,
            "ai": 0.30,
            "derivatives": 0.20,
            "risk": 0.15
        }

    def validate_pipeline(self, data):
        return bool(data and isinstance(data, dict))

    def save_feedback(self, signal, result):
        _append_capped(self.history, {"signal": signal, "result": result}, 256)

    def adaptive_weights(self, market_state="normal"):
        if market_state == "sideways":
            self.weights = {
                "technical": 0.25,
                "ai": 0.25,
                "derivatives": 0.30,
                "risk": 0.20
            }
        elif market_state == "trend":
            self.weights = {
                "technical": 0.45,
                "ai": 0.30,
                "derivatives": 0.15,
                "risk": 0.10
            }
        return self.weights

    def backtest_record(self, decision, price_before, price_after):
        change = 0
        if price_before:
            change = ((price_after - price_before) / price_before) * 100
        return {"decision": decision, "performance": round(change, 4)}

    def anomaly_check(self, volume_change=0, volatility=0):
        if volume_change > 300 or volatility > 10:
            return {"blocked": True, "reason": "market anomaly detected"}
        return {"blocked": False}

    def self_check(self, payload):
        checks = {
            "data": self.validate_pipeline(payload),
            "risk": payload.get("risk", 0) < 50 if isinstance(payload, dict) else False,
            "engine": True
        }
        return {"passed": all(checks.values()), "checks": checks}


TITAN_ENTERPRISE_V4 = TitanEnterpriseEnhancementV4()


# ============================================================
# TITAN FULL AUDIT & TEST FRAMEWORK
# ============================================================

class TitanFullAuditFramework:
    """Internal validation, stress and decision-quality audit layer."""
    def __init__(self):
        self.results = []
        self.paper_trades = []

    def static_check(self):
        return {
            "python_syntax": True,
            "core_loaded": True,
            "error_guard": True,
            "decision_layer": "TITAN_DECISION_CORE" in globals()
        }

    def pipeline_check(self, payload=None):
        return {
            "data": isinstance(payload, dict) if payload is not None else False,
            "risk": True,
            "decision_ready": True
        }

    def stress_test(self, scenario):
        blocked = scenario in ["api_down", "invalid_data", "extreme_volatility"]
        return {"scenario": scenario, "safe_mode": blocked, "action": "WAIT" if blocked else "CONTINUE"}

    def record_paper_trade(self, signal):
        _append_capped(self.paper_trades, signal, 512)
        return {"saved": True, "count": len(self.paper_trades)}

    def decision_report(self, decision):
        report = {
            "decision": decision,
            "has_confidence": "confidence" in decision if isinstance(decision, dict) else False,
            "explainable": "explanation" in decision if isinstance(decision, dict) else False
        }
        _append_capped(self.results, report, 512)
        return report


TITAN_AUDIT_ENGINE = TitanFullAuditFramework()


# ============================================================
# TITAN ULTIMATE - BACKTEST & CALIBRATION ENGINE
# ============================================================

class TitanBacktestCalibrationEngine:
    """Offline evaluation and confidence calibration framework."""
    def __init__(self):
        self.trades = []
        self.stats = {"total": 0, "wins": 0, "losses": 0}

    def record(self, decision, entry, exit_price, confidence=0):
        if not entry:
            return None
        pnl = ((exit_price - entry) / entry) * 100
        if decision == "SHORT":
            pnl *= -1
        result = {
            "decision": decision, "entry": entry, "exit": exit_price,
            "confidence": confidence, "pnl": round(pnl, 4), "success": pnl > 0
        }
        _append_capped(self.trades, result, 2000)
        self.stats["total"] += 1
        if result["success"]:
            self.stats["wins"] += 1
        else:
            self.stats["losses"] += 1
        return result

    def report(self):
        total = self.stats["total"]
        if total == 0:
            return {"status": "no_data", "message": "No backtest records available"}
        return {
            "total_trades": total,
            "win_rate": round((self.stats["wins"] / total) * 100, 2),
            "loss_rate": round((self.stats["losses"] / total) * 100, 2),
            "avg_confidence": round(sum(t["confidence"] for t in self.trades) / total, 2)
        }

    def calibrate(self):
        report = self.report()
        if report.get("win_rate", 0) < 50:
            return {"action": "reduce_risk", "reason": "low historical accuracy"}
        return {"action": "normal", "reason": "acceptable historical performance"}


TITAN_BACKTEST_ENGINE = TitanBacktestCalibrationEngine()


# ============================================================
# TITAN ULTIMATE - WALK FORWARD VALIDATION ENGINE
# ============================================================

class TitanWalkForwardValidationEngine:
    """Walk-forward evaluation and confidence calibration layer."""
    def __init__(self):
        self.windows = []
        self.results = []

    def create_window(self, train_data, test_data):
        window = {
            "train_size": len(train_data) if train_data else 0,
            "test_size": len(test_data) if test_data else 0
        }
        _append_capped(self.windows, window, 512)
        return window

    def evaluate(self, predictions, outcomes):
        if not predictions or not outcomes:
            return {"status": "no_data", "accuracy": 0}
        total = min(len(predictions), len(outcomes))
        correct = sum(1 for p, o in zip(predictions[:total], outcomes[:total]) if p == o)
        result = {"samples": total, "accuracy": round((correct / total) * 100, 2)}
        _append_capped(self.results, result, 512)
        return result

    def calibrate_confidence(self, confidence, accuracy):
        if accuracy < 50:
            return max(0, confidence - 15)
        if accuracy > 70:
            return min(100, confidence + 5)
        return confidence

    def report(self):
        return {"windows": len(self.windows), "evaluations": len(self.results), "results": self.results}


TITAN_WALK_FORWARD_ENGINE = TitanWalkForwardValidationEngine()


# ============================================================
# TITAN QUANT VALIDATION ENGINE
# ============================================================

class TitanQuantValidationEngine:
    def __init__(self):
        self.records = []

    def add_trade(self, pnl_percent):
        _append_capped(self.records, float(pnl_percent), 5000)

    def metrics(self):
        if not self.records:
            return {"trades": 0}
        wins = [x for x in self.records if x > 0]
        losses = [x for x in self.records if x <= 0]
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        equity = 0
        peak = 0
        drawdown = 0
        losing = 0
        max_losing = 0
        for p in self.records:
            equity += p
            peak = max(peak, equity)
            drawdown = max(drawdown, peak - equity)
            losing = losing + 1 if p <= 0 else 0
            max_losing = max(max_losing, losing)
        return {
            "trades": len(self.records),
            "win_rate": round(len(wins) / len(self.records) * 100, 2),
            "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss else None,
            "max_drawdown": round(drawdown, 3),
            "max_losing_streak": max_losing
        }

    def walk_forward(self, values, train=50, test=20):
        results = []
        i = 0
        while i + train + test <= len(values):
            train_set = values[i:i + train]
            test_set = values[i + train:i + train + test]
            results.append({
                "train": len(train_set),
                "test": len(test_set),
                "test_return": round(sum(test_set), 4)
            })
            i += test
        return results

    def stress_test(self, data):
        checks = {
            "empty_data": not bool(data),
            "extreme_volatility": abs(float(data.get("volatility", 0))) > 15 if isinstance(data, dict) else True,
            "invalid_price": float(data.get("price", 1)) <= 0 if isinstance(data, dict) else True
        }
        return {"safe": not any(checks.values()), "checks": checks}


TITAN_QUANT_VALIDATOR = TitanQuantValidationEngine()




# ============================================================
# TITAN ULTIMATE INTEGRATION ORCHESTRATOR
# ============================================================

class TitanUltimateOrchestrator:
    """Connects data, AI, risk, learning and decision layers."""
    def __init__(self):
        self.decision = globals().get("TITAN_DECISION_CORE")
        self.enhancer = globals().get("TITAN_ENTERPRISE_V4")
        self.memory = []

    def run(self, market_data):
        if not isinstance(market_data, dict):
            return {"decision": "WAIT", "confidence": 0, "reason": "invalid_data"}
        health = self.enhancer.self_check(market_data) if self.enhancer else {"passed": True}
        if not health.get("passed", True):
            return {"decision": "WAIT", "confidence": 0, "reason": "self_check_failed"}
        anomaly = self.enhancer.anomaly_check(
            market_data.get("volume_change", 0),
            market_data.get("volatility", 0)
        ) if self.enhancer else {"blocked": False}
        if anomaly.get("blocked"):
            return {"decision": "WAIT", "confidence": 0, "reason": anomaly.get("reason")}
        result = self.decision.decide(market_data) if self.decision else {"decision": "WAIT"}
        _append_capped(self.memory, {"input": market_data, "result": result}, 128)
        return result


TITAN_ULTIMATE = TitanUltimateOrchestrator()

# ============================================================
# FLASK
# ============================================================


app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False
app.config["TEMPLATES_AUTO_RELOAD"] = False
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 3600
# Android-safe default: local-only dashboard.
HOST = "127.0.0.1"
_default_port = os.environ.get("TITAN_PORT_DEFAULT") or "8080"
try:
    PORT = int(os.environ.get("TITAN_PORT", _default_port) or _default_port)
except (TypeError, ValueError):
    PORT = int(_default_port)

@app.get("/favicon.ico")
def titan_favicon():
    return "", 204

@app.errorhandler(404)
def titan_not_found(exc):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "not_found"}), 404
    return ("<h1>TITAN: 404</h1>", 404, {"Content-Type": "text/html; charset=utf-8"})

@app.errorhandler(Exception)
def titan_global_error_handler(exc):
    # Keep API responses JSON, but never leave the human-facing dashboard blank.
    LOGGER.exception("Unhandled application error: %s", exc)
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "internal_error", "detail": str(exc)[:500]}), 500
    detail = str(exc).replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
    return (
        "<!doctype html><html lang='fa' dir='rtl'><meta charset='utf-8'>"
        "<title>TITAN Enterprise Error</title>"
        "<body style='background:#050812;color:#eef2ff;font-family:Tahoma;padding:30px'>"
        "<h2 style='color:#38bdf8'>⚡ TITAN ENTERPRISE</h2>"
        "<p>داشبورد با یک خطای داخلی مواجه شد، اما سرور فعال است.</p>"
        f"<pre style='white-space:pre-wrap;background:#0b1220;padding:16px;border-radius:12px'>{detail}</pre>"
        "<p>بعد از رفع خطا صفحه را Refresh کنید.</p></body></html>", 500, {"Content-Type": "text/html; charset=utf-8"}
    )

def _gemini_dashboard_status(summary: str) -> dict[str, Any]:
    return {
        "available": bool(GEMINI_API_KEY),
        "ready": bool(summary.strip()),
        "label": "تحلیل آماده" if summary.strip() else ("کلید Gemini موجود نیست" if not GEMINI_API_KEY else "در انتظار تحلیل"),
        "updated_at": _now_iso(),
    }

HTML = r'''
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
<meta name="titan-fast-paint" content="1">
<style id="titanBoot">body{background:#020711;color:#eaf5ff}#titanBootSplash{position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;background:#020711;font-family:Tahoma,sans-serif;font-size:14px;color:#7dd3fc}#titanBootSplash.hide{opacity:0;pointer-events:none;transition:opacity .25s}</style>
<meta name="theme-color" content="#020711">
<meta name="mobile-web-app-capable" content="yes">

<style>
.scanTelemetry{margin:7px 0 10px;padding:8px 10px;border:1px solid rgba(56,189,248,.18);border-radius:12px;background:linear-gradient(90deg,rgba(8,18,35,.92),rgba(12,27,45,.72));box-shadow:0 0 18px rgba(0,0,0,.12)}.scanTelemetryTop{display:flex;justify-content:space-between;gap:8px;align-items:center;font-size:9px;color:#9fb3c8}.scanTelemetryBar{height:7px;border-radius:99px;background:#091321;overflow:hidden;margin-top:6px;border:1px solid rgba(255,255,255,.05)}.scanTelemetryBar i{display:block;height:100%;width:0%;transition:width .35s ease;background:linear-gradient(90deg,#38bdf8,#22c55e,#facc15)}.scanTelemetryMeta{display:flex;justify-content:space-between;gap:8px;margin-top:4px;font-size:8px;color:#71869c}.perfLearningGrid{display:grid;grid-template-columns:repeat(4,1fr);gap:6px}.perfLearnCard{padding:8px;border-radius:10px;background:rgba(255,255,255,.025);border:1px solid rgba(56,189,248,.09)}.perfLearnCard b{display:block;font-size:12px}.perfLearnCard small{display:block;color:#71869c;font-size:7px;margin-top:3px}.perfLearnTable{width:100%;border-collapse:collapse;font-size:8px;margin-top:8px}.perfLearnTable th,.perfLearnTable td{padding:5px;border-bottom:1px solid rgba(255,255,255,.05);text-align:center}.perfLearnTable th{color:#7f9ab3}.perfLearnTable td{color:#d8e7f5}

:root{
 --bg:#030711;--bg2:#06101e;--panel:rgba(7,17,32,.86);--panel2:rgba(10,24,44,.72);
 --line:rgba(92,211,255,.20);--line2:rgba(255,255,255,.08);--text:#eaf5ff;--muted:#7890a8;
 --cyan:#31d7ff;--cyan2:#0ea5e9;--green:#23e6a8;--green2:#10b981;--red:#ff4d73;--gold:#ffd34e;--violet:#a78bfa;--blue:#4f8cff;
 --shadow:0 18px 55px rgba(0,0,0,.42), inset 0 1px 0 rgba(255,255,255,.045);
 --radius:18px;
}
*{box-sizing:border-box}
html,body{margin:0;min-height:100%;background:#02060d;color:var(--text);font-family:'Vazirmatn',Tahoma,sans-serif}
body{padding:0 10px 24px;overflow-x:hidden;background:
 radial-gradient(circle at 78% 2%,rgba(38,122,255,.12),transparent 28%),
 radial-gradient(circle at 12% 24%,rgba(0,230,255,.08),transparent 26%),
 linear-gradient(180deg,#020711 0%,#030913 48%,#02060c 100%)}
button,input{font-family:inherit}button{cursor:pointer}
a{text-decoration:none;color:inherit}
.legacyDashboard{display:none!important}
.titanApp{max-width:1600px;margin:0 auto;padding-top:10px}
.topHeader{position:sticky;top:0;z-index:100;display:grid;grid-template-columns:330px 1fr auto;gap:12px;align-items:center;padding:11px 14px;margin-bottom:10px;border:1px solid rgba(49,215,255,.25);border-radius:20px;background:linear-gradient(110deg,rgba(4,15,29,.96),rgba(8,18,38,.91));box-shadow:var(--shadow);backdrop-filter:blur(22px)}
.brand{display:flex;align-items:center;gap:10px;min-width:0}.brandMark{width:48px;height:48px;display:grid;place-items:center;border-radius:15px;background:linear-gradient(145deg,#082d49,#06111e);border:1px solid rgba(49,215,255,.5);box-shadow:0 0 28px rgba(49,215,255,.12);font-size:28px}.brand h1{margin:0;font-size:19px;line-height:1.1;letter-spacing:.4px;color:#f4fbff}.brand h1 span{color:var(--cyan)}.brand small{display:block;margin-top:3px;color:#7692aa;font-size:9px;letter-spacing:.7px}
.statusStrip{display:flex;gap:8px;overflow:auto;scrollbar-width:none}.statusStrip::-webkit-scrollbar{display:none}.statusPill{display:flex;align-items:center;gap:7px;white-space:nowrap;padding:9px 11px;border:1px solid var(--line2);border-radius:13px;background:rgba(255,255,255,.035);font-size:11px;color:#b7cadb}.statusPill b{color:#eaf5ff}.dot{width:8px;height:8px;border-radius:50%;display:inline-block;background:var(--green);box-shadow:0 0 12px currentColor}.dot.warn{background:var(--gold)}.dot.red{background:var(--red)}
.headerActions{display:flex;gap:7px}.glassBtn{border:1px solid rgba(49,215,255,.28);border-radius:12px;min-height:40px;padding:8px 12px;color:#e8f8ff;background:linear-gradient(145deg,rgba(14,165,233,.18),rgba(79,70,229,.14));box-shadow:inset 0 1px 0 rgba(255,255,255,.05);font-weight:800}.glassBtn:hover{border-color:rgba(49,215,255,.65);transform:translateY(-1px)}.glassBtn.gold{border-color:rgba(255,211,78,.35);background:linear-gradient(145deg,rgba(255,211,78,.15),rgba(245,158,11,.08))}
.appGrid{display:grid;grid-template-columns:205px minmax(0,1fr);gap:10px;align-items:start}.sidebar{position:sticky;top:82px;padding:10px;border:1px solid var(--line);border-radius:20px;background:linear-gradient(180deg,rgba(6,18,33,.95),rgba(4,11,21,.9));box-shadow:var(--shadow);backdrop-filter:blur(18px)}.sideBrand{padding:9px 10px 12px;border-bottom:1px solid var(--line2);margin-bottom:9px}.sideBrand b{font-size:13px}.sideBrand small{display:block;color:var(--muted);font-size:9px;margin-top:3px}.sideBtn{width:100%;display:flex;align-items:center;gap:9px;padding:10px 11px;margin:4px 0;border:1px solid transparent;border-radius:12px;background:transparent;color:#9fb3c7;text-align:right;font-weight:800;font-size:11px}.sideBtn:hover{background:rgba(49,215,255,.07);color:#eaffff}.sideBtn.active{color:#fff;border-color:rgba(49,215,255,.35);background:linear-gradient(90deg,rgba(14,165,233,.25),rgba(79,70,229,.12));box-shadow:0 7px 22px rgba(14,165,233,.10)}.sideIcon{width:25px;height:25px;display:grid;place-items:center;border-radius:8px;background:rgba(255,255,255,.05);font-size:14px}.sideFilter{margin-top:10px;padding-top:10px;border-top:1px solid var(--line2)}.sideFilter label{display:block;color:#6f879f;font-size:9px;margin-bottom:5px}.searchBox{width:100%;padding:9px 10px;border-radius:10px;border:1px solid rgba(49,215,255,.18);background:#06101c;color:#eaf5ff;outline:none;font-size:11px}.filterRow{display:grid;grid-template-columns:repeat(3,1fr);gap:4px;margin-top:6px}.filterBtn{padding:7px 3px;border-radius:8px;border:1px solid rgba(255,255,255,.07);background:rgba(255,255,255,.025);color:#91a8bd;font-size:9px;font-weight:900}.filterBtn.active{border-color:rgba(49,215,255,.45);color:#fff;background:rgba(49,215,255,.12)}
.mainArea{min-width:0}.mainTabs{display:flex;gap:6px;overflow:auto;scrollbar-width:none;padding:5px;border:1px solid var(--line);border-radius:16px;background:rgba(5,15,28,.78);margin-bottom:9px}.mainTabs::-webkit-scrollbar{display:none}.mainTab{flex:0 0 auto;border:1px solid transparent;border-radius:11px;padding:9px 12px;color:#8199af;background:transparent;font-size:10px;font-weight:900;white-space:nowrap}.mainTab.active{color:#fff;border-color:rgba(49,215,255,.35);background:linear-gradient(135deg,rgba(14,165,233,.23),rgba(124,58,237,.16));box-shadow:0 8px 22px rgba(14,165,233,.08)}
.tabPanel{display:none}.tabPanel.active{display:block}
.tickerRail{display:grid;grid-template-columns:repeat(7,minmax(150px,1fr));gap:6px;margin-bottom:9px}.ticker{min-width:0;padding:8px 9px;border:1px solid rgba(255,255,255,.07);border-radius:13px;background:linear-gradient(145deg,rgba(9,24,42,.88),rgba(5,13,24,.9));box-shadow:0 9px 28px rgba(0,0,0,.22)}.tickerTop{display:flex;align-items:center;justify-content:space-between;gap:5px}.tickerCoin{display:flex;align-items:center;gap:6px;min-width:0}.tickerIcon{width:27px;height:27px;display:grid;place-items:center;border-radius:9px;background:rgba(255,255,255,.06);font-size:15px}.ticker b{font-size:11px}.ticker small{display:block;color:#657d95;font-size:8px}.tickerPrice{font-size:10px;font-weight:900}.tickerMove{font-size:8px;font-weight:900}.up{color:var(--green)!important}.down{color:var(--red)!important}.neutral{color:var(--gold)!important}
.kpiGrid{display:grid;grid-template-columns:repeat(6,1fr);gap:7px;margin-bottom:9px}.kpi{min-width:0;padding:11px 10px;border:1px solid rgba(255,255,255,.07);border-radius:15px;background:linear-gradient(145deg,rgba(7,23,40,.9),rgba(5,13,24,.92));box-shadow:0 10px 30px rgba(0,0,0,.22)}.kpiHead{display:flex;justify-content:space-between;color:#718aa1;font-size:9px}.kpiValue{margin-top:5px;font-size:19px;font-weight:950}.kpiHint{margin-top:2px;color:#5e7891;font-size:8px}.kpiIcon{font-size:17px;opacity:.85}
.commandGrid{display:grid;grid-template-columns:minmax(0,1fr) 265px;gap:9px}.panel{padding:11px;border:1px solid var(--line);border-radius:18px;background:linear-gradient(145deg,rgba(7,19,35,.93),rgba(4,10,19,.92));box-shadow:var(--shadow);min-width:0}.panelHead{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:9px}.panelTitle{font-size:13px;font-weight:950}.panelSub{font-size:8px;color:#617a92;margin-top:2px}.panelAction{font-size:9px;color:var(--cyan);border:1px solid rgba(49,215,255,.2);padding:6px 8px;border-radius:9px;background:rgba(49,215,255,.05)}
.signalSummary{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-bottom:8px}.signalBox{position:relative;overflow:hidden;padding:12px;border-radius:15px;border:1px solid rgba(255,255,255,.07);background:rgba(0,0,0,.16)}.signalBox:after{content:"";position:absolute;width:70px;height:70px;border-radius:50%;right:-20px;top:-25px;background:currentColor;opacity:.07}.signalBox b{font-size:10px}.signalNum{font-size:24px;font-weight:950;margin-top:2px}.signalMeta{font-size:8px;color:#7089a0}.signalBox.long{color:var(--green);border-color:rgba(35,230,168,.28)}.signalBox.wait{color:var(--gold);border-color:rgba(255,211,78,.24)}.signalBox.short{color:var(--red);border-color:rgba(255,77,115,.27)}
.assetHeader{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:8px 0}.assetTools{display:flex;gap:5px;align-items:center}.assetTools button{font-size:9px;padding:6px 8px;border-radius:9px;border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.03);color:#91a7bb}.assetTools button.active{color:#fff;border-color:rgba(49,215,255,.4);background:rgba(49,215,255,.10)}
.assetGrid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px}.assetCard{position:relative;min-width:0;padding:10px;border:1px solid rgba(255,255,255,.07);border-radius:15px;background:linear-gradient(145deg,rgba(8,24,41,.92),rgba(5,13,23,.92));box-shadow:0 9px 26px rgba(0,0,0,.25);cursor:pointer;overflow:hidden;transition:.16s}.assetCard:hover{transform:translateY(-2px);border-color:rgba(49,215,255,.42);box-shadow:0 15px 32px rgba(0,0,0,.36)}.assetCard.long{border-top:2px solid var(--green)}.assetCard.short{border-top:2px solid var(--red)}.assetCard.wait{border-top:2px solid var(--gold)}.assetTop{display:flex;justify-content:space-between;align-items:center;gap:6px}.assetIdentity{display:flex;align-items:center;gap:7px;min-width:0}.assetIcon{width:32px;height:32px;display:grid;place-items:center;border-radius:10px;background:rgba(255,255,255,.055);font-size:18px;flex:0 0 auto}.assetName{min-width:0}.assetName b{display:block;font-size:11px}.assetName small{display:block;color:#5e7790;font-size:7px;margin-top:1px}.decisionPill{font-size:8px;font-weight:950;padding:5px 7px;border-radius:99px;white-space:nowrap}.decisionPill.long{color:var(--green);background:rgba(35,230,168,.09);border:1px solid rgba(35,230,168,.3)}.decisionPill.short{color:var(--red);background:rgba(255,77,115,.09);border:1px solid rgba(255,77,115,.3)}.decisionPill.wait{color:var(--gold);background:rgba(255,211,78,.09);border:1px solid rgba(255,211,78,.3)}.assetPrice{display:flex;justify-content:space-between;align-items:end;margin:7px 0 5px}.assetPrice b{font-size:13px}.assetPrice span{font-size:8px}.scoreLine{display:flex;align-items:center;gap:6px}.scoreRing{width:35px;height:35px;border-radius:50%;display:grid;place-items:center;background:conic-gradient(var(--ring,#31d7ff) calc(var(--score,0)*1%),#15273a 0);position:relative;flex:0 0 auto}.scoreRing:after{content:"";position:absolute;width:27px;height:27px;border-radius:50%;background:#06111e}.scoreRing span{position:relative;z-index:2;font-size:9px;font-weight:950}.scoreBar{height:5px;flex:1;border-radius:99px;background:#122236;overflow:hidden}.scoreBar i{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,#0ea5e9,#31d7ff)}.assetTF{display:grid;grid-template-columns:repeat(4,1fr);gap:3px;margin-top:7px}.tfMini{padding:4px 2px;text-align:center;border-radius:7px;background:rgba(255,255,255,.025);font-size:7px;color:#607990}.tfMini b{display:block;color:#a8bdd0;font-size:8px;margin-top:2px}.assetBottom{display:flex;justify-content:space-between;gap:4px;margin-top:6px;color:#678099;font-size:7px}.assetOpen{color:var(--cyan);font-weight:900}
.sidePanels{display:grid;gap:9px}.healthList{display:grid;gap:6px}.healthRow{display:flex;justify-content:space-between;align-items:center;padding:7px 8px;border-radius:9px;background:rgba(255,255,255,.025);font-size:8px}.okDot{color:var(--green)}.warnDot{color:var(--gold)}.geminiCard{border-color:rgba(79,140,255,.35);background:linear-gradient(145deg,rgba(15,28,55,.94),rgba(6,13,27,.94))}.aiBadge{display:flex;justify-content:space-between;align-items:center;gap:6px}.aiBadge strong{color:#7db7ff;font-size:12px}.aiText{margin-top:8px;max-height:145px;overflow:auto;color:#b8cae0;font-size:9px;line-height:1.9}.miniGauge{height:7px;background:#13253a;border-radius:99px;overflow:hidden;margin-top:7px}.miniGauge i{display:block;height:100%;background:linear-gradient(90deg,#31d7ff,#8b5cf6);border-radius:99px}
.marketMini{display:grid;grid-template-columns:1fr 1fr;gap:5px}.macroBox{padding:8px;border-radius:10px;background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.05)}.macroBox small{display:block;color:#617991;font-size:7px}.macroBox b{font-size:12px}.eventList{display:grid;gap:5px}.eventItem{padding:7px;border-radius:9px;background:rgba(255,255,255,.025);border-right:2px solid var(--cyan);font-size:8px}.eventItem b{display:block;font-size:9px}.eventItem small{color:#678098}
.bottomGrid{display:grid;grid-template-columns:1.2fr .8fr;gap:9px;margin-top:9px}.performanceStrip{display:grid;grid-template-columns:repeat(4,1fr);gap:6px}.perfStat{padding:8px;border-radius:11px;background:rgba(255,255,255,.025);text-align:center}.perfStat small{display:block;color:#617990;font-size:7px}.perfStat b{display:block;font-size:15px;margin-top:3px}.gaugeDeck{display:grid;grid-template-columns:repeat(4,1fr);gap:6px}.tfGauge{padding:8px;text-align:center;border-radius:11px;background:rgba(255,255,255,.025)}.tfGauge .needle{width:50px;height:25px;margin:4px auto 2px;border-radius:50px 50px 0 0;border:5px solid #163047;border-bottom:0;position:relative}.tfGauge .needle:after{content:"";position:absolute;bottom:-3px;left:50%;width:3px;height:22px;background:var(--cyan);transform-origin:bottom center;transform:rotate(var(--rot,0deg));border-radius:4px}.tfGauge b{font-size:9px}.tfGauge small{display:block;color:#617991;font-size:7px}
.globalSection{margin-top:9px}.dataTable{width:100%;border-collapse:collapse;font-size:9px}.dataTable th,.dataTable td{padding:7px 5px;border-bottom:1px solid rgba(255,255,255,.06);text-align:center}.dataTable th{color:#6f8aa2;background:rgba(255,255,255,.025)}.tableWrap{overflow:auto}.miniChip{display:inline-flex;align-items:center;gap:5px;padding:5px 7px;border-radius:8px;background:rgba(255,255,255,.035);border:1px solid rgba(255,255,255,.06);font-size:8px;color:#a8bacb}.signalBadge{display:inline-flex;align-items:center;padding:5px 8px;border-radius:99px;font-size:8px;font-weight:950}.signalBadge.long{color:var(--green);background:rgba(35,230,168,.1)}.signalBadge.short{color:var(--red);background:rgba(255,77,115,.1)}.signalBadge.wait{color:var(--gold);background:rgba(255,211,78,.1)}
/* Detail modal redesigned as a full coin workspace */
.modal{display:none;position:fixed;inset:0;z-index:1300;background:rgba(1,4,10,.78);backdrop-filter:blur(10px);align-items:center;justify-content:center;padding:12px}.detailModal .modalC{width:min(1180px,98vw);height:min(92vh,900px);max-height:92vh;overflow:hidden;padding:0;border:1px solid rgba(49,215,255,.28);border-radius:22px;background:#04101d;box-shadow:0 30px 90px rgba(0,0,0,.7)}.cdShell{height:100%;display:flex;flex-direction:column}.cdBanner{padding:14px 16px;border-bottom:1px solid rgba(255,255,255,.07);background:linear-gradient(110deg,rgba(7,28,47,.98),rgba(12,14,39,.98))}.cdBanner.long{background:linear-gradient(110deg,rgba(4,45,35,.98),rgba(5,18,34,.98))}.cdBanner.bear{background:linear-gradient(110deg,rgba(52,10,25,.98),rgba(12,14,39,.98))}.cdBanner.flat{background:linear-gradient(110deg,rgba(43,35,6,.98),rgba(8,18,32,.98))}.cdBannerInner{display:flex;justify-content:space-between;align-items:center;gap:12px}.cdTitleBlock{display:flex;align-items:center;gap:11px}.cdIconXL{width:52px;height:52px;display:grid;place-items:center;border-radius:16px;background:rgba(255,255,255,.06);font-size:27px;border:1px solid rgba(255,255,255,.1)}.modalKicker{color:#66839b;font-size:8px}.cdName{margin:2px 0;font-size:22px}.cdPair{font-size:9px;color:#718aa0}.cdPriceBig{font-size:22px;font-weight:950;text-align:left}.cdPriceBig small{font-size:9px;color:#70889e}.cdBodyPad{padding:10px 12px;overflow:auto}.coinDetailTabs{display:flex;gap:5px;overflow:auto;scrollbar-width:none;padding:5px;border:1px solid rgba(255,255,255,.07);border-radius:13px;background:rgba(0,0,0,.18);margin-bottom:9px}.coinDetailTabs::-webkit-scrollbar{display:none}.coinDetailTab{flex:0 0 auto;padding:8px 10px;border:1px solid transparent;border-radius:9px;background:transparent;color:#8299ae;font-size:9px;font-weight:900}.coinDetailTab.active{color:#fff;border-color:rgba(49,215,255,.35);background:rgba(49,215,255,.10)}.coinDetailPanel{display:none}.coinDetailPanel.active{display:block}.cdMetrics{display:grid;grid-template-columns:repeat(4,1fr);gap:7px}.cdMetric{padding:11px;text-align:center;border-radius:13px;background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.06)}.cdMetric .ico{font-size:17px}.cdMetric .val{font-size:20px;font-weight:950;margin:3px 0}.cdMetric small{font-size:8px;color:#607990}.cdInfoBox{margin-top:8px;padding:10px;border-radius:12px;background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.06);font-size:10px;line-height:1.9;color:#b6c8da}.cdSectionLabel{margin:10px 0 6px;font-size:10px;color:var(--cyan);font-weight:900}.cdTfStrip{display:grid;grid-template-columns:repeat(4,1fr);gap:6px}.cdTfCell{padding:9px;text-align:center;border-radius:11px;background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.06)}.cdTfCell small{display:block;color:#607990;font-size:7px}.cdTfCell b{display:block;margin-top:4px;font-size:9px}.cdLevels{display:grid;grid-template-columns:repeat(4,1fr);gap:7px}.cdLevelCard{padding:11px;border-radius:13px;background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.06)}.cdLevelCard .lbl{font-size:8px;color:#7891a6}.cdLevelCard .num{font-size:15px;font-weight:950;margin-top:4px}.detailActionGrid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.aiDetailGrid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.aiDetailCard{padding:11px;border-radius:13px;background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.06);font-size:9px;line-height:1.9}.aiDetailCard>b{display:block;color:#a9c3d8;margin-bottom:5px}.cdChartBox{padding:8px;border-radius:14px;background:#06111d;border:1px solid rgba(49,215,255,.14)}.cdChartBox canvas{width:100%;height:320px;display:block}.cdFullDetails{font-size:9px}.cdFullDetails .card{display:block!important;background:rgba(255,255,255,.02)!important;box-shadow:none!important;border:1px solid rgba(255,255,255,.06)!important}.cdActions{display:flex;justify-content:flex-end;gap:7px;margin-top:9px}.iconBtn{min-width:40px;padding:8px}
/* global tabs */
.sectionGrid{display:grid;grid-template-columns:1fr 1fr;gap:9px}.bigPanel{min-height:120px}.metricCards{display:grid;grid-template-columns:repeat(4,1fr);gap:7px}.metricBox{padding:10px;text-align:center;border-radius:12px;background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.06)}.metricBox b{font-size:18px}.preBox{white-space:pre-wrap;background:#020711;padding:10px;border-radius:11px;color:#b8cadb;max-height:360px;overflow:auto;font-size:9px;line-height:1.7}.perfVisual{padding:0;border:0;background:none;box-shadow:none}.perfGrid{display:grid;grid-template-columns:repeat(4,1fr);gap:7px}.perfCard{padding:11px;border-radius:13px;background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.06);text-align:center}.perfCard small{font-size:8px;color:#647e95}.perfBig{font-size:22px;font-weight:950;margin:5px}.ring{width:78px;height:78px;border-radius:50%;display:grid;place-items:center;margin:7px auto;background:conic-gradient(var(--green) calc(var(--v)*1%),#14283b 0);position:relative}.ring:after{content:"";width:57px;height:57px;border-radius:50%;background:#06111e;position:absolute}.ring span{position:relative;z-index:2;font-size:13px;font-weight:950}.tfVisual{display:grid;grid-template-columns:repeat(4,1fr);gap:6px}.tfBox{padding:9px;border-radius:11px;background:rgba(255,255,255,.025);text-align:center}.tfBar{height:7px;background:#14273a;border-radius:99px;overflow:hidden;margin-top:6px}.tfBar i{display:block;height:100%;background:linear-gradient(90deg,var(--cyan),var(--violet));border-radius:99px}.perfCharts{display:grid;grid-template-columns:1.3fr .7fr;gap:7px;margin-top:7px}.chartPanel{padding:10px;border-radius:12px;background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.06)}.chartPanel h3{font-size:9px;margin:0 0 6px;color:#8aa3b8}.perfCanvas{width:100%;height:210px}.perfNote{font-size:8px;color:#647e95;margin-top:6px}.gaugeGrid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.tfGaugeCard{padding:12px;border-radius:13px;background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.06);text-align:center}.tfGaugeCard .arc{width:92px;height:46px;margin:5px auto 0;border:9px solid #153047;border-bottom:0;border-radius:90px 90px 0 0;position:relative}.tfGaugeCard .arc:after{content:"";position:absolute;bottom:-6px;left:50%;width:4px;height:42px;background:var(--cyan);transform-origin:bottom center;transform:rotate(var(--rot,0deg));border-radius:5px}.tfGaugeCard b{font-size:11px}.tfGaugeCard small{display:block;color:#688098;font-size:8px}
@media(max-width:1200px){.tickerRail{grid-template-columns:repeat(4,minmax(150px,1fr))}.assetGrid{grid-template-columns:repeat(3,1fr)}.kpiGrid{grid-template-columns:repeat(3,1fr)}}
@media(max-width:900px){body{padding:0 6px 18px}.topHeader{position:relative;grid-template-columns:1fr;gap:7px}.headerActions{width:100%}.headerActions>*{flex:1}.appGrid{grid-template-columns:1fr}.sidebar{position:relative;top:auto;display:flex;gap:5px;overflow:auto;padding:6px}.sideBrand,.sideFilter{display:none}.sideBtn{width:auto;flex:0 0 auto;margin:0;padding:8px 10px}.sideBtn span:not(.sideIcon){display:none}.sideIcon{width:28px;height:28px}.tickerRail{grid-template-columns:repeat(3,minmax(145px,1fr));overflow:auto}.commandGrid{grid-template-columns:1fr}.sidePanels{grid-template-columns:repeat(2,1fr)}.assetGrid{grid-template-columns:repeat(2,1fr)}.kpiGrid{grid-template-columns:repeat(3,1fr)}.bottomGrid,.sectionGrid{grid-template-columns:1fr}.perfGrid{grid-template-columns:1fr 1fr}.cdLevels{grid-template-columns:1fr 1fr}.cdMetrics{grid-template-columns:1fr 1fr}.gaugeGrid{grid-template-columns:1fr 1fr}.detailActionGrid,.aiDetailGrid{grid-template-columns:1fr}.perfCharts{grid-template-columns:1fr}}
@media(max-width:600px){.brand h1{font-size:17px}.statusStrip{width:100%}.kpiGrid{grid-template-columns:1fr 1fr}.assetGrid{grid-template-columns:1fr 1fr}.assetCard{padding:8px}.assetPrice b{font-size:11px}.tickerRail{grid-template-columns:repeat(2,minmax(145px,1fr))}.sidePanels{grid-template-columns:1fr}.signalSummary{grid-template-columns:1fr 1fr 1fr}.signalBox{padding:9px}.signalNum{font-size:19px}.cdName{font-size:18px}.cdPriceBig{font-size:18px}.cdBannerInner{align-items:flex-start}.cdChartBox canvas{height:230px}.perfGrid{grid-template-columns:1fr 1fr}.gaugeDeck{grid-template-columns:1fr 1fr}.tfVisual{grid-template-columns:1fr 1fr}}

/* ============================================================
   TITAN MOBILE ULTRA — presentation layer only
   No engine/data/API/decision logic is changed.
   Designed for Android phones: larger typography, touch targets,
   clearer hierarchy, stronger contrast and fewer tiny controls.
   ============================================================ */
@media(max-width:600px){
  :root{--mobilePad:8px}
  html{font-size:16px;-webkit-text-size-adjust:100%;text-size-adjust:100%}
  body{padding:0 var(--mobilePad) calc(28px + env(safe-area-inset-bottom));font-size:16px;line-height:1.55}
  .titanApp{width:100%;max-width:none;padding-top:8px}

  /* Header / branding */
  .topHeader{padding:13px 12px;margin-bottom:10px;border-radius:20px;gap:10px}
  .brand{gap:12px;min-height:62px}
  .brandMark{width:62px!important;height:62px!important;border-radius:18px;font-size:35px!important;flex:0 0 62px}
  .brand h1{font-size:22px!important;line-height:1.2;letter-spacing:.2px}
  .brand small{font-size:11px!important;line-height:1.5;margin-top:4px;letter-spacing:.2px}
  .statusStrip{gap:7px;padding-bottom:2px}
  .statusPill{min-height:42px;padding:9px 12px;font-size:13px!important;border-radius:13px}
  .statusPill b{font-size:13px!important}
  .dot{width:10px;height:10px;flex:0 0 10px}
  .headerActions{gap:8px}
  .headerActions .glassBtn{min-height:48px;padding:10px 12px;font-size:14px!important;border-radius:13px}

  /* Phone navigation */
  .appGrid{display:block}
  .sidebar{position:relative;top:auto;margin-bottom:10px;padding:7px;border-radius:17px;overflow-x:auto;overflow-y:hidden;display:flex;gap:7px;scroll-snap-type:x proximity}
  .sideBrand,.sideFilter{display:none!important}
  .sideBtn{width:auto;min-width:104px;min-height:52px;flex:0 0 auto;margin:0;padding:8px 11px;display:flex;justify-content:center;gap:7px;border-radius:13px;font-size:13px!important;scroll-snap-align:start}
  .sideBtn span:not(.sideIcon){display:inline!important;white-space:nowrap}
  .sideIcon{width:32px;height:32px;min-width:32px;border-radius:10px;font-size:18px!important}

  .mainArea{width:100%}
  .mainTabs{gap:6px;padding:6px;margin-bottom:10px;border-radius:15px}
  .mainTab{min-height:44px;padding:9px 13px;font-size:13px!important;border-radius:11px}

  /* Quick market rail */
  .tickerRail{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;overflow:visible}
  .ticker{padding:11px 10px;border-radius:15px;min-height:88px}
  .tickerIcon{width:36px;height:36px;border-radius:11px;font-size:20px!important}
  .tickerCoin{gap:8px}
  .ticker b{font-size:14px!important}
  .ticker small{font-size:10px!important;margin-top:1px}
  .tickerPrice{font-size:13px!important}
  .tickerMove{font-size:11px!important}

  /* KPI / signal cards */
  .kpiGrid{grid-template-columns:1fr 1fr;gap:8px}
  .kpi{padding:13px 12px;min-height:92px;border-radius:16px}
  .kpiHead{font-size:11px!important}
  .kpiValue{font-size:25px!important;line-height:1.15}
  .kpiHint{font-size:10px!important;line-height:1.5}
  .kpiIcon{font-size:22px!important}
  .signalSummary{grid-template-columns:1fr 1fr 1fr;gap:6px}
  .signalBox{padding:11px 8px;min-height:92px;border-radius:15px}
  .signalBox b{font-size:12px!important}
  .signalNum{font-size:24px!important}
  .signalMeta{font-size:10px!important}

  /* Main panels */
  .commandGrid,.sectionGrid,.bottomGrid,.sidePanels{grid-template-columns:1fr!important}
  .panel{padding:13px;border-radius:18px}
  .panelHead{margin-bottom:10px}
  .panelTitle{font-size:17px!important;line-height:1.4}
  .panelSub{font-size:11px!important;line-height:1.5}
  .panelAction{font-size:11px!important;padding:8px 10px}
  .glassBtn{min-height:46px;padding:9px 12px;font-size:13px!important;border-radius:12px}

  /* Asset cards: two readable columns */
  .assetHeader{margin:10px 0 8px;align-items:flex-start}
  .assetHeader .panelTitle{font-size:16px!important}
  .assetTools{gap:5px;flex-wrap:wrap;justify-content:flex-end}
  .assetTools button{min-height:40px;padding:8px 10px;font-size:11px!important;border-radius:10px}
  .assetGrid{grid-template-columns:1fr 1fr!important;gap:8px}
  .assetCard{padding:11px!important;min-height:154px;border-radius:16px}
  .assetIdentity{gap:8px}
  .assetIcon{width:40px;height:40px;font-size:23px!important;border-radius:12px}
  .assetName b{font-size:14px!important}
  .assetName small{font-size:9px!important}
  .decisionPill{font-size:10px!important;padding:6px 7px}
  .assetPrice{margin:9px 0 7px}
  .assetPrice b{font-size:14px!important}
  .assetPrice span{font-size:10px!important}
  .scoreRing{width:45px;height:45px}
  .scoreRing:after{width:34px;height:34px}
  .scoreRing span{font-size:11px!important}
  .scoreBar{height:7px}
  .assetCard .tfMini,.assetCard .tfRow,.assetCard .timeframes{font-size:10px!important}

  /* AI / performance typography */
  .aiText{font-size:13px!important;line-height:2!important}
  .metricCards{grid-template-columns:1fr 1fr;gap:8px}
  .metricBox{padding:12px;min-height:75px}
  .metricBox small{font-size:10px!important}
  .metricBox b{font-size:20px!important}
  .preBox{font-size:11px!important;line-height:1.8}
  .perfGrid{grid-template-columns:1fr 1fr!important;gap:8px}
  .perfCard{padding:13px;min-height:118px}
  .perfCard small{font-size:10px!important}
  .perfBig{font-size:25px!important}
  .ring{width:88px;height:88px}
  .ring:after{width:64px;height:64px}
  .ring span{font-size:15px!important}
  .chartPanel{padding:12px;border-radius:14px}
  .chartPanel h3{font-size:12px!important}
  .perfCanvas{height:230px}
  .tfVisual{grid-template-columns:1fr 1fr!important;gap:7px}
  .tfBox{padding:12px;font-size:11px!important}
  .tfBox b{font-size:15px!important}
  .perfNote{font-size:10px!important;line-height:1.7}
  .gaugeGrid{grid-template-columns:1fr 1fr!important}
  .tfGaugeCard{padding:13px}
  .tfGaugeCard b{font-size:14px!important}
  .tfGaugeCard small{font-size:10px!important}

  /* Command-center HUD */
  .hudgrid{grid-template-columns:1fr 1fr!important;gap:7px!important}
  .hudbox{padding:12px!important;border-radius:13px!important}
  .hudbox>div:first-child{font-size:11px!important}
  .hudbox .v{font-size:21px!important}

  /* Coin detail modal becomes a phone-first full-screen workspace */
  .modal{padding:0!important}
  .detailModal .modalBox,.modal .modalBox{width:100%!important;max-width:none!important;max-height:96vh!important;height:96vh!important;margin:2vh 0 0!important;border-radius:22px 22px 0 0!important}
  .cdBanner{padding:12px!important}
  .cdIcon{width:52px!important;height:52px!important;font-size:29px!important;border-radius:15px!important}
  .cdName{font-size:23px!important;line-height:1.25}
  .cdPair{font-size:11px!important}
  .cdPriceBig{font-size:23px!important}
  .cdPriceBig small{font-size:10px!important}
  .cdBodyPad{padding:10px!important}
  .coinDetailTabs{gap:5px;padding:5px;margin-bottom:10px}
  .coinDetailTab{min-height:44px;padding:9px 11px;font-size:12px!important;border-radius:10px}
  .cdMetrics{grid-template-columns:1fr 1fr!important;gap:7px}
  .cdMetric{padding:12px;min-height:95px}
  .cdMetric .ico{font-size:22px!important}
  .cdMetric .val{font-size:23px!important}
  .cdMetric small{font-size:10px!important}
  .cdInfoBox{font-size:12px!important;line-height:1.95}
  .cdSectionLabel{font-size:13px!important}
  .cdTfStrip{grid-template-columns:1fr 1fr!important;gap:7px}
  .cdTfCell{padding:11px;min-height:70px}
  .cdTfCell small{font-size:9px!important}
  .cdTfCell b{font-size:12px!important}
  .cdLevels{grid-template-columns:1fr 1fr!important}
  .cdLevelCard{padding:12px}
  .cdLevelCard .lbl{font-size:10px!important}
  .cdLevelCard .num{font-size:17px!important}
  .detailActionGrid,.aiDetailGrid{grid-template-columns:1fr!important}
  .aiDetailCard{padding:13px;font-size:12px!important;line-height:1.9}
  .cdChartBox canvas{height:280px!important}
  .cdFullDetails{font-size:11px!important}

  /* Quick navigation rail/cards */
  .titanNavShell{padding:10px!important;border-radius:18px!important}
  .titanNavHead{gap:8px!important}
  .titanNavTitle{font-size:17px!important}
  .titanNavSub{font-size:10px!important;line-height:1.5}
  .titanNavFilters{gap:5px!important}
  .titanNavFilters button{min-height:42px!important;padding:8px 10px!important;font-size:11px!important}
  .titanCoinRail{grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:8px!important;overflow:visible!important}
  .coinMiniCard{min-height:132px!important;padding:11px!important;border-radius:16px!important}
  .coinMiniIcon{width:39px!important;height:39px!important;font-size:22px!important;border-radius:12px!important}
  .coinMiniIdentity b{font-size:14px!important}
  .coinMiniIdentity small{font-size:9px!important}
  .coinMiniDecision{font-size:10px!important}
  .coinMiniPriceLine{font-size:10px!important}
  .coinMiniPriceLine strong{font-size:17px!important}
  .coinMiniPriceLine i{height:7px!important}
  .coinMiniTF{font-size:10px!important;gap:4px!important}
  .coinMiniOpen{font-size:11px!important}

  /* Avoid accidental tiny inline text throughout the redesigned dashboard. */
  .titanApp .miniChip{font-size:10px!important;min-height:30px;padding:6px 8px}
  .titanApp .signalBadge{font-size:10px!important;padding:7px 9px}
  .titanApp table{font-size:11px!important}
  .titanApp th,.titanApp td{padding:9px 7px!important}
}

@media(max-width:380px){
  body{padding-left:6px;padding-right:6px}
  .brand h1{font-size:20px!important}
  .brandMark{width:58px!important;height:58px!important;flex-basis:58px;font-size:32px!important}
  .brand small{font-size:10px!important}
  .ticker{min-height:82px;padding:9px}
  .tickerIcon{width:33px;height:33px;font-size:18px!important}
  .ticker b{font-size:13px!important}
  .tickerPrice{font-size:12px!important}
  .assetCard{padding:9px!important;min-height:145px}
  .assetIcon{width:36px;height:36px;font-size:21px!important}
  .assetName b{font-size:13px!important}
  .decisionPill{font-size:9px!important;padding:5px 6px}
  .scoreRing{width:41px;height:41px}
  .scoreRing:after{width:31px;height:31px}
  .scoreRing span{font-size:10px!important}
  .coinMiniCard{min-height:126px!important;padding:9px!important}
  .coinMiniIdentity b{font-size:13px!important}
  .coinMiniPriceLine strong{font-size:15px!important}
  .cdName{font-size:21px!important}
  .cdPriceBig{font-size:21px!important}
}

/* Larger phones / landscape: use the extra width instead of enlarging everything too much. */
@media(min-width:601px) and (max-width:900px){
  html{font-size:15px}
  .brand h1{font-size:21px}
  .panelTitle{font-size:15px}
  .assetName b{font-size:13px}
}



.cdVisualSummary{margin-bottom:10px;padding:12px;border-radius:17px;background:linear-gradient(145deg,rgba(9,29,48,.98),rgba(12,17,38,.98));border:1px solid rgba(49,215,255,.20);box-shadow:0 12px 35px rgba(0,0,0,.25)}
.cdVisualHero{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:11px;border-radius:14px;background:rgba(255,255,255,.035);border:1px solid rgba(255,255,255,.07)}
.cdVisualKicker{display:block;color:#6f8da5;font-size:9px;margin-bottom:3px}.cdVisualHero strong{display:block;font-size:18px;color:#fff;font-weight:1000}.cdVisualHero small{display:block;color:#9eb4c7;font-size:10px;margin-top:3px}.cdVisualDecision{padding:9px 12px;border-radius:12px;font-size:13px;font-weight:1000;border:1px solid currentColor}.cdVisualDecision.long{color:#4ade80;background:rgba(74,222,128,.10)}.cdVisualDecision.short{color:#fb7185;background:rgba(251,113,133,.10)}.cdVisualDecision.wait{color:#facc15;background:rgba(250,204,21,.10)}
.cdVisualGrid{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:7px}.cdVisualStat{padding:9px;border-radius:12px;background:rgba(255,255,255,.028);border:1px solid rgba(255,255,255,.06);text-align:center}.cdVisualStat span{display:block;color:#7893a9;font-size:8px}.cdVisualStat b{display:block;color:#fff;font-size:15px;margin-top:3px}.cdVisualStat small{font-size:8px;color:#7992a7;margin-right:2px}.cdVisualLevels{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:7px}.cdVisualLevels>div{padding:9px;border-radius:12px;text-align:center;background:linear-gradient(145deg,rgba(35,230,168,.08),rgba(255,255,255,.025));border:1px solid rgba(35,230,168,.12)}.cdVisualLevels span{display:block;color:#7893a9;font-size:8px}.cdVisualLevels b{display:block;color:#fff;font-size:12px;margin-top:3px}.cdVisualFlow{display:flex;align-items:center;gap:5px;margin-top:8px;overflow:hidden}.cdVisualFlow span{white-space:nowrap;padding:6px 8px;border-radius:9px;background:rgba(49,215,255,.06);border:1px solid rgba(49,215,255,.12);color:#bfefff;font-size:8px;font-weight:900}.cdVisualFlow i{height:1px;min-width:12px;flex:1;background:linear-gradient(90deg,rgba(49,215,255,.45),rgba(167,139,250,.35))}
@media(max-width:600px){.cdVisualGrid{grid-template-columns:repeat(2,1fr)}.cdVisualLevels{grid-template-columns:repeat(2,1fr)}.cdVisualHero strong{font-size:16px}.cdVisualDecision{font-size:11px}.cdVisualFlow span{font-size:7px;padding:6px 5px}.cdVisualFlow i{min-width:5px}}

/* ============================================================
   V27.1 MOBILE CLARITY + VISUAL DETAILS PATCH
   UI-only styling plus opportunity-preserving decision refinement below.
   ============================================================ */
@media(max-width:600px){
  .titanCoinRail{grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:10px!important}
  .coinMiniCard{
    min-height:158px!important;padding:13px!important;border-radius:19px!important;
    border-width:1.5px!important;box-shadow:0 12px 30px rgba(0,0,0,.30),inset 0 1px 0 rgba(255,255,255,.08)!important;
  }
  .coinMiniCard.long{border-color:rgba(35,230,168,.50)!important;background:linear-gradient(145deg,rgba(8,53,45,.94),rgba(4,18,31,.98))!important}
  .coinMiniCard.wait{border-color:rgba(255,211,78,.50)!important;background:linear-gradient(145deg,rgba(54,44,9,.92),rgba(18,18,23,.98))!important}
  .coinMiniCard.short{border-color:rgba(255,77,115,.50)!important;background:linear-gradient(145deg,rgba(58,12,30,.94),rgba(18,14,25,.98))!important}
  .coinMiniTop{align-items:center!important;gap:8px!important}
  .coinMiniIdentity{gap:9px!important;min-width:0!important}
  .coinMiniIcon{
    width:52px!important;height:52px!important;min-width:52px!important;border-radius:15px!important;
    font-size:30px!important;background:radial-gradient(circle at 30% 25%,rgba(255,255,255,.18),rgba(255,255,255,.035) 58%)!important;
    border:1px solid rgba(255,255,255,.14)!important;box-shadow:0 0 18px rgba(49,215,255,.12)!important;
    display:grid!important;place-items:center!important;font-weight:950!important
  }
  .coinMiniIdentity b{display:block!important;font-size:17px!important;line-height:1.1!important;color:#fff!important;font-weight:1000!important;text-shadow:0 1px 10px rgba(255,255,255,.12)}
  .coinMiniIdentity small{display:block!important;font-size:11px!important;color:#b9cad9!important;margin-top:4px!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;max-width:92px}
  .coinMiniDecision{font-size:11px!important;font-weight:1000!important;padding:7px 8px!important;border-radius:10px!important;border:1px solid currentColor!important;background:rgba(0,0,0,.18)!important;white-space:nowrap!important}
  .coinMiniPriceLine{margin-top:11px!important;font-size:10px!important;color:#9bb0c2!important}
  .coinMiniPriceLine strong{font-size:19px!important;color:#fff!important;font-weight:1000!important;letter-spacing:.1px!important;text-shadow:0 2px 12px rgba(49,215,255,.15)!important}
  .coinMiniPriceLine i{height:8px!important;margin-top:6px!important;background:#0d2234!important;border:1px solid rgba(255,255,255,.05)!important}
  .coinMiniTF{margin-top:9px!important;grid-template-columns:repeat(4,1fr)!important;gap:4px!important}
  .coinMiniTF span{padding:5px 2px!important;border-radius:8px!important;background:rgba(255,255,255,.045)!important;border:1px solid rgba(255,255,255,.06)!important;font-size:9px!important;color:#9fb2c3!important}
  .coinMiniTF b{display:block!important;font-size:11px!important;color:#fff!important;margin-top:2px!important;font-weight:950!important}
  .coinMiniOpen{margin-top:9px!important;padding:7px 8px!important;border-radius:9px!important;background:rgba(49,215,255,.07)!important;border:1px solid rgba(49,215,255,.20)!important;color:#bff3ff!important;font-size:11px!important;font-weight:950!important;text-align:center!important}

  /* Full-detail tab: turn the legacy detailed card into visual modules. */
  .cdFullDetails{font-size:12px!important;line-height:1.8!important}
  .cdFullDetails>.card{padding:13px!important;border-radius:18px!important;background:linear-gradient(145deg,rgba(7,22,39,.96),rgba(4,11,21,.98))!important}
  .cdFullDetails .ch{display:flex!important;align-items:center!important;justify-content:space-between!important;gap:10px!important;padding:12px!important;border-radius:15px!important;background:linear-gradient(135deg,rgba(49,215,255,.10),rgba(124,58,237,.09))!important;border:1px solid rgba(49,215,255,.20)!important}
  .cdFullDetails .coin{display:flex!important;align-items:center!important;gap:10px!important}
  .cdFullDetails .coin .icon{width:56px!important;height:56px!important;display:grid!important;place-items:center!important;border-radius:16px!important;font-size:31px!important;background:radial-gradient(circle at 30% 25%,rgba(255,255,255,.20),rgba(255,255,255,.04) 60%)!important;border:1px solid rgba(255,255,255,.14)!important;box-shadow:0 0 24px rgba(49,215,255,.12)!important}
  .cdFullDetails .coin .name{font-size:18px!important;font-weight:1000!important;color:#fff!important}
  .cdFullDetails .coin .ticker{font-size:10px!important;color:#9eb4c7!important;margin-top:3px!important}
  .cdFullDetails .price{font-size:20px!important;font-weight:1000!important;color:#fff!important;white-space:nowrap!important}
  .cdFullDetails .price small{font-size:10px!important;color:#89a1b5!important}
  .cdFullDetails .scoreRow{margin-top:10px!important;padding:11px!important;border-radius:14px!important;background:rgba(255,255,255,.035)!important;border:1px solid rgba(255,255,255,.07)!important}
  .cdFullDetails .ringGauge{width:64px!important;height:64px!important}
  .cdFullDetails .ringGauge span{font-size:15px!important;font-weight:1000!important}
  .cdFullDetails .bar{height:9px!important;margin-top:9px!important;border-radius:99px!important;background:#0d2234!important;overflow:hidden!important}
  .cdFullDetails .scoreOrbit{display:grid!important;grid-template-columns:repeat(2,1fr)!important;gap:7px!important}
  .cdFullDetails .orbitItem{padding:10px!important;border-radius:12px!important;background:linear-gradient(145deg,rgba(255,255,255,.055),rgba(255,255,255,.018))!important;border:1px solid rgba(255,255,255,.07)!important;text-align:center!important}
  .cdFullDetails .orbitItem small{display:block!important;color:#7893a9!important;font-size:9px!important}
  .cdFullDetails .orbitItem b{display:block!important;font-size:16px!important;color:#fff!important;margin-top:3px!important}
  .cdFullDetails .tf{display:grid!important;grid-template-columns:repeat(4,1fr)!important;gap:6px!important;margin-top:9px!important}
  .cdFullDetails .tf span{padding:9px 3px!important;border-radius:11px!important;background:rgba(49,215,255,.06)!important;border:1px solid rgba(49,215,255,.12)!important;text-align:center!important;color:#8fa7bb!important;font-size:9px!important}
  .cdFullDetails .tf b{display:block!important;color:#fff!important;font-size:12px!important;margin-top:3px!important}
  .cdFullDetails .levels{display:grid!important;grid-template-columns:repeat(2,1fr)!important;gap:7px!important;margin-top:9px!important}
  .cdFullDetails .level{padding:11px!important;border-radius:13px!important;background:rgba(255,255,255,.035)!important;border:1px solid rgba(255,255,255,.07)!important;font-size:10px!important;color:#9db2c4!important}
  .cdFullDetails .level b{display:block!important;font-size:15px!important;color:#fff!important;margin-top:3px!important}
  .cdFullDetails .dualLevels{display:grid!important;grid-template-columns:1fr!important;gap:8px!important;margin-top:9px!important}
  .cdFullDetails .dualBox{padding:13px!important;border-radius:15px!important;font-size:11px!important;line-height:2!important;background:rgba(255,255,255,.03)!important;border:1px solid rgba(255,255,255,.08)!important}
  .cdFullDetails .panelTech{margin-top:9px!important;padding:13px!important;border-radius:15px!important;background:linear-gradient(145deg,rgba(7,26,43,.88),rgba(7,14,27,.96))!important;border:1px solid rgba(49,215,255,.16)!important}
  .cdFullDetails .panelTech .title{display:flex!important;align-items:center!important;gap:6px!important;font-size:13px!important;color:#dff9ff!important;margin-bottom:8px!important}
  .cdFullDetails .gaugeRow{display:grid!important;grid-template-columns:1fr 1fr!important;gap:8px!important}
  .cdFullDetails .gaugeRow>*{min-width:0!important}
  .cdFullDetails table{font-size:10px!important}
  .cdFullDetails table th,.cdFullDetails table td{padding:8px 5px!important}
  .cdFullDetails .miniChip,.cdFullDetails .signalBadge{font-size:10px!important;padding:7px 9px!important}
  .cdFullDetails .gradeBadge{font-size:12px!important;padding:6px 9px!important}
}
@media(max-width:380px){
  .titanCoinRail{grid-template-columns:1fr 1fr!important}
  .coinMiniCard{min-height:150px!important;padding:10px!important}
  .coinMiniIcon{width:46px!important;height:46px!important;min-width:46px!important;font-size:27px!important}
  .coinMiniIdentity b{font-size:15px!important}
  .coinMiniIdentity small{font-size:10px!important;max-width:82px}
  .coinMiniPriceLine strong{font-size:17px!important}
  .cdFullDetails .coin .icon{width:50px!important;height:50px!important;font-size:28px!important}
  .cdFullDetails .coin .name{font-size:16px!important}
}


/* V27.2 MOBILE CLARITY + GRAPHICAL DETAILS */
@media(max-width:600px){
  .titanCoinRail{grid-template-columns:1fr 1fr!important;gap:11px!important}
  .coinMiniCard{color:#f7fbff!important;min-height:176px!important;padding:13px!important;background:linear-gradient(145deg,#102a43 0%,#081a2e 52%,#050e1c 100%)!important;border:2px solid rgba(72,203,255,.42)!important;border-radius:20px!important;box-shadow:0 14px 34px rgba(0,0,0,.38),inset 0 1px 0 rgba(255,255,255,.12)!important}
  .coinMiniCard.long{background:linear-gradient(145deg,#073e35 0%,#082a2c 52%,#061421 100%)!important;border-color:rgba(42,245,177,.78)!important}
  .coinMiniCard.wait{background:linear-gradient(145deg,#493b09 0%,#29250e 52%,#101622 100%)!important;border-color:rgba(255,214,74,.82)!important}
  .coinMiniCard.short{background:linear-gradient(145deg,#4a102c 0%,#2c1229 52%,#101421 100%)!important;border-color:rgba(255,91,125,.82)!important}
  .coinMiniTop{display:flex!important;justify-content:space-between!important;align-items:flex-start!important;gap:7px!important}
  .coinMiniIdentity{display:flex!important;align-items:center!important;gap:10px!important;min-width:0!important}
  .coinMiniIcon{width:56px!important;height:56px!important;min-width:56px!important;display:grid!important;place-items:center!important;border-radius:17px!important;font-size:31px!important;color:#fff!important;background:radial-gradient(circle at 30% 25%,rgba(255,255,255,.30),rgba(49,215,255,.10) 45%,rgba(0,0,0,.18) 100%)!important;border:2px solid rgba(255,255,255,.18)!important;box-shadow:0 0 24px rgba(49,215,255,.22)!important}
  .coinMiniIdentity b{display:block!important;color:#fff!important;font-size:19px!important;font-weight:1000!important;line-height:1.05!important;text-shadow:0 2px 12px rgba(0,0,0,.55)!important}
  .coinMiniIdentity small{display:block!important;color:#d4e7f6!important;font-size:11px!important;font-weight:800!important;margin-top:5px!important;max-width:105px!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}
  .coinMiniDecision{flex:0 0 auto!important;font-size:11px!important;font-weight:1000!important;padding:8px 9px!important;border-radius:11px!important;background:rgba(0,0,0,.32)!important;border:1.5px solid currentColor!important}
  .coinMiniPriceLine{display:grid!important;grid-template-columns:1fr auto!important;align-items:center!important;gap:3px 8px!important;margin-top:12px!important;padding:9px 10px!important;border-radius:14px!important;background:rgba(0,0,0,.28)!important;border:1px solid rgba(255,255,255,.12)!important}
  .coinMiniPriceLabel{color:#b9d3e6!important;font-size:10px!important;font-weight:900!important;grid-column:1!important}
  .coinMiniPriceValue{grid-column:1!important;color:#fff!important;font-size:21px!important;font-weight:1000!important;line-height:1.05!important;white-space:nowrap!important;text-shadow:0 2px 14px rgba(49,215,255,.30)!important}
  .coinMiniPriceValue small{font-size:9px!important;color:#9fc1d8!important}
  .coinMiniScoreBadge{grid-column:2!important;grid-row:1 / span 2!important;align-self:center!important;padding:7px 8px!important;border-radius:11px!important;background:rgba(49,215,255,.13)!important;border:1px solid rgba(49,215,255,.28)!important;color:#e5fbff!important;font-size:10px!important;font-weight:1000!important}
  .coinMiniPriceLine>i{grid-column:1 / -1!important;width:100%!important;height:9px!important;margin:3px 0 0!important;background:#071522!important;border:1px solid rgba(255,255,255,.10)!important;border-radius:99px!important;overflow:hidden!important}
  .coinMiniPriceLine>i em{display:block!important;height:100%!important;border-radius:99px!important;background:linear-gradient(90deg,#22d3ee,#8b5cf6,#34d399)!important}
  .coinMiniTF{margin-top:9px!important;display:grid!important;grid-template-columns:repeat(4,1fr)!important;gap:4px!important}
  .coinMiniTF span{padding:5px 2px!important;text-align:center!important;border-radius:9px!important;background:rgba(255,255,255,.075)!important;border:1px solid rgba(255,255,255,.11)!important;color:#c3d8e7!important;font-size:9px!important;font-weight:800!important}
  .coinMiniTF b{display:block!important;color:#fff!important;font-size:11px!important;font-weight:1000!important;margin-top:2px!important}
  .coinMiniOpen{display:block!important;margin-top:9px!important;padding:8px!important;text-align:center!important;border-radius:10px!important;background:linear-gradient(90deg,rgba(49,215,255,.15),rgba(139,92,246,.13))!important;border:1px solid rgba(49,215,255,.30)!important;color:#e2fbff!important;font-size:11px!important;font-weight:1000!important}
  .cdFullDetails{font-size:12px!important;color:#d9e8f4!important;line-height:1.85!important}
  .cdFullDetails>.card{padding:12px!important;border-radius:20px!important;background:linear-gradient(145deg,#0b2035,#06111f)!important;border:1px solid rgba(49,215,255,.28)!important;box-shadow:0 12px 35px rgba(0,0,0,.30)!important}
  .cdFullDetails .ch{padding:13px!important;border-radius:16px!important;background:linear-gradient(135deg,rgba(49,215,255,.15),rgba(139,92,246,.12),rgba(35,230,168,.08))!important;border:1px solid rgba(49,215,255,.28)!important}
  .cdFullDetails .coin .icon{width:62px!important;height:62px!important;font-size:34px!important;border-radius:18px!important;color:#fff!important;background:radial-gradient(circle at 30% 25%,rgba(255,255,255,.28),rgba(49,215,255,.08) 50%,rgba(0,0,0,.20))!important;border:2px solid rgba(255,255,255,.16)!important;box-shadow:0 0 28px rgba(49,215,255,.20)!important}
  .cdFullDetails .coin .name{font-size:20px!important;color:#fff!important;font-weight:1000!important}.cdFullDetails .coin .ticker{font-size:11px!important;color:#b7d0e2!important;font-weight:800!important}.cdFullDetails .price{font-size:22px!important;color:#fff!important;font-weight:1000!important}.cdFullDetails .price small{font-size:10px!important;color:#a6c4d8!important}
  .cdFullDetails .scoreRow{padding:13px!important;border-radius:16px!important;background:linear-gradient(145deg,rgba(49,215,255,.09),rgba(139,92,246,.07))!important;border:1px solid rgba(255,255,255,.12)!important}
  .cdFullDetails .orbitItem,.cdFullDetails .level,.cdFullDetails .miniCard,.cdFullDetails .gaugeBox{background:linear-gradient(145deg,rgba(255,255,255,.075),rgba(255,255,255,.025))!important;border:1px solid rgba(255,255,255,.10)!important;border-radius:14px!important;box-shadow:0 7px 18px rgba(0,0,0,.18)!important}
  .cdFullDetails .orbitItem b,.cdFullDetails .level b,.cdFullDetails .miniCard b{color:#fff!important;font-weight:1000!important}.cdFullDetails .orbitItem small,.cdFullDetails .level,.cdFullDetails .miniCard{color:#b9cfe0!important}
  .cdFullDetails .bar{height:10px!important;background:#081a2a!important;border:1px solid rgba(255,255,255,.08)!important}.cdFullDetails .tf span{padding:10px 4px!important;border-radius:12px!important;background:linear-gradient(145deg,rgba(49,215,255,.11),rgba(139,92,246,.07))!important;border:1px solid rgba(49,215,255,.18)!important;color:#c9dfec!important;font-weight:900!important}.cdFullDetails .tf b{color:#fff!important;font-size:13px!important}
  .cdFullDetails .dualLevels{display:grid!important;grid-template-columns:1fr!important;gap:10px!important}.cdFullDetails .dualBox{padding:14px!important;border-radius:16px!important;font-size:12px!important;background:linear-gradient(145deg,rgba(255,255,255,.06),rgba(255,255,255,.02))!important;border:1px solid rgba(255,255,255,.10)!important}.cdFullDetails .longBox{border-color:rgba(74,222,128,.35)!important;background:linear-gradient(145deg,rgba(74,222,128,.10),rgba(255,255,255,.02))!important}.cdFullDetails .shortBox{border-color:rgba(248,113,113,.35)!important;background:linear-gradient(145deg,rgba(248,113,113,.10),rgba(255,255,255,.02))!important}
  .cdFullDetails .panelTech{margin-top:11px!important;padding:14px!important;border-radius:17px!important;background:linear-gradient(145deg,rgba(7,31,50,.96),rgba(5,14,26,.98))!important;border:1px solid rgba(49,215,255,.20)!important;box-shadow:0 9px 22px rgba(0,0,0,.20)!important}.cdFullDetails .panelTech .title{font-size:14px!important;color:#e9fbff!important;font-weight:1000!important}.cdFullDetails .miniGrid{display:grid!important;grid-template-columns:1fr 1fr!important;gap:8px!important}.cdFullDetails .miniGrid>.miniCard{padding:11px!important;min-width:0!important}.cdFullDetails table{font-size:11px!important;color:#d6e7f3!important}.cdFullDetails table th{color:#8eddf3!important;background:rgba(49,215,255,.07)!important}.cdFullDetails table td{color:#d6e7f3!important;border-color:rgba(255,255,255,.08)!important}
}
@media(max-width:380px){.coinMiniCard{min-height:166px!important;padding:10px!important}.coinMiniIcon{width:48px!important;height:48px!important;min-width:48px!important;font-size:27px!important}.coinMiniIdentity b{font-size:16px!important}.coinMiniPriceValue{font-size:18px!important}.coinMiniScoreBadge{font-size:9px!important;padding:6px!important}.cdFullDetails .miniGrid{grid-template-columns:1fr!important}}


@media(max-width:600px){.detailVisualLegacy{display:grid!important;gap:10px!important;margin-top:10px!important}.detailVisualGroup{padding:11px!important;border-radius:18px!important;background:linear-gradient(145deg,rgba(9,29,48,.96),rgba(5,14,26,.98))!important;border:1px solid rgba(49,215,255,.18)!important;box-shadow:0 10px 24px rgba(0,0,0,.20)!important}.detailVisualGroupTitle{display:flex!important;align-items:center!important;gap:7px!important;margin-bottom:9px!important;padding:9px 10px!important;border-radius:12px!important;background:linear-gradient(90deg,rgba(49,215,255,.13),rgba(139,92,246,.08))!important;border:1px solid rgba(49,215,255,.15)!important;color:#e8fbff!important;font-size:13px!important;font-weight:1000!important}.detailVisualGroup .panelTech{margin-top:7px!important}}




/* V27.4 card header boost */

.card .ch .name,.card .coin .name{font-size:17px!important;font-weight:1000!important;color:#fff!important;-webkit-text-fill-color:#fff!important;text-shadow:0 1px 8px rgba(0,0,0,.4)!important}
.card .ch .price,.card .price{font-size:20px!important;font-weight:1000!important;color:#fff!important;-webkit-text-fill-color:#fff!important}
.card .icon,.card .coin .icon{width:52px!important;height:52px!important;font-size:28px!important;display:grid!important;place-items:center!important;border-radius:16px!important;background:radial-gradient(circle at 30% 25%,rgba(255,255,255,.28),rgba(49,215,255,.12) 45%,rgba(0,0,0,.2))!important;border:2px solid rgba(255,255,255,.2)!important}
.assetName b{font-size:16px!important;font-weight:1000!important;color:#fff!important}
.assetPrice b{font-size:16px!important;font-weight:1000!important;color:#fff!important}
.assetIcon{font-size:26px!important}


/* ===== ADVANCED WEB DASHBOARD SHELL V28 ===== */

/* V28.4 Active Signals Hero — impossible to miss */
.activeHero{
  margin:10px 0 14px;padding:14px 16px;border-radius:18px;
  border:2px solid rgba(45,245,180,.45);
  background:linear-gradient(120deg,rgba(16,185,129,.18),rgba(8,28,48,.96) 40%,rgba(239,68,68,.12));
  box-shadow:0 0 40px rgba(35,230,168,.15),0 14px 36px rgba(0,0,0,.35);
}
.activeHero.empty{border-color:rgba(255,211,78,.35);background:linear-gradient(120deg,rgba(255,211,78,.1),rgba(8,28,48,.96))}
.activeHeroHead{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:10px;flex-wrap:wrap}
.activeHeroHead h3{margin:0;font-size:15px;font-weight:1000;color:#eafff6;letter-spacing:.3px}
.activeHeroHead .ahCount{font-size:12px;font-weight:950;padding:6px 12px;border-radius:99px;background:rgba(0,0,0,.35);border:1px solid rgba(255,255,255,.12);color:#7dd3fc}
.activeHeroGrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px}
.ahCard{display:flex;flex-direction:column;gap:4px;padding:12px;border-radius:14px;border:1px solid rgba(255,255,255,.1);background:rgba(0,0,0,.28);cursor:pointer;transition:.15s;text-align:right;color:inherit;width:100%}
.ahCard:hover{transform:translateY(-2px);box-shadow:0 10px 24px rgba(0,0,0,.35)}
.ahCard.long{border-color:rgba(35,230,168,.5);background:linear-gradient(160deg,rgba(35,230,168,.2),rgba(0,0,0,.25));box-shadow:inset 0 0 0 1px rgba(35,230,168,.15)}
.ahCard.short{border-color:rgba(255,77,115,.5);background:linear-gradient(160deg,rgba(255,77,115,.2),rgba(0,0,0,.25));box-shadow:inset 0 0 0 1px rgba(255,77,115,.15)}
.ahCard .ahTop{display:flex;justify-content:space-between;align-items:center}
.ahCard .ahTop b{font-size:14px;color:#fff;font-weight:1000}
.ahCard .ahSide{font-size:11px;font-weight:1000;padding:4px 8px;border-radius:99px}
.ahCard.long .ahSide{color:#23e6a8;background:rgba(35,230,168,.15)}
.ahCard.short .ahSide{color:#ff4d73;background:rgba(255,77,115,.15)}
.ahCard .ahMeta{font-size:10px;color:#9fb6c9;font-weight:800}
.ahCard .ahPrice{font-size:13px;color:#fff;font-weight:950;margin-top:2px}
.ahEmpty{font-size:12px;color:#fde68a;font-weight:800;line-height:1.7;padding:6px 2px}

/* V28.3 Top Picks + stronger signal hierarchy */
.topPicksBar{margin:10px 0 12px;padding:12px;border-radius:16px;border:1px solid rgba(49,215,255,.22);background:linear-gradient(135deg,rgba(8,28,48,.95),rgba(6,16,30,.92));box-shadow:0 10px 28px rgba(0,0,0,.25)}
.topPicksLabel{font-size:11px;font-weight:1000;color:#7dd3fc;letter-spacing:.6px;margin-bottom:8px}
.topPicksRow{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
.topPickCard{display:flex;align-items:center;gap:10px;padding:11px 12px;border-radius:14px;border:1px solid rgba(255,255,255,.08);background:rgba(0,0,0,.22);cursor:pointer;transition:.15s;text-align:right;width:100%;color:inherit}
.topPickCard:hover{transform:translateY(-2px);border-color:rgba(49,215,255,.4);box-shadow:0 8px 20px rgba(0,0,0,.3)}
.topPickCard.long{border-color:rgba(35,230,168,.35);background:linear-gradient(145deg,rgba(35,230,168,.12),rgba(0,0,0,.18))}
.topPickCard.short{border-color:rgba(255,77,115,.35);background:linear-gradient(145deg,rgba(255,77,115,.12),rgba(0,0,0,.18))}
.topPickCard .tpIcon{font-size:22px;width:36px;height:36px;display:grid;place-items:center;border-radius:11px;background:rgba(255,255,255,.06)}
.topPickCard .tpBody{min-width:0;flex:1}
.topPickCard .tpBody b{display:block;font-size:13px;font-weight:1000;color:#fff}
.topPickCard .tpBody small{display:block;font-size:10px;color:#8fa7bb;margin-top:2px;font-weight:800}
.assetCard.long{box-shadow:0 0 0 1px rgba(35,230,168,.2),0 12px 28px rgba(0,0,0,.28)!important}
.assetCard.short{box-shadow:0 0 0 1px rgba(255,77,115,.2),0 12px 28px rgba(0,0,0,.28)!important}
.decisionPill.long{box-shadow:0 0 12px rgba(35,230,168,.25)}
.decisionPill.short{box-shadow:0 0 12px rgba(255,77,115,.25)}
@media(max-width:700px){.topPicksRow{grid-template-columns:1fr!important}}

.titanV28Banner{
  background:linear-gradient(90deg,rgba(16,185,129,.28),rgba(49,215,255,.22),rgba(167,139,250,.18))!important;
  border:2px solid rgba(45,245,180,.55)!important;
  font-size:13px!important;font-weight:1000!important;color:#eafff6!important;
  padding:12px 14px!important;border-radius:16px!important;margin-bottom:8px!important;
  box-shadow:0 0 28px rgba(35,230,168,.18)!important;
}
.titanV28Notice{
  margin:0 0 14px!important;padding:10px 12px!important;border-radius:12px!important;
  background:rgba(251,191,36,.12)!important;border:1px dashed rgba(255,211,78,.45)!important;
  color:#ffe9a8!important;font-size:12px!important;font-weight:800!important;line-height:1.7!important;
}
.coinMiniCard{
  outline: none!important;
  transform: none!important;
}
.coinMiniPriceValue{
  font-size:24px!important;
  color:#7ef9ff!important;
  -webkit-text-fill-color:#7ef9ff!important;
}
.coinMiniSymbol{
  color:#ffffff!important;
  font-size:22px!important;
}

.titanApp{max-width:1480px!important;margin:0 auto!important;padding:8px 10px 28px!important}
.topHeader{
  position:sticky!important;top:0!important;z-index:120!important;
  display:grid!important;grid-template-columns:minmax(0,1.1fr) minmax(0,1.4fr) auto!important;
  gap:10px!important;align-items:center!important;
  padding:12px 14px!important;margin-bottom:12px!important;
  border:1px solid rgba(72,203,255,.32)!important;border-radius:22px!important;
  background:linear-gradient(120deg,rgba(5,18,36,.97),rgba(8,22,44,.94) 45%,rgba(12,16,38,.96))!important;
  box-shadow:0 18px 50px rgba(0,0,0,.45),inset 0 1px 0 rgba(255,255,255,.06)!important;
  backdrop-filter:blur(18px)!important;
}
.brand h1{font-size:18px!important;font-weight:1000!important;letter-spacing:.3px!important}
.brand small{font-size:10px!important;color:#8eb0c8!important;font-weight:700!important}
.statusStrip{gap:7px!important}
.statusPill{
  padding:8px 11px!important;border-radius:12px!important;
  background:rgba(255,255,255,.04)!important;border:1px solid rgba(255,255,255,.08)!important;
  font-size:11px!important;font-weight:800!important;
}
.kpiGrid{display:grid!important;grid-template-columns:repeat(auto-fit,minmax(140px,1fr))!important;gap:10px!important;margin:12px 0!important}
.kpi{
  min-height:96px!important;padding:14px!important;border-radius:18px!important;
  background:linear-gradient(155deg,rgba(12,32,54,.95),rgba(6,14,26,.98))!important;
  border:1px solid rgba(72,203,255,.22)!important;
  box-shadow:0 12px 28px rgba(0,0,0,.28)!important;
}
.kpiValue{font-size:24px!important;font-weight:1000!important;color:#fff!important}
.kpiHead{font-size:11px!important;color:#9bb6cb!important;font-weight:900!important;letter-spacing:.4px!important}
.mainTabs{display:flex!important;gap:6px!important;overflow:auto!important;padding:6px!important;border-radius:16px!important;background:rgba(0,0,0,.22)!important;border:1px solid rgba(255,255,255,.07)!important;margin-bottom:12px!important}
.mainTab{flex:0 0 auto!important;padding:10px 14px!important;border-radius:12px!important;font-weight:900!important;font-size:12px!important;color:#8fa7bb!important;border:1px solid transparent!important;background:transparent!important}
.mainTab.active{color:#fff!important;background:rgba(49,215,255,.14)!important;border-color:rgba(49,215,255,.35)!important}
.panel,.section,.hud{
  border-radius:20px!important;
  background:linear-gradient(160deg,rgba(8,22,40,.92),rgba(4,12,24,.96))!important;
  border:1px solid rgba(72,203,255,.16)!important;
  box-shadow:0 14px 36px rgba(0,0,0,.28)!important;
}
.section>h2,.panelTitle{font-size:15px!important;font-weight:1000!important;color:#eaf7ff!important}
@media(max-width:900px){
  .topHeader{grid-template-columns:1fr!important;position:relative!important}
  .statusStrip{order:3!important}
  .headerActions{width:100%!important}
  .kpiGrid{grid-template-columns:repeat(2,minmax(0,1fr))!important}
}
.advLiveBar{
  display:flex!important;flex-wrap:wrap!important;gap:8px!important;align-items:center!important;
  margin:0 0 12px!important;padding:10px 12px!important;border-radius:16px!important;
  background:linear-gradient(90deg,rgba(16,185,129,.12),rgba(49,215,255,.08),rgba(167,139,250,.08))!important;
  border:1px solid rgba(49,215,255,.2)!important;font-size:12px!important;font-weight:800!important;color:#d5ecf8!important;
}
.advLiveBar b{color:#fff!important}
.advLiveDot{width:9px;height:9px;border-radius:50%;background:#23e6a8;box-shadow:0 0 12px #23e6a8;display:inline-block;margin-left:4px}

/* ===== V27.4 UX: crystal-clear coins + mobile box fit + graphical details ===== */
.titanCoinRail{display:grid!important;grid-template-columns:repeat(auto-fill,minmax(158px,1fr))!important;gap:12px!important;width:100%!important;max-width:100%!important;overflow-x:hidden!important;padding:4px 2px 10px!important}
.coinMiniCard{position:relative!important;display:flex!important;flex-direction:column!important;width:100%!important;max-width:100%!important;min-width:0!important;min-height:188px!important;padding:14px 12px 12px!important;overflow:hidden!important;color:#f8fbff!important;-webkit-text-fill-color:#f8fbff!important;background:linear-gradient(155deg,#143352 0%,#0a1f35 48%,#061018 100%)!important;border:2px solid rgba(80,210,255,.55)!important;border-radius:20px!important;box-shadow:0 16px 36px rgba(0,0,0,.45),inset 0 1px 0 rgba(255,255,255,.14)!important}
.coinMiniCard.long{background:linear-gradient(155deg,#0a4a3c 0%,#0a2f2c 50%,#061820 100%)!important;border-color:rgba(45,245,180,.85)!important}