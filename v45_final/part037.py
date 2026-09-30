      if(el) el.textContent = d.ready ? "Gemini تحلیل جدید تولید کرد" : (d.available ? "Gemini متصل است ولی پاسخی آماده نیست" : "کلید Gemini تنظیم نشده است");
    } else if(el) el.textContent = "Gemini در دسترس نیست";
  } catch(e) {
    var el2 = safeEl("geminiRefreshState");
    if(el2) el2.textContent = "خطا: " + (e.message||e);
  }
}
async function refreshAdvanced(){
  try {
    var d = await fetch("/api/advanced-metrics", { cache: "no-store" }).then(function(r){ return r.json(); });
    if(!d || !d.ok) return;
    var m = d.metrics || {}, l = m.live || {}, h = m.historical || {}, p = m.paper || {}, q = m.data_quality || {};
    setText("adv-live", (l.status||"--") + " · " + (l.median_age_ms != null ? l.median_age_ms : "-") + "ms");
    setText("adv-hist", (h.win_rate||0) + "% · " + (h.wins||0) + "W/" + (h.losses||0) + "L");
    setText("adv-paper", (p.win_rate||0) + "% · PF=" + (p.profit_factor != null ? p.profit_factor : "-") + " · O=" + (p.open||0));
    setText("adv-quality", (q.healthy||0) + " / " + (q.samples||0));
  } catch(e) {}
}
async function runBacktest(){
  var out = safeEl("adv-result");
  if(out) out.textContent = "در حال اجرای بک‌تست…";
  try {
    var sym = window.currentTFSymbol || "BTC/USDT";
    var j = await fetch("/api/backtest?symbol=" + encodeURIComponent(sym) + "&timeframe=1h&limit=800").then(function(r){ return r.json(); });
    if(out) out.textContent = JSON.stringify(j, null, 2);
  } catch(e) { if(out) out.textContent = String(e); }
}
async function runWalkForward(){
  var out = safeEl("adv-result");
  if(out) out.textContent = "در حال اجرای Walk-Forward…";
  try {
    var sym = window.currentTFSymbol || "BTC/USDT";
    var j = await fetch("/api/walk-forward?symbol=" + encodeURIComponent(sym) + "&timeframe=1h&limit=800&train=250&test=80").then(function(r){ return r.json(); });
    if(out) out.textContent = JSON.stringify(j, null, 2);
  } catch(e) { if(out) out.textContent = String(e); }
}

