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
{% set counts = board.get('counts') or {} %}
{% set gsum = (macro.get('grade_summary') if macro else None) or {} %}
<div class="hudgrid" style="margin-top:12px">
<div class="hudbox"><div>قابل‌اقدام A+/A</div><div class="v" style="color:#4ade80">{{ counts.get('actionable', 0) }}</div></div>
<div class="hudbox"><div>واچ‌لیست B</div><div class="v" style="color:#38bdf8">{{ counts.get('watch', 0) }}</div></div>
<div class="hudbox"><div>LONG فعال</div><div class="v" style="color:#4ade80">{{ counts.get('long', 0) }}</div></div>
<div class="hudbox"><div>SHORT فعال</div><div class="v" style="color:#f43f5e">{{ counts.get('short', 0) }}</div></div>
</div>
<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;font-size:12px">
<span class="gradeBadge gradeAplus">A+ {{ gsum.get('A+', 0) }}</span>
<span class="gradeBadge gradeA">A {{ gsum.get('A', 0) }}</span>
<span class="gradeBadge gradeB">B {{ gsum.get('B', 0) }}</span>
<span class="gradeBadge gradeC">C {{ gsum.get('C', 0) }}</span>
<span class="gradeBadge gradeD">D {{ gsum.get('D', 0) }}</span>
<span class="gradeBadge gradeF">F {{ gsum.get('F', 0) }}</span>
</div>

</div>
<div class="grid">
{% for item in market_data %}<div class="card cardAnchor" id="card-{{ item.tv_symbol }}" data-symbol="{{ item.symbol }}" data-tv="{{ item.tv_symbol }}" data-name="{{ item.coin_name }}" data-icon="{{ item.coin_icon }}" data-base="{{ item.base_symbol }}" data-price="{{ item.price }}" data-entry="{{ item.entry_valid }}" data-sl="{{ item.stop_loss }}" data-tp1="{{ item.tp1 }}" data-tp2="{{ item.tp2 }}" data-bias="{{ item.bias }}" data-score="{{ item.score }}" data-align="{{ item.alignment }}" data-quality="{{ item.signal_quality }}" data-success="{{ item.success_probability|default(0) }}" data-decision="{{ item.get('decision_tag') or item.get('edge', {}).get('decision_tag') or 'WAIT' }}" data-tag="{{ item.signal_tag }}" data-color="{{ item.score_color }}" data-rsi="{{ item.rsi }}" data-rr1="{{ item.rr_tp1 }}" data-rr2="{{ item.rr_tp2 }}" data-oi="{{ item.coinglass_oi }}" data-fund="{{ item.coinglass_funding }}" data-buy="{% if item.get('buy_sell') %}{{ item.buy_sell.get('buy_pct', 50) }}{% else %}{{ item.get('taker_buy_pct', 50) }}{% endif %}" data-sell="{% if item.get('buy_sell') %}{{ item.buy_sell.get('sell_pct', 50) }}{% else %}{{ item.get('taker_sell_pct', 50) }}{% endif %}" data-tf15="{{ item.tfs['15m'] }}" data-tf1h="{{ item.tfs['1h'] }}" data-tf4h="{{ item.tfs['4h'] }}" data-tf1d="{{ item.tfs['1d'] }}"><div class="ch"><div class="coin"><div class="icon">{{ item.coin_icon }}</div><div><div class="name">{{ item.coin_name }}</div><div class="ticker">{{ item.base_symbol }} / USDT · BINANCE</div></div></div><div class="price" data-price>{{ item.price }} <small>USDT</small></div></div>
<div class="scoreRow" style="align-items:center">
<div style="display:flex;align-items:center;gap:10px">
<div class="ringGauge" style="--gv:{{ item.score }};--gcol:{{ item.score_color }};width:52px;height:52px;margin:0"><span style="color:{{ item.score_color }};font-size:12px">{{ item.score }}</span></div>
<div>
<span style="color:{{ item.score_color }};font-weight:900">{{ item.score_icon }} {{ item.score }}/100</span><br>
<small style="color:#94a3b8">همسویی {{ item.alignment }} · کیفیت {{ item.signal_quality }}</small>
</div>
</div>
{% set g = item.get('grade') or (item.get('signal_grade') or {}).get('grade') or '—' %}
<span class="gradeBadge {% if g=='A+' %}gradeAplus{% elif g=='A' %}gradeA{% elif g=='B' %}gradeB{% elif g=='C' %}gradeC{% elif g=='D' %}gradeD{% else %}gradeF{% endif %}">{{ g }}</span>
<span class="miniChip">{{ item.signal_tag }}</span>
<span class="miniChip">Trust {{ item.get('trust_index', (item.get('signal_grade') or {}).get('trust_index', '—')) }}</span>

