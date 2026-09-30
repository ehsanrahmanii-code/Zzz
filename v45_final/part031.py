.tickerRail .tickerIcon, .tickerRail .ringIcon {
  border: none !important;
  box-shadow: none !important;
  outline: none !important;
  background: transparent !important;
  animation: none !important;
}
.tickerIcon .sigRing, .ringIcon .sigRing, .sigRing {
  display: none !important;
  border: none !important;
  box-shadow: none !important;
}

/* Replace double lines with ONE small triangle under name */
.sigUnderline {
  display: inline-block !important;
  width: 0 !important;
  height: 0 !important;
  margin: 5px 0 0 2px !important;
  border-radius: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
  border-left: 5px solid transparent !important;
  border-right: 5px solid transparent !important;
  border-top: none !important;
  border-bottom: 7px solid #ffd34e !important; /* WAIT yellow, point up */
  vertical-align: middle !important;
}
.sigUnderline.up {
  background: transparent !important;
  box-shadow: none !important;
  border-left: 5px solid transparent !important;
  border-right: 5px solid transparent !important;
  border-bottom: 7px solid #23e6a8 !important;
  border-top: none !important;
  filter: drop-shadow(0 0 4px rgba(35,230,168,.7));
}
.sigUnderline.down {
  background: transparent !important;
  box-shadow: none !important;
  /* point down for short */
  border-left: 5px solid transparent !important;
  border-right: 5px solid transparent !important;
  border-top: 7px solid #ff4d73 !important;
  border-bottom: none !important;
  filter: drop-shadow(0 0 4px rgba(255,77,115,.7));
}
.sigUnderline.neutral {
  background: transparent !important;
  box-shadow: none !important;
  border-left: 5px solid transparent !important;
  border-right: 5px solid transparent !important;
  border-bottom: 7px solid #ffd34e !important;
  border-top: none !important;
  filter: drop-shadow(0 0 4px rgba(255,211,78,.7));
}
/* Hide any extra score ring mini glow lines looking like double yellow */
.tickerRail .scoreRingMini {
  box-shadow: none !important;
}

</style>
<body>
<div class="titanApp">

  <header class="topHeader">
    <div class="brand"><div class="brandMark">◈</div><div><h1>TITAN <span>V28</span> ADVANCED</h1><small>موتور کمّی · هوش مصنوعی · فقط تحلیل</small></div></div>
    <div class="statusStrip">
      <div class="statusPill"><span class="dot"></span><b>موتور TITAN</b> فعال</div>
      <div class="statusPill"><span class="dot"></span><b>Binance</b> Live</div>
      <div class="statusPill"><span class="dot"></span><b>CoinGlass V4</b></div>
      <div class="statusPill"><span class="dot"></span><b>Gemini</b> {{ 'آماده' if gemini_status.available else 'کلید موجود نیست' }}</div>
      <div class="statusPill"><span class="dot warn"></span><b>UTC+3:30</b> · {{ gemini_status.updated_at }}</div>
    </div>
    <div class="headerActions"><a class="glassBtn" href="/rescan" onclick="try{TitanSFX&&TitanSFX.play('success')}catch(e){}">⟳ اسکن مجدد</a><button class="glassBtn" type="button" id="sfxToggleBtn" onclick="(function(b){var on=TitanSFX.toggle();b.textContent=on?'🔊 صدا':'🔇 قطع';b.title=on?'افکت صوتی روشن':'افکت صوتی خاموش';})(this)">🔊 صدا</button><button class="glassBtn gold" onclick="openM()">⚙ تنظیمات</button></div><div class="scanTelemetry" id="scanTelemetry"><div class="scanTelemetryTop"><b id="scanPhase">آماده</b><span id="scanPct">0%</span></div><div class="scanTelemetryBar"><i id="scanBar"></i></div><div class="scanTelemetryMeta"><span id="scanTime">آخرین اسکن: —</span><span id="scanAge">داده: —</span></div></div>
  </header>

<div class="rtAnalysisBar" id="rtAnalysisBar">
  <div class="rtLeft"><span class="rtDot"></span><b>تحلیل بلادرنگ</b> <span id="rtStatus">در حال اتصال…</span></div>
  <div class="rtMid" id="rtBreadth">▲ -- · ▼ -- · ◆ --</div>
  <div class="rtRight" id="rtLeaders">—</div>

<div class="scalp30Box" id="scalp30Box">
  <div class="scalp30Head">
    <b>⚡ پنجره اهرمی ۳۰–۶۰ دقیقه</b>
    <span>فقط سیگنال کوتاه‌مدت · بستن حداکثر تا ۶۰ دقیقه · تحلیل نه توصیه قطعی</span>
  </div>
  <div class="scalp30Grid" id="scalp30Grid"><div style="color:#8fa7bb;font-size:12px">در حال محاسبه فرصت‌های نیم‌ساعته…</div></div>
