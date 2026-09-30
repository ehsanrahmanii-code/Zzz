  <div style="margin-top:10px">
    <b style="color:var(--gold);font-size:12px">مسیر احتمالی کندل‌های بعدی</b>
    <div class="tableWrap" style="margin-top:6px">
      <table>
        <thead><tr><th>#</th><th>Open</th><th>High</th><th>Low</th><th>Close</th><th>جهت</th><th>اطمینان</th><th>باند پایین</th><th>باند بالا</th></tr></thead>
        <tbody>
        {% for c in (fc.get('candles') or []) %}
        <tr>
          <td>{{ c.get('step') }}</td>
          <td>{{ c.get('open') }}</td>
          <td>{{ c.get('high') }}</td>
          <td>{{ c.get('low') }}</td>
          <td><b>{{ c.get('close') }}</b></td>
          <td style="color:{% if c.get('direction')=='صعودی' %}var(--green){% else %}var(--pink){% endif %}">{{ c.get('direction') }}</td>
          <td>{{ c.get('confidence') }}%</td>
          <td>{{ c.get('band_low') }}</td>
          <td>{{ c.get('band_high') }}</td>
        </tr>
        {% else %}
        <tr><td colspan="9">پیش‌بینی هنوز آماده نیست — اسکن مجدد بزنید</td></tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
    <div style="font-size:11px;color:#94a3b8;line-height:1.8;margin-top:8px">{{ fc.get('narrative','') }}</div>
    <canvas id="fc-{{ item.tv_symbol }}" width="800" height="160" style="width:100%;height:160px;margin-top:8px;border-radius:12px;background:#0b1220;border:1px solid rgba(56,189,248,.2)"></canvas>
    <div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap">
      <button type="button" class="btn" onclick="refreshPatternForecast('{{ item.symbol }}','{{ item.tv_symbol }}')">🔄 بروزرسانی پیش‌بینی</button>
      <button type="button" class="btn" onclick="drawForecastChart('{{ item.tv_symbol }}')">📈 رسم مسیر پیش‌بینی</button>
    </div>
  </div>
</div>
</div>{% endfor %}</div>
<div class="section"><h2>📊 جدول خلاصه</h2><div class="tableWrap"><table><thead><tr><th>نماد</th><th>درجه</th><th>تصمیم</th><th>قیمت</th><th>تمایل</th><th>Score</th><th>Trust</th><th>Quality</th><th>Prob</th><th>RR1</th><th>OI</th></tr></thead><tbody>{% for item in market_data %}<tr><td><b>{{ item.coin_icon }} {{ item.coin_name }}</b><div style="font-size:11px;color:#94a3b8">{{ item.base_symbol }}/USDT</div></td><td><span class="gradeBadge {% set g = item.get('grade') or '—' %}{% if g=='A+' %}gradeAplus{% elif g=='A' %}gradeA{% elif g=='B' %}gradeB{% elif g=='C' %}gradeC{% elif g=='D' %}gradeD{% else %}gradeF{% endif %}">{{ g }}</span></td><td><b style="color:{% if item.decision_tag=='LONG' %}#4ade80{% elif item.decision_tag=='SHORT' %}#f43f5e{% else %}#fbbf24{% endif %}">{{ item.decision_tag or 'WAIT' }}</b></td><td data-table-price="{{ item.symbol }}">{{ item.price }}</td><td style="color:{{ item.score_color }}">{{ item.bias }}</td><td>{{ item.score }}</td><td>{{ item.get('trust_index', '—') }}</td><td>{{ item.signal_quality }}</td><td>{{ item.success_probability }}%</td><td style="color:var(--green)">{{ item.rr_tp1 }}</td><td>{{ item.coinglass_oi }}</td></tr>{% endfor %}</tbody></table></div></div>
<div class="foot"><div class="sb"><b style="color:var(--cyan)">ترس و طمع</b><div style="font-size:20px;color:var(--gold);margin-top:4px">{{ macro.fear_greed_val }}</div><small>{{ macro.fear_greed_text }}</small></div><div class="sb"><b style="color:var(--cyan)">BTC Dominance</b><div style="font-size:18px;margin-top:5px">{{ macro.dominance_btc }}</div></div><div class="sb"><b style="color:var(--cyan)">سیستم</b><div style="font-size:18px;color:var(--green);margin-top:5px">فعال</div><small>{{ market_data|length }} نماد</small></div><div class="sb"><b style="color:var(--cyan)">دقت تاریخی</b><div style="font-size:18px;color:var(--gold);margin-top:5px">{{ audit.win_rate }}%</div><small>{{ audit.wins }}W / {{ audit.losses }}L</small>
<div style="margin-top:6px"><span class="accTier {{ audit.get('tier','C') }}">رتبه {{ audit.get('tier','C') }} · {{ audit.get('tier_label','—') }}</span></div>
<small style="display:block;margin-top:4px">Long {{ audit.get('long_win_rate',0) }}% · Short {{ audit.get('short_win_rate',0) }}%</small>
</div></div>
</div><!-- /tab-market -->

