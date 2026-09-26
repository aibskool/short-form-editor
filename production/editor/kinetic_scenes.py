"""Word-cued editorial diagrams. Every visible change has an authored cue."""
from html import escape
import json


def cue(value, start, end, fallback, name):
    result = float(fallback if value is None else value)
    if not start <= result < end:
        raise ValueError(f'{name} must fall inside the scene')
    return result


def kinetic_markup(scene, ident, start, end, width, height):
    kind = scene['kind']
    if kind not in {'kinetic_ranking', 'kinetic_stat', 'kinetic_comparison'}:
        raise ValueError(f'unsupported kinetic scene: {kind}')
    values = scene.get('items', [])
    if not 1 <= len(values) <= 5:
        raise ValueError('kinetic scene needs one to five items')
    rows = []
    animations = []
    visual_events = [start, end]
    beat = min(.46, max(.18, (end-start-.5)/(len(values)+1)))
    for j, item in enumerate(values):
        label = escape(item['label'])
        value = escape(str(item.get('value', '')))
        accent = ' kinetic-accent' if item.get('accent') else ' kinetic-negative' if item.get('negative') else ''
        onset = cue(item.get('at'), start, end, start + .22 + j*beat, f'item {j} at')
        visual_events.append(onset)
        rows.append(f'<div id="{ident}-row-{j}" class="kinetic-row{accent}"><span class="kinetic-index">{j+1:02}</span><span class="kinetic-name">{label}</span><strong id="{ident}-value-{j}">{value}</strong><i id="{ident}-bar-{j}"></i><b id="{ident}-strike-{j}" class="kinetic-strike"></b></div>')
        animations.append(f'tl.fromTo("#{ident}-row-{j}",{{opacity:0,y:42,scale:.94}},{{opacity:1,y:0,scale:1,duration:.22,ease:"power3.out"}},{onset});')
        animations.append(f'tl.fromTo("#{ident}-bar-{j}",{{scaleX:0}},{{scaleX:1,duration:.36,ease:"power2.out"}},{onset});')
        if item.get('count_to') is not None:
            count = int(item['count_to'])
            if not 0 <= count <= 100:
                raise ValueError('count_to must be 0–100')
            var = ident.replace('-', '_') + f'_count_{j}'
            animations.append(f'const {var}={{n:0}};tl.to({var},{{n:{count},duration:.52,ease:"power2.out",onUpdate:()=>{{document.getElementById({json.dumps(f"{ident}-value-{j}")}).textContent=Math.round({var}.n)+"%";}}}},{onset});')
        if item.get('fade_at') is not None:
            fade = cue(item['fade_at'], onset, end, onset, f'item {j} fade_at')
            visual_events.append(fade)
            animations.append(f'tl.to("#{ident}-row-{j}",{{opacity:.30,backgroundColor:"#303238",duration:.27,ease:"power2.out"}},{fade});')
            animations.append(f'tl.fromTo("#{ident}-strike-{j}",{{scaleX:0}},{{scaleX:1,duration:.29,ease:"power2.out"}},{fade});')
    title = escape(scene.get('title', ''))
    source = escape(scene.get('source', ''))
    tag = escape(scene.get('tag', ''))
    markup = (f'<section id="{ident}" class="kinetic-scene clip" data-start="{start}" data-duration="{end-start}" data-track-index="2" style="width:{width}px;height:{height}px;">'
              f'<div class="kinetic-grid"></div><div id="{ident}-scan" class="kinetic-scan"></div><div class="kinetic-content"><div id="{ident}-tag" class="kinetic-tag">{tag}</div>'
              f'<h2 id="{ident}-title">{title}</h2><div class="kinetic-rows">{"".join(rows)}</div>'
              f'<div id="{ident}-source" class="kinetic-source">{source}</div></div></section>')
    animations.append(f'tl.fromTo("#{ident}-title, #{ident}-tag",{{opacity:0,y:30}},{{opacity:1,y:0,duration:.30,stagger:.10,ease:"power2.out"}},{start+.08});')
    animations.append(f'tl.fromTo("#{ident}-source",{{opacity:0,y:10}},{{opacity:1,y:0,duration:.24}},{min(end-.3,start+.4)});')
    animations.append(f'tl.fromTo("#{ident} .kinetic-grid",{{xPercent:-8}},{{xPercent:8,duration:{end-start},ease:"none"}},{start});')
    for j, change in enumerate(scene.get('motion_cues', [])):
        at = cue(change.get('at'), start, end, start, f'motion cue {j}')
        visual_events.append(at)
        motion_kind = change.get('kind', 'scan')
        if motion_kind == 'scan':
            animations.append(f'tl.fromTo("#{ident}-scan",{{x:0,opacity:0}},{{x:{width*1.25},opacity:.55,duration:.48,ease:"power2.out"}},{at});tl.set("#{ident}-scan",{{opacity:0}},{at+.48});')
        elif motion_kind == 'pulse':
            target = int(change.get('target', 0))
            if not 0 <= target < len(values):
                raise ValueError('motion cue target is outside items')
            animations.append(f'tl.to("#{ident}-row-{target}",{{scale:1.08,duration:.16,yoyo:true,repeat:1,ease:"power2.out"}},{at});')
        else:
            raise ValueError(f'unsupported motion cue: {motion_kind}')
    if max(b-a for a,b in zip(sorted(visual_events),sorted(visual_events)[1:])) > 2.001:
        raise ValueError('kinetic scene has more than 2 seconds without an authored visual change')
    return markup, animations