</div>
<div class="bar"><i style="width:{{ item.score_bar }}%;background:{{ item.score_color }}"></i></div>
<div class="scoreOrbit" style="margin-top:6px">
<div class="orbitItem"><span class="perfEmoji">🧭</span><small>همسویی</small><b>{{ item.alignment }}</b></div>
<div class="orbitItem"><span class="perfEmoji">✨</span><small>کیفیت</small><b>{{ item.signal_quality }}</b></div>
<div class="orbitItem"><span class="perfEmoji">📐</span><small>RR1</small><b style="color:var(--green)">1:{{ item.rr_tp1 }}</b></div>
<div class="orbitItem"><span class="perfEmoji">🎯</span><small>RR2</small><b style="color:var(--green)">1:{{ item.rr_tp2 }}</b></div>
</div>
<div class="tf"><span>15m <b>{{ item.tfs['15m'] }}</b></span><span>1h <b>{{ item.tfs['1h'] }}</b></span><span>4h <b>{{ item.tfs['4h'] }}</b></span><span>1d <b>{{ item.tfs['1d'] }}</b></span></div>
{% set dtag = item.get('decision_tag') or item.get('edge', {}).get('decision_tag') or 'WAIT' %}
{% set fus = item.get('fusion') or item.get('titan_analysis', {}).get('fusion') or item.get('edge', {}).get('fusion') or {} %}
{% set sp = item.get('success_probability') or fus.get('success_probability') or 0 %}
<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-top:8px">
<span class="signalBadge {% if dtag == 'LONG' %}long{% elif dtag == 'SHORT' %}short{% else %}wait{% endif %}">
{% if dtag == 'LONG' %}▲ خرید{% elif dtag == 'SHORT' %}▼ فروش{% else %}◆ انتظار{% endif %}
· {{ item.bias }} · کیفیت {{ item.signal_quality }}
</span>
<span class="miniChip">تگ: {{ item.signal_tag }}</span>
<span class="miniChip" style="border-color:rgba(74,222,128,.4)">🎲 شانس {{ sp }}%</span>
{% if fus.get('ai_majority') %}
<span class="miniChip">🤖 AI: {{ fus.get('ai_majority') }}</span>
{% endif %}
</div>
{% if fus.get('explanation') %}
<div style="font-size:11px;color:#94a3b8;margin-top:6px;line-height:1.7">
{% for line in fus.get('explanation')[:3] %}• {{ line }}<br>{% endfor %}
</div>
{% endif %}
<div class="levels"><div class="level">🎯 Entry: <b>{{ item.entry_valid }}</b></div><div class="level">🛑 SL: <b style="color:var(--pink)">{{ item.stop_loss }}</b></div><div class="level">🟢 TP1: <b>{{ item.tp1 }}</b></div><div class="level">🚀 TP2: <b>{{ item.tp2 }}</b></div></div>
<div class="dualLevels">
<div class="dualBox longBox"><b style="color:var(--green)">سناریو Long</b><br>
ورود: {{ item.entry_valid }} · SL: {{ item.stop_loss if dtag != 'SHORT' else '—' }}<br>
TP1: {{ item.tp1 if dtag != 'SHORT' else '—' }} · TP2: {{ item.tp2 if dtag != 'SHORT' else '—' }}<br>
RR: 1:{{ item.rr_tp1 }} / 1:{{ item.rr_tp2 }}
</div>
<div class="dualBox shortBox"><b style="color:var(--pink)">سناریو Short</b><br>
{% if dtag == 'SHORT' %}
ورود: {{ item.entry_valid }} · SL: {{ item.stop_loss }}<br>
TP1: {{ item.tp1 }} · TP2: {{ item.tp2 }}<br>
RR: 1:{{ item.rr_tp1 }} / 1:{{ item.rr_tp2 }}
{% else %}
در صورت نزولی شدن: SL بالای مقاومت · TP زیر حمایت<br>
فقط با تأیید ساختار نزولی فعال می‌شود
{% endif %}
</div>
</div>
{% set tech = item.get('technical') or {} %}
{% set fib = tech.get('fibonacci') or {} %}
{% set bb = tech.get('bollinger') or {} %}
{% set tfscores = item.get('tf_scores') or {} %}
{% set bs = item.get('buy_sell') or {} %}
{% set whale = item.get('whale') or {} %}
{% set sent = item.get('sentiment') or {} %}
<div class="panelTech">
<b class="title">📐 فیبوناچی · حمایت و مقاومت · بولینگر</b>
<div style="font-size:11px;color:#94a3b8;line-height:1.7;margin-bottom:8px">
این پنل سطوح کلیدی قیمت را نشان می‌دهد. <b style="color:#cbd5e1">حمایت</b> ناحیه احتمالی توقف ریزش، <b style="color:#cbd5e1">مقاومت</b> ناحیه احتمالی توقف رشد است.
سطوح <b style="color:#cbd5e1">فیبوناچی</b> نقاط بازگشت احتمالی در اصلاح قیمت هستند (۰.۶۱۸ طلایی‌ترین سطح).
نوارهای <b style="color:#cbd5e1">بولینگر</b> محدوده نوسان را نشان می‌دهند؛ لمس باند بالا/پایین می‌تواند نشانه اشباع خرید/فروش باشد.
</div>
<div style="font-size:12px;line-height:1.9">
<div>حمایت: <b style="color:var(--green)">{{ tech.get('support','N/A') }}</b> · مقاومت: <b style="color:var(--pink)">{{ tech.get('resistance','N/A') }}</b></div>
<div>فیبو ۰.۲۳۶: <b>{{ fib.get('0.236','N/A') }}</b> · ۰.۳۸۲: <b>{{ fib.get('0.382','N/A') }}</b> · ۰.۵: <b>{{ fib.get('0.500','N/A') }}</b></div>
<div>فیبو ۰.۶۱۸: <b style="color:var(--gold)">{{ fib.get('0.618','N/A') }}</b> · ۰.۷۸۶: <b>{{ fib.get('0.786','N/A') }}</b></div>
<div>بولینگر بالا: <b>{{ bb.get('upper','N/A') }}</b> · میانه: <b>{{ bb.get('middle','N/A') }}</b> · پایین: <b>{{ bb.get('lower','N/A') }}</b></div>
{% set piv = item.get('pivots') or {} %}
{% if piv %}
<div style="margin-top:4px">پیوت: <b>{{ piv.get('pp','N/A') }}</b> · R1 {{ piv.get('r1','N/A') }} · S1 {{ piv.get('s1','N/A') }} · R2 {{ piv.get('r2','N/A') }} · S2 {{ piv.get('s2','N/A') }}</div>
{% endif %}
</div>
</div>
<div class="panelTech" style="border-color:rgba(56,189,248,.4)">
<b class="title" style="color:var(--cyan)">⏱ عقربه تایم‌فریم‌ها</b>
<div style="font-size:11px;color:#94a3b8;line-height:1.7;margin-bottom:8px">
امتیاز ۰ تا ۱۰۰ برای هر تایم‌فریم. <b style="color:var(--green)">بالای ۶۰</b> تمایل صعودی، <b style="color:var(--pink)">زیر ۴۰</b> تمایل نزولی، وسط خنثی.
همسویی چند تایم‌فریم (مثلاً ۱h و ۴h با هم) قدرت سیگنال را بیشتر می‌کند.
</div>
<div class="gaugeRow">
{% for tfname in ['15m','1h','4h','1d'] %}
{% set sc = tfscores.get(tfname, item.score) %}
<div class="gaugeBox"><small>{{ tfname }}</small><div class="gval" style="color:{% if sc|float >= 60 %}var(--green){% elif sc|float <= 40 %}var(--pink){% else %}var(--gold){% endif %}">{{ sc }}</div><div class="gaugeBar"><i style="width:{{ sc }}%"></i></div></div>
{% endfor %}
</div>
<button class="btn" style="margin-top:10px;width:100%" onclick="openTFWindow('{{ item.symbol }}')">نمایش جزئیات عقربه‌ها</button>
</div>
{% set macd = item.get('macd') or {} %}
{% set stoch = item.get('stoch_rsi') or {} %}
{% set sess = item.get('session') or {} %}
{% set obf = item.get('order_blocks_fvg') or {} %}
{% set bcorr = item.get('btc_correlation') or {} %}
{% set depth = item.get('depth') or {} %}
{% set cal = (item.get('fusion') or {}).get('probability_calibration') or {} %}
<div class="panelTech" style="border-color:rgba(251,191,36,.45)">
<b class="title" style="color:var(--gold)">📐 Order Block · FVG · همبستگی BTC · عمق بازار · کالیبراسیون</b>
<div style="font-size:11px;color:#94a3b8;line-height:1.75;margin-bottom:8px">
بلاک سفارش و FVG نواحی بالقوه تقاضا/عرضه هستند. فیلتر همبستگی BTC در نوسان بالا از سیگنال خلاف‌جهت بیت‌کوین روی آلت‌های هم‌بسته جلوگیری می‌کند.
عمق بازار فقط برای نمادهای نقدشونده (BTC/ETH/SOL/BNB/XRP) از WebSocket می‌آید. احتمال موفقیت با Platt+Isotonic روی paper trades کالیبره می‌شود.
</div>
<div class="miniGrid">
<div class="miniCard"><b style="color:#4ade80">نزدیک‌ترین Order Block</b><br>
{% if obf.get('nearest_ob') %}
{{ obf.nearest_ob.get('type') }} · {{ obf.nearest_ob.get('low') }}–{{ obf.nearest_ob.get('high') }}<br>
<span style="font-size:10px;color:#94a3b8">{{ (obf.nearest_ob.get('guide') or '')[:100] }}</span>
{% else %}یافت نشد{% endif %}
</div>
<div class="miniCard"><b style="color:#c084fc">نزدیک‌ترین FVG</b><br>
{% if obf.get('nearest_fvg') %}
{{ obf.nearest_fvg.get('type') }} · {{ obf.nearest_fvg.get('low') }}–{{ obf.nearest_fvg.get('high') }}<br>
<span style="font-size:10px;color:#94a3b8">{{ (obf.nearest_fvg.get('guide') or '')[:100] }}</span>
{% else %}یافت نشد{% endif %}
</div>
<div class="miniCard"><b style="color:#38bdf8">همبستگی با BTC</b><br>
corr: <b>{{ bcorr.get('corr', '—') }}</b> · {{ bcorr.get('corr_regime', bcorr.get('regime','—')) }}<br>
{% if bcorr.get('filter_applied') %}<span style="color:var(--pink)">فیلتر فعال: {{ bcorr.get('reason','') }}</span>{% else %}<span style="color:#94a3b8">{{ bcorr.get('reason','—') }}</span>{% endif %}
</div>
<div class="miniCard"><b style="color:#fbbf24">عمق بازار / احتمال</b><br>
{% if depth.get('available') %}
Bid {{ depth.get('bid') }} · Ask {{ depth.get('ask') }} · Spread {{ depth.get('spread_bps') }}bps<br>
Imbalance {{ depth.get('imbalance') }} · سن {{ depth.get('age_sec') }}s
{% else %}عمق فقط برای واچ‌لیست نقدشونده{% endif %}<br>
کالیبره: <b>{{ cal.get('calibrated', item.get('success_probability','—')) }}%</b>
<small>({{ cal.get('method','—') }} · n={{ cal.get('samples','—') }})</small>
</div>
</div>
</div>
<div class="panelTech" style="border-color:rgba(56,189,248,.4)">
<b class="title" style="color:var(--cyan)">⚙️ لایه فنی پیشرفته · MACD · StochRSI · جلسه</b>
<div style="font-size:11px;color:#94a3b8;line-height:1.7;margin-bottom:8px">
MACD و Stochastic RSI برای زمان‌بندی ورود؛ جلسه معاملاتی برای نقدینگی. نسبت لانگ/شورت ازدحام جمعیتی را نشان می‌دهد.
</div>
<div class="miniGrid">
<div class="miniCard"><b style="color:#38bdf8">MACD</b><br>
Hist: <b>{{ macd.get('hist', '—') }}</b> · Cross: <b>{{ macd.get('cross', '—') }}</b><br>
MACD: {{ macd.get('macd', '—') }} · Signal: {{ macd.get('signal', '—') }}
</div>
<div class="miniCard"><b style="color:#c084fc">Stoch RSI</b><br>
K: <b>{{ stoch.get('k', '—') }}</b> · D: <b>{{ stoch.get('d', '—') }}</b><br>
Zone: <b>{{ stoch.get('zone', '—') }}</b>
</div>
<div class="miniCard"><b style="color:#fbbf24">لانگ/شورت</b><br>
L/S: <b>{{ item.get('long_short_ratio', '—') }}</b><br>
Long% {{ item.get('long_ratio', '—') }} · Short% {{ item.get('short_ratio', '—') }}
</div>
<div class="miniCard"><b style="color:#4ade80">جلسه · Taker</b><br>
{{ sess.get('session', '—') }} (UTC {{ sess.get('hour_utc', '—') }})<br>
Taker Buy: <b>{{ item.get('taker_buy_pct', '—') }}%</b>
</div>
</div>
</div>
<div class="panelTech" style="border-color:rgba(74,222,128,.35)">
<b class="title" style="color:var(--green)">📊 فشار خرید / فروش · احساسات · نهنگ‌ها</b>
<div style="font-size:11px;color:#94a3b8;line-height:1.7;margin:4px 0 8px">
نوار خرید/فروش تقریبی از فشار حجم و موقعیت کندل است. <b style="color:#cbd5e1">احساسات</b> از RSI و Funding ساخته می‌شود.
<b style="color:#cbd5e1">نهنگ‌ها</b> از تغییر Open Interest و Funding خوانده می‌شوند: رشد OI با صعود = ورود پول، رشد OI با نزول = فشار فروش سنگین.
</div>
<div style="margin-top:6px;font-size:12px">خرید <b style="color:var(--green)">{{ bs.get('buy_pct',50) }}%</b> · فروش <b style="color:var(--pink)">{{ bs.get('sell_pct',50) }}%</b> · وضعیت: <b>{{ bs.get('bias','—') }}</b></div>
<div style="display:flex;gap:14px;align-items:center;justify-content:center;margin:10px 0;flex-wrap:wrap">
  <div style="text-align:center">
    <div class="ringGauge" style="--gv:{{ bs.get('buy_pct',50) }};--gcol:#4ade80;width:72px;height:72px;margin:0 auto"><span style="color:#4ade80;font-size:13px">{{ bs.get('buy_pct',50) }}%</span></div>
    <small style="color:#4ade80;font-weight:800">عقربه خرید</small>
  </div>
  <div style="text-align:center">
    <div class="ringGauge" style="--gv:{{ bs.get('sell_pct',50) }};--gcol:#f43f5e;width:72px;height:72px;margin:0 auto"><span style="color:#f43f5e;font-size:13px">{{ bs.get('sell_pct',50) }}%</span></div>
    <small style="color:#f43f5e;font-weight:800">عقربه فروش</small>
  </div>
  <div style="text-align:center;min-width:90px">
    <div style="font-size:22px;font-weight:900;color:{% if bs.get('buy_pct',50)|int >= 58 %}#4ade80{% elif bs.get('sell_pct',50)|int >= 58 %}#f43f5e{% else %}#fbbf24{% endif %}">
      {% if bs.get('buy_pct',50)|int >= 58 %}▲ خرید{% elif bs.get('sell_pct',50)|int >= 58 %}▼ فروش{% else %}◆ متعادل{% endif %}
    </div>
    <small style="color:#94a3b8">Taker {{ bs.get('taker_buy_pct', '—') }}% · ΔVol {{ bs.get('volume_delta_pct', '—') }}%</small>
  </div>