<div class="tabPanel" id="tab-edge">
<div class="section" style="border-color:rgba(192,132,252,.55);background:linear-gradient(135deg,rgba(35,16,55,.82),rgba(5,10,22,.94))"><div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap"><h2 style="margin:0;color:#c084fc">🧠 TITAN PROFESSIONAL EDGE SUITE · 12 MODULES</h2><span id="edge-status" style="font-size:12px;color:#94a3b8">ACTIVE</span></div><div class="hudgrid" style="margin-top:10px"><div class="hudbox"><div>Confluence</div><div class="v" id="edge-conf">--</div></div><div class="hudbox"><div>Meta Label</div><div class="v" id="edge-meta">--</div></div><div class="hudbox"><div>AI Consensus</div><div class="v" id="edge-ai">--</div></div><div class="hudbox"><div>Risk State</div><div class="v" id="edge-risk" style="font-size:15px">--</div></div></div><div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px"><button class="btn" onclick="loadEdgeTerminal()">🛰 Decision Terminal</button><button class="btn" onclick="runProLab()">🧪 12-Layer Pro Lab</button><span id="edge-msg" style="align-self:center;font-size:11px;color:#94a3b8"></span></div><pre id="edge-terminal" style="white-space:pre-wrap;background:#020617;padding:12px;border-radius:10px;color:#cbd5e1;overflow:auto;margin-top:10px;max-height:320px">داده آماده است</pre></div>
</div><!-- /tab-edge -->

<div class="tabPanel" id="tab-ai">
<div class="section" id="geminiPanel" style="border-color:rgba(66,133,244,.55);background:linear-gradient(135deg,rgba(15,23,42,.97),rgba(16,28,54,.92))"><div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap"><h2 style="margin:0;color:#60a5fa">🤖 Gemini Global Intelligence</h2><span id="geminiStatus" style="font-size:12px;color:#94a3b8">{{ gemini_status.label }}</span></div><div style="margin-top:8px;font-size:11px;color:#64748b">آخرین تولید: {{ gemini_status.updated_at }} · API: {{ 'متصل' if gemini_status.available else 'غیرفعال' }}</div><div id="geminiAnalysis" style="margin-top:12px;line-height:2;color:#e0ecff;font-size:14px">{{ gemini_summary if gemini_summary else 'تحلیل کلان Gemini در حال حاضر در دسترس نیست؛ روی دریافت تحلیل Gemini بزنید.' }}</div><div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap"><button class="btn" onclick="refreshGemini()">🤖 دریافت تحلیل Gemini</button><button class="btn" onclick="loadAiVoteBoard()">📊 خلاصه رأی مدل‌ها</button><span id="geminiRefreshState" style="align-self:center;font-size:11px;color:#94a3b8"></span></div></div>

