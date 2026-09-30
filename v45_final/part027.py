  .cdFullDetails .gaugeRow>*{min-width:0!important}
  .cdFullDetails table{font-size:10px!important}
  .cdFullDetails table th,.cdFullDetails table td{padding:8px 5px!important}
  .cdFullDetails .miniChip,.cdFullDetails .signalBadge{font-size:10px!important;padding:7px 9px!important}
  .cdFullDetails .gradeBadge{font-size:12px!important;padding:6px 9px!important}
}
@media(max-width:380px){
  .titanCoinRail{grid-template-columns:1fr 1fr!important}
  .coinMiniCard{min-height:150px!important;padding:10px!important}
  .coinMiniIcon{width:46px!important;height:46px!important;min-width:46px!important;font-size:27px!important}
  .coinMiniIdentity b{font-size:15px!important}
  .coinMiniIdentity small{font-size:10px!important;max-width:82px}
  .coinMiniPriceLine strong{font-size:17px!important}
  .cdFullDetails .coin .icon{width:50px!important;height:50px!important;font-size:28px!important}
  .cdFullDetails .coin .name{font-size:16px!important}
}


/* V27.2 MOBILE CLARITY + GRAPHICAL DETAILS */
@media(max-width:600px){
  .titanCoinRail{grid-template-columns:1fr 1fr!important;gap:11px!important}
  .coinMiniCard{color:#f7fbff!important;min-height:176px!important;padding:13px!important;background:linear-gradient(145deg,#102a43 0%,#081a2e 52%,#050e1c 100%)!important;border:2px solid rgba(72,203,255,.42)!important;border-radius:20px!important;box-shadow:0 14px 34px rgba(0,0,0,.38),inset 0 1px 0 rgba(255,255,255,.12)!important}
  .coinMiniCard.long{background:linear-gradient(145deg,#073e35 0%,#082a2c 52%,#061421 100%)!important;border-color:rgba(42,245,177,.78)!important}
  .coinMiniCard.wait{background:linear-gradient(145deg,#493b09 0%,#29250e 52%,#101622 100%)!important;border-color:rgba(255,214,74,.82)!important}
  .coinMiniCard.short{background:linear-gradient(145deg,#4a102c 0%,#2c1229 52%,#101421 100%)!important;border-color:rgba(255,91,125,.82)!important}
  .coinMiniTop{display:flex!important;justify-content:space-between!important;align-items:flex-start!important;gap:7px!important}
  .coinMiniIdentity{display:flex!important;align-items:center!important;gap:10px!important;min-width:0!important}
  .coinMiniIcon{width:56px!important;height:56px!important;min-width:56px!important;display:grid!important;place-items:center!important;border-radius:17px!important;font-size:31px!important;color:#fff!important;background:radial-gradient(circle at 30% 25%,rgba(255,255,255,.30),rgba(49,215,255,.10) 45%,rgba(0,0,0,.18) 100%)!important;border:2px solid rgba(255,255,255,.18)!important;box-shadow:0 0 24px rgba(49,215,255,.22)!important}
  .coinMiniIdentity b{display:block!important;color:#fff!important;font-size:19px!important;font-weight:1000!important;line-height:1.05!important;text-shadow:0 2px 12px rgba(0,0,0,.55)!important}
  .coinMiniIdentity small{display:block!important;color:#d4e7f6!important;font-size:11px!important;font-weight:800!important;margin-top:5px!important;max-width:105px!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}
  .coinMiniDecision{flex:0 0 auto!important;font-size:11px!important;font-weight:1000!important;padding:8px 9px!important;border-radius:11px!important;background:rgba(0,0,0,.32)!important;border:1.5px solid currentColor!important}
  .coinMiniPriceLine{display:grid!important;grid-template-columns:1fr auto!important;align-items:center!important;gap:3px 8px!important;margin-top:12px!important;padding:9px 10px!important;border-radius:14px!important;background:rgba(0,0,0,.28)!important;border:1px solid rgba(255,255,255,.12)!important}
  .coinMiniPriceLabel{color:#b9d3e6!important;font-size:10px!important;font-weight:900!important;grid-column:1!important}
  .coinMiniPriceValue{grid-column:1!important;color:#fff!important;font-size:21px!important;font-weight:1000!important;line-height:1.05!important;white-space:nowrap!important;text-shadow:0 2px 14px rgba(49,215,255,.30)!important}
  .coinMiniPriceValue small{font-size:9px!important;color:#9fc1d8!important}
  .coinMiniScoreBadge{grid-column:2!important;grid-row:1 / span 2!important;align-self:center!important;padding:7px 8px!important;border-radius:11px!important;background:rgba(49,215,255,.13)!important;border:1px solid rgba(49,215,255,.28)!important;color:#e5fbff!important;font-size:10px!important;font-weight:1000!important}
  .coinMiniPriceLine>i{grid-column:1 / -1!important;width:100%!important;height:9px!important;margin:3px 0 0!important;background:#071522!important;border:1px solid rgba(255,255,255,.10)!important;border-radius:99px!important;overflow:hidden!important}
  .coinMiniPriceLine>i em{display:block!important;height:100%!important;border-radius:99px!important;background:linear-gradient(90deg,#22d3ee,#8b5cf6,#34d399)!important}
  .coinMiniTF{margin-top:9px!important;display:grid!important;grid-template-columns:repeat(4,1fr)!important;gap:4px!important}
  .coinMiniTF span{padding:5px 2px!important;text-align:center!important;border-radius:9px!important;background:rgba(255,255,255,.075)!important;border:1px solid rgba(255,255,255,.11)!important;color:#c3d8e7!important;font-size:9px!important;font-weight:800!important}
  .coinMiniTF b{display:block!important;color:#fff!important;font-size:11px!important;font-weight:1000!important;margin-top:2px!important}
  .coinMiniOpen{display:block!important;margin-top:9px!important;padding:8px!important;text-align:center!important;border-radius:10px!important;background:linear-gradient(90deg,rgba(49,215,255,.15),rgba(139,92,246,.13))!important;border:1px solid rgba(49,215,255,.30)!important;color:#e2fbff!important;font-size:11px!important;font-weight:1000!important}
  .cdFullDetails{font-size:12px!important;color:#d9e8f4!important;line-height:1.85!important}
  .cdFullDetails>.card{padding:12px!important;border-radius:20px!important;background:linear-gradient(145deg,#0b2035,#06111f)!important;border:1px solid rgba(49,215,255,.28)!important;box-shadow:0 12px 35px rgba(0,0,0,.30)!important}
  .cdFullDetails .ch{padding:13px!important;border-radius:16px!important;background:linear-gradient(135deg,rgba(49,215,255,.15),rgba(139,92,246,.12),rgba(35,230,168,.08))!important;border:1px solid rgba(49,215,255,.28)!important}
  .cdFullDetails .coin .icon{width:62px!important;height:62px!important;font-size:34px!important;border-radius:18px!important;color:#fff!important;background:radial-gradient(circle at 30% 25%,rgba(255,255,255,.28),rgba(49,215,255,.08) 50%,rgba(0,0,0,.20))!important;border:2px solid rgba(255,255,255,.16)!important;box-shadow:0 0 28px rgba(49,215,255,.20)!important}
  .cdFullDetails .coin .name{font-size:20px!important;color:#fff!important;font-weight:1000!important}.cdFullDetails .coin .ticker{font-size:11px!important;color:#b7d0e2!important;font-weight:800!important}.cdFullDetails .price{font-size:22px!important;color:#fff!important;font-weight:1000!important}.cdFullDetails .price small{font-size:10px!important;color:#a6c4d8!important}
  .cdFullDetails .scoreRow{padding:13px!important;border-radius:16px!important;background:linear-gradient(145deg,rgba(49,215,255,.09),rgba(139,92,246,.07))!important;border:1px solid rgba(255,255,255,.12)!important}
  .cdFullDetails .orbitItem,.cdFullDetails .level,.cdFullDetails .miniCard,.cdFullDetails .gaugeBox{background:linear-gradient(145deg,rgba(255,255,255,.075),rgba(255,255,255,.025))!important;border:1px solid rgba(255,255,255,.10)!important;border-radius:14px!important;box-shadow:0 7px 18px rgba(0,0,0,.18)!important}
  .cdFullDetails .orbitItem b,.cdFullDetails .level b,.cdFullDetails .miniCard b{color:#fff!important;font-weight:1000!important}.cdFullDetails .orbitItem small,.cdFullDetails .level,.cdFullDetails .miniCard{color:#b9cfe0!important}
  .cdFullDetails .bar{height:10px!important;background:#081a2a!important;border:1px solid rgba(255,255,255,.08)!important}.cdFullDetails .tf span{padding:10px 4px!important;border-radius:12px!important;background:linear-gradient(145deg,rgba(49,215,255,.11),rgba(139,92,246,.07))!important;border:1px solid rgba(49,215,255,.18)!important;color:#c9dfec!important;font-weight:900!important}.cdFullDetails .tf b{color:#fff!important;font-size:13px!important}
  .cdFullDetails .dualLevels{display:grid!important;grid-template-columns:1fr!important;gap:10px!important}.cdFullDetails .dualBox{padding:14px!important;border-radius:16px!important;font-size:12px!important;background:linear-gradient(145deg,rgba(255,255,255,.06),rgba(255,255,255,.02))!important;border:1px solid rgba(255,255,255,.10)!important}.cdFullDetails .longBox{border-color:rgba(74,222,128,.35)!important;background:linear-gradient(145deg,rgba(74,222,128,.10),rgba(255,255,255,.02))!important}.cdFullDetails .shortBox{border-color:rgba(248,113,113,.35)!important;background:linear-gradient(145deg,rgba(248,113,113,.10),rgba(255,255,255,.02))!important}
  .cdFullDetails .panelTech{margin-top:11px!important;padding:14px!important;border-radius:17px!important;background:linear-gradient(145deg,rgba(7,31,50,.96),rgba(5,14,26,.98))!important;border:1px solid rgba(49,215,255,.20)!important;box-shadow:0 9px 22px rgba(0,0,0,.20)!important}.cdFullDetails .panelTech .title{font-size:14px!important;color:#e9fbff!important;font-weight:1000!important}.cdFullDetails .miniGrid{display:grid!important;grid-template-columns:1fr 1fr!important;gap:8px!important}.cdFullDetails .miniGrid>.miniCard{padding:11px!important;min-width:0!important}.cdFullDetails table{font-size:11px!important;color:#d6e7f3!important}.cdFullDetails table th{color:#8eddf3!important;background:rgba(49,215,255,.07)!important}.cdFullDetails table td{color:#d6e7f3!important;border-color:rgba(255,255,255,.08)!important}
}
@media(max-width:380px){.coinMiniCard{min-height:166px!important;padding:10px!important}.coinMiniIcon{width:48px!important;height:48px!important;min-width:48px!important;font-size:27px!important}.coinMiniIdentity b{font-size:16px!important}.coinMiniPriceValue{font-size:18px!important}.coinMiniScoreBadge{font-size:9px!important;padding:6px!important}.cdFullDetails .miniGrid{grid-template-columns:1fr!important}}


@media(max-width:600px){.detailVisualLegacy{display:grid!important;gap:10px!important;margin-top:10px!important}.detailVisualGroup{padding:11px!important;border-radius:18px!important;background:linear-gradient(145deg,rgba(9,29,48,.96),rgba(5,14,26,.98))!important;border:1px solid rgba(49,215,255,.18)!important;box-shadow:0 10px 24px rgba(0,0,0,.20)!important}.detailVisualGroupTitle{display:flex!important;align-items:center!important;gap:7px!important;margin-bottom:9px!important;padding:9px 10px!important;border-radius:12px!important;background:linear-gradient(90deg,rgba(49,215,255,.13),rgba(139,92,246,.08))!important;border:1px solid rgba(49,215,255,.15)!important;color:#e8fbff!important;font-size:13px!important;font-weight:1000!important}.detailVisualGroup .panelTech{margin-top:7px!important}}




/* V27.4 card header boost */

.card .ch .name,.card .coin .name{font-size:17px!important;font-weight:1000!important;color:#fff!important;-webkit-text-fill-color:#fff!important;text-shadow:0 1px 8px rgba(0,0,0,.4)!important}
.card .ch .price,.card .price{font-size:20px!important;font-weight:1000!important;color:#fff!important;-webkit-text-fill-color:#fff!important}
.card .icon,.card .coin .icon{width:52px!important;height:52px!important;font-size:28px!important;display:grid!important;place-items:center!important;border-radius:16px!important;background:radial-gradient(circle at 30% 25%,rgba(255,255,255,.28),rgba(49,215,255,.12) 45%,rgba(0,0,0,.2))!important;border:2px solid rgba(255,255,255,.2)!important}
.assetName b{font-size:16px!important;font-weight:1000!important;color:#fff!important}
.assetPrice b{font-size:16px!important;font-weight:1000!important;color:#fff!important}
.assetIcon{font-size:26px!important}


/* ===== ADVANCED WEB DASHBOARD SHELL V28 ===== */

/* V28.4 Active Signals Hero — impossible to miss */
.activeHero{
  margin:10px 0 14px;padding:14px 16px;border-radius:18px;
  border:2px solid rgba(45,245,180,.45);
  background:linear-gradient(120deg,rgba(16,185,129,.18),rgba(8,28,48,.96) 40%,rgba(239,68,68,.12));
  box-shadow:0 0 40px rgba(35,230,168,.15),0 14px 36px rgba(0,0,0,.35);
}
.activeHero.empty{border-color:rgba(255,211,78,.35);background:linear-gradient(120deg,rgba(255,211,78,.1),rgba(8,28,48,.96))}
.activeHeroHead{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:10px;flex-wrap:wrap}
.activeHeroHead h3{margin:0;font-size:15px;font-weight:1000;color:#eafff6;letter-spacing:.3px}
.activeHeroHead .ahCount{font-size:12px;font-weight:950;padding:6px 12px;border-radius:99px;background:rgba(0,0,0,.35);border:1px solid rgba(255,255,255,.12);color:#7dd3fc}
.activeHeroGrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px}
.ahCard{display:flex;flex-direction:column;gap:4px;padding:12px;border-radius:14px;border:1px solid rgba(255,255,255,.1);background:rgba(0,0,0,.28);cursor:pointer;transition:.15s;text-align:right;color:inherit;width:100%}
.ahCard:hover{transform:translateY(-2px);box-shadow:0 10px 24px rgba(0,0,0,.35)}
.ahCard.long{border-color:rgba(35,230,168,.5);background:linear-gradient(160deg,rgba(35,230,168,.2),rgba(0,0,0,.25));box-shadow:inset 0 0 0 1px rgba(35,230,168,.15)}
.ahCard.short{border-color:rgba(255,77,115,.5);background:linear-gradient(160deg,rgba(255,77,115,.2),rgba(0,0,0,.25));box-shadow:inset 0 0 0 1px rgba(255,77,115,.15)}
.ahCard .ahTop{display:flex;justify-content:space-between;align-items:center}
.ahCard .ahTop b{font-size:14px;color:#fff;font-weight:1000}
.ahCard .ahSide{font-size:11px;font-weight:1000;padding:4px 8px;border-radius:99px}
.ahCard.long .ahSide{color:#23e6a8;background:rgba(35,230,168,.15)}
.ahCard.short .ahSide{color:#ff4d73;background:rgba(255,77,115,.15)}
.ahCard .ahMeta{font-size:10px;color:#9fb6c9;font-weight:800}
.ahCard .ahPrice{font-size:13px;color:#fff;font-weight:950;margin-top:2px}
.ahEmpty{font-size:12px;color:#fde68a;font-weight:800;line-height:1.7;padding:6px 2px}

/* V28.3 Top Picks + stronger signal hierarchy */
.topPicksBar{margin:10px 0 12px;padding:12px;border-radius:16px;border:1px solid rgba(49,215,255,.22);background:linear-gradient(135deg,rgba(8,28,48,.95),rgba(6,16,30,.92));box-shadow:0 10px 28px rgba(0,0,0,.25)}
.topPicksLabel{font-size:11px;font-weight:1000;color:#7dd3fc;letter-spacing:.6px;margin-bottom:8px}
.topPicksRow{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
.topPickCard{display:flex;align-items:center;gap:10px;padding:11px 12px;border-radius:14px;border:1px solid rgba(255,255,255,.08);background:rgba(0,0,0,.22);cursor:pointer;transition:.15s;text-align:right;width:100%;color:inherit}
.topPickCard:hover{transform:translateY(-2px);border-color:rgba(49,215,255,.4);box-shadow:0 8px 20px rgba(0,0,0,.3)}
.topPickCard.long{border-color:rgba(35,230,168,.35);background:linear-gradient(145deg,rgba(35,230,168,.12),rgba(0,0,0,.18))}
.topPickCard.short{border-color:rgba(255,77,115,.35);background:linear-gradient(145deg,rgba(255,77,115,.12),rgba(0,0,0,.18))}
.topPickCard .tpIcon{font-size:22px;width:36px;height:36px;display:grid;place-items:center;border-radius:11px;background:rgba(255,255,255,.06)}
.topPickCard .tpBody{min-width:0;flex:1}
.topPickCard .tpBody b{display:block;font-size:13px;font-weight:1000;color:#fff}
.topPickCard .tpBody small{display:block;font-size:10px;color:#8fa7bb;margin-top:2px;font-weight:800}
.assetCard.long{box-shadow:0 0 0 1px rgba(35,230,168,.2),0 12px 28px rgba(0,0,0,.28)!important}
.assetCard.short{box-shadow:0 0 0 1px rgba(255,77,115,.2),0 12px 28px rgba(0,0,0,.28)!important}
.decisionPill.long{box-shadow:0 0 12px rgba(35,230,168,.25)}
.decisionPill.short{box-shadow:0 0 12px rgba(255,77,115,.25)}
@media(max-width:700px){.topPicksRow{grid-template-columns:1fr!important}}

.titanV28Banner{
  background:linear-gradient(90deg,rgba(16,185,129,.28),rgba(49,215,255,.22),rgba(167,139,250,.18))!important;
  border:2px solid rgba(45,245,180,.55)!important;
  font-size:13px!important;font-weight:1000!important;color:#eafff6!important;
  padding:12px 14px!important;border-radius:16px!important;margin-bottom:8px!important;
  box-shadow:0 0 28px rgba(35,230,168,.18)!important;
}
.titanV28Notice{
  margin:0 0 14px!important;padding:10px 12px!important;border-radius:12px!important;
  background:rgba(251,191,36,.12)!important;border:1px dashed rgba(255,211,78,.45)!important;
  color:#ffe9a8!important;font-size:12px!important;font-weight:800!important;line-height:1.7!important;
}
.coinMiniCard{
  outline: none!important;
  transform: none!important;
}
.coinMiniPriceValue{
  font-size:24px!important;
  color:#7ef9ff!important;
  -webkit-text-fill-color:#7ef9ff!important;
}
.coinMiniSymbol{
  color:#ffffff!important;
  font-size:22px!important;
}

.titanApp{max-width:1480px!important;margin:0 auto!important;padding:8px 10px 28px!important}
.topHeader{
  position:sticky!important;top:0!important;z-index:120!important;
  display:grid!important;grid-template-columns:minmax(0,1.1fr) minmax(0,1.4fr) auto!important;
  gap:10px!important;align-items:center!important;
  padding:12px 14px!important;margin-bottom:12px!important;
  border:1px solid rgba(72,203,255,.32)!important;border-radius:22px!important;
  background:linear-gradient(120deg,rgba(5,18,36,.97),rgba(8,22,44,.94) 45%,rgba(12,16,38,.96))!important;
  box-shadow:0 18px 50px rgba(0,0,0,.45),inset 0 1px 0 rgba(255,255,255,.06)!important;
  backdrop-filter:blur(18px)!important;
}
.brand h1{font-size:18px!important;font-weight:1000!important;letter-spacing:.3px!important}
.brand small{font-size:10px!important;color:#8eb0c8!important;font-weight:700!important}
.statusStrip{gap:7px!important}
.statusPill{
  padding:8px 11px!important;border-radius:12px!important;
  background:rgba(255,255,255,.04)!important;border:1px solid rgba(255,255,255,.08)!important;
  font-size:11px!important;font-weight:800!important;
}
.kpiGrid{display:grid!important;grid-template-columns:repeat(auto-fit,minmax(140px,1fr))!important;gap:10px!important;margin:12px 0!important}
.kpi{
  min-height:96px!important;padding:14px!important;border-radius:18px!important;
  background:linear-gradient(155deg,rgba(12,32,54,.95),rgba(6,14,26,.98))!important;
  border:1px solid rgba(72,203,255,.22)!important;
  box-shadow:0 12px 28px rgba(0,0,0,.28)!important;
}
.kpiValue{font-size:24px!important;font-weight:1000!important;color:#fff!important}
.kpiHead{font-size:11px!important;color:#9bb6cb!important;font-weight:900!important;letter-spacing:.4px!important}
.mainTabs{display:flex!important;gap:6px!important;overflow:auto!important;padding:6px!important;border-radius:16px!important;background:rgba(0,0,0,.22)!important;border:1px solid rgba(255,255,255,.07)!important;margin-bottom:12px!important}
.mainTab{flex:0 0 auto!important;padding:10px 14px!important;border-radius:12px!important;font-weight:900!important;font-size:12px!important;color:#8fa7bb!important;border:1px solid transparent!important;background:transparent!important}
.mainTab.active{color:#fff!important;background:rgba(49,215,255,.14)!important;border-color:rgba(49,215,255,.35)!important}
.panel,.section,.hud{
  border-radius:20px!important;
  background:linear-gradient(160deg,rgba(8,22,40,.92),rgba(4,12,24,.96))!important;
  border:1px solid rgba(72,203,255,.16)!important;
  box-shadow:0 14px 36px rgba(0,0,0,.28)!important;
}
.section>h2,.panelTitle{font-size:15px!important;font-weight:1000!important;color:#eaf7ff!important}
@media(max-width:900px){
  .topHeader{grid-template-columns:1fr!important;position:relative!important}
  .statusStrip{order:3!important}
  .headerActions{width:100%!important}
  .kpiGrid{grid-template-columns:repeat(2,minmax(0,1fr))!important}
}
.advLiveBar{
  display:flex!important;flex-wrap:wrap!important;gap:8px!important;align-items:center!important;
  margin:0 0 12px!important;padding:10px 12px!important;border-radius:16px!important;
  background:linear-gradient(90deg,rgba(16,185,129,.12),rgba(49,215,255,.08),rgba(167,139,250,.08))!important;
  border:1px solid rgba(49,215,255,.2)!important;font-size:12px!important;font-weight:800!important;color:#d5ecf8!important;
}
.advLiveBar b{color:#fff!important}
.advLiveDot{width:9px;height:9px;border-radius:50%;background:#23e6a8;box-shadow:0 0 12px #23e6a8;display:inline-block;margin-left:4px}

/* ===== V27.4 UX: crystal-clear coins + mobile box fit + graphical details ===== */
.titanCoinRail{display:grid!important;grid-template-columns:repeat(auto-fill,minmax(158px,1fr))!important;gap:12px!important;width:100%!important;max-width:100%!important;overflow-x:hidden!important;padding:4px 2px 10px!important}
.coinMiniCard{position:relative!important;display:flex!important;flex-direction:column!important;width:100%!important;max-width:100%!important;min-width:0!important;min-height:188px!important;padding:14px 12px 12px!important;overflow:hidden!important;color:#f8fbff!important;-webkit-text-fill-color:#f8fbff!important;background:linear-gradient(155deg,#143352 0%,#0a1f35 48%,#061018 100%)!important;border:2px solid rgba(80,210,255,.55)!important;border-radius:20px!important;box-shadow:0 16px 36px rgba(0,0,0,.45),inset 0 1px 0 rgba(255,255,255,.14)!important}
.coinMiniCard.long{background:linear-gradient(155deg,#0a4a3c 0%,#0a2f2c 50%,#061820 100%)!important;border-color:rgba(45,245,180,.85)!important}
.coinMiniCard.short{background:linear-gradient(155deg,#551230 0%,#2e1228 50%,#10141f 100%)!important;border-color:rgba(255,95,130,.85)!important}
.coinMiniCard.wait{background:linear-gradient(155deg,#4d3f0c 0%,#2a2510 50%,#12161f 100%)!important;border-color:rgba(255,215,70,.85)!important}
.coinMiniTop{display:flex!important;align-items:flex-start!important;justify-content:space-between!important;gap:8px!important;min-width:0!important}
.coinMiniIdentity{display:flex!important;align-items:center!important;gap:10px!important;min-width:0!important;flex:1!important}
.coinMiniIcon{width:58px!important;height:58px!important;min-width:58px!important;display:grid!important;place-items:center!important;border-radius:18px!important;font-size:32px!important;line-height:1!important;color:#fff!important;-webkit-text-fill-color:#fff!important;background:radial-gradient(circle at 30% 25%,rgba(255,255,255,.35),rgba(49,215,255,.14) 42%,rgba(0,0,0,.25) 100%)!important;border:2px solid rgba(255,255,255,.28)!important;box-shadow:0 0 28px rgba(49,215,255,.28)!important}
.coinMiniNameBlock{display:flex!important;flex-direction:column!important;min-width:0!important;flex:1!important}
.coinMiniSymbol,.coinMiniIdentity b{display:block!important;color:#ffffff!important;-webkit-text-fill-color:#fff!important;font-size:20px!important;font-weight:1000!important;line-height:1.1!important;letter-spacing:.3px!important;text-shadow:0 2px 12px rgba(0,0,0,.55)!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}
.coinMiniFullName,.coinMiniIdentity small{display:block!important;color:#d8ebf8!important;-webkit-text-fill-color:#d8ebf8!important;font-size:12px!important;font-weight:800!important;margin-top:3px!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;max-width:100%!important;opacity:1!important}
.coinMiniPair{display:block!important;font-style:normal!important;color:#8ec6e0!important;font-size:10px!important;font-weight:800!important;margin-top:2px!important}
.coinMiniDecision{flex:0 0 auto!important;padding:7px 9px!important;border-radius:999px!important;font-size:11px!important;font-weight:1000!important;letter-spacing:.2px!important;white-space:nowrap!important;color:#fff!important;background:rgba(0,0,0,.35)!important;border:1px solid rgba(255,255,255,.18)!important}
.coinMiniCard.long .coinMiniDecision{background:rgba(16,185,129,.28)!important;border-color:rgba(45,245,180,.55)!important;color:#9ff5d2!important}
.coinMiniCard.short .coinMiniDecision{background:rgba(244,63,94,.28)!important;border-color:rgba(255,95,130,.55)!important;color:#ffb3c4!important}
.coinMiniCard.wait .coinMiniDecision{background:rgba(251,191,36,.22)!important;border-color:rgba(255,215,70,.55)!important;color:#ffe9a3!important}
.coinMiniPriceLine{display:grid!important;grid-template-columns:1fr auto!important;align-items:center!important;gap:2px 8px!important;margin-top:12px!important;padding:10px 11px!important;border-radius:14px!important;background:rgba(0,0,0,.32)!important;border:1px solid rgba(255,255,255,.14)!important;min-width:0!important}
.coinMiniPriceLabel{grid-column:1/-1!important;color:#b9d3e6!important;font-size:11px!important;font-weight:900!important}
.coinMiniPriceValue{grid-column:1!important;color:#ffffff!important;-webkit-text-fill-color:#fff!important;font-size:22px!important;font-weight:1000!important;line-height:1.15!important;letter-spacing:.2px!important;text-shadow:0 2px 16px rgba(49,215,255,.35)!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;max-width:100%!important}
.coinMiniPriceUnit{grid-column:2!important;color:#9fc1d8!important;font-size:11px!important;font-weight:900!important}
.coinMiniScoreBadge{grid-column:2!important;justify-self:end!important;padding:6px 8px!important;border-radius:10px!important;background:rgba(49,215,255,.15)!important;border:1px solid rgba(49,215,255,.28)!important;color:#e8f9ff!important;font-size:11px!important;font-weight:1000!important;white-space:nowrap!important}
.coinMiniPriceLine i{grid-column:1/-1!important;display:block!important;height:8px!important;margin-top:6px!important;border-radius:99px!important;background:#0d2234!important;overflow:hidden!important}
.coinMiniPriceLine i em{display:block!important;height:100%!important;background:linear-gradient(90deg,#31d7ff,#23e6a8)!important;border-radius:99px!important}
.coinMiniTF{display:grid!important;grid-template-columns:repeat(4,minmax(0,1fr))!important;gap:5px!important;margin-top:10px!important}
.coinMiniTF span{min-width:0!important;padding:6px 2px!important;text-align:center!important;border-radius:10px!important;background:rgba(255,255,255,.05)!important;border:1px solid rgba(255,255,255,.08)!important;font-size:9px!important;color:#9db4c8!important;overflow:hidden!important}
.coinMiniTF b{display:block!important;color:#fff!important;font-size:12px!important;margin-top:2px!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}
.coinMiniOpen{display:block!important;margin-top:10px!important;text-align:center!important;padding:8px!important;border-radius:12px!important;background:rgba(49,215,255,.10)!important;border:1px solid rgba(49,215,255,.22)!important;color:#c8f0ff!important;font-size:12px!important;font-weight:900!important}

/* Modal / detail: no overflow off-screen */
.modal{padding:8px!important;align-items:flex-start!important}
.detailModal .modalC{width:min(1180px,100%)!important;max-width:100%!important;height:min(94vh,960px)!important;max-height:94vh!important;overflow:hidden!important}
.cdBodyPad{overflow:auto!important;overflow-x:hidden!important;-webkit-overflow-scrolling:touch!important;max-width:100%!important}
.cdFullDetails,.cdFullDetails *{max-width:100%!important;word-wrap:break-word!important;overflow-wrap:anywhere!important}
.cdMetrics{grid-template-columns:repeat(2,minmax(0,1fr))!important}
@media(min-width:720px){.cdMetrics{grid-template-columns:repeat(4,minmax(0,1fr))!important}}
.cdMetric .val{font-size:18px!important}
.cdName{font-size:20px!important;font-weight:1000!important;color:#fff!important}
.cdPriceBig{font-size:24px!important;font-weight:1000!important;color:#fff!important;text-shadow:0 2px 14px rgba(49,215,255,.25)!important}
.cdIconXL{width:56px!important;height:56px!important;font-size:30px!important}

/* Graphical detail blocks */
.cdVisualSummary{margin:8px 0 12px!important;padding:12px!important;border-radius:18px!important;background:linear-gradient(145deg,rgba(10,32,52,.98),rgba(6,14,28,.98))!important;border:1px solid rgba(49,215,255,.28)!important;box-shadow:0 12px 28px rgba(0,0,0,.28)!important}
.cdVisualHero{display:flex!important;justify-content:space-between!important;align-items:center!important;gap:10px!important;flex-wrap:wrap!important}
.cdVisualHero strong{display:block!important;font-size:18px!important;color:#fff!important}
.cdVisualHero small{display:block!important;color:#9bb8ce!important;margin-top:4px!important}
.cdVisualDecision{padding:10px 14px!important;border-radius:999px!important;font-weight:1000!important;font-size:14px!important}
.cdVisualDecision.long{background:rgba(16,185,129,.22)!important;color:#7dffc8!important;border:1px solid rgba(45,245,180,.45)!important}
.cdVisualDecision.short{background:rgba(244,63,94,.22)!important;color:#ffb0c2!important;border:1px solid rgba(255,95,130,.45)!important}
.cdVisualDecision.wait{background:rgba(251,191,36,.18)!important;color:#ffe39a!important;border:1px solid rgba(255,215,70,.4)!important}
.cdVisualGrid{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:8px!important;margin-top:12px!important}
@media(min-width:640px){.cdVisualGrid{grid-template-columns:repeat(4,minmax(0,1fr))!important}}
.cdVisualStat{padding:11px!important;border-radius:14px!important;background:rgba(255,255,255,.04)!important;border:1px solid rgba(255,255,255,.08)!important;min-width:0!important}
.cdVisualStat span{display:block!important;font-size:11px!important;color:#93acc0!important;font-weight:800!important}
.cdVisualStat b{display:block!important;margin-top:4px!important;font-size:18px!important;color:#fff!important;font-weight:1000!important}
.cdVisualLevels{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:8px!important;margin-top:10px!important}
.cdVisualLevels>div{padding:11px!important;border-radius:14px!important;background:rgba(0,0,0,.22)!important;border:1px solid rgba(255,255,255,.08)!important;min-width:0!important}
.cdVisualLevels span{display:block!important;font-size:11px!important;color:#9db4c8!important}
.cdVisualLevels b{display:block!important;margin-top:3px!important;font-size:15px!important;color:#eaf7ff!important;word-break:break-all!important}
.cdVisualFlow{display:flex!important;align-items:center!important;justify-content:space-between!important;gap:4px!important;flex-wrap:wrap!important;margin-top:12px!important;padding:10px!important;border-radius:14px!important;background:rgba(49,215,255,.07)!important;border:1px solid rgba(49,215,255,.16)!important;font-size:11px!important;font-weight:900!important;color:#cfeeff!important}
.cdVisualFlow i{flex:1!important;min-width:12px!important;height:2px!important;background:linear-gradient(90deg,rgba(49,215,255,.1),rgba(49,215,255,.55),rgba(49,215,255,.1))!important}
.detailVisualLegacy{display:grid!important;gap:12px!important;margin-top:10px!important}
.detailVisualGroup{padding:12px!important;border-radius:18px!important;background:linear-gradient(145deg,rgba(9,29,48,.96),rgba(5,14,26,.98))!important;border:1px solid rgba(49,215,255,.2)!important;box-shadow:0 10px 24px rgba(0,0,0,.22)!important;overflow:hidden!important}
.detailVisualGroupTitle{display:flex!important;align-items:center!important;gap:8px!important;margin-bottom:10px!important;padding:10px 12px!important;border-radius:12px!important;background:linear-gradient(90deg,rgba(49,215,255,.16),rgba(139,92,246,.1))!important;border:1px solid rgba(49,215,255,.18)!important;color:#e8fbff!important;font-size:14px!important;font-weight:1000!important}
.cdSchemaGrid{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:8px!important;margin:8px 0 12px!important}
.cdSchemaCard{padding:12px!important;border-radius:14px!important;background:rgba(255,255,255,.035)!important;border:1px solid rgba(255,255,255,.09)!important;min-width:0!important}
.cdSchemaCard .h{display:flex!important;align-items:center!important;gap:7px!important;font-size:12px!important;font-weight:1000!important;color:#cfeeff!important;margin-bottom:6px!important}
.cdSchemaCard .b{font-size:15px!important;font-weight:1000!important;color:#fff!important;line-height:1.45!important;word-break:break-word!important}
.cdSchemaCard .t{font-size:11px!important;color:#8fa7bb!important;margin-top:4px!important;line-height:1.6!important}
.panelTech,.dualBox,.level,.miniCard{max-width:100%!important;overflow:hidden!important}
.tableWrap{overflow-x:auto!important;-webkit-overflow-scrolling:touch!important;max-width:100%!important}
.section,.panel,.hud,.card{max-width:100%!important;overflow-x:hidden!important}
body,html{overflow-x:hidden!important;max-width:100vw!important}
.titanApp{max-width:100%!important;padding-left:8px!important;padding-right:8px!important}
@media(max-width:420px){
  .titanCoinRail{grid-template-columns:1fr 1fr!important;gap:8px!important}
  .coinMiniIcon{width:48px!important;height:48px!important;min-width:48px!important;font-size:28px!important}
  .coinMiniSymbol,.coinMiniIdentity b{font-size:16px!important}
  .coinMiniPriceValue{font-size:17px!important}
  .cdSchemaGrid{grid-template-columns:1fr!important}
  .cdVisualLevels{grid-template-columns:1fr 1fr!important}
}


/* V27.3 MOBILE-FIRST HARD VISIBILITY OVERRIDES
   These are intentionally global because Android/Pydroid browsers can report a
   desktop CSS viewport even when the physical screen is a phone. */
.coinMiniCard{
  color:#f8fbff!important;
  -webkit-text-fill-color:#f8fbff!important;
  background:linear-gradient(145deg,#102a43 0%,#081a2e 52%,#050e1c 100%)!important;
  border:2px solid rgba(72,203,255,.48)!important;
  border-radius:20px!important;
  min-height:176px!important;
  padding:13px!important;
  box-shadow:0 14px 34px rgba(0,0,0,.42),inset 0 1px 0 rgba(255,255,255,.12),0 0 22px rgba(49,215,255,.07)!important;
  overflow:hidden!important;
  position:relative!important;
}
.coinMiniCard.long{background:linear-gradient(145deg,#073e35 0%,#082a2c 52%,#061421 100%)!important;border-color:rgba(42,245,177,.85)!important;box-shadow:0 14px 34px rgba(0,0,0,.42),0 0 24px rgba(42,245,177,.10)!important}
.coinMiniCard.wait{background:linear-gradient(145deg,#493b09 0%,#29250e 52%,#101622 100%)!important;border-color:rgba(255,214,74,.88)!important;box-shadow:0 14px 34px rgba(0,0,0,.42),0 0 24px rgba(255,214,74,.09)!important}
.coinMiniCard.short{background:linear-gradient(145deg,#4a102c 0%,#2c1229 52%,#101421 100%)!important;border-color:rgba(255,91,125,.88)!important;box-shadow:0 14px 34px rgba(0,0,0,.42),0 0 24px rgba(255,91,125,.10)!important}
.coinMiniCard *{box-sizing:border-box!important;color:inherit!important;-webkit-text-fill-color:inherit!important}
.coinMiniTop{display:flex!important;justify-content:space-between!important;align-items:flex-start!important;gap:8px!important}