</div>
<div class="bsBar"><div class="buy" style="width:{{ bs.get('buy_pct',50) }}%"></div><div class="sell" style="width:{{ bs.get('sell_pct',50) }}%"></div></div>
<div class="miniGrid">
<div class="miniCard"><b style="color:var(--gold)">احساسات</b><div style="font-size:10px;color:#94a3b8;margin:2px 0 6px">خوانش کوتاه‌مدت هیجان بازار از RSI و فاندینگ</div>برچسب: <b>{{ sent.get('label','—') }}</b><br>RSI: {{ sent.get('rsi','—') }} · {{ sent.get('rsi_note','') }}<br>{{ sent.get('funding_note','') }}</div>
<div class="miniCard"><b style="color:#c084fc">رفتار نهنگ</b><div style="font-size:10px;color:#94a3b8;margin:2px 0 6px">تغییر موقعیت‌های بزرگ در فیوچرز (OI) و هزینه نگهداری</div><b>{{ whale.get('label','—') }}</b><br>OI: {{ whale.get('oi','N/A') }} · ΔOI: {{ whale.get('oi_delta',0) }}%<br>Funding: {{ whale.get('funding','N/A') }}</div>
</div>
</div>
<div class="deriv"><b style="color:var(--cyan)">📊 CoinGlass / مشتقات</b><div style="margin-top:4px">OI: <b>{{ item.coinglass_oi }}</b> · Funding: <b>{{ item.coinglass_funding }}</b></div><div class="metrics"><div class="mini"><small>نوسان</small><br><b>{{ item.volatility_pct }}%</b></div><div class="mini"><small>تا SL</small><br><b>{{ item.risk_distance_pct }}%</b></div><div class="mini"><small>RR1</small><br><b style="color:var(--green)">1:{{ item.rr_tp1 }}</b></div><div class="mini"><small>RR2</small><br><b style="color:var(--green)">1:{{ item.rr_tp2 }}</b></div></div><div style="font-size:11px;color:#94a3b8;margin-top:5px">وضعیت: <b style="color:var(--gold)">{{ item.signal_tag }}</b> · منبع: {{ item.derivatives_source }}</div></div>
<div class="ai"><div class="aiTitle">🧠 هوش مصنوعی متصل · هم‌جوشی تطبیقی</div>
{% set fus = item.get('titan_analysis', {}).get('fusion') or {} %}
{% if fus.get('explanation') %}
<div class="aiRow" style="border-color:rgba(56,189,248,.4);background:rgba(56,189,248,.08)">
<b style="color:#38bdf8">🔗 هم‌جوشی TITAN↔AI:</b>
{% for line in fus.get('explanation', [])[:4] %}{{ line }}{% if not loop.last %} · {% endif %}{% endfor %}
{% if fus.get('success_probability') %} · شانس موفقیت ≈ {{ fus.get('success_probability') }}%{% endif %}
{% set calx = fus.get('probability_calibration') or {} %}
{% if calx.get('honest_label') %}<div style="font-size:11px;color:#94a3b8;margin-top:4px">{{ calx.get('honest_label') }}</div>{% endif %}
{% set ladder = item.get('entry_ladder') or fus.get('entry_ladder') or {} %}
{% set dq = item.get('data_quality') or fus.get('data_quality') or {} %}
{% set gates = item.get('confidence_gates') or {} %}
<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:6px">
  <span class="miniChip">نسخه {{ item.get('param_version', 'V9') }}</span>
  <span class="miniChip">DQ {{ dq.get('score', '—') }}{% if gates.get('dq_veto') %} · وتو{% endif %}</span>
  <span class="miniChip">Ladder {% if ladder.get('passed') %}✓{% else %}×{% endif %} · HTF {{ ladder.get('htf_score','—') }} / MTF {{ ladder.get('mtf_score','—') }}</span>
  {% set mv = item.get('meta_v8') or fus.get('meta_v8') or {} %}
  <span class="miniChip">Meta {{ mv.get('label', '—') }} · {{ mv.get('probability', '—') }}</span>
  {% set nv = item.get('neural_v9') or fus.get('neural_v9') or {} %}
  <span class="miniChip">Neural {{ nv.get('side', '—') }} · {{ nv.get('neural_score', '—') }} · conf {{ nv.get('confidence', '—') }}</span>
  {% set sg = item.get('signal_grade') or {} %}
  <span class="miniChip">درجه {{ sg.get('grade', item.get('grade','—')) }} · {{ sg.get('label_fa', item.get('grade_label','—')) }}</span>
  <span class="miniChip">{{ sg.get('action', item.get('grade_action','—')) }}</span>
  {% set fa = item.get('forecast_accuracy') or fus.get('forecast_accuracy') or {} %}
  <span class="miniChip">PathAcc {{ fa.get('dir_acc', '—') }} · n={{ fa.get('samples', 0) }}</span>
