  try {
    var fd = await fetch("/api/pattern-forecast?symbol=" + encodeURIComponent(symbol) + "&timeframe=1h&horizon=12", {cache:"no-store"}).then(function(r){return r.json();});
    var ft = document.getElementById("cdForecastText");
    if(fd && fd.ok && fd.forecast){
      if(ft) ft.textContent = fd.forecast.narrative || ("روند احتمالی: " + (fd.forecast.overall_bias||"—") + " · حرکت مورد انتظار " + (fd.forecast.expected_move_pct||0) + "%");
      var fc = document.getElementById("cdForecastCanvas");
      if(fc){ window._cdForecast = fd.forecast; drawForecastIntoCanvas(fc, fd.forecast); }
    } else if(ft) ft.textContent = "پیش‌بینی برای این لحظه داده کافی ندارد.";
  } catch(e){ var ft2=document.getElementById("cdForecastText"); if(ft2) ft2.textContent="پیش‌بینی کندل در دسترس نیست."; }
  try {
    var av = await fetch("/api/ai-votes", {cache:"no-store"}).then(function(r){return r.json();});
    var row = (av && av.board || []).find(function(x){return x.symbol===symbol;});
    var aiEl = document.getElementById("cdAIOpinion");
    if(aiEl && row){
      aiEl.innerHTML = '<b>' + (row.majority||"WAIT") + '</b> · اجماع ' + (row.agreement||0) + '% · وضعیت ' + (row.status||"—") +
        '<br><small>Gemini: ' + ((row.gemini||"—").toString().slice(0,220)) + '</small>';
    }
  } catch(e){}
}

function drawForecastIntoCanvas(cv, fc){
  try{
    var candles=fc.candles||[]; if(!candles.length) return;
    var dpr=window.devicePixelRatio||1,W=cv.clientWidth||320,H=220;
    cv.width=Math.floor(W*dpr);cv.height=Math.floor(H*dpr);
    var ctx=cv.getContext("2d");ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,W,H);
    var lo=Math.min.apply(null,candles.map(function(c){return +c.band_low;}));
    var hi=Math.max.apply(null,candles.map(function(c){return +c.band_high;})); if(lo===hi){lo*=.99;hi*=1.01;}
    var pad=12, x=function(i){return pad+i*(W-pad*2)/Math.max(1,candles.length-1)}, y=function(v){return pad+(1-(v-lo)/(hi-lo))*(H-pad*2)};
    ctx.strokeStyle="rgba(56,189,248,.18)";ctx.lineWidth=1;
    for(var g=0;g<4;g++){var gy=pad+g*(H-pad*2)/3;ctx.beginPath();ctx.moveTo(pad,gy);ctx.lineTo(W-pad,gy);ctx.stroke();}
    ctx.beginPath();candles.forEach(function(c,i){i?ctx.lineTo(x(i),y(+c.band_high)):ctx.moveTo(x(i),y(+c.band_high));});
    for(var j=candles.length-1;j>=0;j--)ctx.lineTo(x(j),y(+candles[j].band_low));ctx.closePath();ctx.fillStyle="rgba(56,189,248,.10)";ctx.fill();
    ctx.beginPath();candles.forEach(function(c,i){i?ctx.lineTo(x(i),y(+c.close)):ctx.moveTo(x(i),y(+c.close));});ctx.strokeStyle="#c084fc";ctx.lineWidth=2.4;ctx.stroke();
    candles.forEach(function(c,i){ctx.fillStyle=c.direction==="صعودی"?"#22c55e":c.direction==="نزولی"?"#ef4444":"#facc15";ctx.beginPath();ctx.arc(x(i),y(+c.close),3.2,0,Math.PI*2);ctx.fill();});
    ctx.fillStyle="#cbd5e1";ctx.font="11px Tahoma";ctx.fillText("پیش‌بینی "+(fc.overall_bias||"—")+" · "+candles.length+" کندل",pad,12);
  }catch(e){}
}