<div class="section" style="border-color:rgba(96,165,250,.45);background:linear-gradient(135deg,rgba(12,20,40,.96),rgba(20,16,48,.94))">
<div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap">
<h2 style="margin:0;color:#60a5fa">🗳️ هیئت رأی هوش مصنوعی · LONG / SHORT / WAIT</h2>
<span id="aiVoteSummary" style="font-size:12px;color:#94a3b8">در حال آماده‌سازی…</span>
<span id="modelScoreChips" class="chipRow" style="margin-top:6px;width:100%"></span>
</div>
<div class="sub" style="margin:8px 0 12px">رأی هر مدل از متن فارسی/انگلیسی استخراج می‌شود. اولویت با نشانه‌های نزولی است تا بایاس لانگ کاهش یابد. TITAN فقط با اجماع قوی ارتقا می‌گیرد.</div>
<div class="hudgrid" style="margin-bottom:12px">
<div class="hudbox"><div>اکثریت LONG</div><div class="v" id="voteLong" style="color:var(--green)">--</div></div>
<div class="hudbox"><div>اکثریت SHORT</div><div class="v" id="voteShort" style="color:var(--pink)">--</div></div>
<div class="hudbox"><div>WAIT</div><div class="v" id="voteWait" style="color:var(--gold)">--</div></div>
<div class="hudbox"><div>نمادها</div><div class="v" id="voteCount">--</div></div>
</div>
<div id="providerTally" class="chipRow" style="margin-bottom:12px"></div>
<div class="tableWrap"><table><thead><tr>
<th>نماد</th><th>TITAN</th><th>اکثریت AI</th><th>توافق</th><th>Gemini</th><th>ChatGPT</th><th>Grok</th><th>Claude</th><th>DeepSeek</th>
</tr></thead><tbody id="aiVoteBody"><tr><td colspan="9">برای بارگذاری روی «خلاصه رأی مدل‌ها» بزنید</td></tr></tbody></table></div>
<pre id="aiVoteDetail" style="white-space:pre-wrap;background:#020617;padding:12px;border-radius:10px;color:#cbd5e1;overflow:auto;margin-top:10px;max-height:280px;display:none"></pre>
</div>
</div><!-- /tab-ai -->

<div class="tabPanel" id="tab-control">
<div class="section"><h2>🛡️ Advanced Control Center</h2><div class="foot" style="border:none;padding:0"><div class="sb"><b>Live</b><div id="adv-live">--</div></div><div class="sb"><b>Historical</b><div id="adv-hist">--</div></div><div class="sb"><b>Paper</b><div id="adv-paper">--</div></div><div class="sb"><b>Quality</b><div id="adv-quality">--</div></div></div><div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px"><button class="btn" onclick="runBacktest()">🧪 بک‌تست</button><button class="btn" onclick="runWalkForward()">🔬 Walk-Forward</button><button class="btn" onclick="refreshAdvanced()">🔄 Refresh</button></div><pre id="adv-result" style="white-space:pre-wrap;background:#020617;padding:12px;border-radius:10px;color:#cbd5e1;overflow:auto">آماده</pre></div>
</div><!-- /tab-control -->

<div class="tabPanel" id="tab-perf">
<div class="section" style="border-color:rgba(56,189,248,.45);background:linear-gradient(135deg,rgba(10,20,38,.96),rgba(20,13,38,.94));margin-bottom:12px">
<div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap">
<h2 style="margin:0;color:#38bdf8">🎯 V22 BALANCED OPPORTUNITY ENGINE</h2>
<button class="btn" onclick="loadV22Opportunities()">🔄 بررسی فرصت‌ها</button>
</div>
<div class="sub" style="margin:7px 0 12px">WAIT به‌تنهایی پایان تحلیل نیست؛ فرصت‌های نزدیک به فعال‌شدن به‌صورت EARLY/WATCH نمایش داده می‌شوند و فقط با شواهد مستقل + پایداری + سلامت سطوح به سیگنال نهایی ارتقا می‌گیرند.</div>
<div class="hudgrid">
<div class="hudbox"><div>READY</div><div class="v" id="v22Ready" style="color:var(--green)">--</div></div>
<div class="hudbox"><div>EARLY</div><div class="v" id="v22Early" style="color:var(--cyan)">--</div></div>
<div class="hudbox"><div>WATCH</div><div class="v" id="v22Watch" style="color:var(--gold)">--</div></div>
<div class="hudbox"><div>NO EDGE</div><div class="v" id="v22NoEdge">--</div></div>
</div>
<div class="tableWrap" style="margin-top:12px"><table><thead><tr><th>نماد</th><th>تصمیم</th><th>فرصت</th><th>امتیاز</th><th>سمت</th><th>AI</th><th>یادگیری</th><th>دلیل</th></tr></thead>
<tbody id="v22OppBody"><tr><td colspan="8">در حال آماده‌سازی…</td></tr></tbody></table></div>
</div>

