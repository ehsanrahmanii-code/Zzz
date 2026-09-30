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
    }
    if(d.forecast) window["_fc_" + tv] = d.forecast;
    drawForecastChart(tv);
  } catch(e){ console.warn(e); }
}

function drawForecastChart(tv){
  var cv = document.getElementById("fc-" + tv);
  if(!cv) return;
  var fc = window["_fc_" + tv];
  if(!fc || !fc.candles || !fc.candles.length){
    // try read from nothing - skip
    return;
  }
  var candles = fc.candles;
  try {
    var dpr = window.devicePixelRatio || 1;
    var W = cv.clientWidth || 320, H = 160;
    cv.width = Math.floor(W * dpr); cv.height = Math.floor(H * dpr);
    var ctx = cv.getContext("2d");
    ctx.setTransform(dpr,0,0,dpr,0,0);
    ctx.fillStyle = "#0b1220"; ctx.fillRect(0,0,W,H);
    var lows = candles.map(function(c){return +c.band_low;});
    var highs = candles.map(function(c){return +c.band_high;});
    var minP = Math.min.apply(null, lows), maxP = Math.max.apply(null, highs);
    if(minP===maxP){minP*=0.99;maxP*=1.01;}
    var pad=8;
    function y(p){ return pad + (1-(p-minP)/(maxP-minP))*(H-pad*2); }
    function x(i){ return pad + i*(W-pad*2)/Math.max(1,candles.length-1); }
    // band
    ctx.beginPath();
    candles.forEach(function(c,i){ var yy=y(+c.band_high); if(i) ctx.lineTo(x(i),yy); else ctx.moveTo(x(i),yy); });
    for(var j=candles.length-1;j>=0;j--){ ctx.lineTo(x(j), y(+candles[j].band_low)); }
    ctx.closePath();
    ctx.fillStyle = "rgba(56,189,248,0.12)"; ctx.fill();
    // mid path
    ctx.beginPath();
    candles.forEach(function(c,i){ var yy=y(+c.close); if(i) ctx.lineTo(x(i),yy); else ctx.moveTo(x(i),yy); });
    ctx.strokeStyle = "#c084fc"; ctx.lineWidth = 2; ctx.stroke();
    candles.forEach(function(c,i){
      ctx.fillStyle = c.direction==="صعودی" ? "#4ade80" : "#f43f5e";
      ctx.beginPath(); ctx.arc(x(i), y(+c.close), 4, 0, Math.PI*2); ctx.fill();
    });
    ctx.fillStyle = "#94a3b8"; ctx.font = "11px Tahoma"; ctx.textAlign="left";
    ctx.fillText("مسیر پیش‌بینی " + (fc.overall_bias||"") + " · " + candles.length + " کندل", pad, 14);
  } catch(e){ console.warn(e); }
}

window.reloadTV = reloadTV;
window.openPatternPanel = openPatternPanel;
window.refreshPatternForecast = refreshPatternForecast;
window.drawForecastChart = drawForecastChart;

async function loadAllCoinCharts(){
  var grid = safeEl("allChartsGrid");
  if(!grid) return;
  grid.innerHTML = "";
  var cards = qsa(".card[data-symbol]");
  if(!cards.length){
    grid.innerHTML = "<div style='color:#94a3b8'>ارزی در داشبورد نیست — اسکن مجدد بزنید</div>";
    return;
  }
  cards.forEach(function(card){
    var symbol = card.getAttribute("data-symbol");
    var base = card.getAttribute("data-base") || symbol;
    var icon = card.getAttribute("data-icon") || "";
    var score = card.getAttribute("data-score") || "";
    var color = card.getAttribute("data-color") || "#fbbf24";
    var bias = card.getAttribute("data-bias") || "";
    var box = document.createElement("div");
    box.className = "allCard";
    box.innerHTML = '<div class="atitle"><span>' + icon + " " + base + '</span><span style="color:' + color + '">' + score + "/100</span></div><canvas height=\"180\"></canvas><div style=\"font-size:11px;color:#94a3b8;margin-top:4px\">" + bias + "</div>";
    grid.appendChild(box);
    var cv = box.querySelector("canvas");
    fetchCandles(symbol, "1h", 60).then(function(candles){
      drawCandleChart(cv, candles, base + " 1H");
    }).catch(function(err){
      box.insertAdjacentHTML("beforeend", "<div style='color:#f43f5e;font-size:11px'>" + (err.message||err) + "</div>");
    });
  });
}