function performanceScore(m){
  m = m || {};
  var wr = Number(m.win_rate) || 0;
  var pf = Number(m.profit_factor);
  var exp = Number(m.expectancy) || 0;
  var s = wr * 0.45 + Math.min(100, Math.max(0, (isFinite(pf) ? pf : 0) * 50)) * 0.30 + Math.min(100, Math.max(0, 50 + exp * 50)) * 0.25;
  return Math.max(0, Math.min(100, s));
}
function drawEquityVisual(values){
  var c = safeEl("equityVisual"); if(!c) return;
  var ctx = c.getContext("2d"), dpr = window.devicePixelRatio||1, w = c.clientWidth||500, h = c.clientHeight||220;
  c.width = w*dpr; c.height = h*dpr; ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.clearRect(0,0,w,h);
  ctx.strokeStyle = "#ffffff18"; ctx.lineWidth = 1;
  for(var i=1;i<5;i++){ var y=i*h/5; ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke(); }
  if(!values || !values.length) return;
  var min = Math.min(0, Math.min.apply(null, values)), max = Math.max(0, Math.max.apply(null, values));
  if(min===max){ min-=1; max+=1; }
  function x(i){ return 8 + i*(w-16)/Math.max(1, values.length-1); }
  function y(v){ return h-18 - (v-min)/(max-min)*(h-35); }
  ctx.beginPath();
  values.forEach(function(v,i){ if(i) ctx.lineTo(x(i),y(v)); else ctx.moveTo(x(i),y(v)); });
  ctx.strokeStyle = "#38bdf8"; ctx.lineWidth = 2.5; ctx.stroke();
}
function drawWLVisual(wins, losses, neutral){
  var c = safeEl("wlVisual"); if(!c) return;
  var ctx = c.getContext("2d"), dpr = window.devicePixelRatio||1, w = c.clientWidth||300, h = c.clientHeight||220;
  c.width = w*dpr; c.height = h*dpr; ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.clearRect(0,0,w,h);
  var vals = [Math.max(0,wins), Math.max(0,losses), Math.max(0,neutral)];
  var total = Math.max(1, vals[0]+vals[1]+vals[2]);
  var cx = w/2, cy = h/2-8, r = Math.min(w,h)*0.32, a = -Math.PI/2;
  var colors = ["#4ade80","#f43f5e","#64748b"];
  vals.forEach(function(v,i){ var da=v/total*Math.PI*2; ctx.beginPath(); ctx.moveTo(cx,cy); ctx.arc(cx,cy,r,a,a+da); ctx.closePath(); ctx.fillStyle=colors[i]; ctx.fill(); a+=da; });
  ctx.beginPath(); ctx.arc(cx,cy,r*0.58,0,Math.PI*2); ctx.fillStyle="#071020"; ctx.fill();
  ctx.fillStyle="#eef2ff"; ctx.font="900 18px Tahoma"; ctx.textAlign="center";
  ctx.fillText((vals[0]/total*100).toFixed(1)+"%", cx, cy+6);
}
async function loadVisualPerformance(){
  var note = safeEl("visNote");
  if(note) note.textContent = "در حال تحلیل عملکرد…";
  var sym = window.currentTFSymbol || "BTC/USDT";
  var tfs = ["15m","1h","4h","1d"];
  try {
    var results = {};
    for(var i=0;i<tfs.length;i++){
      try {
        results[tfs[i]] = await fetch("/api/performance?symbol="+encodeURIComponent(sym)+"&timeframe="+tfs[i]+"&limit=600",{cache:"no-store"}).then(function(r){return r.json();});
      } catch(err){ results[tfs[i]] = {ok:false}; }
    }
    var base = results["1h"] || {};
    var m = (base.backtest && base.backtest.metrics) || base.historical || {};
    var hist = base.historical || {};
    var wr = Number(m.win_rate || hist.win_rate || 0);
    var wins = Number(m.wins || hist.wins || 0);
    var losses = Number(m.losses || hist.losses || 0);
    var neutral = Number(m.neutral_trades || hist.neutral || 0);
    var score = performanceScore(m);
    setText("visWR", wr.toFixed(1)+"%");
    var ring = safeEl("wrRing"); if(ring) ring.style.setProperty("--v", Math.max(0, Math.min(100, wr)));
    setText("visWL", wins+" W / "+losses+" L");
    setText("visScore", score.toFixed(0)+"/100");
    var sb = safeEl("visScoreBar"); if(sb) sb.style.width = score+"%";
    setText("visExp", (Number(m.expectancy)||0).toFixed(3)+"%");
    setText("visPF", "PF: " + (m.profit_factor==null?"—":Number(m.profit_factor).toFixed(2)));
    setText("visDD", (Number(m.max_drawdown)||0).toFixed(2)+"%");
    var oos = (base.walk_forward && base.walk_forward.professional && base.walk_forward.professional.out_of_sample && base.walk_forward.professional.out_of_sample.status) || "—";
    setText("visOOS", "OOS: "+oos);
    var tfEl = safeEl("tfVisual");
    if(tfEl){
      tfEl.innerHTML = "";
      tfs.forEach(function(tf){
        var d = results[tf] || {};
        var mm = (d.backtest && d.backtest.metrics) || {};
        var sc = performanceScore(mm);
        var wr2 = Number(mm.win_rate)||0;
        var div = document.createElement("div");
        div.className = "tfBox";
        div.innerHTML = "<b>"+tf+"</b><div style='font-size:18px;font-weight:900;margin-top:4px'>"+sc.toFixed(0)+"/100</div><small style='color:#94a3b8'>WR "+wr2.toFixed(1)+"%</small><div class='tfBar'><i style='width:"+sc+"%'></i></div>";
        tfEl.appendChild(div);
      });
    }
    var rs = (base.backtest && base.backtest.return_series_pct) || [];
    var equity = [0], eq = 1;
    (rs||[]).forEach(function(x){
      var r = Number(x);
      if(!isFinite(r)) return;
      eq *= (1 + r/100);
      equity.push((eq-1)*100);
    });
    drawEquityVisual(equity.length > 1 ? equity : [0]);
    drawWLVisual(wins, losses, neutral);
    if(note) note.textContent = "منبع: بک‌تست برای "+sym;
  } catch(e) {
    if(note) note.textContent = "خطا: "+(e.message||e);
  }
}