function initCoinDetailTabs(){
  document.querySelectorAll("#coinDetailTabs .coinDetailTab").forEach(function(btn){
    btn.addEventListener("click",function(){
      var id=btn.getAttribute("data-cdtab");
      document.querySelectorAll("#coinDetailTabs .coinDetailTab").forEach(function(b){b.classList.toggle("active",b===btn);});
      document.querySelectorAll(".coinDetailPanel").forEach(function(p){p.classList.toggle("active",p.getAttribute("data-cdpanel")===id);});
      if(id==="charts"){var cv=document.getElementById("cdCanvas");if(cv&&cv._candles)drawCandleChart(cv,cv._candles,window.currentTFSymbol||"");}
      if(id==="forecast"&&window._cdForecast){var fcv=document.getElementById("cdForecastCanvas");if(fcv)drawForecastIntoCanvas(fcv,window._cdForecast);}
    });
  });
}

function initTitanCoinNavigation(){
  var root=document.getElementById("coinNav"); if(!root) return;
  var rail=root.querySelector(".titanCoinRail");
  if(!rail) return;
  function applyFilter(filter){
    root.querySelectorAll(".glassFilter").forEach(function(b){
      b.classList.toggle("active",b.getAttribute("data-navfilter")===filter);
    });
    rail.querySelectorAll(".coinMiniCard").forEach(function(card){
      var tag=card.getAttribute("data-decision")||"WAIT";
      card.style.display=(filter==="all" || filter===tag)?"":"none";
    });
  }
  root.querySelectorAll(".glassFilter").forEach(function(btn){
    btn.addEventListener("click",function(){applyFilter(btn.getAttribute("data-navfilter")||"all");});
  });
  applyFilter("all");
}

function jumpToCoin(tv, symbol){
  window.currentTFSymbol = symbol || window.currentTFSymbol;
  window._detailTv = tv || window._detailTv;
  var card = safeEl("card-" + tv) || qs('.card[data-symbol="' + symbol + '"]');
  if(card) openCoinDetailFromCard(card);
  else scrollToCard(tv);
}

window.jumpToCoin = jumpToCoin;
window.scrollToCard = scrollToCard;
window.closeCoinDetail = closeCoinDetail;
window.openTFWindow = openTFWindow;
window.closeTFWindow = closeTFWindow;
window.loadAllCoinCharts = loadAllCoinCharts;
window.loadVisualPerformance = loadVisualPerformance;
window.refreshGemini = refreshGemini;
window.refreshAdvanced = refreshAdvanced;
window.runBacktest = runBacktest;
window.runWalkForward = runWalkForward;
window.loadEdgeTerminal = loadEdgeTerminal;
window.runProLab = runProLab;
window.openM = openM;
window.closeM = closeM;

