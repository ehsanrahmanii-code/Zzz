}




/* Hide duplicate main tab row (sidebar already has nav) */
.mainTabs,#mainTabsNew{display:none!important;height:0!important;margin:0!important;padding:0!important;border:0!important;overflow:hidden!important}

/* Per-coin colorful borders (12 hues) */
.coinHue0{--coinAccent:#31d7ff;--coinGlow:rgba(49,215,255,.35)}
.coinHue1{--coinAccent:#a78bfa;--coinGlow:rgba(167,139,250,.35)}
.coinHue2{--coinAccent:#f472b6;--coinGlow:rgba(244,114,182,.35)}
.coinHue3{--coinAccent:#fbbf24;--coinGlow:rgba(251,191,36,.35)}
.coinHue4{--coinAccent:#34d399;--coinGlow:rgba(52,211,153,.35)}
.coinHue5{--coinAccent:#60a5fa;--coinGlow:rgba(96,165,250,.35)}
.coinHue6{--coinAccent:#fb7185;--coinGlow:rgba(251,113,133,.35)}
.coinHue7{--coinAccent:#2dd4bf;--coinGlow:rgba(45,212,191,.35)}
.coinHue8{--coinAccent:#c084fc;--coinGlow:rgba(192,132,252,.35)}
.coinHue9{--coinAccent:#f59e0b;--coinGlow:rgba(245,158,11,.35)}
.coinHue10{--coinAccent:#22d3ee;--coinGlow:rgba(34,211,238,.35)}
.coinHue11{--coinAccent:#e879f9;--coinGlow:rgba(232,121,249,.35)}

.ticker.coinHue0,.ticker.coinHue1,.ticker.coinHue2,.ticker.coinHue3,
.ticker.coinHue4,.ticker.coinHue5,.ticker.coinHue6,.ticker.coinHue7,
.ticker.coinHue8,.ticker.coinHue9,.ticker.coinHue10,.ticker.coinHue11,
.assetCard.coinHue0,.assetCard.coinHue1,.assetCard.coinHue2,.assetCard.coinHue3,
.assetCard.coinHue4,.assetCard.coinHue5,.assetCard.coinHue6,.assetCard.coinHue7,
.assetCard.coinHue8,.assetCard.coinHue9,.assetCard.coinHue10,.assetCard.coinHue11,
.coinMiniCard.coinHue0,.coinMiniCard.coinHue1,.coinMiniCard.coinHue2,.coinMiniCard.coinHue3,
.coinMiniCard.coinHue4,.coinMiniCard.coinHue5,.coinMiniCard.coinHue6,.coinMiniCard.coinHue7,
.coinMiniCard.coinHue8,.coinMiniCard.coinHue9,.coinMiniCard.coinHue10,.coinMiniCard.coinHue11{
  border:2px solid var(--coinAccent)!important;
  box-shadow:
    0 12px 28px rgba(0,0,0,.4),
    0 0 18px var(--coinGlow),
    inset 0 1px 0 rgba(255,255,255,.1)!important;
  background:
    radial-gradient(circle at 100% 0%, var(--coinGlow), transparent 42%),
    linear-gradient(160deg,#12304c 0%,#0c1f36 50%,#08131f 100%)!important;
}

/* LONG / SHORT override with strong green/red rings */
.ticker.up,.assetCard.long,.coinMiniCard.long{
  border-color:#23e6a8!important;
  box-shadow:0 12px 28px rgba(0,0,0,.42),0 0 22px rgba(35,230,168,.35),inset 0 0 20px rgba(35,230,168,.06)!important;
}
.ticker.down,.assetCard.short,.coinMiniCard.short{
  border-color:#ff4d73!important;
  box-shadow:0 12px 28px rgba(0,0,0,.42),0 0 22px rgba(255,77,115,.35),inset 0 0 20px rgba(255,77,115,.06)!important;
}

/* Signal ring around icon */
.tickerIcon.ringIcon,.assetIcon,.coinMiniIcon{
  position:relative!important;
  overflow:visible!important;
}
.tickerIcon.ringIcon .sigRing,
.assetCard .sigRing,
.coinMiniIcon .sigRing{
  position:absolute;inset:-4px;border-radius:50%;
  border:2px solid transparent;
  pointer-events:none;
}
.tickerIcon.up .sigRing,.ringIcon.up{
  box-shadow:0 0 0 2px rgba(35,230,168,.85),0 0 14px rgba(35,230,168,.45)!important;
  animation:ringPulseGreen 1.8s ease-in-out infinite;
}
.tickerIcon.down .sigRing,.ringIcon.down{
  box-shadow:0 0 0 2px rgba(255,77,115,.85),0 0 14px rgba(255,77,115,.45)!important;
  animation:ringPulseRed 1.8s ease-in-out infinite;
}
.tickerIcon.neutral{
  box-shadow:0 0 0 2px rgba(255,211,78,.55),0 0 10px rgba(255,211,78,.25)!important;
}
@keyframes ringPulseGreen{
  0%,100%{box-shadow:0 0 0 2px rgba(35,230,168,.7),0 0 10px rgba(35,230,168,.3)}
  50%{box-shadow:0 0 0 3px rgba(35,230,168,1),0 0 18px rgba(35,230,168,.55)}
}
@keyframes ringPulseRed{
  0%,100%{box-shadow:0 0 0 2px rgba(255,77,115,.7),0 0 10px rgba(255,77,115,.3)}
  50%{box-shadow:0 0 0 3px rgba(255,77,115,1),0 0 18px rgba(255,77,115,.55)}
}

.sigBadge.up{color:#7dffc8!important;background:rgba(16,185,129,.2)!important;border:1px solid rgba(45,245,180,.5)!important;padding:4px 7px!important;border-radius:99px!important}
.sigBadge.down{color:#ffb0c2!important;background:rgba(244,63,94,.2)!important;border:1px solid rgba(255,95,130,.5)!important;padding:4px 7px!important;border-radius:99px!important}
.sigBadge.neutral{color:#ffe9a3!important;background:rgba(251,191,36,.15)!important;border:1px solid rgba(255,211,78,.4)!important;padding:4px 7px!important;border-radius:99px!important}

.scoreChip{
  display:inline-flex!important;align-items:center!important;gap:5px!important;
  font-size:11px!important;font-weight:1000!important;color:#eaf7ff!important;
}
.scoreRingMini{
  width:16px;height:16px;border-radius:50%;
  background:conic-gradient(var(--coinAccent,#31d7ff) calc(var(--sc,0)*1%), rgba(255,255,255,.12) 0);
  box-shadow:0 0 8px var(--coinGlow,rgba(49,215,255,.3));
  display:inline-block;
}
.scoreChip.up .scoreRingMini{background:conic-gradient(#23e6a8 calc(var(--sc,0)*1%), rgba(255,255,255,.1) 0)}
.scoreChip.down .scoreRingMini{background:conic-gradient(#ff4d73 calc(var(--sc,0)*1%), rgba(255,255,255,.1) 0)}
.scoreChip.neutral .scoreRingMini{background:conic-gradient(#ffd34e calc(var(--sc,0)*1%), rgba(255,255,255,.1) 0)}

/* Ambient light orbs on panels */
.kpi,.signalBox,.hudbox,.panel{
  position:relative;overflow:hidden;
}
.kpi::before,.signalBox.long::after,.signalBox.short::after{
  content:"";position:absolute;width:80px;height:80px;border-radius:50%;
  filter:blur(28px);opacity:.35;pointer-events:none;z-index:0;
}
.kpi::before{top:-20px;right:-10px;background:rgba(49,215,255,.5)}
.signalBox.long::after{bottom:-15px;left:-10px;background:rgba(35,230,168,.55)}
.signalBox.short::after{bottom:-15px;left:-10px;background:rgba(255,77,115,.55)}
.signalBox.long{border:1.5px solid rgba(35,230,168,.45)!important;box-shadow:0 0 20px rgba(35,230,168,.15)!important}
.signalBox.short{border:1.5px solid rgba(255,77,115,.45)!important;box-shadow:0 0 20px rgba(255,77,115,.15)!important}
.signalBox.wait{border:1.5px solid rgba(255,211,78,.4)!important;box-shadow:0 0 16px rgba(255,211,78,.12)!important}

.topHeader{
  box-shadow:0 18px 50px rgba(0,0,0,.45),0 0 40px rgba(49,215,255,.08),inset 0 1px 0 rgba(255,255,255,.06)!important;
}
.brandMark{
  box-shadow:0 0 24px rgba(49,215,255,.35),inset 0 0 12px rgba(49,215,255,.15)!important;
  animation:brandGlow 3s ease-in-out infinite alternate;
}
@keyframes brandGlow{
  from{box-shadow:0 0 16px rgba(49,215,255,.25)}
  to{box-shadow:0 0 28px rgba(49,215,255,.5),0 0 40px rgba(167,139,250,.2)}
}
.dot{animation:dotBlink 2s ease-in-out infinite}
@keyframes dotBlink{0%,100%{opacity:1}50%{opacity:.55}}

.decisionPill.long{
  color:#9ff5d2!important;background:rgba(16,185,129,.25)!important;border:1px solid rgba(45,245,180,.55)!important;
  box-shadow:0 0 12px rgba(35,230,168,.25)!important;
}
.decisionPill.short{
  color:#ffb3c4!important;background:rgba(244,63,94,.25)!important;border:1px solid rgba(255,95,130,.55)!important;
  box-shadow:0 0 12px rgba(255,77,115,.25)!important;
}
.decisionPill.wait{
  color:#ffe9a3!important;background:rgba(251,191,36,.2)!important;border:1px solid rgba(255,211,78,.5)!important;
}


/* ===== HARD COLORED CARD BORDERS (final priority) ===== */
.ticker.coinHue0, .assetCard.coinHue0, .coinMiniCard.coinHue0,
button.ticker.coinHue0, button.assetCard.coinHue0, button.coinMiniCard.coinHue0{
  border: 0.32px solid #31d7ff !important;
  box-shadow: 0 0 0 1px rgba(49,215,255,.25), 0 8px 20px rgba(0,0,0,.4), 0 0 12px rgba(49,215,255,.3) !important;
}
.ticker.coinHue1, .assetCard.coinHue1, .coinMiniCard.coinHue1,
button.ticker.coinHue1, button.assetCard.coinHue1, button.coinMiniCard.coinHue1{
  border: 0.32px solid #a78bfa !important;
  box-shadow: 0 0 0 1px rgba(167,139,250,.25), 0 8px 20px rgba(0,0,0,.4), 0 0 12px rgba(167,139,250,.3) !important;
}
.ticker.coinHue2, .assetCard.coinHue2, .coinMiniCard.coinHue2,
button.ticker.coinHue2, button.assetCard.coinHue2, button.coinMiniCard.coinHue2{
  border: 0.32px solid #f472b6 !important;
  box-shadow: 0 0 0 1px rgba(244,114,182,.25), 0 8px 20px rgba(0,0,0,.4), 0 0 12px rgba(244,114,182,.3) !important;
}
.ticker.coinHue3, .assetCard.coinHue3, .coinMiniCard.coinHue3,
button.ticker.coinHue3, button.assetCard.coinHue3, button.coinMiniCard.coinHue3{
  border: 0.32px solid #fbbf24 !important;
  box-shadow: 0 0 0 1px rgba(251,191,36,.25), 0 8px 20px rgba(0,0,0,.4), 0 0 12px rgba(251,191,36,.3) !important;
}
.ticker.coinHue4, .assetCard.coinHue4, .coinMiniCard.coinHue4,
button.ticker.coinHue4, button.assetCard.coinHue4, button.coinMiniCard.coinHue4{
  border: 0.32px solid #34d399 !important;
  box-shadow: 0 0 0 1px rgba(52,211,153,.25), 0 8px 20px rgba(0,0,0,.4), 0 0 12px rgba(52,211,153,.3) !important;
}
.ticker.coinHue5, .assetCard.coinHue5, .coinMiniCard.coinHue5,
button.ticker.coinHue5, button.assetCard.coinHue5, button.coinMiniCard.coinHue5{
  border: 0.32px solid #60a5fa !important;
  box-shadow: 0 0 0 1px rgba(96,165,250,.25), 0 8px 20px rgba(0,0,0,.4), 0 0 12px rgba(96,165,250,.3) !important;
}
.ticker.coinHue6, .assetCard.coinHue6, .coinMiniCard.coinHue6,
button.ticker.coinHue6, button.assetCard.coinHue6, button.coinMiniCard.coinHue6{
  border: 0.32px solid #fb7185 !important;
  box-shadow: 0 0 0 1px rgba(251,113,133,.25), 0 8px 20px rgba(0,0,0,.4), 0 0 12px rgba(251,113,133,.3) !important;
}
.ticker.coinHue7, .assetCard.coinHue7, .coinMiniCard.coinHue7,
button.ticker.coinHue7, button.assetCard.coinHue7, button.coinMiniCard.coinHue7{
  border: 0.32px solid #2dd4bf !important;
  box-shadow: 0 0 0 1px rgba(45,212,191,.25), 0 8px 20px rgba(0,0,0,.4), 0 0 12px rgba(45,212,191,.3) !important;
}
.ticker.coinHue8, .assetCard.coinHue8, .coinMiniCard.coinHue8,
button.ticker.coinHue8, button.assetCard.coinHue8, button.coinMiniCard.coinHue8{
  border: 0.32px solid #c084fc !important;
  box-shadow: 0 0 0 1px rgba(192,132,252,.25), 0 8px 20px rgba(0,0,0,.4), 0 0 12px rgba(192,132,252,.3) !important;
}
.ticker.coinHue9, .assetCard.coinHue9, .coinMiniCard.coinHue9,
button.ticker.coinHue9, button.assetCard.coinHue9, button.coinMiniCard.coinHue9{
  border: 0.32px solid #f59e0b !important;
  box-shadow: 0 0 0 1px rgba(245,158,11,.25), 0 8px 20px rgba(0,0,0,.4), 0 0 12px rgba(245,158,11,.3) !important;
}
.ticker.coinHue10, .assetCard.coinHue10, .coinMiniCard.coinHue10,
button.ticker.coinHue10, button.assetCard.coinHue10, button.coinMiniCard.coinHue10{
  border: 0.32px solid #22d3ee !important;
  box-shadow: 0 0 0 1px rgba(34,211,238,.25), 0 8px 20px rgba(0,0,0,.4), 0 0 12px rgba(34,211,238,.3) !important;
}
.ticker.coinHue11, .assetCard.coinHue11, .coinMiniCard.coinHue11,
button.ticker.coinHue11, button.assetCard.coinHue11, button.coinMiniCard.coinHue11{
  border: 0.32px solid #e879f9 !important;
  box-shadow: 0 0 0 1px rgba(232,121,249,.25), 0 8px 20px rgba(0,0,0,.4), 0 0 12px rgba(232,121,249,.3) !important;
}

/* Signal still wins when directional */
.ticker.up, .assetCard.long, .coinMiniCard.long,
button.ticker.up, button.assetCard.long, button.coinMiniCard.long{
  border: 0.32px solid #23e6a8 !important;
  box-shadow: 0 0 0 1px rgba(35,230,168,.3), 0 8px 20px rgba(0,0,0,.42), 0 0 14px rgba(35,230,168,.4) !important;
}
.ticker.down, .assetCard.short, .coinMiniCard.short,
button.ticker.down, button.assetCard.short, button.coinMiniCard.short{
  border: 0.32px solid #ff4d73 !important;
  box-shadow: 0 0 0 1px rgba(255,77,115,.3), 0 8px 20px rgba(0,0,0,.42), 0 0 14px rgba(255,77,115,.4) !important;
}

/* Fallback: any card without hue still gets a cyan border so nothing is plain */
.ticker:not([class*="coinHue"]),
.assetCard:not([class*="coinHue"]),
.coinMiniCard:not([class*="coinHue"]){
  border: 2px solid rgba(72,203,255,.55) !important;
}


/* ===== LIGHT EFFECTS + THIN BORDERS + BUY/SELL RINGS ===== */
.ticker, .assetCard, .coinMiniCard, button.ticker, button.assetCard, button.coinMiniCard {
  border-width: 0.32px !important;
}

/* Soft ambient light sweep on panels */
.topHeader, .panel, .kpi, .signalBox, .hudbox, .section, .cdBanner, .detailVisualGroup {
  position: relative;
  overflow: hidden;
}
.topHeader::after, .panel::before, .section.hud::before {
  content: "";
  position: absolute;
  top: -40%;
  left: -20%;
  width: 60%;
  height: 180%;
  background: linear-gradient(115deg, transparent 0%, rgba(255,255,255,.04) 42%, rgba(49,215,255,.07) 50%, transparent 58%);
  pointer-events: none;
  animation: lightSweep 7s ease-in-out infinite;
  z-index: 0;
}
@keyframes lightSweep {
  0% { transform: translateX(-30%) rotate(8deg); opacity: .35; }
  50% { transform: translateX(80%) rotate(8deg); opacity: .7; }
  100% { transform: translateX(140%) rotate(8deg); opacity: .35; }
}

/* Neon light bars under headers */
.panelHead, .panelTitle, .section > h2, .brand h1 {
  position: relative;
}
.section > h2::after, .panelTitle::after {
  content: "";
  display: block;
  height: 2px;
  margin-top: 6px;
  width: 42%;
  border-radius: 99px;
  background: linear-gradient(90deg, #31d7ff, #a78bfa, transparent);
  box-shadow: 0 0 12px rgba(49,215,255,.45);
}

/* Glow orbs */
.kpi::after {
  content: "";
  position: absolute;
  width: 70px; height: 70px;
  right: -12px; bottom: -18px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(49,215,255,.28), transparent 70%);
  pointer-events: none;
  filter: blur(2px);
}
.signalBox.long::before, .signalBox.short::before, .signalBox.wait::before {
  content: "";
  position: absolute;
  inset: auto auto -20px -15px;
  width: 90px; height: 90px;
  border-radius: 50%;
  pointer-events: none;
  filter: blur(22px);
  opacity: .45;
}
.signalBox.long::before { background: #23e6a8; }
.signalBox.short::before { background: #ff4d73; }
.signalBox.wait::before { background: #ffd34e; }

.statusPill {
  box-shadow: 0 0 14px rgba(49,215,255,.08), inset 0 0 12px rgba(255,255,255,.03) !important;
}
.dot {
  box-shadow: 0 0 10px currentColor, 0 0 18px currentColor !important;
}