async function refreshScanTelemetry(){
  try{
    var j=await fetch("/api/scan-progress",{cache:"no-store"}).then(function(r){return r.json();});
    var p=(j&&j.progress)||{};
    var pct=Math.max(0,Math.min(100,Number(p.percent)||0));
    var bar=safeEl("scanBar"); if(bar) bar.style.width=pct+"%";
    setText("scanPct",pct.toFixed(0)+"%");
    setText("scanPhase",p.message||p.phase||"آماده");
    var finished=Number(p.last_success_at||p.finished_at||0);
    if(finished){
      var d=new Date(finished*1000);
      setText("scanTime","آخرین اسکن: "+d.toLocaleString("fa-IR"));
    } else if(p.status==="running") setText("scanTime","اسکن جدید در حال اجراست…");
    else setText("scanTime","آخرین اسکن: ثبت نشده");
    var age=(j&&j.progress&&j.progress.cache_age_sec!=null)?Number(j.progress.cache_age_sec):null;
    if(age!=null) setText("scanAge",age<60?"داده: "+age.toFixed(0)+" ثانیه پیش":"داده: "+(age/60).toFixed(1)+" دقیقه پیش");
    var box=safeEl("scanTelemetry"); if(box){ box.style.opacity=(p.status==="running"?"1":".94"); }
  }catch(e){}
}
function refreshPerformanceLearning(){
  var sym=window.currentTFSymbol||"";
  fetch("/api/performance-learning"+(sym?"?symbol="+encodeURIComponent(sym):""),{cache:"no-store"}).then(function(r){return r.json();}).then(function(j){
    if(!j||!j.ok)return;
    var s=j.summary||{};
    setText("learnTotal",String(s.total||0)); setText("learnWR",s.directional_win_rate==null?"—":s.directional_win_rate+"%"); setText("learnPending",String(s.pending||0)); setText("learnWaitMiss",String(s.wait_missed||0));
    var tb=safeEl("learnTable"); if(!tb)return;
    var rows=(j.matrix&&j.matrix.items)||[];
    tb.innerHTML=rows.slice(0,24).map(function(x){return "<tr><td>"+(x.symbol||"")+(x.timeframe?" · "+x.timeframe:"")+"</td><td>"+(x.decision||"")+"</td><td>"+(x.samples||0)+"</td><td>"+(x.win_rate==null?"—":x.win_rate+"%")+"</td><td>"+(x.reliability||50)+"</td><td>"+(x.sample_status||"")+(x.wait_missed?" · miss "+x.wait_missed:"")+"</td></tr>";}).join("")||"<tr><td colspan='6'>هنوز نمونه تاریخی کافی ثبت نشده است.</td></tr>";
  }).catch(function(){});
}

/* ---------- fast bootstrap: show cached dashboard first, then refresh once data is ready ---------- */
function pollDashboardReady(){
  try {
    if(document.querySelectorAll(".card[data-symbol]").length > 0) return;
    fetch("/api/dashboard-status", {cache:"no-store"}).then(function(r){return r.json();}).then(function(d){
      if(d && d.ready){ window.location.reload(); }
      else if(d && d.refreshing){ setTimeout(pollDashboardReady, 1800); }
    }).catch(function(){ setTimeout(pollDashboardReady, 2500); });
  } catch(e){ setTimeout(pollDashboardReady, 2500); }
}