/* ---------- TF gauge ---------- */
function openTFWindow(symbol){
  window.currentTFSymbol = symbol || window.currentTFSymbol || "BTC/USDT";
  var m = document.getElementById("tfWindow");
  if(m){
    m.style.display = "flex";
    m.style.zIndex = "1300";
  }
  try { loadTFGauge(); } catch(e){ console.warn(e); }
}
function closeTFWindow(){
  var m = safeEl("tfWindow");
  if(m) m.style.display = "none";
}
async function loadTFGauge(){
  var box = safeEl("tfGaugeBox");
  var title = safeEl("tfModalTitle");
  if(box) box.innerHTML = "<div style='color:#94a3b8;grid-column:1/-1'>در حال دریافت عقربه‌های گرافیکی…</div>";
  try {
    var sym = window.currentTFSymbol || "BTC/USDT";
    if(title) title.textContent = "عقربه‌های تایم‌فریم · " + sym;
    var d = await fetch("/api/tf-gauge?symbol=" + encodeURIComponent(sym), { cache: "no-store" }).then(function(r){ return r.json(); });
    if(!box) return;
    if(d && d.ok && d.timeframes && d.timeframes.length){
      box.innerHTML = d.timeframes.map(function(x){
        var sc = Number(x.score)||0;
        var col = sc>=60 ? "#4ade80" : sc<=40 ? "#f43f5e" : "#fbbf24";
        var emoji = sc>=60 ? "🚀" : sc<=40 ? "🔻" : "⚖️";
        var label = sc>=60 ? "صعودی" : sc<=40 ? "نزولی" : "خنثی";
        var mode = sc>=60 ? "▲ خرید" : sc<=40 ? "▼ فروش" : "◆ انتظار";
        var modeCol = sc>=60 ? "#4ade80" : sc<=40 ? "#f43f5e" : "#fbbf24";
        return '<div class="tfGaugeCard">' +
          '<div style="font-weight:900;color:#e2e8f0">' + emoji + " " + x.name + "</div>" +
          '<div class="ringGauge" style="--gv:' + sc + ";--gcol:" + col + '"><span style="color:' + col + '">' + sc + "</span></div>" +
          '<div style="font-weight:900;color:' + modeCol + ';margin-bottom:4px;font-size:15px">' + mode + "</div>" +
          '<div style="font-weight:800;color:' + col + ';margin-bottom:6px">' + label + " · " + sc + "/100</div>" +
          '<div class="scoreOrbit">' +
            '<div class="orbitItem"><small>روند</small><b style="color:#38bdf8">' + x.trend + "</b></div>" +
            '<div class="orbitItem"><small>مومنتوم</small><b style="color:#c084fc">' + x.momentum + "</b></div>" +
            '<div class="orbitItem"><small>حجم</small><b style="color:#fbbf24">' + x.volume + "</b></div>" +
            '<div class="orbitItem"><small>همسویی</small><b style="color:#4ade80">' + x.alignment + "</b></div>" +
          "</div></div>";
      }).join("");
    } else {
      box.innerHTML = "<div style='grid-column:1/-1;color:#fbbf24'>داده تایم‌فریم هنوز آماده نیست… <button class='btn' style='margin-top:10px' onclick='loadTFGauge()'>🔄 دریافت دوباره</button></div>";
      setTimeout(function(){ if(safeEl("tfWindow") && safeEl("tfWindow").style.display !== "none") loadTFGauge(); }, 1000);
    }
  } catch(e) {
    if(box) box.innerHTML = "<div style='grid-column:1/-1;color:#f43f5e'>خطا: " + (e.message||e) + "</div>";
  }
}

/* ---------- settings modal ---------- */
function openM(){ var m = safeEl("modal"); if(m) m.style.display = "flex"; }
function closeM(){ var m = safeEl("modal"); if(m) m.style.display = "none"; }

/* ---------- other API buttons ---------- */
async function loadEdgeTerminal(){
  var msg = safeEl("edge-msg"), out = safeEl("edge-terminal");
  try {
    if(msg) msg.textContent = "در حال خواندن Decision Terminal…";
    var sym = window.currentTFSymbol || "BTC/USDT";
    var d = await fetch("/api/titan-terminal?symbol=" + encodeURIComponent(sym), { cache: "no-store" }).then(function(r){ return r.json(); });
    if(d && d.ok){
      var t = d.terminal || {};
      setText("edge-conf", (t.confluence!=null?t.confluence:0));
      setText("edge-meta", (t.meta_probability!=null?t.meta_probability:0) + "%");
      setText("edge-ai", (t.ai_consensus!=null?t.ai_consensus:0) + "%");
      setText("edge-risk", t.final_state || t.signal_tag || "--");
      if(out) out.textContent = JSON.stringify(t, null, 2);
      if(msg) msg.textContent = "ترمینال آماده · " + sym;
    } else if(msg) msg.textContent = (d && d.error) || "داده‌ای موجود نیست";
  } catch(e) { if(msg) msg.textContent = "خطا در Decision Terminal"; }
}
async function runProLab(){
  var msg = safeEl("edge-msg"), out = safeEl("edge-terminal");
  try {
    if(msg) msg.textContent = "در حال اجرای Pro Lab…";
    var sym = window.currentTFSymbol || "BTC/USDT";
    var d = await fetch("/api/pro-lab?symbol=" + encodeURIComponent(sym) + "&timeframe=1h&limit=800", { cache: "no-store" }).then(function(r){ return r.json(); });
    if(out) out.textContent = JSON.stringify(d, null, 2);
    if(msg) msg.textContent = (d && d.ok) ? "Pro Lab تکمیل شد" : "Pro Lab داده کافی ندارد";
  } catch(e) { if(msg) msg.textContent = "خطا در Pro Lab"; }
}