</div>

</div>

  <div class="appGrid">
    <aside class="sidebar">
      <div class="sideBrand"><b>◈ NAVIGATION</b><small>مرکز کنترل طبقه‌بندی‌شده</small></div>
      <button class="sideBtn active" data-side-tab="tab-market" onclick="switchMainTab('tab-market',this)"><span class="sideIcon">⌂</span><span>مرکز بازار</span></button>
      <button class="sideBtn" data-side-tab="tab-edge" onclick="switchMainTab('tab-edge',this)"><span class="sideIcon">◈</span><span>Edge Suite</span></button>
      <button class="sideBtn" data-side-tab="tab-ai" onclick="switchMainTab('tab-ai',this)"><span class="sideIcon">✦</span><span>هوش مصنوعی</span></button>
      <button class="sideBtn" data-side-tab="tab-perf" onclick="switchMainTab('tab-perf',this)"><span class="sideIcon">◌</span><span>عملکرد</span></button>
      <button class="sideBtn" data-side-tab="tab-charts" onclick="switchMainTab('tab-charts',this)"><span class="sideIcon">⌁</span><span>نمودارها</span></button>
      <button class="sideBtn" data-side-tab="tab-control" onclick="switchMainTab('tab-control',this)"><span class="sideIcon">⚙</span><span>کنترل</span></button>
      <div class="sideFilter"><label>جستجوی سریع ارز</label><input id="coinSearch" class="searchBox" placeholder="BTC / ETH / SHIB ..." oninput="filterAssets()"><div class="filterRow"><button class="filterBtn active" data-filter="ALL" onclick="setAssetFilter('ALL',this)">همه</button><button class="filterBtn" data-filter="LONG" onclick="setAssetFilter('LONG',this)">LONG</button><button class="filterBtn" data-filter="WAIT" onclick="setAssetFilter('WAIT',this)">WAIT</button></div><div class="filterRow"><button class="filterBtn" data-filter="SHORT" onclick="setAssetFilter('SHORT',this)">SHORT</button><button class="filterBtn" data-filter="TOP" onclick="setAssetFilter('TOP',this)">برتر</button><button class="filterBtn" onclick="clearAssetFilter()">پاک</button></div></div>
    </aside>

    <main class="mainArea">
      

      <section class="tabPanel active" id="tab-market">
        <div class="tickerRail">
          {% for item in market_data %}
          {% set dec=item.get('decision_tag','WAIT')|upper %}{% set cls='up' if dec=='LONG' else 'down' if dec=='SHORT' else 'neutral' %}
          <button class="ticker coinHue{{ loop.index0 % 12 }} {{ cls }}" data-decision="{{ dec }}" data-jump="{{ item.tv_symbol }}" data-symbol="{{ item.symbol }}"><div class="tickerTop"><span class="tickerCoin"><span class="tickerIcon ringIcon {{ cls }}"><i class="sigRing"></i>{{ item.coin_icon }}</span><span><b>{{ item.base_symbol }}</b><small>{{ item.coin_name }}</small><i class="sigUnderline {{ cls }}"></i></span></span><span class="tickerMove {{ cls }} sigBadge">{{ '▲ خرید' if dec=='LONG' else '▼ فروش' if dec=='SHORT' else '◆ انتظار' }}</span></div><div class="tickerTop" style="margin-top:4px"><span class="tickerPrice">{{ item.price }}</span><span class="scoreChip {{ cls }}"><span class="scoreRingMini" style="--sc:{{ item.score|default(0) }}"></span> {{ item.score }}</span></div></button>
          {% endfor %}
        </div>

        {% set board=(macro.get('signal_board') if macro else None) or {} %}{% set counts=board.get('counts') or {} %}{% set gsum=(macro.get('grade_summary') if macro else None) or {} %}
        {% set active_list = board.get('active') if board.get('active') is not none else none %}
        <div class="activeHero" id="activeHeroBoard">
          <div class="activeHeroHead">
            <h3>⚡ سیگنال‌های فعال همین لحظه · V28.5</h3>
            <span class="ahCount" id="ahCountLabel">LONG {{ counts.get('long',0) }} · SHORT {{ counts.get('short',0) }} · WAIT {{ counts.get('wait',0) }}</span>
          </div>
          <div class="activeHeroGrid" id="activeHeroGrid">
            {% for a in market_data if (a.get('decision_tag') or 'WAIT')|upper in ['LONG','SHORT'] %}
              {% if loop.index <= 12 %}
                {% set ad = (a.get('decision_tag') or 'WAIT')|upper %}
                {% set acls = 'long' if ad=='LONG' else 'short' %}
                {% set asym = a.get('symbol') or '' %}
                {% set abase = a.get('base_symbol') or (asym.split('/')[0] if asym else '—') %}
                <button class="ahCard {{ acls }}" data-symbol="{{ asym }}" onclick="jumpToCoin('{{ asym.replace('/','') }}','{{ asym }}')">
                  <div class="ahTop"><b>{{ a.get('coin_icon') or '◆' }} {{ abase }}</b><span class="ahSide">{{ '▲ LONG' if ad=='LONG' else '▼ SHORT' }}</span></div>
                  <div class="ahPrice">{{ a.get('price') or '—' }}</div>
                  <div class="ahMeta">{{ a.get('grade') or '—' }} · Q{{ a.get('signal_quality') or '—' }} · RR{{ a.get('rr_tp1') or a.get('effective_rr_tp1') or '—' }} · Trust {{ a.get('trust_index') or '—' }}</div>
                </button>
              {% endif %}
            {% else %}
              <div class="ahEmpty" style="grid-column:1/-1">الان سیگنال جهت‌دار فعال نیست — بازار در حالت انتظار است. بعد از Rescan اگر لبه واقعی باشد اینجا سبز/قرمز می‌شود.</div>
            {% endfor %}
          </div>
        </div>
        <script>
        (function(){
          try{
            var g=document.getElementById('activeHeroGrid');
            var board=document.getElementById('activeHeroBoard');
            if(g && board && !g.querySelector('.ahCard')) board.classList.add('empty');
          }catch(e){}
        })();
        </script>
        <div class="kpiGrid">
          <div class="kpi"><div class="kpiHead"><span>REGIME</span><span class="kpiIcon">◈</span></div><div class="kpiValue" id="pulse-regime">--</div><div class="kpiHint">رژیم غالب بازار</div></div>
          <div class="kpi"><div class="kpiHead"><span>MARKET SCORE</span><span class="kpiIcon">◉</span></div><div class="kpiValue" id="pulse-score">--</div><div class="kpiHint">میانگین امتیاز</div></div>
          <div class="kpi"><div class="kpiHead"><span>BREADTH</span><span class="kpiIcon">▥</span></div><div class="kpiValue" id="pulse-breadth">--</div><div class="kpiHint">عرض بازار</div></div>
          <div class="kpi"><div class="kpiHead"><span>LONG / SHORT</span><span class="kpiIcon">⇄</span></div><div class="kpiValue"><span class="up">{{ counts.get('long',0) }}</span> / <span class="down">{{ counts.get('short',0) }}</span></div><div class="kpiHint">سیگنال فعال · نه فقط A+</div></div>
          <div class="kpi"><div class="kpiHead"><span>FEAR & GREED</span><span class="kpiIcon">◉</span></div><div class="kpiValue">{{ macro.fear_greed_val|default('—') }}</div><div class="kpiHint">{{ macro.fear_greed_text|default('—') }}</div></div>
          <div class="kpi"><div class="kpiHead"><span>BTC DOMINANCE</span><span class="kpiIcon">₿</span></div><div class="kpiValue">{{ macro.dominance_btc|default('—') }}</div><div class="kpiHint">{{ market_data|length }} نماد تحت پایش</div></div>
        </div>

        <div class="commandGrid">
          <section class="panel">
            <div class="panelHead"><div><div class="panelTitle">◈ مرکز فرصت‌ها · TITAN V28.4 SIGNAL-FIRST</div><div class="panelSub">سیگنال‌های LONG/SHORT اول لیست · درجه + Trust روی کارت · برای جزئیات کلیک کنید</div></div><span class="panelAction" id="pulse-time">LIVE</span></div>
            <div class="signalSummary"><div class="signalBox long"><b>▲ LONG</b><div class="signalNum">{{ counts.get('long',0) }}</div><div class="signalMeta">فعال · همه درجات</div></div><div class="signalBox wait"><b>◆ WAIT</b><div class="signalNum">{{ counts.get('wait',0) }}</div><div class="signalMeta">صبر / EARLY / WATCH</div></div><div class="signalBox short"><b>▼ SHORT</b><div class="signalNum">{{ counts.get('short',0) }}</div><div class="signalMeta">فعال · همه درجات</div></div></div>
            {% set top3 = board.get('top3') or board.get('actionable') or [] %}
            {% if top3 %}
            <div class="topPicksBar">
              <div class="topPicksLabel">★ برترین سیگنال‌ها</div>
              <div class="topPicksRow">
              {% for t in top3[:3] %}
                {% set td = (t.get('decision') or 'WAIT')|upper %}
                <button class="topPickCard {{ 'long' if td=='LONG' else 'short' if td=='SHORT' else 'wait' }}" data-jump="{{ t.get('symbol','') }}" onclick="jumpToCoin('{{ (t.get('symbol') or '').replace('/','') }}','{{ t.get('symbol','') }}')">
                  <span class="tpIcon">{{ t.get('icon') or '◆' }}</span>
                  <span class="tpBody">
                    <b>{{ t.get('base') or t.get('symbol') }}</b>
                    <small>{{ td }} · {{ t.get('grade') or '—' }} · Q{{ t.get('quality') or '—' }} · RR{{ t.get('rr1') or '—' }}</small>
                  </span>
                </button>
              {% endfor %}
              </div>
            </div>
            {% endif %}
            <div class="assetHeader"><div class="panelTitle">ارزهای تحت پایش <span style="color:#5e7890;font-size:9px">{{ market_data|length }} نماد · A+/A={{ counts.get('actionable',0) }} · فعال={{ counts.get('active', counts.get('long',0)+counts.get('short',0)) }}</span></div><div class="assetTools"><button class="active" onclick="setAssetFilter('ALL',this)">همه</button><button onclick="setAssetFilter('LONG',this)">LONG</button><button onclick="setAssetFilter('WAIT',this)">WAIT</button><button onclick="setAssetFilter('SHORT',this)">SHORT</button></div></div>
            <div class="assetGrid" id="assetGrid">
              {% for item in market_data %}
              {% set dec=item.get('decision_tag','WAIT')|upper %}{% set cls='long' if dec=='LONG' else 'short' if dec=='SHORT' else 'wait' %}{% set sc=(item.get('score') or 0)|float %}{% set gr=item.get('grade') or (item.get('signal_grade') or {}).get('grade') or '—' %}
              <button class="assetCard coinHue{{ loop.index0 % 12 }} {{ cls }}" data-jump="{{ item.tv_symbol }}" data-symbol="{{ item.symbol }}" data-decision="{{ dec }}" data-score="{{ sc }}" data-name="{{ item.coin_name }} {{ item.base_symbol }}" onclick="jumpToCoin('{{ item.tv_symbol }}','{{ item.symbol }}')">
                <div class="assetTop"><span class="assetIdentity"><span class="assetIcon">{{ item.coin_icon }}</span><span class="assetName"><b>{{ item.base_symbol }} <span style="font-size:9px;opacity:.85;color:{% if gr in ['A+','A'] %}#4ade80{% elif gr=='B' %}#38bdf8{% else %}#94a3b8{% endif %}">{{ gr }}</span></b><small>{{ item.coin_name }}{% if item.get('opportunity_score') %} · Opp {{ item.opportunity_score|int }}{% endif %}</small></span></span><span class="decisionPill {{ cls }}">{{ '▲ LONG' if dec=='LONG' else '▼ SHORT' if dec=='SHORT' else '◆ WAIT' }}</span></div>
                <div class="assetPrice"><b>{{ item.price }}</b><span class="{{ cls }}">{{ item.bias|default('خنثی') }}</span></div>
                <div class="scoreLine"><div class="scoreRing" style="--score:{{ sc }};--ring:{{ '#23e6a8' if dec=='LONG' else '#ff4d73' if dec=='SHORT' else '#ffd34e' }}"><span>{{ item.score }}</span></div><div style="flex:1"><div style="font-size:7px;color:#607990;display:flex;justify-content:space-between"><span>Signal Quality</span><b style="color:#b9cde0">{{ item.signal_quality|default('—') }}</b></div><div class="scoreBar"><i style="width:{{ sc }}%"></i></div></div></div>
                <div class="assetTF"><span class="tfMini">15m<b>{{ item.tfs['15m'] }}</b></span><span class="tfMini">1h<b>{{ item.tfs['1h'] }}</b></span><span class="tfMini">4h<b>{{ item.tfs['4h'] }}</b></span><span class="tfMini">1D<b>{{ item.tfs['1d'] }}</b></span></div>
                <div class="assetBottom"><span>Prob {{ item.success_probability|default('—') }}%</span><span class="assetOpen">مشاهده پروفایل ⟵</span></div>
              </button>
              {% endfor %}
            </div>
          </section>

          <aside class="sidePanels">
            <section class="panel geminiCard"><div class="panelHead"><div><div class="panelTitle">✦ Gemini Intelligence</div><div class="panelSub">تحلیل کلان AI</div></div><span id="geminiStatus" class="miniChip">{{ gemini_status.label }}</span></div><div class="aiBadge"><strong>Gemini</strong><span id="geminiRefreshState">{{ gemini_status.updated_at }}</span></div><div id="geminiAnalysis" class="aiText">{{ gemini_summary if gemini_summary else 'تحلیل Gemini در حال آماده‌سازی است…' }}</div><div class="miniGauge"><i style="width:{{ 100 if gemini_status.ready else 20 }}%"></i></div><button class="glassBtn" style="width:100%;margin-top:8px;font-size:9px" onclick="refreshGemini()">↻ دریافت تحلیل Gemini</button></section>
            <section class="panel"><div class="panelHead"><div class="panelTitle">◉ وضعیت سیستم</div><span class="dot"></span></div><div class="healthList"><div class="healthRow"><span>دریافت داده بازار</span><b class="okDot">● OK</b></div><div class="healthRow"><span>تحلیل تکنیکال</span><b class="okDot">● OK</b></div><div class="healthRow"><span>AI Fusion</span><b class="okDot">● OK</b></div><div class="healthRow"><span>پیش‌بینی کندل</span><b class="okDot">● OK</b></div><div class="healthRow"><span>SQLite / Memory</span><b class="okDot">● OK</b></div></div></section>
            <section class="panel"><div class="panelHead"><div class="panelTitle">◌ شاخص‌های بازار</div></div><div class="marketMini"><div class="macroBox"><small>Fear & Greed</small><b class="neutral">{{ macro.fear_greed_val|default('—') }}</b></div><div class="macroBox"><small>BTC Dom.</small><b>{{ macro.dominance_btc|default('—') }}</b></div><div class="macroBox"><small>Actionable</small><b class="up">{{ counts.get('actionable',0) }}</b></div><div class="macroBox"><small>Best Quality</small><b id="pulse-leader">--</b></div></div></section>
            <section class="panel"><div class="panelHead"><div class="panelTitle">◷ رویدادها / زمینه بازار</div></div><div class="eventList"><div class="eventItem"><b>Macro Context</b><small>داده‌های کلان و ریسک بازار در Edge Suite</small></div><div class="eventItem"><b>AI Consensus</b><small>اجماع مدل‌ها در بخش هوش مصنوعی</small></div><div class="eventItem"><b>Opportunity Engine</b><small>READY / EARLY / WATCH در تب فرصت‌ها</small></div></div></section>
          </aside>
        </div>

        <div class="bottomGrid">
          <section class="panel"><div class="panelHead"><div><div class="panelTitle">◌ عملکرد تاریخی · خلاصه</div><div class="panelSub">جزئیات کامل در تب عملکرد</div></div><button class="panelAction" onclick="switchMainTab('tab-perf',null)">باز کردن عملکرد</button></div><div class="performanceStrip"><div class="perfStat"><small>WIN RATE</small><b class="up">{{ audit.win_rate|default(0) }}%</b></div><div class="perfStat"><small>W / L</small><b>{{ audit.wins|default(0) }} / {{ audit.losses|default(0) }}</b></div><div class="perfStat"><small>ACCURACY TIER</small><b>{{ audit.get('tier','—') }}</b></div><div class="perfStat"><small>LEADER</small><b id="pulse-leader">--</b></div></div></section>
          <section class="panel"><div class="panelHead"><div class="panelTitle">⏱ وضعیت تایم‌فریم‌ها</div><button class="panelAction" onclick="openTFWindow()">عقربه کامل</button></div><div class="gaugeDeck"><div class="tfGauge"><div class="needle"></div><b>15m</b><small>کوتاه‌مدت</small></div><div class="tfGauge"><div class="needle" style="--rot:18deg"></div><b>1h</b><small>مرجع</small></div><div class="tfGauge"><div class="needle" style="--rot:34deg"></div><b>4h</b><small>روند</small></div><div class="tfGauge"><div class="needle" style="--rot:48deg"></div><b>1D</b><small>ساختار</small></div></div></section>
        </div>
      </section>

      <section class="tabPanel" id="tab-edge">
        <div class="panel"><div class="panelHead"><div><div class="panelTitle">🧠 TITAN PROFESSIONAL EDGE SUITE</div><div class="panelSub">لایه‌های تصمیم، ریسک، اجماع AI و فرصت</div></div><span id="edge-status" class="miniChip">ACTIVE</span></div><div class="metricCards"><div class="metricBox"><small>Confluence</small><b id="edge-conf">--</b></div><div class="metricBox"><small>Meta Label</small><b id="edge-meta">--</b></div><div class="metricBox"><small>AI Consensus</small><b id="edge-ai">--</b></div><div class="metricBox"><small>Risk State</small><b id="edge-risk">--</b></div></div><div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px"><button class="glassBtn" onclick="loadEdgeTerminal()">🛰 Decision Terminal</button><button class="glassBtn" onclick="runProLab()">🧪 12-Layer Pro Lab</button><span id="edge-msg" style="align-self:center;font-size:8px;color:#6f879e"></span></div><pre id="edge-terminal" class="preBox">داده آماده است</pre></div>
        <div class="sectionGrid" style="margin-top:9px"><div class="panel"><div class="panelTitle">⚖️ تعادل Signal / WAIT</div><p style="font-size:9px;line-height:1.9;color:#8fa5b9">سیستم فرصت‌های نزدیک را از تصمیم نهایی جدا نگه می‌دارد تا WAIT به‌صورت بی‌دلیل غالب نشود و در عین حال LONG/SHORT بدون شواهد کافی صادر نشود.</p></div><div class="panel"><div class="panelTitle">🧩 طبقات تصمیم</div><div style="display:flex;gap:5px;flex-wrap:wrap;margin-top:8px"><span class="signalBadge long">READY LONG</span><span class="signalBadge wait">EARLY / WATCH</span><span class="signalBadge short">READY SHORT</span></div></div></div>
      </section>

      <section class="tabPanel" id="tab-ai">
        <div class="panel geminiCard"><div class="panelHead"><div><div class="panelTitle">🤖 Gemini Global Intelligence</div><div class="panelSub">تحلیل Gemini باید در همین‌جا قابل مشاهده باشد</div></div><span id="geminiStatus">{{ gemini_status.label }}</span></div><div id="geminiAnalysis" style="font-size:10px;line-height:2;color:#c4d5e7;max-height:300px;overflow:auto">{{ gemini_summary if gemini_summary else 'تحلیل Gemini هنوز آماده نیست.' }}</div><div style="display:flex;gap:6px;margin-top:8px"><button class="glassBtn" onclick="refreshGemini()">↻ تحلیل جدید</button><span id="geminiRefreshState" class="miniChip"></span></div></div>
        <div class="panel" style="margin-top:9px"><div class="panelHead"><div><div class="panelTitle">🗳 هیئت رأی مدل‌ها</div><div class="panelSub">Gemini · Grok · Claude · DeepSeek · ChatGPT در صورت موجود بودن</div></div><span id="aiVoteSummary">در حال آماده‌سازی…</span></div><div id="modelScoreChips" style="display:flex;gap:5px;flex-wrap:wrap;margin-bottom:8px"></div><div class="metricCards" style="margin-bottom:8px"><div class="metricBox"><small>LONG</small><b id="voteLong" class="up">--</b></div><div class="metricBox"><small>SHORT</small><b id="voteShort" class="down">--</b></div><div class="metricBox"><small>WAIT</small><b id="voteWait" class="neutral">--</b></div><div class="metricBox"><small>SYMBOLS</small><b id="voteCount">--</b></div></div><div id="providerTally" style="display:flex;gap:5px;flex-wrap:wrap;margin-bottom:8px"></div><div class="tableWrap"><table class="dataTable"><thead><tr><th>نماد</th><th>TITAN</th><th>AI</th><th>توافق</th><th>Gemini</th><th>Grok</th><th>Claude</th><th>DeepSeek</th></tr></thead><tbody id="aiVoteBody"><tr><td colspan="8">برای بارگذاری رأی مدل‌ها چند ثانیه صبر کنید.</td></tr></tbody></table></div></div>
      </section>

      <section class="tabPanel" id="tab-perf">
        <div class="panel"><div class="panelHead"><div><div class="panelTitle">📊 Performance Intelligence</div><div class="panelSub">Win Rate · Expectancy · Profit Factor · Drawdown · OOS · تایم‌فریم</div></div><button class="glassBtn" onclick="loadVisualPerformance(true)">↻ بروزرسانی</button></div><div class="perfGrid"><div class="perfCard"><small>WIN RATE</small><div class="ring" id="wrRing" style="--v:0"><span id="visWR">--%</span></div><div style="font-size:8px;color:#667f96" id="visWL">-- W / -- L</div></div><div class="perfCard"><small>PERFORMANCE SCORE</small><div class="perfBig" id="visScore">--/100</div><div class="tfBar"><i id="visScoreBar" style="width:0%"></i></div></div><div class="perfCard"><small>EXPECTANCY</small><div class="perfBig" id="visExp">--%</div><div style="font-size:8px;color:#667f96" id="visPF">PF: --</div></div><div class="perfCard"><small>MAX DRAWDOWN</small><div class="perfBig" id="visDD">--%</div><div style="font-size:8px;color:#667f96" id="visOOS">OOS: --</div></div></div><div class="perfCharts"><div class="chartPanel"><h3>📈 Equity / Return Curve</h3><canvas id="equityVisual" class="perfCanvas"></canvas></div><div class="chartPanel"><h3>🎯 Win / Loss / Neutral</h3><canvas id="wlVisual" class="perfCanvas"></canvas></div></div><div class="chartPanel" style="margin-top:7px"><h3>⏱ امتیاز تمام تایم‌فریم‌ها</h3><div id="tfVisual" class="tfVisual"></div></div><div id="visNote" class="perfNote">در حال دریافت داده عملکرد…</div><button class="glassBtn" style="margin-top:7px" onclick="openTFWindow()">نمایش عقربه‌های تایم‌فریم</button></div>
        <div class="panel" style="margin-top:9px"><div class="panelHead"><div class="panelTitle">🎯 Balanced Opportunity Engine</div><button class="glassBtn" onclick="loadV22Opportunities()">↻ بررسی فرصت‌ها</button></div><div class="metricCards"><div class="metricBox"><small>READY</small><b id="v22Ready" class="up">--</b></div><div class="metricBox"><small>EARLY</small><b id="v22Early">--</b></div><div class="metricBox"><small>WATCH</small><b id="v22Watch" class="neutral">--</b></div><div class="metricBox"><small>NO EDGE</small><b id="v22NoEdge">--</b></div></div><div class="tableWrap" style="margin-top:8px"><table class="dataTable"><thead><tr><th>نماد</th><th>تصمیم</th><th>فرصت</th><th>امتیاز</th><th>AI</th><th>یادگیری</th><th>دلیل</th></tr></thead><tbody id="v22OppBody"><tr><td colspan="7">در حال آماده‌سازی…</td></tr></tbody></table></div></div>
      </section>

      <section class="tabPanel" id="tab-charts">
        <div class="panel"><div class="panelHead"><div><div class="panelTitle">📈 Market Chart Gallery</div><div class="panelSub">نمودارهای واقعی برای همه نمادها · بدون حذف داده</div></div><button class="glassBtn" onclick="loadAllCoinCharts(true)">↻ بروزرسانی</button></div><div class="allGrid" id="allChartsGrid">در حال آماده‌سازی…</div></div>
      </section>

      <section class="tabPanel" id="tab-control">
        <div class="panel"><div class="panelHead"><div><div class="panelTitle">🛡 Advanced Control Center</div><div class="panelSub">بک‌تست، Walk-Forward، سلامت داده و حافظه</div></div><button class="glassBtn" onclick="refreshAdvanced()">↻ Refresh</button></div><div class="metricCards"><div class="metricBox"><small>LIVE</small><b id="adv-live">--</b></div><div class="metricBox"><small>HISTORICAL</small><b id="adv-hist">--</b></div><div class="metricBox"><small>PAPER</small><b id="adv-paper">--</b></div><div class="metricBox"><small>QUALITY</small><b id="adv-quality">--</b></div></div><div style="display:flex;gap:6px;margin-top:8px"><button class="glassBtn" onclick="runBacktest()">🧪 بک‌تست</button><button class="glassBtn" onclick="runWalkForward()">🔬 Walk-Forward</button></div><pre id="adv-result" class="preBox" style="margin-top:8px">آماده</pre></div><div class="panel"><div class="panelHead"><div><div class="panelTitle">🧠 Continuous Performance & Learning V32</div><div class="panelSub">تاریخچه واقعی بر اساس نتیجه آینده بازار، تفکیک ارز و تایم‌فریم</div></div><button class="glassBtn" onclick="refreshPerformanceLearning()">↻ بروزرسانی</button></div><div class="perfLearningGrid"><div class="perfLearnCard"><small>نمونه ثبت‌شده</small><b id="learnTotal">0</b></div><div class="perfLearnCard"><small>Win Rate جهت‌دار</small><b id="learnWR">—</b></div><div class="perfLearnCard"><small>در انتظار ارزیابی</small><b id="learnPending">0</b></div><div class="perfLearnCard"><small>WAIT از دست‌رفته</small><b id="learnWaitMiss">0</b></div></div><div style="overflow:auto;max-height:310px"><table class="perfLearnTable"><thead><tr><th>ارز/TF</th><th>تصمیم</th><th>نمونه</th><th>WR</th><th>Reliability</th><th>وضعیت</th></tr></thead><tbody id="learnTable"><tr><td colspan="6">در حال بارگذاری…</td></tr></tbody></table></div></div>
      </section>
    </main>
  </div>