CSS = '''
.kinetic-scene{position:absolute;left:0;top:0;z-index:2;overflow:hidden;background:radial-gradient(ellipse at 49% 41%,#24432f 0%,#141c1b 47%,#090d10 100%);color:#fff;font-family:Arial,sans-serif}
.kinetic-grid{position:absolute;inset:-15%;opacity:.16;background:repeating-linear-gradient(90deg,transparent 0 49px,#49cf26 50px 51px),repeating-linear-gradient(0deg,transparent 0 49px,#49cf26 50px 51px);transform:skew(-9deg)}
.kinetic-scan{position:absolute;left:-25%;top:0;bottom:0;width:30%;background:linear-gradient(90deg,transparent,#49cf2640,transparent);opacity:0;pointer-events:none}
.kinetic-content{position:absolute;inset:8% 7% 13%;display:flex;flex-direction:column;justify-content:center}
.kinetic-tag{font-size:25px;letter-spacing:.14em;font-weight:800;color:#49cf26;text-transform:uppercase;min-height:34px}
.kinetic-content h2{font-size:62px;line-height:1.02;letter-spacing:-.045em;margin:14px 0 40px;max-width:100%}
.kinetic-rows{display:flex;flex-direction:column;gap:16px}.kinetic-row{position:relative;display:flex;align-items:center;gap:19px;min-height:90px;padding:14px 20px;background:#20262b;border-radius:13px;box-shadow:0 9px 25px #0008;font-size:31px;overflow:hidden}
.kinetic-row i{position:absolute;left:0;right:0;bottom:0;height:5px;background:#49cf26;transform-origin:left}.kinetic-row.kinetic-accent{background:#245c35}.kinetic-row.kinetic-negative{background:#303238;border-left:3px solid #a9434d}.kinetic-index{font-size:21px;color:#8bba99;font-weight:800}.kinetic-name{flex:1;font-weight:750}.kinetic-row strong{font-size:48px;color:#f3f5f2;white-space:nowrap}.kinetic-row.kinetic-accent strong{color:#49cf26}.kinetic-row.kinetic-negative strong{color:#a9a9a9}.kinetic-strike{position:absolute;left:6%;right:6%;top:50%;height:3px;background:#ce5d66;transform-origin:left;transform:scaleX(0);box-shadow:0 0 9px #ce5d66}
.kinetic-source{font-size:21px;color:#cbd3ce;margin-top:32px;min-height:26px}
'''
