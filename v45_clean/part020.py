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