</div>

<div class="legacyDashboard">

<div class="header"><div><h1>⚡ TITAN ENTERPRISE V10 PRO-GRADE</h1><div class="sub">Neural Synapse · Grade A+/A/B/C · Entry Ladder · DQ68 · AI Fusion · Ranked Signals</div></div><div style="display:flex;gap:8px"><a class="btn" href="/rescan">🔄 اسکن مجدد</a><button class="btn gold" onclick="openM()">⚙️ تنظیمات</button></div></div>

<div class="tabBar" id="mainTabs">
<button type="button" class="tabBtn active" data-tab="tab-market" onclick="switchTab('tab-market',this)">◈ بازار و سیگنال‌ها</button>
<button type="button" class="tabBtn" data-tab="tab-edge" onclick="switchTab('tab-edge',this)">🧠 Edge Suite</button>
<button type="button" class="tabBtn" data-tab="tab-ai" onclick="switchTab('tab-ai',this)">🤖 هوش مصنوعی</button>
<button type="button" class="tabBtn" data-tab="tab-perf" onclick="switchTab('tab-perf',this)">📊 عملکرد و دقت</button>
<button type="button" class="tabBtn" data-tab="tab-charts" onclick="switchTab('tab-charts',this)">📈 نمودارها</button>
<button type="button" class="tabBtn" data-tab="tab-control" onclick="switchTab('tab-control',this)">🛡️ کنترل پیشرفته</button>
</div>

