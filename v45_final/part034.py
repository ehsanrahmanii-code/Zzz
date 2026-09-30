          "</td><td>" + voteCell(row.majority) + "</td><td>" + (row.agreement!=null?row.agreement:"—") +
          "%</td><td>" + modelTitle("gemini",v.gemini) + "</td><td>" + modelTitle("openai",v.openai) +
          "</td><td>" + modelTitle("grok",v.grok) + "</td><td>" + modelTitle("claude",v.claude) +
          "</td><td>" + modelTitle("deepseek",v.deepseek) + "</td></tr>";
      }).join("") || "<tr><td colspan='9'>رأیی ثبت نشده است؛ اگر اسکن پس‌زمینه هنوز تمام نشده، چند ثانیه بعد دوباره بزنید.</td></tr>";
    }
    if(!(d.board||[]).length && d.count === 0){
      if(sum) sum.textContent = "تحلیل بازار در پس‌زمینه در حال آماده‌سازی است…";
      setTimeout(function(){ loadAiVoteBoard(); }, 1800);
    }
  } catch(e) {
    if(sum) sum.textContent = "خطا: " + (e.message||e);
  }
}
window.loadAiVoteBoard = loadAiVoteBoard;

async function loadV22Opportunities(){
  try{
    var d = await fetch("/api/opportunities",{cache:"no-store"}).then(function(r){return r.json();});
    if(!d || !d.ok) return;
    setText("v22Ready", d.summary.ready||0);
    setText("v22Early", d.summary.early||0);
    setText("v22Watch", d.summary.watch||0);
    setText("v22NoEdge", d.summary.no_edge||0);
    var body = document.getElementById("v22OppBody");
    if(!body) return;
    body.innerHTML = (d.rows||[]).slice(0,15).map(function(x){
      var st = String(x.state||"NO_EDGE");
      var col = st==="READY" ? "var(--green)" : st.indexOf("EARLY")===0 ? "var(--cyan)" : st.indexOf("WATCH")===0 ? "var(--gold)" : "#94a3b8";
      var dec = String(x.decision||"WAIT");
      var dcol = dec==="LONG" ? "var(--green)" : dec==="SHORT" ? "var(--pink)" : "var(--gold)";
      var ai = x.ai||{}, lr = x.learning||{}, chosen = lr.chosen_side||{};
      var reasons = (x.reasons||[]).slice(0,3).join(" · ");
      return "<tr><td><b>"+(x.symbol||"")+"</b></td>"+
        "<td><b style='color:"+dcol+"'>"+dec+"</b></td>"+
        "<td><span style='color:"+col+"'>"+st+"</span></td>"+
        "<td><b>"+(x.score!=null?x.score:"—")+"</b></td>"+
        "<td>"+(x.side||"WAIT")+"</td>"+
        "<td>"+(ai.majority||"WAIT")+" · "+(ai.agreement!=null?ai.agreement:"—")+"%</td>"+
        "<td>"+(chosen.samples!=null?chosen.samples:0)+" n · WR "+(chosen.win_rate!=null?chosen.win_rate:"—")+"%</td>"+
        "<td style='font-size:10px;color:#94a3b8;max-width:360px'>"+reasons+"</td></tr>";
    }).join("") || "<tr><td colspan='8'>فرصتی ثبت نشده است.</td></tr>";
  }catch(e){ console.warn("V22 opportunities",e); }
}
window.loadV22Opportunities = loadV22Opportunities;



window.__tvScriptFailed = window.__tvScriptFailed || false;

function safeEl(id){ try { return document.getElementById(id); } catch(e){ return null; } }
function setText(id, v){ var el = safeEl(id); if(el) el.textContent = v; }
function qs(sel, root){ try { return (root||document).querySelector(sel); } catch(e){ return null; } }
function qsa(sel, root){ try { return Array.prototype.slice.call((root||document).querySelectorAll(sel)); } catch(e){ return []; } }

window.currentTFSymbol = window.currentTFSymbol || "BTC/USDT";
window._detailTv = window._detailTv || "BTCUSDT";

