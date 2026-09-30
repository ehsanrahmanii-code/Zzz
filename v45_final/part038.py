        tone(360, 0.08, "triangle", 0.05);
        setTimeout(function(){ tone(540, 0.1, "triangle", 0.045); }, 55);
      } else if(kind === "short"){
        tone(480, 0.08, "sawtooth", 0.035);
        setTimeout(function(){ tone(300, 0.1, "triangle", 0.04); }, 55);
      } else if(kind === "wait"){
        tone(400, 0.07, "sine", 0.035);
      } else if(kind === "success"){
        tone(440, 0.07, "sine", 0.05);
        setTimeout(function(){ tone(660, 0.1, "sine", 0.045); }, 70);
      } else if(kind === "hover"){
        tone(700, 0.025, "sine", 0.018);
      } else {
        tone(480, 0.04, "sine", 0.03);
      }
    } catch(e){}
  }

  function setEnabled(v){
    enabled = !!v;
  }

  function toggle(){
    setEnabled(!enabled);
    play(enabled ? "success" : "click");
    return enabled;
  }

  // Unlock audio on first user gesture (required by browsers)
  ["pointerdown","touchstart","keydown"].forEach(function(ev){
    window.addEventListener(ev, function once(){
      ensure();
      window.removeEventListener(ev, once, true);
    }, true);
  });

  return { play: play, toggle: toggle, setEnabled: setEnabled, isEnabled: function(){ return enabled; }, unlock: ensure };
})();

/* Wire sounds to common UI actions */
(function(){
  function decisionSound(el){
    if(!el || !window.TitanSFX) return;
    var d = (el.getAttribute("data-decision") || el.getAttribute("data-side") || "").toUpperCase();
    if(d === "LONG") TitanSFX.play("long");
    else if(d === "SHORT") TitanSFX.play("short");
    else if(d === "WAIT") TitanSFX.play("wait");
    else TitanSFX.play("open");
  }

  document.addEventListener("click", function(ev){
    if(!window.TitanSFX) return;
    var t = ev.target;
    if(!t || !t.closest) return;
    var card = t.closest(".coinMiniCard, .assetCard, .ticker, [data-jump]");
    if(card){
      decisionSound(card);
      return;
    }
    var tab = t.closest(".sideBtn, .mainTab, .coinDetailTab, .assetTools button");
    if(tab){
      TitanSFX.play("tab");
      return;
    }
    var btn = t.closest(".glassBtn, button, a.glassBtn");
    if(btn){
      TitanSFX.play("click");
    }
  }, true);

  // Subtle hover ticks only on fine pointers (desktop)
  if(window.matchMedia && window.matchMedia("(hover:hover) and (pointer:fine)").matches){
    var hoverLast = 0;
    document.addEventListener("mouseover", function(ev){
      if(!window.TitanSFX || !TitanSFX.isEnabled()) return;
      var t = ev.target;
      if(!t || !t.closest) return;
      var el = t.closest(".ticker, .assetCard, .coinMiniCard, .glassBtn, .sideBtn");
      if(!el) return;
      var now = Date.now();
      if(now - hoverLast < 120) return;
      hoverLast = now;
      TitanSFX.play("hover");
    }, true);
  }
})();

})();

/* Ensure colored borders on cards even if class missing */
(function(){
  function paintBorders(){
    var nodes = document.querySelectorAll(".ticker, .assetCard, .coinMiniCard");
    nodes.forEach(function(el, i){
      var has = false;
      for(var h=0;h<12;h++){ if(el.classList.contains("coinHue"+h)){ has=true; break; } }
      if(!has) el.classList.add("coinHue" + (i % 12));
    });
  }
  if(document.readyState === "loading") document.addEventListener("DOMContentLoaded", paintBorders);
  else paintBorders();
  setTimeout(paintBorders, 800);
})();

</script></body></html>