async function refreshScalpWindow(){
  try{
    var grid = document.getElementById("scalp30Grid");
    if(!grid) return;
    var d = await fetch("/api/scalp-window",{cache:"no-store"}).then(function(r){return r.json();});
    if(!d || !d.ok){
      grid.innerHTML = '<div style="color:#f43f5e;font-size:12px">خطا در تحلیل نیم‌ساعته</div>';
      return;
    }
    var rows = (d.rows||[]).slice(0,2);
    if(!rows.length){
      grid.innerHTML = '<div style="color:#8fa7bb;font-size:12px;font-weight:800">الان فرصت قوی ۳۰–۶۰ دقیقه‌ای نیست — صبر منطقی است</div>';
      return;
    }
    grid.innerHTML = rows.map(function(r){
      var cls = r.side==="LONG"?"long":"short";
      var lab = r.side==="LONG"?"▲ لانگ اهرمی":"▼ شورت اهرمی";
      return '<div class="scalpChip '+cls+'">'+
        '<div class="s1">'+(r.base||r.symbol)+'</div>'+
        '<div class="s2 '+cls+'">'+lab+' · '+Math.round(r.confidence||0)+'%</div>'+
        '<div class="s3">⏱ '+(r.hold_minutes||30)+'–'+(r.max_hold_minutes||60)+' دقیقه<br>'+(r.reason||'')+'</div>'+
        '</div>';
    }).join("");
  }catch(e){
    var g=document.getElementById("scalp30Grid");
    if(g) g.innerHTML = '<div style="color:#f43f5e;font-size:12px">'+(e.message||e)+'</div>';
  }
}
window.refreshScalpWindow = refreshScalpWindow;