/* ---------- boot: charts + live first ---------- */
function bootUI(){
  try{initTitanCoinNavigation();}catch(e){}
  try { initCoinDetailTabs(); } catch(e){ console.warn(e); }
  try { loadAllCardCharts(); } catch(e){ console.warn(e); }
  // Draw server-rendered forecast paths
  try {
    qsa(".patternPanel").forEach(function(p){
      var id = p.id || "";
      var tv = id.replace("pattern-","");
      if(!tv) return;
      // fetch once for chart
      var card = document.getElementById("card-" + tv);
      var sym = card ? card.getAttribute("data-symbol") : null;
      if(sym) setTimeout(function(){ refreshPatternForecast(sym, tv); }, 1200);
    });
  } catch(e){}
  // First paint is kept lightweight. Heavy analytics start only after the UI is visible.
  try { setTimeout(loadAllCoinCharts, 900); } catch(e){}
  try { setTimeout(refreshLive, 50); } catch(e){}
  try { setTimeout(refreshScalpWindow, 400); } catch(e){}
  try { setInterval(refreshScalpWindow, 45000); } catch(e){}
  try { setTimeout(refreshPulse, 250); } catch(e){}
  try { setTimeout(refreshAdvanced, 700); } catch(e){}
  try { setTimeout(refreshScanTelemetry, 200); setInterval(refreshScanTelemetry, 2500); } catch(e){}
  try { setTimeout(refreshPerformanceLearning, 1200); setInterval(refreshPerformanceLearning, 30000); } catch(e){}
  try { setTimeout(loadVisualPerformance, 2500); } catch(e){}
  try { setTimeout(pollDashboardReady, 1200); } catch(e){}

  try {
    var sb = document.getElementById("sfxToggleBtn");
    if(sb && window.TitanSFX){
      var on = TitanSFX.isEnabled();
      sb.textContent = on ? "🔊 صدا" : "🔇 قطع";
    }
  } catch(e){}

  setInterval(refreshLive, 2500);
  setInterval(refreshPulse, 15000);
  setInterval(refreshAdvanced, 30000);
}

if(document.readyState === "loading"){
  document.addEventListener("DOMContentLoaded", bootUI);
} else {
  bootUI();
}

window.addEventListener("resize", function(){
  qsa(".tv-fallback").forEach(function(cv){
    if(cv.style.display !== "none" && cv._candles) drawCandleChart(cv, cv._candles, cv._title || "");
  });
});

/* event delegation so chips/buttons always work */
document.addEventListener("click", function(ev){
  var t = ev.target;
  if(!t) return;
  var chip = t.closest ? t.closest(".coinMiniCard, .coinChip, [data-jump]") : null;
  if(chip){
    ev.preventDefault();
    var tv = chip.getAttribute("data-jump") || chip.getAttribute("data-tv");
    var sym = chip.getAttribute("data-symbol");
    if(!sym && tv){
      var card = safeEl("card-" + tv);
      if(card) sym = card.getAttribute("data-symbol");
    }
    jumpToCoin(tv, sym);
    return;
  }
});


/* ===== TITAN SFX: Web-Audio UI sounds (no external files) ===== */
window.TitanSFX = (function(){
  var ctx = null, unlocked = false, enabled = true, lastTs = 0;
  function ensure(){
    if(!ctx){
      var AC = window.AudioContext || window.webkitAudioContext;
      if(!AC) return null;
      ctx = new AC();
    }
    if(ctx.state === "suspended"){
      try { ctx.resume(); } catch(e){}
    }
    unlocked = true;
    return ctx;
  }

  function tone(freq, dur, type, vol, slide){
    if(!enabled) return;
    var c = ensure();
    if(!c) return;
    var now = c.currentTime;
    var o = c.createOscillator();
    var g = c.createGain();
    o.type = type || "sine";
    o.frequency.setValueAtTime(freq, now);
    if(slide){
      o.frequency.linearRampToValueAtTime(slide, now + dur);
    }
    g.gain.setValueAtTime(0.0001, now);
    g.gain.exponentialRampToValueAtTime(Math.max(0.001, vol || 0.06), now + 0.012);
    g.gain.exponentialRampToValueAtTime(0.0001, now + dur);
    o.connect(g); g.connect(c.destination);
    o.start(now);
    o.stop(now + dur + 0.02);
  }

  function play(kind){
    if(!enabled) return;
    var t = Date.now();
    if(t - lastTs < 35) return; // debounce spam
    lastTs = t;
    try {
      if(kind === "click"){
        tone(520, 0.05, "triangle", 0.045);
      } else if(kind === "tab"){
        tone(380, 0.06, "sine", 0.04);
        setTimeout(function(){ tone(520, 0.05, "sine", 0.03); }, 40);
      } else if(kind === "open"){
        tone(280, 0.09, "sine", 0.05, 520);
      } else if(kind === "long"){