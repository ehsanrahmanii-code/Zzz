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