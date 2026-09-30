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