<div class="perfVisual" id="visualPerformance"><div class="perfHead"><div><h2>📊 PERFORMANCE INTELLIGENCE · امتیازدهی و عملکرد گذشته</h2><div class="perfSub">نمایش گرافیکی با حلقه، نوار و نماد · Win Rate · Equity · تایم‌فریم‌ها · رتبه دقت</div></div><button class="btn" onclick="loadVisualPerformance(true)">🔄 بروزرسانی عملکرد</button></div><div class="perfGrid"><div class="perfCard"><small>WIN RATE</small><div class="ring" id="wrRing" style="--v:0"><span id="visWR">--%</span></div><div class="metricState" id="visWL">-- W / -- L</div></div><div class="perfCard"><small>PERFORMANCE SCORE</small><div class="perfBig" id="visScore">--/100</div><div class="tfBar"><i id="visScoreBar" style="width:0%"></i></div><div class="metricState" id="visScoreState">بر اساس داده تاریخی واقعی</div></div><div class="perfCard"><small>EXPECTANCY</small><div class="perfBig" id="visExp">--%</div><div class="metricState" id="visPF">PF: --</div></div><div class="perfCard"><small>MAX DRAWDOWN</small><div class="perfBig" id="visDD">--%</div><div class="metricState" id="visOOS">OOS: --</div></div></div><div class="perfCharts"><div class="chartPanel"><h3>📈 Equity / Historical Return Curve</h3><canvas id="equityVisual" class="perfCanvas"></canvas></div><div class="chartPanel"><h3>🎯 Win / Loss / Neutral</h3><canvas id="wlVisual" class="perfCanvas"></canvas></div></div><div class="chartPanel" style="margin-top:12px"><h3>⏱ امتیاز عملکرد در تمام تایم‌فریم‌ها</h3><div id="tfVisual" class="tfVisual"></div></div><div class="perfNote" id="visNote">در حال دریافت داده عملکرد…</div><button class="btn" onclick="openTFWindow()">نمایش عقربه تایم‌فریم‌ها</button>
</div>
</div><!-- /tab-perf -->

<div class="tabPanel" id="tab-charts">
<div class="allCharts" id="allChartsSection">
<div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap">
<h2>📈 گالری نمودار همه ارزها</h2>
<button type="button" class="btn" onclick="loadAllCoinCharts(true)">🔄 بروزرسانی نمودارها</button>
</div>
<div class="sub" style="margin-bottom:10px">کندل واقعی از چند منبع (Binance / data-api) — اگر TradingView لود نشود همین‌جا نمایش داده می‌شود</div>
<div class="allGrid" id="allChartsGrid">در حال آماده‌سازی…</div>
</div>
</div><!-- /tab-charts -->


</div>
<div id="modal" class="modal"><div class="modalC"><h2 style="color:var(--cyan);margin-top:0">تنظیمات TITAN</h2><form action="/update_settings" method="POST"><label>ضریب ریسک ATR</label><input type="number" step="0.1" min="0.2" max="5" name="risk_multiplier" value="{{ settings.risk_multiplier }}"><label>نمادها</label><input type="text" name="active_coins" value="{{ settings.active_coins|join(', ') }}"><div style="display:flex;justify-content:flex-end;gap:8px"><button type="button" class="btn" onclick="closeM()">انصراف</button><button class="btn gold">ذخیره</button></div></form></div></div>

<!-- ROOT MODALS (outside tabs so display:none ancestors cannot hide them) -->
<div id="tfWindow" class="modal glassModal"><div class="modalC glassCard">
<div class="modalHead">
<div>
<div class="modalKicker">⏱ تحلیل چندتایم‌فریمی</div>
<h2 id="tfModalTitle">عقربه‌های تایم‌فریم</h2>
</div>
<button type="button" class="btn iconBtn" onclick="closeTFWindow()">✕</button>
</div>
<div id="tfGaugeBox" class="tfGaugeGrid">در حال دریافت…</div>
<div class="modalFoot"><button type="button" class="btn" onclick="closeTFWindow()">بستن</button></div>
</div></div>