</div>
{% set checks = (item.get('grade_checklist') or (item.get('signal_grade') or {}).get('checklist') or []) %}
{% if checks %}
<div class="chkGrid">
{% for c in checks %}
<div class="chkItem {% if c.get('ok') %}chkOk{% else %}chkFail{% endif %}">{% if c.get('ok') %}✓{% else %}×{% endif %} {{ c.get('name','') }} <span style="opacity:.7">{{ c.get('detail','') }}</span></div>
{% endfor %}
</div>
{% endif %}
</div>
{% endif %}
<div class="aiRow"><b>TITAN:</b> {{ item.ai_opinions.internal }}</div><div class="aiRow" style="border-color:rgba(66,133,244,.55);background:linear-gradient(135deg,rgba(66,133,244,.11),rgba(15,23,42,.34))"><b style="color:#60a5fa">🤖 Gemini:</b> {% if item.ai_opinions.get('gemini') %}{{ item.ai_opinions.get('gemini') }}{% else %}<span style="color:#94a3b8">{{ item.ai_opinions.ai_status.get('gemini','در انتظار تحلیل') }}</span>{% endif %}</div>{% for provider,label in [('openai','ChatGPT'),('grok','Grok'),('claude','Claude'),('deepseek','DeepSeek')] %}{% if item.ai_opinions.ai_status.get(provider)=='تحلیل آماده' and item.ai_opinions.get(provider) %}<div class="aiRow"><b>{{ label }}:</b> {{ item.ai_opinions.get(provider) }}</div>{% endif %}{% endfor %}</div>
<div class="tv-wrap" data-symbol="{{ item.symbol }}" data-tv="{{ item.tv_symbol }}" style="width:100%;margin-top:10px">
  <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px;align-items:center">
    <span class="miniChip">RSI: <b>{{ item.rsi }}</b></span>
    <span class="miniChip">MACD Hist: <b>{{ (item.macd or {}).get('hist', item.get('macd_hist','—')) }}</b></span>
    <span class="miniChip">MACD Cross: <b>{{ (item.macd or {}).get('cross', item.get('macd_cross','—')) }}</b></span>
    <button type="button" class="btn" style="padding:6px 10px;font-size:11px" onclick="reloadTV('{{ item.tv_symbol }}')">🔄 بارگذاری TradingView</button>
    <button type="button" class="btn gold" style="padding:6px 10px;font-size:11px" onclick="openPatternPanel('{{ item.symbol }}','{{ item.tv_symbol }}')">🔮 پیش‌بینی کندل و الگوها</button>
  </div>
  <div class="tv" id="tv-{{ item.tv_symbol }}" style="width:100%;height:360px;min-height:360px;display:block;position:relative;background:#0b1220;border:1px solid rgba(56,189,248,.25);border-radius:12px;overflow:hidden"></div>
  <iframe class="tv-iframe" id="tvif-{{ item.tv_symbol }}" data-symbol="{{ item.tv_symbol }}" style="display:none;width:100%;height:360px;border:1px solid rgba(56,189,248,.25);border-radius:12px;background:#0b1220" loading="lazy" allowtransparency="true" frameborder="0"></iframe>
  <canvas class="tv-fallback" id="cv-{{ item.tv_symbol }}" width="800" height="320" style="display:none;width:100%;height:320px;background:#0b1220;border:1px solid rgba(56,189,248,.25);border-radius:12px"></canvas>
  <div class="tv-status" style="font-size:11px;color:#94a3b8;margin-top:6px">در حال آماده‌سازی نمودار…</div>