/* ---------- coin nav / detail ---------- */
function scrollToCard(tv){
  var el = safeEl("card-" + tv);
  if(!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "start" });
  el.style.outline = "2px solid #38bdf8";
  setTimeout(function(){ el.style.outline = ""; }, 1200);
}

function closeCoinDetail(){
  var m = safeEl("coinDetailModal");
  if(m) m.style.display = "none";
}

async function openCoinDetailFromCard(card){
  if(!card) return;
  var m = document.getElementById("coinDetailModal");
  if(m){ m.style.display = "flex"; m.style.zIndex = "1300"; }
  var symbol = card.getAttribute("data-symbol") || "";
  var tv = card.getAttribute("data-tv") || "";
  window.currentTFSymbol = symbol;
  window._detailTv = tv;

  var icon = card.getAttribute("data-icon") || "●";
  var name = card.getAttribute("data-name") || "";
  var base = card.getAttribute("data-base") || "";
  var color = card.getAttribute("data-color") || "#fbbf24";
  var bias = card.getAttribute("data-bias") || "";
  var score = card.getAttribute("data-score") || "—";
  var price = card.getAttribute("data-price") || "—";
  var rawDecision = (card.getAttribute("data-decision") || "").toUpperCase().trim();
  var dtag = rawDecision === "LONG" || rawDecision === "SHORT" || rawDecision === "WAIT" ? rawDecision : "WAIT";
  var mode = dtag === "LONG" ? "bull" : dtag === "SHORT" ? "bear" : "flat";

  var banner = document.getElementById("cdBanner");
  if(banner){ banner.className = "cdBanner " + mode; }
  var iconEl = document.getElementById("cdIcon");
  if(iconEl) iconEl.textContent = icon;
  var title = document.getElementById("cdTitle");
  if(title) title.textContent = name || base;
  var pair = document.getElementById("cdPair");
  if(pair) pair.textContent = (base || "—") + " / USDT · BINANCE SPOT";
  var priceEl = document.getElementById("cdPriceBig");
  if(priceEl) priceEl.innerHTML = price + " <small>USDT</small>";

  var sig = document.getElementById("cdSignalRow");
  if(sig){
    var badgeClass = dtag === "LONG" ? "long" : dtag === "SHORT" ? "short" : "wait";
    var badgeTxt = dtag === "LONG" ? "▲ خرید" : dtag === "SHORT" ? "▼ فروش" : "◆ انتظار";
    sig.innerHTML =
      '<span class="signalBadge ' + badgeClass + '">' + badgeTxt + " · " + bias + "</span>" +
      '<span class="miniChip">تگ: ' + (card.getAttribute("data-tag") || "—") + "</span>";
  }

  var metrics = document.getElementById("cdMetrics");
  if(metrics){
    metrics.innerHTML =
      '<div class="cdMetric"><div class="ico">🎯</div><div class="val" style="color:' + color + '">' + score + '</div><small>امتیاز</small></div>' +
      '<div class="cdMetric"><div class="ico">🧭</div><div class="val">' + (card.getAttribute("data-align") || "—") + '</div><small>همسویی</small></div>' +
      '<div class="cdMetric"><div class="ico">✨</div><div class="val">' + (card.getAttribute("data-quality") || "—") + '</div><small>کیفیت</small></div>' +
      '<div class="cdMetric"><div class="ico">📊</div><div class="val">' + (card.getAttribute("data-rsi") || "—") + '</div><small>قدرت نسبی</small></div>';
  }

  var levels = document.getElementById("cdLevels");
  if(levels){
    levels.innerHTML =
      '<div class="cdLevelCard entry"><div class="lbl">🎯 نقطه ورود</div><div class="num">' + (card.getAttribute("data-entry") || price) + '</div></div>' +
      '<div class="cdLevelCard sl"><div class="lbl">🛑 حد ضرر</div><div class="num" style="color:#fb7185">' + (card.getAttribute("data-sl") || "—") + '</div></div>' +
      '<div class="cdLevelCard tp1"><div class="lbl">🟢 حد سود ۱ · RR 1:' + (card.getAttribute("data-rr1") || "—") + '</div><div class="num" style="color:#4ade80">' + (card.getAttribute("data-tp1") || "—") + '</div></div>' +
      '<div class="cdLevelCard tp2"><div class="lbl">🚀 حد سود ۲ · RR 1:' + (card.getAttribute("data-rr2") || "—") + '</div><div class="num" style="color:#fbbf24">' + (card.getAttribute("data-tp2") || "—") + '</div></div>';
  }

  var tf = document.getElementById("cdTfStrip");
  if(tf){
    var cells = [
      ["۱۵ دقیقه", card.getAttribute("data-tf15")],
      ["۱ ساعت", card.getAttribute("data-tf1h")],
      ["۴ ساعت", card.getAttribute("data-tf4h")],
      ["۱ روز", card.getAttribute("data-tf1d")]
    ];
    tf.innerHTML = cells.map(function(c){
      var v = c[1] || "—";
      var col = (v.indexOf("صعود") >= 0 || v.indexOf("🟢") >= 0) ? "#4ade80" :
                (v.indexOf("نزول") >= 0 || v.indexOf("🔴") >= 0) ? "#fb7185" : "#fbbf24";
      return '<div class="cdTfCell"><small>' + c[0] + '</small><b style="color:' + col + '">' + v + '</b></div>';
    }).join("");
  }

  var extra = document.getElementById("cdExtra");
  if(extra){
    extra.innerHTML =
      '<span class="miniChip">🐋 بهره باز: ' + (card.getAttribute("data-oi") || "—") + '</span>' +
      '<span class="miniChip">💸 نرخ تأمین مالی: ' + (card.getAttribute("data-fund") || "—") + '</span>' +
      '<span class="miniChip">📐 فاصله تا حد ضرر وابسته به ATR</span>';
  }

  var sys = document.getElementById("cdSystemOpinion");
  if(sys) sys.innerHTML = '<b style="color:' + color + '">' + dtag + '</b> · ' + (bias || "خنثی") +
      '<br>امتیاز ' + score + '/100 · همسویی ' + (card.getAttribute("data-align")||"—") +
      ' · کیفیت ' + (card.getAttribute("data-quality")||"—");
  var ai = document.getElementById("cdAIOpinion");
  if(ai) ai.textContent = 'در حال بارگذاری اجماع مدل‌ها…';
  var aim = document.getElementById("cdAIMetrics");
  
  // Buy/Sell graphical dual ring (shape + text)
  var buyP = parseFloat(card.getAttribute("data-buy") || "50");
  var sellP = parseFloat(card.getAttribute("data-sell") || "");
  if(!isFinite(buyP)) buyP = 50;
  if(!isFinite(sellP)) sellP = Math.max(0, 100 - buyP);
  buyP = Math.max(0, Math.min(100, buyP));
  sellP = Math.max(0, Math.min(100, sellP));
  var bsHost = document.getElementById("cdBuySellFlow");
  if(!bsHost){
    var metricsEl2 = document.getElementById("cdMetrics");
    if(metricsEl2 && metricsEl2.parentNode){
      bsHost = document.createElement("div");
      bsHost.id = "cdBuySellFlow";
      metricsEl2.parentNode.insertBefore(bsHost, metricsEl2.nextSibling);
    }
  }
  if(bsHost){
    bsHost.innerHTML =
      '<div class="bsFlowBox" style="--buy:'+buyP+'">'+
        '<div class="bsDualRing" style="--buy:'+buyP+'"><div class="bsCenter"><b>'+Math.round(buyP)+'%</b>خرید</div></div>'+
        '<div class="bsLegend">'+
          '<div class="bsRow buy"><span>▲ فشار خرید</span><b class="buyPct">'+buyP.toFixed(1)+'%</b></div>'+
          '<div class="bsRow sell"><span>▼ فشار فروش</span><b class="sellPct">'+sellP.toFixed(1)+'%</b></div>'+
          '<div class="bsBar" style="--buy:'+buyP+'"></div>'+
          '<div style="font-size:11px;color:#8fb0c6;margin-top:4px;font-weight:800">حلقه سبز = خرید · حلقه قرمز = فروش · داده سفارش‌گیر</div>'+
        '</div>'+
      '</div>';
  }

  if(aim) aim.innerHTML = 'شانس موفقیت: <b>' + (card.getAttribute("data-success")||"—") + '</b><br>RR1: 1:' + (card.getAttribute("data-rr1")||"—") + ' · RR2: 1:' + (card.getAttribute("data-rr2")||"—");

  var schema = document.getElementById("cdSchemaBoard");
  if(!schema){
    var metricsEl = document.getElementById("cdMetrics");
    if(metricsEl && metricsEl.parentNode){
      schema = document.createElement("div");
      schema.id = "cdSchemaBoard";
      schema.className = "cdSchemaGrid";
      metricsEl.parentNode.insertBefore(schema, metricsEl.nextSibling);
    }
  }
  if(schema){
    var sc = card.getAttribute("data-success")||"—";
    var q = card.getAttribute("data-quality")||"—";
    var al = card.getAttribute("data-align")||"—";
    var entry = card.getAttribute("data-entry")||"—";
    var slv = card.getAttribute("data-sl")||"—";
    var t1 = card.getAttribute("data-tp1")||"—";
    var t2 = card.getAttribute("data-tp2")||"—";
    var r1 = card.getAttribute("data-rr1")||"—";
    var r2 = card.getAttribute("data-rr2")||"—";
    var sigColor = dtag==="LONG"?"#23e6a8":dtag==="SHORT"?"#ff4d73":"#ffd34e";
    schema.innerHTML =
      '<div class="cdSchemaCard" style="border-color:'+sigColor+'55"><div class="h">🚦 سیگنال نهایی</div><div class="b" style="color:'+sigColor+'">'+dtag+' · '+(bias||"خنثی")+'</div><div class="t">تصمیم هسته + فرصت‌محور V22</div></div>' +
      '<div class="cdSchemaCard"><div class="h">🎲 شانس مدل</div><div class="b">'+sc+'%</div><div class="t">کالیبره‌شده · نه تضمین سود</div></div>' +
      '<div class="cdSchemaCard"><div class="h">✨ کیفیت / همسویی</div><div class="b">'+q+' / '+al+'</div><div class="t">فیلتر نویز و انسجام چندتایم‌فریم</div></div>' +
      '<div class="cdSchemaCard"><div class="h">🟦 نقطه ورود</div><div class="b">'+entry+'</div><div class="t">محدوده ورود معتبر سیستم</div></div>' +
      '<div class="cdSchemaCard"><div class="h">🛑 حد ضرر</div><div class="b" style="color:#ff8fa3">'+slv+'</div><div class="t">ریسک ساختاری</div></div>' +
      '<div class="cdSchemaCard"><div class="h">🎯 اهداف</div><div class="b" style="color:#7dffc8">TP1 '+t1+'<br>TP2 '+t2+'</div><div class="t">RR 1:'+r1+' · 1:'+r2+'</div></div>';
  }

  var reason = document.getElementById("cdReasoning");
  if(reason) reason.textContent = card.getAttribute("data-tag") || "منطق تصمیم در کارت اصلی و Edge Suite موجود است.";
  var overview = document.getElementById("cdOverviewText");
  if(overview) overview.innerHTML = '<b>وضعیت:</b> ' + dtag + ' · <b>روند:</b> ' + (bias||"خنثی") +
      '<br><b>قیمت:</b> ' + price + ' USDT · <b>RR:</b> 1:' + (card.getAttribute("data-rr1")||"—") +
      ' / 1:' + (card.getAttribute("data-rr2")||"—");

  var trade = document.getElementById("cdTradePanel");
  if(trade){
    var entry = card.getAttribute("data-entry") || price, sl = card.getAttribute("data-sl") || "—", tp1 = card.getAttribute("data-tp1") || "—", tp2 = card.getAttribute("data-tp2") || "—";
    var longActive = dtag === "LONG", shortActive = dtag === "SHORT";
    trade.innerHTML =
      '<div class="aiDetailCard" style="border-color:' + (longActive?'rgba(74,222,128,.65)':'rgba(148,163,184,.16)') + '"><b style="color:#4ade80">🟢 LONG · ' + (longActive?'فعال':'غیرفعال در تصمیم فعلی') + '</b>' +
      '<div>' + (longActive ? ('ورود: '+entry+'<br>SL: '+sl+'<br>TP1: '+tp1+'<br>TP2: '+tp2) : 'این ارز در تصمیم نهایی فعلی SHORT/WAIT است؛ سطوح LONG در این نما اعمال نمی‌شوند.') + '</div></div>' +
      '<div class="aiDetailCard" style="border-color:' + (shortActive?'rgba(248,113,113,.65)':'rgba(148,163,184,.16)') + '"><b style="color:#f87171">🔴 SHORT · ' + (shortActive?'فعال':'غیرفعال در تصمیم فعلی') + '</b>' +
      '<div>' + (shortActive ? ('ورود: '+entry+'<br>SL: '+sl+'<br>TP1: '+tp1+'<br>TP2: '+tp2) : 'این ارز در تصمیم نهایی فعلی LONG/WAIT است؛ سطوح SHORT در این نما اعمال نمی‌شوند.') + '</div></div>' +
      '<div class="aiDetailCard"><b style="color:#facc15">⚖️ تصمیم نهایی TITAN</b><div style="font-size:18px;font-weight:950;color:' + (dtag==='LONG'?'#4ade80':dtag==='SHORT'?'#f87171':'#fde047') + '">' + dtag + '</div><div style="margin-top:4px">' + (bias||'خنثی') + ' · ' + (card.getAttribute("data-tag")||'—') + '</div></div>';
  }

  var full = document.getElementById("cdFullDetails");
  if(full){
    var clone = card.cloneNode(true);
    clone.removeAttribute("id");
    clone.style.margin = "0";
    var fscore = card.getAttribute("data-score") || "—";
    var falign = card.getAttribute("data-align") || "—";
    var fqual = card.getAttribute("data-quality") || "—";
    var fsucc = card.getAttribute("data-success") || "—";
    var fr1 = card.getAttribute("data-rr1") || "—";
    var fr2 = card.getAttribute("data-rr2") || "—";
    var frsi = card.getAttribute("data-rsi") || "—";
    var foi = card.getAttribute("data-oi") || "—";
    var ffund = card.getAttribute("data-fund") || "—";
    full.innerHTML = '<div class="cdVisualSummary">' +
      '<div class="cdVisualHero"><div><span class="cdVisualKicker">📌 خلاصه تخصصی دارایی</span><strong>'+base+' / USDT</strong><small>'+dtag+' · '+(bias||"خنثی")+' · '+(card.getAttribute("data-tag")||"—")+'</small></div><div class="cdVisualDecision '+(dtag==='LONG'?'long':dtag==='SHORT'?'short':'wait')+'">'+(dtag==='LONG'?'▲ LONG':dtag==='SHORT'?'▼ SHORT':'◆ WAIT')+'</div></div>' +
      '<div class="cdVisualGrid"><div class="cdVisualStat"><span>🎯 امتیاز</span><b>'+fscore+'<small>/100</small></b></div><div class="cdVisualStat"><span>🧭 همسویی</span><b>'+falign+'</b></div><div class="cdVisualStat"><span>🛡️ کیفیت</span><b>'+fqual+'</b></div><div class="cdVisualStat"><span>🎲 شانس مدل</span><b>'+fsucc+'<small>%</small></b></div><div class="cdVisualStat"><span>📐 RR1</span><b>1:'+fr1+'</b></div><div class="cdVisualStat"><span>🚀 RR2</span><b>1:'+fr2+'</b></div><div class="cdVisualStat"><span>📊 RSI</span><b>'+frsi+'</b></div><div class="cdVisualStat"><span>🌐 OI</span><b>'+foi+'</b></div></div>' +
      '<div class="cdVisualLevels"><div><span>🟦 ورود</span><b>'+entry+'</b></div><div><span>🛑 حد ضرر</span><b>'+sl+'</b></div><div><span>🟢 TP1</span><b>'+tp1+'</b></div><div><span>🚀 TP2</span><b>'+tp2+'</b></div></div>' +
      '<div class="cdVisualFlow"><span>🔎 داده واقعی</span><i></i><span>🧠 TITAN</span><i></i><span>🤖 AI</span><i></i><span>🎯 تصمیم</span></div></div>';
    var groups=[{title:"🪙 هویت و وضعیت بازار",keys:["ch","scoreRow","bar","scoreOrbit","tf"]},{title:"🎯 نقاط ورود و خروج",keys:["levels","dualLevels"]},{title:"📐 تحلیل تکنیکال و ساختار",keys:["panelTech"]},{title:"🧠 داده‌های تخصصی و بازار",keys:["miniGrid","table","gaugeRow"]}];
    var holder=document.createElement("div"); holder.className="detailVisualLegacy";
    var topChildren=Array.prototype.slice.call(clone.children||[]), used=new Set();
    groups.forEach(function(g){var sec=document.createElement("section");sec.className="detailVisualGroup";var h=document.createElement("div");h.className="detailVisualGroupTitle";h.textContent=g.title;sec.appendChild(h);topChildren.forEach(function(el){if(used.has(el))return;var cls=String(el.className||"");var match=g.keys.some(function(k){return cls.indexOf(k)>=0||(k==="table"&&el.tagName==="TABLE");});if(match){sec.appendChild(el);used.add(el);}});if(sec.children.length>1)holder.appendChild(sec);});
    topChildren.forEach(function(el){if(!used.has(el))holder.appendChild(el);});
    full.appendChild(holder);
  }

  try {
    var candles = await fetchCandles(symbol, "1h", 90);
    var cv = document.getElementById("cdCanvas");
    if(cv) drawCandleChart(cv, candles, (base || symbol) + " · ۱ ساعته");
  } catch(e) {
    console.warn("cd chart", e);
  }