<div id="coinDetailModal" class="modal detailModal glassModal"><div class="modalC glassCard wideModal">
<div class="cdShell">
  <div id="cdBanner" class="cdBanner flat">
    <div class="cdBannerInner">
      <div class="cdTitleBlock">
        <div id="cdIcon" class="cdIconXL">●</div>
        <div><div class="modalKicker">✦ پروفایل دارایی · TITAN</div><h2 id="cdTitle" class="cdName">جزئیات ارز</h2><div id="cdPair" class="cdPair">— / USDT · BINANCE</div></div>
      </div>
      <div style="text-align:left"><div id="cdPriceBig" class="cdPriceBig">— <small>USDT</small></div><div id="cdSignalRow" class="chipRow" style="justify-content:flex-end;margin-top:8px"></div><button type="button" class="btn iconBtn" style="margin-top:8px;float:left" onclick="closeCoinDetail()">✕</button></div>
    </div>
  </div>
  <div class="cdBodyPad">
    <div class="coinDetailTabs" id="coinDetailTabs">
      <button class="coinDetailTab active" data-cdtab="overview">◈ خلاصه</button>
      <button class="coinDetailTab" data-cdtab="charts">📈 نمودار و تایم‌فریم</button>
      <button class="coinDetailTab" data-cdtab="trade">🟢 خرید / 🔴 فروش</button>
      <button class="coinDetailTab" data-cdtab="levels">🎯 ورود و خروج</button>
      <button class="coinDetailTab" data-cdtab="ai">🤖 سیستم و AI</button>
      <button class="coinDetailTab" data-cdtab="forecast">🔮 پیش‌بینی کندل</button>
      <button class="coinDetailTab" data-cdtab="full">🧩 جزئیات کامل</button>
    </div>

    <section class="coinDetailPanel active" data-cdpanel="overview">
      <div id="cdMetrics" class="cdMetrics"></div>
      <div id="cdOverviewText" class="cdInfoBox"></div>
      <div class="cdSectionLabel">⏱ وضعیت تایم‌فریم‌ها</div><div id="cdTfStrip" class="cdTfStrip"></div>
    </section>

    <section class="coinDetailPanel" data-cdpanel="charts">
      <div class="cdSectionLabel">📈 نمودار ۱ ساعته</div>
      <div class="cdChartBox"><canvas id="cdCanvas" width="720" height="240"></canvas></div>
      <div id="cdChartNote" class="cdInfoBox">داده نمودار از بازار زنده/کش معتبر TITAN دریافت می‌شود.</div>
      <div class="cdActions"><button type="button" class="btn" onclick="openTFWindow(window.currentTFSymbol)">⏱ عقربه‌های همه تایم‌فریم‌ها</button></div>
    </section>

    <section class="coinDetailPanel" data-cdpanel="trade">
      <div id="cdTradePanel" class="detailActionGrid"></div>
    </section>

    <section class="coinDetailPanel" data-cdpanel="levels">
      <div class="cdSectionLabel">🎯 سطوح ورود و خروج</div><div id="cdLevels" class="cdLevels"></div>
      <div id="cdExtra" class="chipRow" style="margin-top:12px"></div>
    </section>

    <section class="coinDetailPanel" data-cdpanel="ai">
      <div class="aiDetailGrid">
        <div class="aiDetailCard"><b>🧠 نظر TITAN</b><div id="cdSystemOpinion">—</div></div>
        <div class="aiDetailCard"><b>🤖 اجماع هوش مصنوعی</b><div id="cdAIOpinion">در حال دریافت…</div></div>
        <div class="aiDetailCard"><b>🎯 کیفیت و اطمینان</b><div id="cdAIMetrics">—</div></div>
        <div class="aiDetailCard"><b>🔍 دلایل تصمیم</b><div id="cdReasoning">—</div></div>
      </div>
    </section>

    <section class="coinDetailPanel" data-cdpanel="forecast">
      <div class="cdSectionLabel">🔮 مسیر احتمالی کندل‌های آینده · ۱۲ کندل</div>
      <div class="cdChartBox"><canvas id="cdForecastCanvas" width="720" height="220"></canvas></div>
      <div id="cdForecastText" class="cdInfoBox">در حال دریافت پیش‌بینی…</div>
    </section>

    <section class="coinDetailPanel" data-cdpanel="full">
      <div class="cdSectionLabel">🧩 جزئیات تکمیلی همین ارز · بدون تکرار در داشبورد</div>
      <div id="cdFullDetails" class="cdFullDetails"></div>
    </section>

    <div class="cdActions">
      
      <button type="button" class="btn" onclick="closeCoinDetail()">بستن</button>
    </div>
  </div>