<div class="tabPanel active" id="tab-market">
<div class="titanNavShell" id="coinNav">
  <div class="titanNavHead">
    <div class="navBrand">
      <span class="navBrandIcon">◈</span>
      <div><span class="titanNavTitle">ناوبری سریع دارایی‌ها</span><span class="titanNavSub">هر کارت = یک پنجره مستقل؛ اطلاعات کامل فقط داخل همان ارز</span></div>
    </div>
    <div class="titanNavFilters">
      <button type="button" class="glassFilter active" data-navfilter="all">◈ همه</button>
      <button type="button" class="glassFilter" data-navfilter="LONG">▲ LONG</button>
      <button type="button" class="glassFilter" data-navfilter="WAIT">◆ WAIT</button>
      <button type="button" class="glassFilter" data-navfilter="SHORT">▼ SHORT</button>
    </div>
  </div>
  <div class="navLegend">
    <span class="legendItem long">● LONG</span><span class="legendItem wait">● WAIT</span><span class="legendItem short">● SHORT</span>
    <span class="legendHint">← برای دیدن سایر ارزها افقی حرکت دهید →</span>
  </div>
  <div class="titanCoinRail" data-navgrid="ALL">
    {% for item in market_data %}
    {% set navtag = item.get('decision_tag') or item.get('edge', {}).get('decision_tag') or 'WAIT' %}
    {% set navcls = 'long' if navtag == 'LONG' else 'short' if navtag == 'SHORT' else 'wait' %}
    <button type="button" class="coinMiniCard coinHue{{ loop.index0 % 12 }} {{ navcls }}" data-decision="{{ navtag }}" data-jump="{{ item.tv_symbol }}" data-tv="{{ item.tv_symbol }}" data-symbol="{{ item.symbol }}" title="باز کردن پنجره تخصصی {{ item.coin_name }}">
      <span class="coinMiniGlow"></span>
      <span class="coinMiniTop">
        <span class="coinMiniIdentity">
          <span class="coinMiniIcon" aria-hidden="true">{{ item.coin_icon }}</span>
          <span class="coinMiniNameBlock">
            <b class="coinMiniSymbol">{{ item.base_symbol }}</b>
            <small class="coinMiniFullName">{{ item.coin_name }}</small>
            <em class="coinMiniPair">USDT · BINANCE</em>
          </span>
        </span>
        <span class="coinMiniDecision">{{ '▲ LONG' if navtag == 'LONG' else '▼ SHORT' if navtag == 'SHORT' else '◆ WAIT' }}</span>
      </span>
      <span class="coinMiniPriceLine">
        <span class="coinMiniPriceLabel">💰 قیمت زنده</span>
        <strong class="coinMiniPriceValue" data-live-price="{{ item.symbol }}">{{ item.price }}</strong>
        <span class="coinMiniPriceUnit">USDT</span>
        <span class="coinMiniScoreBadge">🎯 {{ item.score|default(0) }}/100</span>
        <i aria-hidden="true"><em style="width:{{ item.score|default(0) }}%"></em></i>
      </span>
      <span class="coinMiniTF">
        <span>15m<b>{{ item.tfs['15m'] }}</b></span><span>1h<b>{{ item.tfs['1h'] }}</b></span><span>4h<b>{{ item.tfs['4h'] }}</b></span><span>1D<b>{{ item.tfs['1d'] }}</b></span>
      </span>
      <span class="coinMiniOpen">⌁ جزئیات کامل</span>
    </button>
    {% endfor %}
  </div>
</div>
<div class="section hud"><h2>◈ MARKET COMMAND CENTER · V10</h2><div class="hudgrid"><div class="hudbox"><div>رژیم</div><div class="v" id="pulse-regime">--</div></div><div class="hudbox"><div>میانگین Score</div><div class="v" id="pulse-score">--</div></div><div class="hudbox"><div>Breadth</div><div class="v" id="pulse-breadth" style="font-size:15px">--</div></div><div class="hudbox"><div>بهترین کیفیت</div><div class="v" id="pulse-leader" style="font-size:15px">--</div></div></div><div id="pulse-time" style="text-align:left;color:#64748b;font-size:11px;margin-top:8px">--</div>
{% set board = (macro.get('signal_board') if macro else None) or {} %}