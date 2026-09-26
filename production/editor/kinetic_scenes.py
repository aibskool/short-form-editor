"""Animated, authored editorial diagrams. Values and labels come from the claim map."""
from html import escape


def kinetic_markup(scene, ident, start, end, width, height):
    kind = scene['kind']
    if kind not in {'kinetic_ranking', 'kinetic_stat', 'kinetic_comparison'}:
        raise ValueError(f'unsupported kinetic scene: {kind}')
    values = scene.get('items', [])
    if not 1 <= len(values) <= 5:
        raise ValueError('kinetic scene needs one to five items')
    rows = []
    animations = []
    beat = min(.46, max(.18, (end-start-.5)/(len(values)+1)))
    for j, item in enumerate(values):
        label = escape(item['label'])
        value = escape(str(item.get('value', '')))
        accent = ' kinetic-accent' if item.get('accent') else ''
        rows.append(f'<div id="{ident}-row-{j}" class="kinetic-row{accent}"><span class="kinetic-index">{j+1:02}</span><span class="kinetic-name">{label}</span><strong>{value}</strong><i id="{ident}-bar-{j}"></i></div>')
        cue = start + .22 + j*beat
        animations.append(f'tl.fromTo("#{ident}-row-{j}",{{opacity:0,y:42,scale:.94}},{{opacity:1,y:0,scale:1,duration:.30,ease:"power3.out"}},{cue});')
        animations.append(f'tl.fromTo("#{ident}-bar-{j}",{{scaleX:0}},{{scaleX:1,duration:.42,ease:"power2.out"}},{cue+.12});')
    title = escape(scene.get('title', ''))
    source = escape(scene.get('source', ''))
    tag = escape(scene.get('tag', ''))
    markup = (f'<section id="{ident}" class="kinetic-scene clip" data-start="{start}" data-duration="{end-start}" data-track-index="2" style="width:{width}px;height:{height}px;">'
              f'<div class="kinetic-grid"></div><div class="kinetic-content"><div id="{ident}-tag" class="kinetic-tag">{tag}</div>'
              f'<h2 id="{ident}-title">{title}</h2><div class="kinetic-rows">{"".join(rows)}</div>'
              f'<div id="{ident}-source" class="kinetic-source">{source}</div></div></section>')
    animations.append(f'tl.fromTo("#{ident}-title, #{ident}-tag",{{opacity:0,y:30}},{{opacity:1,y:0,duration:.30,stagger:.10,ease:"power2.out"}},{start+.08});')
    animations.append(f'tl.fromTo("#{ident}-source",{{opacity:0,y:10}},{{opacity:1,y:0,duration:.24}},{min(end-.3,start+.4+len(values)*beat)});')
    animations.append(f'tl.fromTo("#{ident} .kinetic-grid",{{xPercent:-8}},{{xPercent:8,duration:{end-start},ease:"none"}},{start});')
    return markup, animations


CSS = '''
.kinetic-scene{position:absolute;left:0;top:0;z-index:2;overflow:hidden;background:#101519;color:#fff;font-family:Arial,sans-serif}
.kinetic-grid{position:absolute;inset:-15%;opacity:.16;background:repeating-linear-gradient(90deg,transparent 0 49px,#49cf26 50px 51px),repeating-linear-gradient(0deg,transparent 0 49px,#49cf26 50px 51px);transform:skew(-9deg)}
.kinetic-content{position:absolute;inset:8% 7% 13%;display:flex;flex-direction:column;justify-content:center}
.kinetic-tag{font-size:25px;letter-spacing:.14em;font-weight:800;color:#49cf26;text-transform:uppercase;min-height:34px}
.kinetic-content h2{font-size:62px;line-height:1.02;letter-spacing:-.045em;margin:14px 0 40px;max-width:100%}
.kinetic-rows{display:flex;flex-direction:column;gap:16px}.kinetic-row{position:relative;display:flex;align-items:center;gap:19px;min-height:90px;padding:14px 20px;background:#20262b;border-radius:13px;box-shadow:0 9px 25px #0008;font-size:31px;overflow:hidden}
.kinetic-row i{position:absolute;left:0;right:0;bottom:0;height:5px;background:#49cf26;transform-origin:left}.kinetic-row.kinetic-accent{background:#245c35}.kinetic-index{font-size:21px;color:#8bba99;font-weight:800}.kinetic-name{flex:1;font-weight:750}.kinetic-row strong{font-size:48px;color:#49cf26;white-space:nowrap}
.kinetic-source{font-size:21px;color:#cbd3ce;margin-top:32px;min-height:26px}
'''