</div></div></div>


<script>
function switchMainTab(id, btn){
  document.querySelectorAll('.mainArea .tabPanel').forEach(function(p){p.classList.remove('active')});
  document.querySelectorAll('.mainTabs .mainTab').forEach(function(b){b.classList.remove('active')});
  document.querySelectorAll('.sidebar .sideBtn').forEach(function(b){b.classList.remove('active')});
  var p=document.getElementById(id); if(p)p.classList.add('active');
  if(btn){btn.classList.add('active'); var sid=btn.getAttribute('data-side-tab'); if(sid){var s=document.querySelector('.sideBtn[data-side-tab="'+sid+'"]'); if(s)s.classList.add('active');}}
  else {var s=document.querySelector('.sideBtn[data-side-tab="'+id+'"]'); if(s)s.classList.add('active'); var t=document.querySelector('.mainTabs .mainTab[onclick*="'+id+'"]'); if(t)t.classList.add('active');}
  if(id==='tab-ai'){try{loadAiVoteBoard();refreshGemini()}catch(e){}}
  if(id==='tab-perf'){try{loadVisualPerformance();loadV22Opportunities()}catch(e){}}
  if(id==='tab-charts'){try{loadAllCoinCharts()}catch(e){}}
  if(id==='tab-edge'){try{loadEdgeTerminal()}catch(e){}}
  if(id==='tab-control'){try{refreshAdvanced()}catch(e){}}
}
function filterAssets(){
  var q=(document.getElementById('coinSearch')||{}).value||''; q=q.toLowerCase().trim();
  document.querySelectorAll('#assetGrid .assetCard').forEach(function(c){var txt=(c.getAttribute('data-name')||'').toLowerCase();var ok=!q||txt.indexOf(q)>=0;var f=window.assetFilter||'ALL';var d=c.getAttribute('data-decision')||'WAIT';if(f==='TOP')ok=ok&&Number(c.getAttribute('data-score')||0)>=70;else if(f!=='ALL')ok=ok&&d===f;c.style.display=ok?'':'none';});
}
window.assetFilter='ALL';
function setAssetFilter(f,btn){window.assetFilter=f;document.querySelectorAll('.filterBtn').forEach(function(x){x.classList.toggle('active',x.getAttribute('data-filter')===f)});document.querySelectorAll('.assetTools button').forEach(function(x){x.classList.remove('active')});if(btn&&btn.parentElement&&btn.parentElement.classList.contains('assetTools'))btn.classList.add('active');filterAssets();}
function clearAssetFilter(){window.assetFilter='ALL';var q=document.getElementById('coinSearch');if(q)q.value='';document.querySelectorAll('.filterBtn').forEach(function(x){x.classList.toggle('active',x.getAttribute('data-filter')==='ALL')});filterAssets();}
</script>
<script type="text/javascript" src="https://s3.tradingview.com/tv.js" onerror="window.__tvScriptFailed=true"></script>
<script>
(function(){
"use strict";

function switchTab(id, btn){
  try {
    document.querySelectorAll(".tabPanel").forEach(function(p){ p.classList.remove("active"); });
    document.querySelectorAll(".tabBtn").forEach(function(b){ b.classList.remove("active"); });
    var panel = document.getElementById(id);
    if(panel) panel.classList.add("active");
    if(btn) btn.classList.add("active");
    if(id === "tab-charts") { try { loadAllCoinCharts(); } catch(e){} }
    if(id === "tab-perf") { try { loadVisualPerformance(); } catch(e){} try { loadV22Opportunities(); } catch(e){} }
    if(id === "tab-edge") { try { loadEdgeTerminal(); } catch(e){} }
    if(id === "tab-control") { try { refreshAdvanced(); } catch(e){} }
    if(id === "tab-ai") { try { loadAiVoteBoard(); refreshGemini(); } catch(e){} }
  } catch(e) { console.warn(e); }
}

window.switchTab = switchTab;

async function loadAiVoteBoard(){
  var body = document.getElementById("aiVoteBody");
  var sum = document.getElementById("aiVoteSummary");
  try {
    if(sum) sum.textContent = "در حال خواندن رأی مدل‌ها…";
    var d = await fetch("/api/ai-votes", {cache:"no-store"}).then(function(r){return r.json();});
    if(!d || !d.ok){ if(sum) sum.textContent = "داده رأی در دسترس نیست"; return; }
    var t = d.tally || {};
    setText("voteLong", t.LONG != null ? t.LONG : 0);
    setText("voteShort", t.SHORT != null ? t.SHORT : 0);
    setText("voteWait", t.WAIT != null ? t.WAIT : 0);
    setText("voteCount", d.count != null ? d.count : 0);
    if(sum) sum.textContent = "به‌روز · " + (d.count||0) + " نماد";
    var pt = document.getElementById("providerTally");
    if(pt){
      pt.innerHTML = "";
      var prov = t.providers || {};
      Object.keys(prov).forEach(function(p){
        var b = prov[p] || {};
        var total = (b.LONG||0)+(b.SHORT||0)+(b.WAIT||0);
        var conf = total ? Math.round(Math.max(b.LONG||0, b.SHORT||0) / total * 100) : 0;
        var el = document.createElement("span");
        el.className = "miniChip";
        el.textContent = p + ": L" + (b.LONG||0) + " / S" + (b.SHORT||0) + " / W" + (b.WAIT||0) + " · امتیاز " + conf + "%";
        pt.appendChild(el);
      });
    }
    var msc = document.getElementById("modelScoreChips");
    if(msc){
      msc.innerHTML = "";
      var names = {gemini:"Gemini", openai:"ChatGPT", grok:"Grok", claude:"Claude", deepseek:"DeepSeek"};
      var prov2 = t.providers || {};
      Object.keys(names).forEach(function(p){
        var b = prov2[p] || {};
        var total = (b.LONG||0)+(b.SHORT||0)+(b.WAIT||0);
        var mode = "WAIT"; var sc = 50;
        if((b.LONG||0) >= (b.SHORT||0) && (b.LONG||0) >= (b.WAIT||0) && (b.LONG||0)>0){ mode="LONG"; sc = total? Math.round(b.LONG/total*100):50; }
        else if((b.SHORT||0) >= (b.LONG||0) && (b.SHORT||0) >= (b.WAIT||0) && (b.SHORT||0)>0){ mode="SHORT"; sc = total? Math.round(b.SHORT/total*100):50; }
        else { mode="WAIT"; sc = total? Math.round((b.WAIT||0)/total*100):50; }
        var col = mode==="LONG"?"#4ade80": mode==="SHORT"?"#f43f5e":"#fbbf24";
        var el = document.createElement("span");
        el.className = "miniChip";
        el.style.borderColor = col;
        el.innerHTML = "<b style='color:"+col+"'>" + names[p] + "</b> · حالت " + mode + " · امتیاز مدل " + sc + "%";
        msc.appendChild(el);
      });
    }
    function voteCell(v){
      if(v==="LONG") return '<span class="signalBadge long">LONG</span>';
      if(v==="SHORT") return '<span class="signalBadge short">SHORT</span>';
      if(v==="WAIT") return '<span class="signalBadge wait">WAIT</span>';
      return '<span style="color:#64748b">—</span>';
    }
    if(body){
      body.innerHTML = (d.board||[]).map(function(row){
        var v = row.votes || {};
        var details = row.details || {};
        function modelTitle(name, vote){
          var z = details[name] || {};
          var sn = String(z.snippet || "").replace(/</g,"&lt;").replace(/>/g,"&gt;");
          return voteCell(vote) + (sn ? "<div style='font-size:10px;color:#64748b;margin-top:4px;max-width:180px;line-height:1.5'>" + sn.slice(0,120) + "</div>" : "");
        }
        return "<tr><td><b>" + (row.symbol||"") + "</b></td><td>" + voteCell(row.titan) +