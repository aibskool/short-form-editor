"""Stylesheet for motion graphic components on a 1080-px design grid."""


def component_css(px):
    return f"""
.hl{{font-weight:800;line-height:1.02;letter-spacing:-.035em;color:var(--text);text-shadow:0 {px(4)} {px(26)} rgba(0,0,0,.5)}}
.hl-line{{display:block}} .hl-line+.hl-line{{margin-top:.07em}}
.hl-box{{position:relative;display:inline-block;isolation:isolate;padding:0 .14em .03em;margin:0 .03em}}
.hl-box-bg{{position:absolute;left:0;right:0;top:.1em;bottom:.02em;background:var(--accent);border-radius:.1em;transform-origin:0 50%;z-index:-1;box-shadow:0 0 {px(44)} rgba(73,207,38,.35)}}
.hl-on-box{{color:var(--accent-ink);text-shadow:none}}
.hl .serif{{font-size:1.12em;line-height:.94}}
.hl-ul{{position:relative;display:inline-block}}
.hl-ul-svg{{position:absolute;left:0;bottom:-.1em;width:100%;height:.24em;overflow:visible}}
.hl-ul-svg path{{fill:none;stroke:var(--accent);stroke-width:{px(9)};stroke-linecap:round;vector-effect:non-scaling-stroke}}
.st{{font-weight:900;line-height:.98;letter-spacing:-.045em;color:var(--text);text-shadow:0 {px(6)} {px(32)} rgba(0,0,0,.55)}}
.cd{{border-radius:{px(38)};padding:{px(40)} {px(44)};display:flex;gap:{px(30)};color:var(--text)}}
.cd-row{{flex-direction:row;align-items:center}} .cd-column{{flex-direction:column;align-items:flex-start}}
.cd-solid{{background:var(--panel-solid);border:{px(1.5)} solid var(--line);box-shadow:0 {px(22)} {px(60)} rgba(0,0,0,.55)}}
.cd-accent{{background:var(--accent);color:var(--accent-ink);box-shadow:0 0 {px(60)} rgba(73,207,38,.35)}}
.cd-outline{{border:{px(3)} solid var(--accent);background:rgba(0,0,0,.42)}}
.cd-icon{{flex:none;width:{px(132)};height:{px(132)};border-radius:{px(34)};display:grid;place-items:center;background:rgba(73,207,38,.14);border:{px(1.5)} solid rgba(73,207,38,.38);color:var(--accent)}}
.cd-icon svg{{width:54%;height:54%}}
.cd-img{{width:100%;border-radius:{px(22)};overflow:hidden;aspect-ratio:16/10;border:{px(1.5)} solid var(--line)}}
.cd-img img{{width:100%;height:100%;object-fit:cover;display:block}}
.cd-copy{{display:flex;flex-direction:column;gap:{px(10)};min-width:0}}
.cd-kicker{{font-size:{px(30)};letter-spacing:.16em;text-transform:uppercase;font-weight:800;color:var(--accent)}}
.cd-accent .cd-kicker{{color:var(--accent-ink);opacity:.75}}
.cd-title{{font-size:{px(62)};font-weight:800;line-height:1.05;letter-spacing:-.03em}}
.cd-value{{font-size:{px(128)};font-weight:900;line-height:.92;letter-spacing:-.05em;color:var(--accent);font-variant-numeric:tabular-nums}}
.cd-accent .cd-value{{color:var(--accent-ink)}}
.cd-text{{font-size:{px(38)};font-weight:600;line-height:1.28;color:var(--text2)}}
.stt{{color:var(--text)}}
.stt-pill{{display:inline-block;margin-bottom:{px(16)};padding:{px(10)} {px(24)};border-radius:999px;background:rgba(255,255,255,.1);border:{px(1.5)} solid var(--line);font-size:{px(30)};font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:var(--text2)}}
.stt-num{{font-weight:900;letter-spacing:-.055em;line-height:.9;color:var(--accent);font-variant-numeric:tabular-nums;text-shadow:0 {px(8)} {px(40)} rgba(0,0,0,.5)}}
.stt-label{{margin-top:{px(30)};font-size:{px(52)};font-weight:750;letter-spacing:-.02em;text-shadow:0 {px(4)} {px(20)} rgba(0,0,0,.5)}}
.stt-spark{{display:block;margin:{px(20)} auto 0;width:62%;height:{px(80)};overflow:visible}}
.stt-spark path{{fill:none;stroke:var(--accent);stroke-width:{px(5)};stroke-linecap:round;stroke-linejoin:round;vector-effect:non-scaling-stroke}}
.fl{{position:relative}}
.fl-svg{{position:absolute;left:0;top:0;overflow:visible}}
.fl-link{{fill:none;stroke-linecap:round}}
.fl-dot{{fill:#fff;filter:drop-shadow(0 0 {px(10)} var(--accent))}}
.fl-node{{position:absolute;transform:translate(-50%,-50%)}}
.fl-slot{{position:absolute;opacity:0;left:50%;top:0;transform:translateX(-50%);width:var(--ns);height:var(--ns);border-radius:calc(var(--ns) * .28);border:{px(3)} dashed rgba(255,255,255,.2);background:rgba(255,255,255,.025)}}
.fl-slot-pill,.fl-slot-card{{top:50%;transform:translate(-50%,-50%);height:calc(var(--ns) * .5);width:calc(var(--ns) * 1.5);border-radius:999px}}
.fl-slot-card{{border-radius:{px(28)};height:calc(var(--ns) * .7);width:calc(var(--ns) * 1.8)}}
.fl-guide{{fill:none;stroke:rgba(255,255,255,.22);stroke-linecap:round}}
.fl-node-in{{display:flex;flex-direction:column;align-items:center;gap:{px(14)}}}
.fl-icon{{width:var(--ns);height:var(--ns);border-radius:calc(var(--ns) * .28);display:grid;place-items:center;background:var(--panel);border:{px(2)} solid var(--line);color:var(--text);box-shadow:0 {px(18)} {px(44)} rgba(0,0,0,.55)}}
.fl-icon svg{{width:46%;height:46%}}
.fl-accent .fl-icon{{background:rgba(73,207,38,.16);border-color:var(--accent);color:var(--accent);box-shadow:0 0 {px(44)} rgba(73,207,38,.35)}}
.fl-img{{width:var(--ns);height:calc(var(--ns) * 1.25);border-radius:{px(22)};overflow:hidden;border:{px(2)} solid var(--line);box-shadow:0 {px(18)} {px(44)} rgba(0,0,0,.55)}}
.fl-img img{{width:100%;height:100%;object-fit:cover;display:block}}
.fl-text{{text-align:center}}
.fl-label{{font-size:{px(44)};font-weight:800;letter-spacing:-.02em;white-space:nowrap;text-shadow:0 {px(3)} {px(16)} rgba(0,0,0,.6)}}
.fl-sub{{font-size:{px(30)};font-weight:600;color:var(--muted);white-space:nowrap;margin-top:{px(4)}}}
.fl-pill .fl-node-in,.fl-card .fl-node-in{{background:var(--panel);border:{px(2)} solid var(--line);box-shadow:0 {px(18)} {px(44)} rgba(0,0,0,.5)}}
.fl-pill .fl-node-in{{flex-direction:row;border-radius:999px;padding:{px(22)} {px(38)}}}
.fl-card .fl-node-in{{border-radius:{px(28)};padding:{px(26)} {px(30)};align-items:flex-start;min-width:calc(var(--ns) * 1.7)}}
.fl-card .fl-text{{text-align:left}}
.fl-accent.fl-pill .fl-node-in,.fl-accent.fl-card .fl-node-in{{border-color:var(--accent);box-shadow:0 0 {px(44)} rgba(73,207,38,.35)}}
.fl-link-label{{position:absolute;transform:translate(-50%,-50%);background:#0b0f0d;border:{px(1.5)} solid rgba(73,207,38,.45);color:var(--text);font-size:{px(30)};font-weight:700;padding:{px(10)} {px(22)};border-radius:999px;white-space:nowrap}}
.fl-ring{{position:absolute;left:0;top:0;width:0;height:0;border:{px(4)} solid var(--accent);border-radius:50%;box-shadow:0 0 {px(30)} rgba(73,207,38,.5),inset 0 0 {px(24)} rgba(73,207,38,.25)}}
.ob{{position:relative}}
.ob-svg{{position:absolute;left:0;top:0;overflow:visible}}
.ob-svg circle{{fill:none;stroke:rgba(255,255,255,.34)}}
.ob-center{{position:absolute;transform:translate(-50%,-50%);background:var(--accent);color:var(--accent-ink);border-radius:{px(22)};padding:{px(28)} {px(40)};font-size:{px(68)};line-height:.95;text-align:center;box-shadow:0 0 {px(70)} rgba(73,207,38,.4);display:flex;flex-direction:column;align-items:center;gap:{px(8)}}}
.ob-center img{{width:{px(120)};height:{px(120)};object-fit:contain}}
.ob-item{{position:absolute;transform:translate(-50%,-50%)}}
.ob-item-in{{display:flex;flex-direction:column;align-items:center;gap:{px(8)};background:var(--panel);border:{px(1.5)} solid var(--line);border-radius:{px(22)};padding:{px(16)} {px(24)};font-size:{px(32)};font-weight:750;white-space:nowrap;box-shadow:0 {px(16)} {px(40)} rgba(0,0,0,.55)}}
.ob-media .ob-item-in{{padding:{px(6)}}}
.ob-media img{{width:{px(170)};height:{px(226)};object-fit:cover;border-radius:{px(16)};display:block}}
.ob-icon{{width:{px(54)};height:{px(54)};color:var(--accent)}}
.dv{{position:relative;overflow:hidden;border:{px(2)} solid rgba(255,255,255,.16);box-shadow:0 {px(40)} {px(90)} rgba(0,0,0,.65),0 0 0 {px(1)} rgba(0,0,0,.6)}}
.dv-phone{{padding:{px(14)};background:linear-gradient(160deg,#20262a,#0a0c0d)}}
.dv-window{{background:#0c0f0e}}
.dv-card{{background:#0c0f0e}}
.dv-bar{{height:{px(64)};display:flex;align-items:center;gap:{px(10)};padding:0 {px(22)};background:#161b19;border-bottom:{px(1.5)} solid var(--line)}}
.dv-bar i{{width:{px(14)};height:{px(14)};border-radius:50%;background:#3a403d}}
.dv-bar span{{margin-left:{px(14)};font-size:{px(26)};font-weight:600;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.dv-screen{{position:relative;overflow:hidden;background:#000;width:100%}}
.dv-cam{{position:absolute;inset:0;transform-origin:50% 35%}}
.dv-cam img,.dv-cam video{{position:absolute;inset:0;width:100%;height:100%;display:block}}
.dv-hl{{position:absolute;border:{px(4)} solid var(--accent);border-radius:{px(14)};box-shadow:0 0 0 {px(2000)} rgba(0,0,0,.42),0 0 {px(26)} rgba(73,207,38,.55);transform-origin:50% 50%}}
.dv-hl-ring{{border-radius:50%}}
.dv-hl-label{{position:absolute;background:var(--accent);color:var(--accent-ink);font-size:{px(32)};font-weight:800;padding:{px(10)} {px(18)};border-radius:{px(10)};white-space:nowrap}}
.dv-tap{{position:absolute;width:{px(70)};height:{px(70)};margin:{px(-35)} 0 0 {px(-35)};border-radius:50%;background:rgba(255,255,255,.4);border:{px(3)} solid #fff}}
.dv-badge{{position:absolute;right:{px(-16)};top:{px(-22)};background:var(--accent);color:var(--accent-ink);font-size:{px(44)};font-weight:900;padding:{px(14)} {px(28)};border-radius:999px;box-shadow:0 0 {px(40)} rgba(73,207,38,.5),0 {px(10)} {px(24)} rgba(0,0,0,.5);white-space:nowrap}}
.ch{{position:relative;border-radius:{px(30)};padding:{px(26)} {px(30)}}}
.ch-title{{position:relative;z-index:1;font-size:{px(44)};font-weight:800;letter-spacing:-.02em}}
.ch-svg{{position:absolute;left:0;top:0;overflow:visible}}
.ch-grid line{{stroke:rgba(255,255,255,.08);stroke-width:{px(2)}}}
.ch-line{{fill:none;stroke-linecap:round;stroke-linejoin:round;filter:drop-shadow(0 0 {px(10)} rgba(73,207,38,.55))}}
.ch-pill-pos{{position:absolute;transform:translate(-50%,-100%)}} .ch-pill-first{{transform:translate(-18%,-100%)}} .ch-pill-last{{transform:translate(-82%,-100%)}}
.ch-pill{{background:#fff;color:#0b0f0d;font-size:{px(32)};font-weight:800;padding:{px(8)} {px(16)};border-radius:999px;white-space:nowrap;box-shadow:0 {px(8)} {px(20)} rgba(0,0,0,.45)}}
.ch-dot{{position:absolute;width:{px(22)};height:{px(22)};margin:{px(-11)} 0 0 {px(-11)};border-radius:50%;background:var(--accent);border:{px(4)} solid #0b0f0d}}
.ck{{border-radius:{px(34)};padding:{px(32)} {px(34)}}}
.ck-title{{font-size:{px(52)};font-weight:800;letter-spacing:-.025em;margin-bottom:{px(12)}}}
.ck-row{{position:relative;display:flex;align-items:center;gap:{px(24)};padding:{px(22)} {px(6)};border-top:{px(1.5)} solid rgba(255,255,255,.07)}}
.ck-num{{width:{px(50)};font-size:{px(28)};font-weight:800;color:var(--muted);font-variant-numeric:tabular-nums}}
.ck-box{{flex:none;width:{px(64)};height:{px(64)};border-radius:{px(18)};border:{px(3)} solid rgba(255,255,255,.3);display:grid;place-items:center}}
.ck-box svg{{width:66%;height:66%;overflow:visible}}
.ck-box path{{fill:none;stroke:var(--accent-ink);stroke-width:3.4;stroke-linecap:round;stroke-linejoin:round}}
.ck-fail .ck-box path{{stroke:#fff}}
.ck-text{{font-size:{px(46)};font-weight:700;letter-spacing:-.02em;line-height:1.15}}
.ck-strike{{position:absolute;left:{px(140)};right:4%;top:50%;height:{px(5)};background:var(--negative);transform:scaleX(0);transform-origin:0 50%;border-radius:{px(3)}}}
.cp{{display:grid;grid-template-columns:1fr auto 1fr;gap:{px(16)};align-items:stretch}}
.cp-side{{position:relative;border-radius:{px(30)};padding:{px(30)} {px(26)};background:var(--panel-solid);border:{px(1.5)} solid var(--line);box-shadow:0 {px(20)} {px(50)} rgba(0,0,0,.5)}}
.cp-positive{{border-color:rgba(73,207,38,.55)}}
.cp-head{{display:flex;align-items:center;gap:{px(14)};font-size:{px(42)};font-weight:800;letter-spacing:-.02em;margin-bottom:{px(14)}}}
.cp-ico{{flex:none;width:{px(56)};height:{px(56)};border-radius:50%;display:grid;place-items:center}}
.cp-ico svg{{width:58%;height:58%}}
.cp-negative .cp-ico{{background:rgba(255,93,93,.15);color:var(--negative)}}
.cp-positive .cp-ico{{background:rgba(73,207,38,.18);color:var(--accent)}}
.cp ul{{list-style:none;margin:0;padding:0}}
.cp li{{font-size:{px(36)};font-weight:600;color:var(--text2);padding:{px(11)} 0;border-top:{px(1)} solid rgba(255,255,255,.07);line-height:1.2}}
.cp-vs{{align-self:center;width:{px(96)};height:{px(96)};border-radius:50%;display:grid;place-items:center;background:var(--panel-solid);border:{px(1.5)} solid var(--line);font-family:var(--serif);font-style:italic;font-size:{px(60)};line-height:1;padding-bottom:{px(8)};box-sizing:border-box;color:var(--accent)}}
.cp-strike{{position:absolute;left:6%;right:6%;top:62%;height:{px(6)};background:var(--negative);transform:scaleX(0);transform-origin:0 50%;border-radius:{px(3)};box-shadow:0 0 {px(12)} rgba(255,93,93,.6)}}
.pr{{position:relative;border-radius:{px(34)};padding:{px(30)} {px(34)} {px(36)}}}
.pr-head{{display:flex;align-items:center;gap:{px(12)};font-size:{px(28)};font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin-bottom:{px(18)}}}
.pr-head.pr-script{{font-size:{px(64)};letter-spacing:0;text-transform:none;color:var(--text);justify-content:center}}
.pr-dot{{width:{px(12)};height:{px(12)};border-radius:50%;background:var(--accent);box-shadow:0 0 {px(12)} var(--accent)}}
.pr-body{{position:relative;font-size:{px(48)};font-weight:650;line-height:1.3;color:var(--text);padding-right:{px(90)}}}
.pr-script .pr-body,.pr-script+.pr-body{{font-weight:750}}
.pr-terminal .pr-body{{font-family:var(--mono);font-size:{px(38)};color:var(--accent);font-weight:500}}
.pr-ghost{{visibility:hidden}}
.pr-live{{position:absolute;left:0;top:0;right:{px(90)}}}
.pr-caret{{display:inline-block;width:.45em;height:1.05em;background:var(--accent);vertical-align:-.16em;margin-left:.06em}}
.pr-send{{position:absolute;right:{px(24)};bottom:{px(24)};width:{px(76)};height:{px(76)};border-radius:50%;background:rgba(255,255,255,.12);color:var(--text);display:grid;place-items:center}}
.pr-send svg{{width:44%;height:44%}}
.sp-svg{{overflow:visible;fill:none;stroke:var(--accent);filter:drop-shadow(0 0 {px(12)} rgba(73,207,38,.65));stroke-linecap:round}}
.sp-label{{position:absolute;left:50%;top:100%;transform:translateX(-50%);margin-top:{px(14)};background:var(--accent);color:var(--accent-ink);font-size:{px(34)};font-weight:800;padding:{px(8)} {px(18)};border-radius:999px;white-space:nowrap}}
.bd-wrap{{display:flex;justify-content:center}}
.bd{{display:inline-flex;align-items:center;gap:.35em;font-weight:900;letter-spacing:-.01em;padding:.26em .7em;border-radius:999px;white-space:nowrap}}
.bd-ico{{width:1em;height:1em;display:inline-block}} .bd-ico svg{{width:100%;height:100%}}
.bd-accent{{background:var(--accent);color:var(--accent-ink);box-shadow:0 0 {px(40)} rgba(73,207,38,.45),0 {px(10)} {px(24)} rgba(0,0,0,.45)}}
.bd-dark{{background:#0b0f0d;border:{px(2)} solid var(--line);color:var(--text);box-shadow:0 {px(10)} {px(24)} rgba(0,0,0,.45)}}
.bd-outline{{border:{px(3)} solid var(--accent);color:var(--accent);background:rgba(0,0,0,.42)}}
.bd-number{{background:var(--accent);color:var(--accent-ink);border-radius:.28em;padding:.1em .42em;transform:rotate(-4deg);box-shadow:0 {px(14)} 0 rgba(0,0,0,.35),0 0 {px(40)} rgba(73,207,38,.4)}}
.eq{{display:flex;flex-direction:column;align-items:center;gap:{px(18)}}}
.eq-row,.eq-res{{display:flex;align-items:center;justify-content:center;gap:{px(22)};flex-wrap:wrap}}
.eq-cell{{position:relative}}
.eq-slot{{position:absolute;inset:0;opacity:0;border-radius:{px(44)};border:{px(4)} dashed rgba(255,255,255,.3);display:grid;place-items:center;font-size:{px(96)};font-weight:900;color:rgba(255,255,255,.35);background:rgba(0,0,0,.25)}}
.eq-tile{{min-width:{px(220)};height:{px(220)};padding:0 {px(24)};border-radius:{px(38)};background:var(--panel);border:{px(1.5)} solid var(--line);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:{px(8)};box-shadow:0 {px(20)} {px(46)} rgba(0,0,0,.55)}}
.eq-tile img{{max-width:{px(120)};max-height:{px(120)};object-fit:contain}}
.eq-ico{{width:{px(92)};height:{px(92)};color:var(--accent)}}
.eq-lab{{font-size:{px(36)};font-weight:800;white-space:nowrap}}
.eq-op{{font-size:{px(110)};font-weight:900;color:var(--text);opacity:.85;text-shadow:0 {px(4)} {px(20)} rgba(0,0,0,.6)}}
.eq-result{{font-size:{px(104)};text-align:center;font-weight:900;letter-spacing:-.04em;text-shadow:0 {px(6)} {px(30)} rgba(0,0,0,.55)}}
.eq-rwrap{{position:relative;display:inline-block}}
.eq-rslot{{position:absolute;inset:{px(-6)} {px(-14)};opacity:0;border-radius:{px(30)};border:{px(4)} dashed rgba(255,255,255,.3);display:grid;place-items:center;font-size:{px(72)};font-weight:900;color:rgba(255,255,255,.35);background:rgba(0,0,0,.25)}}
.ct{{display:flex;flex-direction:column;align-items:center;gap:{px(18)};text-align:center}}
.ct-line{{display:flex;align-items:center;justify-content:center;flex-wrap:wrap;gap:{px(22)}}}
.ct-pre{{font-size:{px(72)};font-weight:800;letter-spacing:-.03em;text-shadow:0 {px(4)} {px(24)} rgba(0,0,0,.55)}}
.ct-key{{font-size:{px(100)};font-weight:900;letter-spacing:-.02em;display:inline-block}}
.ct-chip{{background:var(--accent);color:var(--accent-ink);padding:.1em .45em;border-radius:.22em;box-shadow:0 0 {px(50)} rgba(73,207,38,.45),0 {px(12)} {px(30)} rgba(0,0,0,.45)}}
.ct-stamp{{border:{px(7)} solid var(--accent);color:var(--accent);padding:.04em .34em;border-radius:.16em;text-transform:uppercase;background:rgba(0,0,0,.4);transform:rotate(-4deg)}}
.ct-type{{font-family:var(--mono);color:var(--accent);background:rgba(0,0,0,.6);border:{px(2)} solid rgba(73,207,38,.5);padding:.08em .35em;border-radius:.2em;min-width:4ch;text-align:left}}
.ct-caret{{display:inline-block;width:.42em;height:.95em;background:var(--accent);vertical-align:-.1em;margin-left:.05em}}
.ct-bubble{{display:inline-flex;align-items:center;gap:.22em;background:#fff;color:#0b0f0d;padding:.12em .5em .12em .34em;border-radius:.46em .46em .46em .08em;box-shadow:0 {px(14)} {px(34)} rgba(0,0,0,.45)}}
.ct-bubble svg{{width:.78em;height:.78em;color:var(--accent);stroke-width:2.6}}
.ct-ul{{position:relative;color:var(--accent)}}
.ct-ul svg{{position:absolute;left:0;bottom:-.12em;width:100%;height:.24em;overflow:visible}}
.ct-ul path{{fill:none;stroke:var(--accent);stroke-width:{px(10)};stroke-linecap:round;vector-effect:non-scaling-stroke}}
.ct-sub{{font-size:{px(42)};font-weight:650;color:var(--text2);text-shadow:0 {px(4)} {px(20)} rgba(0,0,0,.55)}}
.ct-fan{{position:relative;width:100%;height:{px(360)};margin-bottom:{px(-44)}}}
.ct-line{{position:relative;z-index:2}}
.ct-page{{position:absolute;left:50%;top:{px(20)};width:{px(236)};height:{px(300)};margin-left:{px(-118)};background:#f3f5f2;border-radius:{px(14)};padding:{px(22)};display:flex;flex-direction:column;gap:{px(12)};transform-origin:50% 130%;box-shadow:0 {px(24)} {px(50)} rgba(0,0,0,.55);overflow:hidden}}
.ct-page img{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
.ct-page-t{{font-size:{px(28)};font-weight:800;color:#0b0f0d;line-height:1.15;text-align:left;margin-bottom:{px(6)}}}
.ct-page i{{display:block;height:{px(10)};background:#d9ddd8;border-radius:{px(5)}}}
.ct-page i.short{{width:60%}}
"""
