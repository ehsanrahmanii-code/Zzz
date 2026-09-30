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