/* ---------- charts: always prefer canvas candles ---------- */
function drawCandleChart(canvas, candles, title){
  if(!canvas || !candles || !candles.length) return false;
  try {
    var dpr = window.devicePixelRatio || 1;
    var cssW = canvas.clientWidth || canvas.parentElement && canvas.parentElement.clientWidth || 320;
    var cssH = canvas.clientHeight || 220;
    if(cssW < 40) cssW = 320;
    if(cssH < 40) cssH = 220;
    canvas.width = Math.floor(cssW * dpr);
    canvas.height = Math.floor(cssH * dpr);
    var ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    var W = cssW, H = cssH;
    ctx.fillStyle = "#0b1220";
    ctx.fillRect(0, 0, W, H);
    var padL = 6, padR = 52, padT = 24, padB = 18;
    var n = candles.length;
    var highs = candles.map(function(c){ return +c.h; });
    var lows = candles.map(function(c){ return +c.l; });
    var minP = Math.min.apply(null, lows);
    var maxP = Math.max.apply(null, highs);
    if(!isFinite(minP) || !isFinite(maxP) || minP === maxP){ minP = (minP||1)*0.99; maxP = (maxP||1)*1.01; }
    var span = maxP - minP || 1;
    function y(p){ return padT + (1 - (p - minP) / span) * (H - padT - padB); }
    var slot = (W - padL - padR) / n;
    var bodyW = Math.max(2, slot * 0.62);
    ctx.strokeStyle = "rgba(148,163,184,0.12)";
    ctx.lineWidth = 1;
    for(var g=0;g<5;g++){
      var gy = padT + g * (H - padT - padB) / 4;
      ctx.beginPath(); ctx.moveTo(padL, gy); ctx.lineTo(W - padR, gy); ctx.stroke();
      var gp = maxP - span * g / 4;
      ctx.fillStyle = "#94a3b8";
      ctx.font = "10px Tahoma,sans-serif";
      ctx.textAlign = "left";
      ctx.fillText(gp >= 1000 ? gp.toFixed(1) : (gp >= 1 ? gp.toFixed(4) : gp.toFixed(6)), W - padR + 3, gy + 3);
    }
    for(var i=0;i<n;i++){
      var c = candles[i];
      var x = padL + i * slot + slot / 2;
      var up = (+c.c) >= (+c.o);
      ctx.strokeStyle = up ? "#4ade80" : "#f43f5e";
      ctx.fillStyle = up ? "#4ade80" : "#f43f5e";
      ctx.beginPath();
      ctx.moveTo(x, y(+c.h));
      ctx.lineTo(x, y(+c.l));
      ctx.stroke();
      var y1 = y(Math.max(+c.o, +c.c));
      var y2 = y(Math.min(+c.o, +c.c));
      ctx.fillRect(x - bodyW / 2, y1, bodyW, Math.max(1, y2 - y1));
    }
    ctx.fillStyle = "#e2e8f0";
    ctx.font = "bold 12px Tahoma,sans-serif";
    ctx.textAlign = "right";
    ctx.fillText(title || "Chart", W - padR - 4, 16);
    var last = candles[n-1];
    ctx.fillStyle = (+last.c) >= (+last.o) ? "#4ade80" : "#f43f5e";
    ctx.textAlign = "left";
    var lp = +last.c;
    ctx.fillText(lp >= 1000 ? lp.toFixed(2) : lp.toFixed(6), padL, 16);
    return true;
  } catch(err) {
    console.warn("drawCandleChart", err);
    return false;
  }
}

async function fetchCandles(symbol, tf, limit){
  tf = tf || "1h";
  limit = limit || 100;
  var url = "/api/klines?symbol=" + encodeURIComponent(symbol) + "&timeframe=" + encodeURIComponent(tf) + "&limit=" + limit;
  var res = await fetch(url, { cache: "no-store" });
  var data = await res.json();
  if(!data || !data.ok || !data.candles || !data.candles.length) throw new Error((data && data.error) || "no candles");
  return data.candles;
}

async function loadFallbackChart(tvSymbol){
  var wrap = qs('.tv-wrap[data-tv="' + tvSymbol + '"]');
  if(!wrap) return;
  var status = qs(".tv-status", wrap);
  var tvBox = safeEl("tv-" + tvSymbol);
  var canvas = safeEl("cv-" + tvSymbol);
  var pair = wrap.getAttribute("data-symbol") || (tvSymbol.indexOf("/") >= 0 ? tvSymbol : tvSymbol.replace(/USDT$/,"") + "/USDT");
  try {
    if(status) status.textContent = "در حال دریافت کندل…";
    var candles = await fetchCandles(pair, "1h", 120);
    if(tvBox) tvBox.style.display = "none";
    if(canvas){
      canvas.style.display = "block";
      canvas._candles = candles;
      canvas._title = pair + " · 1H";
      drawCandleChart(canvas, candles, canvas._title);
    }
    if(status) status.textContent = "نمودار کندل فعال · " + pair + " · " + candles.length + " شمع";
  } catch(e) {
    if(status) status.textContent = "نمودار: " + (e.message || e);
  }
}

function tryTradingViewWidget(tvSymbol, containerId){
  try {
    if(window.__tvScriptFailed || typeof TradingView === "undefined" || !TradingView.widget){
      return false;
    }
    var el = document.getElementById(containerId);
    if(!el) return false;
    el.innerHTML = "";
    el.style.display = "block";
    el.style.height = "360px";
    new TradingView.widget({
      "autosize": true,
      "symbol": "BINANCE:" + tvSymbol,
      "interval": "60",
      "timezone": "Etc/UTC",
      "theme": "dark",
      "style": "1",
      "locale": "en",
      "toolbar_bg": "#0b1220",
      "enable_publishing": false,
      "allow_symbol_change": true,
      "hide_side_toolbar": false,
      "container_id": containerId,
      "studies": [
        "RSI@tv-basicstudies",
        "MACD@tv-basicstudies",
        "MASimple@tv-basicstudies"
      ],
      "overrides": {
        "paneProperties.background": "#0b1220",
        "paneProperties.vertGridProperties.color": "#1e293b",
        "paneProperties.horzGridProperties.color": "#1e293b"
      },
      "disabled_features": ["header_symbol_search", "use_localstorage_for_settings"],
      "enabled_features": ["move_logo_to_main_pane", "side_toolbar_in_fullscreen_mode"]
    });
    return true;
  } catch(e) {
    console.warn("TV widget fail", e);
    return false;
  }
}