async function refreshLive(){
  var priceNodes = [];
  qsa(".card[data-symbol], .ticker[data-symbol], .assetCard[data-symbol], .coinMiniCard[data-symbol]").forEach(function(card){
    var sym = card.getAttribute("data-symbol");
    if(!sym) return;
    var el = qs("[data-price]", card) || qs(".tickerPrice", card) || qs(".coinMiniPriceValue", card) || qs(".assetPrice b", card);
    if(el) priceNodes.push({ symbol: sym, el: el, card: card });
  });
  try {
    var d = await fetch("/api/realtime-analysis", { cache: "no-store" }).then(function(r){ return r.json(); });
    if(!d || !d.ok){
      // fallback to simple live prices
      if(!priceNodes.length) return;
      var d2 = await fetch("/api/live-prices?symbols=" + encodeURIComponent(priceNodes.map(function(x){return x.symbol;}).join(",")), {cache:"no-store"}).then(function(r){return r.json();});
      if(!d2||!d2.ok) return;
      priceNodes.forEach(function(x){
        var n = Number((d2.prices||{})[x.symbol]);
        if(isFinite(n)&&n>0){ x.el.textContent = (n>=1000?n.toLocaleString("en-US",{maximumFractionDigits:2}):n.toLocaleString("en-US",{maximumFractionDigits:8})); }
      });
      return;
    }
    var by = {};
    (d.rows||[]).forEach(function(r){ by[r.symbol]=r; });
    priceNodes.forEach(function(x){
      var r = by[x.symbol];
      if(!r || !(r.price>0)) return;
      var n = Number(r.price);
      var prev = parseFloat(String(x.el.textContent||"").replace(/[^0-9.\-]/g, ""));
      var txt = (n>=1000?n.toLocaleString("en-US",{maximumFractionDigits:2}):n.toLocaleString("en-US",{maximumFractionDigits:8}));
      if(x.el.classList && x.el.classList.contains("coinMiniPriceValue")) x.el.textContent = txt;
      else if(x.el.tagName==="B") x.el.textContent = txt;
      else x.el.innerHTML = txt + (x.el.innerHTML.indexOf("USDT")>=0 ? " <small>USDT</small>" : "");
      if(isFinite(prev) && prev>0){
        x.el.classList.remove("flashUp","flashDown");
        void x.el.offsetWidth;
        if(n>prev*1.00005) x.el.classList.add("flashUp");
        else if(n<prev*0.99995) x.el.classList.add("flashDown");
      }
      if(x.card){
        if(r.change_pct!=null) x.card.setAttribute("data-live-chg", r.change_pct);
        // Keep the modal/detail source attributes synchronized with the same
        // live snapshot used by the price display.
        if(r.price>0) x.card.setAttribute("data-price", r.price);
        if(r.entry>0) x.card.setAttribute("data-entry", r.entry);
        if(r.stop_loss>0) x.card.setAttribute("data-sl", r.stop_loss);
        if(r.tp1>0) x.card.setAttribute("data-tp1", r.tp1);
        if(r.tp2>0) x.card.setAttribute("data-tp2", r.tp2);
        if(r.rr_tp1>0) x.card.setAttribute("data-rr1", r.rr_tp1);
        if(r.rr_tp2>0) x.card.setAttribute("data-rr2", r.rr_tp2);
        x.card.setAttribute("data-live-sync", r.live_sync ? "1" : "0");
      }
    });
    var st = document.getElementById("rtStatus");
    var br = document.getElementById("rtBreadth");
    var ld = document.getElementById("rtLeaders");
    var b = d.breadth||{};
    var live = d.live||{};
    if(st) st.textContent = (live.status||"LIVE") + (live.median_age_ms!=null ? (" · "+Math.round(live.median_age_ms/1000)+"s") : "") + " · " + (live.websocket?"WS+REST":"REST");
    if(br) br.innerHTML = '<span style="color:#7dffc8">▲ '+((b.up)||0)+'</span> · <span style="color:#ffb0c2">▼ '+((b.down)||0)+'</span> · <span style="color:#ffe9a3">◆ '+((b.flat)||0)+'</span>';
    if(ld){
      ld.innerHTML = (d.leaders||[]).slice(0,4).map(function(r){
        var cls = (r.change_pct||0)>=0 ? "up" : "down";
        var ch = (r.change_pct||0);
        var sign = ch>=0?"+":"";
        return '<span class="rtChip '+cls+'">'+(r.symbol||"").replace("/USDT","")+' '+sign+ch.toFixed(2)+'%</span>';
      }).join("") || "بدون حرکت تند";
    }
  } catch(e) {}
}
async function refreshPulse(){
  try {
    var d = await fetch("/api/market-pulse", { cache: "no-store" }).then(function(r){ return r.json(); });
    if(!d || !d.ok) return;
    var p = d.pulse || {}, b = p.breadth || {}, l = p.leader || {};
    setText("pulse-regime", p.regime || "--");
    setText("pulse-score", (p.avg_score != null ? p.avg_score : "--") + "/100");
    setText("pulse-breadth", (b.bullish||0) + " 🟢 · " + (b.bearish||0) + " 🔴 · " + (b.neutral||0) + " 🟡");
    setText("pulse-leader", l.symbol ? (l.symbol + " · " + (l.quality||0)) : "--");
    setText("pulse-time", p.timestamp || "--");
  } catch(e) {}
}
async function refreshGemini(){
  try {
    var el = safeEl("geminiRefreshState");
    if(el) el.textContent = "در حال دریافت تحلیل Gemini…";
    var d = await fetch("/api/gemini-analysis?refresh=1", { cache: "no-store" }).then(function(r){ return r.json(); });
    var box = safeEl("geminiAnalysis");
    var st = safeEl("geminiStatus");
    if(d && d.ok){
      if(box) box.textContent = d.analysis || d.error || "تحلیل خالی بود";
      if(st) st.textContent = d.analysis ? "تحلیل آماده" : "داده‌ای دریافت نشد";