</div>

{% set pats = (item.get('patterns') or {}).get('patterns') or [] %}
{% set fc = item.get('candle_forecast') or {} %}
<div class="panelTech patternPanel" id="pattern-{{ item.tv_symbol }}" style="border-color:rgba(192,132,252,.5);margin-top:12px">
  <b class="title" style="color:#c084fc">🔮 پیش‌بینی کندل آینده · تشخیص الگو · راهنما</b>
  <div style="font-size:11px;color:#94a3b8;line-height:1.75;margin:6px 0 10px">
    این بخش از تاریخچه بازده، شباهت الگویی، MACD/RSI و ساختار بازار ساخته می‌شود. <b style="color:#fbbf24">تضمین سود نیست</b> — سناریوی احتمالی برای تصمیم‌گیری آگاهانه است.
  </div>
  <div class="miniGrid">
    <div class="miniCard">
      <b style="color:#38bdf8">سناریوی کلی پیش‌بینی</b><br>
      تمایل: <b style="color:{% if fc.get('overall_bias')=='صعودی' %}var(--green){% elif fc.get('overall_bias')=='نزولی' %}var(--pink){% else %}var(--gold){% endif %}">{{ fc.get('overall_bias','—') }}</b><br>
      افق: {{ fc.get('horizon', 12) }} کندل · قیمت مبنا: {{ fc.get('last_price', item.price) }}
    </div>
    <div class="miniCard">
      <b style="color:#c084fc">الگوی اصلی</b><br>
      {% if (item.get('patterns') or {}).get('primary') %}
      <b>{{ (item.get('patterns').get('primary') or {}).get('id','—') }}</b>
      · اطمینان {{ (item.get('patterns').get('primary') or {}).get('confidence','—') }}%<br>
      <span style="color:#94a3b8;font-size:10px">{{ ((item.get('patterns').get('primary') or {}).get('guide') or {}).get('meaning','')[:90] }}</span>
      {% else %}
      الگوی استاندارد قوی تشخیص داده نشد
      {% endif %}
    </div>
  </div>
  {% if pats %}
  <div style="margin-top:10px">
    {% for p in pats[:4] %}
    <div style="padding:10px;margin:6px 0;border-radius:12px;background:rgba(0,0,0,.28);border:1px solid rgba(255,255,255,.08);font-size:12px;line-height:1.8">
      <b style="color:#e2e8f0">{{ p.get('id') }}</b>
      <span class="miniChip">اطمینان {{ p.get('confidence') }}%</span>
      <span class="miniChip">سوگیری: {{ (p.get('guide') or {}).get('bias','—') }}</span>
      <div style="color:#94a3b8;margin-top:4px"><b style="color:#7dd3fc">یعنی چه؟</b> {{ (p.get('guide') or {}).get('meaning','') }}</div>
      <div style="color:#cbd5e1"><b style="color:#fbbf24">چه انتظاری؟</b> {{ (p.get('guide') or {}).get('expect','') }}</div>
    </div>
    {% endfor %}
  </div>
  {% endif %}
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