function loadTradingViewIframe(tvSymbol){
  try {
    var ifr = document.getElementById("tvif-" + tvSymbol);
    var tvBox = document.getElementById("tv-" + tvSymbol);
    var canvas = document.getElementById("cv-" + tvSymbol);
    if(!ifr) return false;
    var src = "https://s.tradingview.com/widgetembed/?frameElementId=tvif-" + encodeURIComponent(tvSymbol)
      + "&symbol=BINANCE%3A" + encodeURIComponent(tvSymbol)
      + "&interval=60&hidesidetoolbar=0&hidetoptoolbar=0&symboledit=1&saveimage=0"
      + "&toolbarbg=0b1220&studies=%5B%22RSI%40tv-basicstudies%22%2C%22MACD%40tv-basicstudies%22%5D"
      + "&theme=dark&style=1&timezone=Etc%2FUTC&withdateranges=1&hideideas=1&studies_overrides=%7B%7D&overrides=%7B%7D"
      + "&enabled_features=%5B%5D&disabled_features=%5B%5D&locale=en&utm_source=titan&utm_medium=widget";
    ifr.src = src;
    ifr.style.display = "block";
    if(tvBox) tvBox.style.display = "none";
    if(canvas) canvas.style.display = "none";
    return true;
  } catch(e) {
    console.warn("TV iframe fail", e);
    return false;
  }
}

function reloadTV(tvSymbol){
  var wrap = qs('.tv-wrap[data-tv="' + tvSymbol + '"]');
  var status = wrap ? qs(".tv-status", wrap) : null;
  if(status) status.textContent = "در حال بارگذاری مجدد TradingView…";
  var ok = tryTradingViewWidget(tvSymbol, "tv-" + tvSymbol);
  if(ok){
    var ifr = document.getElementById("tvif-" + tvSymbol);
    if(ifr) ifr.style.display = "none";
    var tvBox = document.getElementById("tv-" + tvSymbol);
    if(tvBox) tvBox.style.display = "block";
    if(status) status.textContent = "TradingView Widget · BINANCE:" + tvSymbol + " · RSI+MACD";
    return;
  }
  if(loadTradingViewIframe(tvSymbol)){
    if(status) status.textContent = "TradingView Embed · BINANCE:" + tvSymbol + " · RSI+MACD";
    return;
  }
  loadFallbackChart(tvSymbol);
}

function loadAllCardCharts(){
  qsa(".tv-wrap[data-tv]").forEach(function(w, idx){
    var tv = w.getAttribute("data-tv");
    if(!tv) return;
    var status = qs(".tv-status", w);
    // Stagger to avoid TV rate limits
    setTimeout(function(){
      var ok = tryTradingViewWidget(tv, "tv-" + tv);
      if(ok){
        var canvas = document.getElementById("cv-" + tv);
        if(canvas) canvas.style.display = "none";
        var ifr = document.getElementById("tvif-" + tv);
        if(ifr) ifr.style.display = "none";
        var tvBox = document.getElementById("tv-" + tv);
        if(tvBox) tvBox.style.display = "block";
        if(status) status.textContent = "TradingView فعال · BINANCE:" + tv + " · RSI + MACD";
        setTimeout(function(){
          // If widget stayed empty, fall back to embed
          var box = document.getElementById("tv-" + tv);
          if(box && box.children.length === 0){
            if(loadTradingViewIframe(tv)){
              if(status) status.textContent = "TradingView Embed · BINANCE:" + tv;
            } else {
              loadFallbackChart(tv);
            }
          }
        }, 4500);
      } else if(loadTradingViewIframe(tv)){
        if(status) status.textContent = "TradingView Embed · BINANCE:" + tv + " · RSI + MACD";
      } else {
        loadFallbackChart(tv);
      }
    }, idx * 350);
  });
}

function openPatternPanel(symbol, tv){
  var el = document.getElementById("pattern-" + tv);
  if(el){
    el.scrollIntoView({behavior:"smooth", block:"start"});
    el.style.outline = "2px solid #c084fc";
    setTimeout(function(){ el.style.outline = ""; }, 1400);
  }
  refreshPatternForecast(symbol, tv);
}

async function refreshPatternForecast(symbol, tv){
  try {
    var d = await fetch("/api/pattern-forecast?symbol=" + encodeURIComponent(symbol) + "&timeframe=1h&horizon=12", {cache:"no-store"}).then(function(r){return r.json();});
    if(!d || !d.ok) return;
    // Update narrative if present
    var panel = document.getElementById("pattern-" + tv);
    if(panel && d.forecast && d.forecast.narrative){
      var notes = panel.querySelectorAll("div");
      // soft: redraw forecast chart