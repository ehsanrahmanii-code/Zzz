/* Buy / Sell dual ring widget */
.bsFlowBox {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 14px;
  align-items: center;
  margin: 12px 0;
  padding: 14px;
  border-radius: 18px;
  background: linear-gradient(145deg, rgba(8,28,48,.95), rgba(5,14,26,.98));
  border: 0.32px solid rgba(72,203,255,.35);
  box-shadow: 0 0 24px rgba(49,215,255,.12), inset 0 0 30px rgba(255,255,255,.02);
  position: relative;
  overflow: hidden;
}
.bsFlowBox::before {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0; height: 1px;
  background: linear-gradient(90deg, transparent, rgba(49,215,255,.55), rgba(167,139,250,.4), transparent);
  box-shadow: 0 0 10px rgba(49,215,255,.4);
}
.bsDualRing {
  width: 88px; height: 88px;
  border-radius: 50%;
  position: relative;
  background: conic-gradient(#23e6a8 0 calc(var(--buy,50) * 1%), #ff4d73 0);
  box-shadow: 0 0 18px rgba(35,230,168,.25), 0 0 18px rgba(255,77,115,.18);
}
.bsDualRing::after {
  content: "";
  position: absolute;
  inset: 11px;
  border-radius: 50%;
  background: #07111c;
  box-shadow: inset 0 0 12px rgba(0,0,0,.5);
}
.bsDualRing .bsCenter {
  position: absolute;
  inset: 0;
  z-index: 2;
  display: grid;
  place-items: center;
  text-align: center;
  font-size: 10px;
  font-weight: 1000;
  color: #e8f6ff;
  line-height: 1.25;
}
.bsDualRing .bsCenter b { display: block; font-size: 13px; color: #7dffc8; }
.bsLegend { display: grid; gap: 8px; min-width: 0; }
.bsRow {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 8px 10px; border-radius: 12px;
  background: rgba(0,0,0,.28); border: 0.32px solid rgba(255,255,255,.08);
}
.bsRow.buy { border-color: rgba(35,230,168,.35); box-shadow: 0 0 12px rgba(35,230,168,.12); }
.bsRow.sell { border-color: rgba(255,77,115,.35); box-shadow: 0 0 12px rgba(255,77,115,.12); }
.bsRow span { font-size: 12px; font-weight: 900; color: #cfe6f5; }
.bsRow b.buyPct { color: #7dffc8; font-size: 15px; }
.bsRow b.sellPct { color: #ffb0c2; font-size: 15px; }
.bsBar {
  height: 6px; border-radius: 99px; margin-top: 8px;
  background: linear-gradient(90deg, #23e6a8 0 calc(var(--buy,50)*1%), #ff4d73 0);
  box-shadow: 0 0 12px rgba(35,230,168,.25);
}

/* Light edge on modal */
.detailModal .modalC {
  border: 0.32px solid rgba(72,203,255,.4) !important;
  box-shadow: 0 30px 90px rgba(0,0,0,.7), 0 0 40px rgba(49,215,255,.12) !important;
}
.cdBanner {
  box-shadow: inset 0 -1px 0 rgba(49,215,255,.15), 0 8px 24px rgba(0,0,0,.2) !important;
}
.cdBanner.long { box-shadow: inset 0 -1px 0 rgba(35,230,168,.35), 0 0 30px rgba(35,230,168,.1) !important; }
.cdBanner.bear { box-shadow: inset 0 -1px 0 rgba(255,77,115,.35), 0 0 30px rgba(255,77,115,.1) !important; }

.glassBtn, .sideBtn, .mainTab {
  box-shadow: 0 0 14px rgba(49,215,255,.08), inset 0 1px 0 rgba(255,255,255,.06) !important;
}


/* Realtime analysis bar */
.rtAnalysisBar{
  display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:10px;
  margin:0 0 12px;padding:11px 14px;border-radius:16px;
  background:linear-gradient(110deg,rgba(6,28,48,.95),rgba(8,18,36,.96));
  border:0.65px solid rgba(49,215,255,.35);
  box-shadow:0 0 24px rgba(49,215,255,.12), inset 0 0 20px rgba(255,255,255,.02);
  position:relative;overflow:hidden;
}
.rtAnalysisBar::before{
  content:"";position:absolute;top:0;left:0;right:0;height:1px;
  background:linear-gradient(90deg,transparent,#31d7ff,transparent);
  box-shadow:0 0 12px rgba(49,215,255,.5);
}
.rtLeft{display:flex;align-items:center;gap:8px;font-size:12px;font-weight:900;color:#d6eefc}
.rtLeft b{color:#fff}
.rtDot{width:9px;height:9px;border-radius:50%;background:#23e6a8;box-shadow:0 0 12px #23e6a8;animation:dotBlink 1.2s ease-in-out infinite}
.rtMid{font-size:12px;font-weight:1000;color:#cfe8f7}
.rtRight{font-size:11px;font-weight:800;color:#9ec5dc;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rtChip{display:inline-flex;align-items:center;gap:4px;padding:3px 8px;margin:0 3px;border-radius:99px;background:rgba(0,0,0,.28);border:0.65px solid rgba(255,255,255,.1)}
.rtChip.up{color:#7dffc8;border-color:rgba(35,230,168,.4)}
.rtChip.down{color:#ffb0c2;border-color:rgba(255,77,115,.4)}
.tickerPrice.flashUp{animation:flashUp .45s ease}
.tickerPrice.flashDown{animation:flashDown .45s ease}
@keyframes flashUp{from{color:#7dffc8;text-shadow:0 0 12px rgba(35,230,168,.6)}to{color:#fff;text-shadow:none}}
@keyframes flashDown{from{color:#ffb0c2;text-shadow:0 0 12px rgba(255,77,115,.6)}to{color:#fff;text-shadow:none}}


/* ===== TOP COIN CARDS: clear glass bg (no murky yellow) + signal under-name bar ===== */
/* Background only — borders left to existing hue rules */
.ticker,
button.ticker,
.assetCard,
button.assetCard,
.ticker.neutral,
button.ticker.neutral,
.ticker.up,
button.ticker.up,
.ticker.down,
button.ticker.down,
.assetCard.wait,
button.assetCard.wait,
.assetCard.long,
button.assetCard.long,
.assetCard.short,
button.assetCard.short,
.ticker.coinHue0, .ticker.coinHue1, .ticker.coinHue2, .ticker.coinHue3,
.ticker.coinHue4, .ticker.coinHue5, .ticker.coinHue6, .ticker.coinHue7,
.ticker.coinHue8, .ticker.coinHue9, .ticker.coinHue10, .ticker.coinHue11,
.assetCard.coinHue0, .assetCard.coinHue1, .assetCard.coinHue2, .assetCard.coinHue3,
.assetCard.coinHue4, .assetCard.coinHue5, .assetCard.coinHue6, .assetCard.coinHue7,
.assetCard.coinHue8, .assetCard.coinHue9, .assetCard.coinHue10, .assetCard.coinHue11 {
  background: rgba(6, 14, 26, 0.42) !important;
  background-image: linear-gradient(160deg, rgba(12, 28, 48, 0.38), rgba(5, 12, 22, 0.28)) !important;
  backdrop-filter: blur(10px) !important;
  -webkit-backdrop-filter: blur(10px) !important;
}

/* Remove gold fill on wait — keep only border color from previous rules */
.coinMiniCard.wait,
button.coinMiniCard.wait {
  background: rgba(6, 14, 26, 0.42) !important;
  background-image: linear-gradient(160deg, rgba(12, 28, 48, 0.38), rgba(5, 12, 22, 0.28)) !important;
}

/* Signal light bar under coin name */
.ticker .tickerCoin > span:last-child,
.assetCard .assetName,
.coinMiniCard .coinMiniNameBlock {
  position: relative !important;
  padding-bottom: 7px !important;
}
.ticker .tickerCoin > span:last-child::after,
.assetCard .assetName::after,
.coinMiniCard .coinMiniNameBlock::after {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 2px;
  border-radius: 99px;
  background: #ffd34e;
  box-shadow: 0 0 8px rgba(255, 211, 78, 0.75), 0 0 14px rgba(255, 211, 78, 0.35);
  opacity: 0.95;
}

/* WAIT = yellow bar (default above) */
.ticker.neutral .tickerCoin > span:last-child::after,
.assetCard.wait .assetName::after,
.coinMiniCard.wait .coinMiniNameBlock::after,
.ticker[data-decision="WAIT"] .tickerCoin > span:last-child::after {
  background: #ffd34e !important;
  box-shadow: 0 0 8px rgba(255, 211, 78, 0.8), 0 0 14px rgba(255, 211, 78, 0.4) !important;
}

/* LONG = green bar */
.ticker.up .tickerCoin > span:last-child::after,
.assetCard.long .assetName::after,
.coinMiniCard.long .coinMiniNameBlock::after,
.ticker[data-decision="LONG"] .tickerCoin > span:last-child::after {
  background: #23e6a8 !important;
  box-shadow: 0 0 8px rgba(35, 230, 168, 0.85), 0 0 14px rgba(35, 230, 168, 0.45) !important;
}

/* SHORT = red bar */
.ticker.down .tickerCoin > span:last-child::after,
.assetCard.short .assetName::after,
.coinMiniCard.short .coinMiniNameBlock::after,
.ticker[data-decision="SHORT"] .tickerCoin > span:last-child::after {
  background: #ff4d73 !important;
  box-shadow: 0 0 8px rgba(255, 77, 115, 0.85), 0 0 14px rgba(255, 77, 115, 0.45) !important;
}


/* TOP TICKER CARDS: transparent glass fill, keep colored border */
.tickerRail .ticker,
.tickerRail button.ticker,
button.ticker{
  background: rgba(6, 14, 26, 0.22) !important;
  background-image: none !important;
  backdrop-filter: blur(10px) saturate(1.15) !important;
  -webkit-backdrop-filter: blur(10px) saturate(1.15) !important;
}
/* Kill yellow/green/red muddy fills on top tickers only — border stays */
.tickerRail .ticker.up,
.tickerRail .ticker.down,
.tickerRail .ticker.neutral,
.tickerRail .ticker.coinHue0,
.tickerRail .ticker.coinHue1,
.tickerRail .ticker.coinHue2,
.tickerRail .ticker.coinHue3,
.tickerRail .ticker.coinHue4,
.tickerRail .ticker.coinHue5,
.tickerRail .ticker.coinHue6,
.tickerRail .ticker.coinHue7,
.tickerRail .ticker.coinHue8,
.tickerRail .ticker.coinHue9,
.tickerRail .ticker.coinHue10,
.tickerRail .ticker.coinHue11,
.tickerRail button.ticker.up,
.tickerRail button.ticker.down,
.tickerRail button.ticker.neutral{
  background: rgba(6, 14, 26, 0.22) !important;
  background-image: none !important;
}
/* Soften inner glow so it does not look yellow muddy */
.tickerRail .ticker,
.tickerRail button.ticker{
  box-shadow: 0 0 0 0.5px rgba(255,255,255,.06), 0 8px 18px rgba(0,0,0,.25) !important;
}
.tickerRail .ticker.coinHue0{ box-shadow: 0 0 0 0.32px #31d7ff, 0 0 10px rgba(49,215,255,.22), 0 8px 18px rgba(0,0,0,.25) !important; }
.tickerRail .ticker.coinHue1{ box-shadow: 0 0 0 0.32px #a78bfa, 0 0 10px rgba(167,139,250,.22), 0 8px 18px rgba(0,0,0,.25) !important; }
.tickerRail .ticker.coinHue2{ box-shadow: 0 0 0 0.32px #f472b6, 0 0 10px rgba(244,114,182,.22), 0 8px 18px rgba(0,0,0,.25) !important; }
.tickerRail .ticker.coinHue3{ box-shadow: 0 0 0 0.32px #fbbf24, 0 0 10px rgba(251,191,36,.2), 0 8px 18px rgba(0,0,0,.25) !important; }
.tickerRail .ticker.coinHue4{ box-shadow: 0 0 0 0.32px #34d399, 0 0 10px rgba(52,211,153,.22), 0 8px 18px rgba(0,0,0,.25) !important; }
.tickerRail .ticker.coinHue5{ box-shadow: 0 0 0 0.32px #60a5fa, 0 0 10px rgba(96,165,250,.22), 0 8px 18px rgba(0,0,0,.25) !important; }
.tickerRail .ticker.coinHue6{ box-shadow: 0 0 0 0.32px #fb7185, 0 0 10px rgba(251,113,133,.22), 0 8px 18px rgba(0,0,0,.25) !important; }
.tickerRail .ticker.coinHue7{ box-shadow: 0 0 0 0.32px #2dd4bf, 0 0 10px rgba(45,212,191,.22), 0 8px 18px rgba(0,0,0,.25) !important; }
.tickerRail .ticker.coinHue8{ box-shadow: 0 0 0 0.32px #c084fc, 0 0 10px rgba(192,132,252,.22), 0 8px 18px rgba(0,0,0,.25) !important; }
.tickerRail .ticker.coinHue9{ box-shadow: 0 0 0 0.32px #f59e0b, 0 0 10px rgba(245,158,11,.2), 0 8px 18px rgba(0,0,0,.25) !important; }
.tickerRail .ticker.coinHue10{ box-shadow: 0 0 0 0.32px #22d3ee, 0 0 10px rgba(34,211,238,.22), 0 8px 18px rgba(0,0,0,.25) !important; }
.tickerRail .ticker.coinHue11{ box-shadow: 0 0 0 0.32px #e879f9, 0 0 10px rgba(232,121,249,.22), 0 8px 18px rgba(0,0,0,.25) !important; }
.tickerRail .ticker.up{ box-shadow: 0 0 0 0.32px #23e6a8, 0 0 12px rgba(35,230,168,.28), 0 8px 18px rgba(0,0,0,.25) !important; border-color:#23e6a8!important; }
.tickerRail .ticker.down{ box-shadow: 0 0 0 0.32px #ff4d73, 0 0 12px rgba(255,77,115,.28), 0 8px 18px rgba(0,0,0,.25) !important; border-color:#ff4d73!important; }
.tickerRail .ticker.neutral{ box-shadow: 0 0 0 0.32px rgba(255,211,78,.7), 0 0 10px rgba(255,211,78,.2), 0 8px 18px rgba(0,0,0,.25) !important; }

/* Signal underline under coin name */
.tickerCoin span b{ position:relative; display:inline-block; }
.sigUnderline{
  display:block!important;
  width:100%;
  height:3px!important;
  margin-top:4px!important;
  border-radius:99px!important;
  background:rgba(255,211,78,.85)!important;
  box-shadow:0 0 8px rgba(255,211,78,.75), 0 0 14px rgba(255,211,78,.35)!important;
}
.sigUnderline.up{
  background:#23e6a8!important;
  box-shadow:0 0 8px rgba(35,230,168,.85), 0 0 14px rgba(35,230,168,.4)!important;
}
.sigUnderline.down{
  background:#ff4d73!important;
  box-shadow:0 0 8px rgba(255,77,115,.85), 0 0 14px rgba(255,77,115,.4)!important;
}
.sigUnderline.neutral{
  background:#ffd34e!important;
  box-shadow:0 0 8px rgba(255,211,78,.8), 0 0 14px rgba(255,211,78,.4)!important;
}

/* 30-60m leverage window panel */
.scalp30Box{
  margin:0 0 12px;padding:12px 14px;border-radius:16px;
  background:linear-gradient(120deg,rgba(8,24,44,.92),rgba(10,16,32,.95));
  border:0.65px solid rgba(167,139,250,.35);
  box-shadow:0 0 22px rgba(167,139,250,.12), inset 0 0 18px rgba(255,255,255,.02);
}
.scalp30Head{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px;margin-bottom:10px}
.scalp30Head b{color:#fff;font-size:13px}
.scalp30Head span{color:#9eb8cc;font-size:11px;font-weight:800}
.scalp30Grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px}
.scalpChip{
  padding:10px;border-radius:14px;background:rgba(0,0,0,.28);
  border:0.65px solid rgba(255,255,255,.1);min-width:0;
}
.scalpChip.long{border-color:rgba(35,230,168,.5);box-shadow:0 0 12px rgba(35,230,168,.15)}
.scalpChip.short{border-color:rgba(255,77,115,.5);box-shadow:0 0 12px rgba(255,77,115,.15)}
.scalpChip .s1{font-size:13px;font-weight:1000;color:#fff}
.scalpChip .s2{font-size:11px;font-weight:900;margin-top:3px}
.scalpChip .s2.long{color:#7dffc8}
.scalpChip .s2.short{color:#ffb0c2}
.scalpChip .s3{font-size:10px;color:#8fa7bb;margin-top:4px;font-weight:800;line-height:1.4}


/* No frame around coin LOGO only */
.tickerIcon, .tickerIcon.ringIcon, .assetIcon, .coinMiniIcon,