</body></html>
'''

# ============================================================
# TITAN V10.5 — COGNITIVE NEXUS / EVIDENCE GRAPH
# ------------------------------------------------------------------
# Final arbitration layer above the existing V10 engine.
# Analysis-only: no live order execution and no fabricated market data.
#
# It connects:
# live freshness -> multi-TF spine -> structure/regime -> derivatives
# -> precision -> forecast/patterns -> AI ensemble -> historical outcomes
# -> neural V9 -> Cognitive Nexus -> one canonical decision.
# ============================================================

CNS_VERSION = "TITAN-CNS-10.6-BALANCED"
CNS_HISTORY_LIMIT = 320
CNS_MIN_HISTORY = 5
CNS_PROMOTE_MIN_STRENGTH = 0.40
CNS_PROMOTE_MIN_MARGIN = 0.07
CNS_PROMOTE_MIN_QUALITY = 48.0
CNS_PROMOTE_MIN_DQ = 50.0
CNS_PROMOTE_MIN_NEURAL = 42.0
CNS_PROMOTE_MIN_RR = 1.02
CNS_HARD_CONFLICT = 0.85


class TitanCognitiveNexusV10:
    """Evidence-graph arbitration with Bayesian historical shrinkage.

    Each evidence source is normalized to [-1,+1].
    Historical win rates use Beta(2,2) shrinkage so small samples cannot
    become artificial 0%/100% certainty. Historical data calibrates fresh
    evidence; it never creates a trade by itself.
    """

    TF_WEIGHTS = {"15m": 0.15, "1h": 0.28, "4h": 0.30, "1d": 0.27}

    def _beta_wr(self, wins: float, losses: float) -> float:
        wins = max(0.0, float(wins))
        losses = max(0.0, float(losses))
        return ((wins + 2.0) / (wins + losses + 4.0)) * 100.0

    def _history(self, symbol: str, direction: str, timeframe: str = "") -> dict[str, Any]:
        """Recency-aware historical evidence from evaluated forecasts."""
        out = {
            "samples": 0, "wins": 0, "losses": 0,
            "win_rate": 50.0, "recent_wr": 50.0,
            "confidence": 0.0, "source": "sqlite",
        }
        try:
            params = [symbol, direction]
            sql = (
                "SELECT outcome,created_at FROM forecasts "
                "WHERE symbol=? AND direction=? AND outcome IN ('WIN','LOSS') "
            )
            if timeframe:
                sql += "AND timeframe=? "
                params.append(timeframe)
            sql += "ORDER BY created_at DESC LIMIT ?"
            params.append(CNS_HISTORY_LIMIT)

            with DB_LOCK, db_conn() as con:
                rows = con.execute(sql, params).fetchall()

            if not rows:
                return out

            wins = sum(1 for r in rows if str(r["outcome"]) == "WIN")
            losses = sum(1 for r in rows if str(r["outcome"]) == "LOSS")

            # Recent observations receive more weight, while old observations
            # remain useful for regime-independent baseline calibration.
            now = time.time()
            rw = rl = 0.0
            for i, r in enumerate(rows):
                age_days = max(
                    0.0,
                    (now - safe_float(r["created_at"], now)) / 86400.0,
                )
                w = math.exp(-age_days / 21.0) * (0.985 ** i)
                if str(r["outcome"]) == "WIN":
                    rw += w
                else:
                    rl += w

            out.update({
                "samples": wins + losses,
                "wins": wins,
                "losses": losses,
                "win_rate": round(self._beta_wr(wins, losses), 2),
                "recent_wr": round(self._beta_wr(rw, rl), 2),
                "confidence": round(clamp((wins + losses) / 40.0, 0, 1), 3),
            })
        except Exception as exc:
            LOGGER.debug("CNS history failed %s/%s: %s", symbol, direction, exc)
        return out

    def _ai_reliability(self, symbol: str, direction: str) -> dict[str, Any]:
        """Provider-specific historical alignment from persisted AI votes."""
        out = {
            "samples": 0,
            "aligned": 0,
            "alignment_pct": 50.0,
            "providers": {},
        }
        try:
            with DB_LOCK, db_conn() as con:
                rows = con.execute(
                    "SELECT provider,direction,aligned,created_at "
                    "FROM ai_votes WHERE symbol=? "
                    "ORDER BY created_at DESC LIMIT 160",
                    (symbol,),
                ).fetchall()

            aligned = 0
            total = 0
            providers: dict[str, list[int]] = {}
            for r in rows:
                if str(r["direction"] or "") != direction:
                    continue
                total += 1
                aligned += int(bool(r["aligned"]))
                providers.setdefault(str(r["provider"]), []).append(
                    int(bool(r["aligned"]))
                )

            out["samples"] = total
            out["aligned"] = aligned
            out["alignment_pct"] = round(aligned / total * 100, 1) if total else 50.0
            out["providers"] = {
                k: round(sum(v) / len(v) * 100, 1)
                for k, v in providers.items()
                if v
            }
        except Exception as exc:
            LOGGER.debug("CNS AI reliability failed %s: %s", symbol, exc)
        return out

    def _tf_evidence(
        self, tf_scores: dict[str, Any]
    ) -> tuple[float, float, dict[str, Any]]:
        long_e = short_e = 0.0
        used = 0.0
        rows = {}

        for tf, w in self.TF_WEIGHTS.items():
            if tf not in tf_scores:
                continue
            s = clamp(safe_float(tf_scores.get(tf), 50), 0, 100)
            e = (s - 50.0) / 50.0
            long_e += max(0.0, e) * w
            short_e += max(0.0, -e) * w
            used += w
            rows[tf] = {
                "score": round(s, 1),
                "edge": round(e, 3),
                "weight": w,
            }

        if used <= 0:
            return 0.0, 0.0, {"coherence": 0.0, "frames": rows}

        long_e /= used
        short_e /= used

        active = [v["edge"] for v in rows.values() if abs(v["edge"]) >= 0.08]
        if len(active) <= 1:
            coherence = 0.35 if active else 0.0
        else:
            signs = [1 if x > 0 else -1 for x in active]
            dominant = max(signs.count(1), signs.count(-1))
            coherence = dominant / len(signs)

        return (
            long_e,
            short_e,
            {"coherence": round(coherence, 3), "frames": rows},
        )

    def evaluate(self, item: dict[str, Any]) -> dict[str, Any]:
        symbol = str(item.get("symbol") or "")
        tf_scores = item.get("tf_scores") or {}
        tf_long, tf_short, tf_meta = self._tf_evidence(tf_scores)

        edge = item.get("edge") or {}
        structure = edge.get("structure") or {}
        confluence = edge.get("confluence") or {}
        regime = edge.get("regime") or {}
        precision = item.get("precision") or {}
        neural = (
            item.get("neural_v9")
            or (item.get("fusion") or {}).get("neural_v9")
            or {}