# Motion system: presenter-first graphics, word cues, screens, transitions and sound

This is the operator reference for the renderer in `production/editor/`. Its defaults come from the [house style](house-style.md) and `production/editor/style_spec.json`: Brandon full size most of the reel with graphics over or beside him, short white captions with at most one green word, big kinetic type in its own zone, full-frame 2.5D screens for a few seconds at a time, showpieces at the hook, the major reveal and the payoff, soft bubble pops, no background music and no disclaimers. The stage layout from the [reference breakdown](stage-reference-breakdown.md) remains as an occasional option. `plan_reel.py` drafts a timeline in this vocabulary and `review_reel.py` checks one.

Every graphic below renders through HyperFrames (HTML + GSAP, deterministic browser capture). Nothing here is a mock-up: build, check and render it, then watch the encoded MP4.

## 1. Word cues: sync to the exact spoken word

Any time field in the new system accepts seconds **or** a cue resolved against the mapped (post-cut) transcript:

| Cue | Meaning |
| --- | --- |
| `"@casino"` | start of the spoken word "casino" |
| `"@first client"` | start of the consecutive phrase |
| `"@casino:end"`, `"@casino:mid"` | end or middle of the word/phrase |
| `"@casino+0.12"`, `"@casino-0.1"` | offset in seconds |
| `"@then#2"` | the second "then" in the reel |
| `"@w14"` | mapped word index 14 (a spoken word like "W2" is matched as a word; use `{"word_index": 2}` for its index) |
| `{"word": "casino", "n": 2, "edge": "end", "offset": 0.1}` | object form |

Rules the builder enforces:

- A **start** cue (graphic, shot, transition, camera, sfx) must be unambiguous. If the word is spoken more than once the build fails and lists every occurrence with its time; add `#N` or use a longer phrase.
- An **end** cue and every **internal** cue (node `at`, `count_at`, `type_end`…) pick the next spoken occurrence after the graphic starts, so `"end": "@then-0.1"` means the next "then".
- Cues snap to the encoded frame grid. An internal cue outside its graphic's span fails the build.
- A cue that lands on the final frame is clamped to the video's end instead of failing.
- After a pause-cut retime (`production/retime_timeline.py`) numeric times are remapped and `@` cues simply re-resolve against the new word map. Prefer cues.
- The build writes `resolved-timeline.json` next to `index.html`: the same timeline with outer cues replaced by seconds, for tools such as `production/check_editorial.py`.

## 2. Design tokens and feel

`design` (optional) overrides tokens: `accent`, `accent_ink`, `text`, `text_2`, `muted`, `negative`, `warm`, `canvas`, `panel`, `panel_solid`, `line`, `display_font`, `serif_font`, `caption_font`, `mono_font`, `feel`, `stage_backdrop`. Fonts are bundled (OFL, via `@fontsource`) and copied into every composition, so a Mac and a Linux render match: **Inter Tight** (display), **Instrument Serif** italic (accent phrases), **Archivo Black** (captions), **JetBrains Mono** (code/prompts).

`feel` changes timing without re-authoring: `snap` (default; spring overshoot pops, fast exits), `glide` (smooth, no overshoot), `editorial` (slower mask reveals). Every component also takes `scale` (0.5–2.5) to enlarge or shrink it with real layout reflow.

## 3. Layouts and shot motion

| Layout | Use |
| --- | --- |
| `presenter` | Default. Brandon full frame; graphics pop over the chest/sides with an optional local `scrim`. `frame` picks a framing that keeps him full size: `center`, `tight` (1.14×), `close` (1.26×), `space_left` / `space_right` (1.14× and shifted to open negative space for a graphic on that side); `frame_move: "glide"` eases into it from the previous presenter shot instead of cutting. `zoom`, `x_percent`, `y_percent`, `zoom_to` still work. |
| `screen` | A real capture full frame on a 2.5D plane over its own blurred backdrop: `media`, `source_start`, `aspect` (capture width/height), `plane_w` (%), `tilt` `[x, y]` degrees, `fill`, `backdrop` (`blur` \| `dark`), `focus` `[{at, rect:[x,y,w,h] %, duration, tilt, anchor_y}]` crops that land on spoken words, `highlights` `[{rect, at, end, label}]` that ride on the plane, `sweep`. Focus moves start once the plane has landed. Bright captures get a caption backing automatically. |
| `stage` | Optional, at most 4 s at a time (the review warns above 4 s and fails above 6 s): dark canvas above, Brandon in a bottom band card. Settings (top-level `stage` or per shot): `band_top` (63.5 %), `inset`, `bottom`, `radius`, `edge` (`card` \| `fade`), `presenter_scale` (0.9), `presenter_x`, `presenter_y` (42 = yPercent shift that lands the face in the band), `caption_y` (default: just above the band). `backdrop`: `dots`, `grid`, `radial`, `plain`. |
| `full_broll` / `split` | Screen recordings and images as before (`media`, `media_crop`, `media_zoom`, `media_motion`, `fit`). Bright media under the caption band automatically gets a dark caption backing (disable with `spoken_captions.auto_backing:false`, or set `caption_background` per shot). |

Shot `enter` / `exit` on `full_broll` and `split` shots: `cut` (default), `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `iris` (`origin: [x, y]` in %), `zoom`, `expand` (a card that grows to full frame). Presenter and stage shots change by cut, or by `enter: "morph"` from the other layout (Brandon's footage shrinks into the band, or grows back, over `duration`); the build warns about any other motion on them. Morphs and entrances other than `cut` and `fade` add a quiet whoosh; set `enter_sfx` to another kit sound or `false`.

Tune `presenter_scale` / `presenter_y` on the first stage frame of real footage so his face sits in the band with headroom and the chest-level caption does not cover his mouth.

## 4. Graphics (`graphics` list)

Common fields: `id` (starts with a letter; letters, digits, `-`, `_`), `type`, `start`, `end`, `beat` (story beat), `captions` (`keep` \| `hide`: whether short captions step aside while it is up; hero and reveal hide by default), `showpiece` (mark an art-directed moment for the review), `region` or `x`/`y`/`w`/`h` (frame %), `enter` (`pop`, `rise`, `mask`, `slide_left`, `slide_right`, `drop`, `fade`, `blur`, `tilt`, `none`; honored by headline, card, stat, flow, device, chart, checklist and prompt, while statement uses `reveal` and orbit, compare, spotlight, badge, equation and CTA have built-in entrances), `exit` (`fade`, `fall`, `rise`, `slide_left`, `slide_right`, `scale`, `blur`, `cut`, `none`), `scrim` (`true` \| `"band"` \| `"plate"`: a dark rounded plate for big type over a bright screen), `float` (idle drift, default on), `sfx` (entrance sound, or `null` to silence every sound the graphic makes), `scale`, `depth` (`front` \| `behind`).

Regions: `headline` (top band), `top`, `upper`, `stage` (between headline and the band), `center`, `left`/`right` (beside the face), `upper_left`/`upper_right`, `lower` (over the chest, above captions), `seam`.

| Type | What it does | Key fields |
| --- | --- | --- |
| `hero` | Big kinetic type on the chest (`zone`: `chest`, `top`, `center`, `low`), each word landing on its spoken time. Variants: `stack` (words rise through masks), `slam` (the key word crashes in from scale with blur, a shock ring and a small frame kick; `impact: true` adds the restrained impact), `split` (two lines drive in from opposite sides, an accent bar draws between), `outline` (outlined words, the accent fills green on its word), `card` (white Instagram-style hook card with a green marker), `depth` (stack behind Brandon; needs `source.matte`). Words never enter after the exit begins. `slam`, `split`, `outline` and `depth` count as showpieces | `text` or `lines`, `variant`, `accent_words`, `zone`, `size` (104–200; a long line shrinks to fit, never below 84, and the review warns under 104), `align`, `sync` |
| `tag` | Callout pills that pop in on their words beside Brandon, optional icon, `tone: "win"`, and a drawn leader line to a point (`anchor`) | `items[{text,icon,at,tone,win_at}]`, `x`, `y`, `align`, `anchor`, `size` |
| `reveal` | The payoff: the result rises in 2.5D onto a lit card with a reflection and a light sweep, the title lands word by word, particles drift up, a restrained impact | `media`, `media_start`, `title`, `accent_words`, `variant` (`tilt`, `float`, `phone`), `aspect`, `card_w`, `card_y`, `backdrop` (`media_blur`, `dark`, `none`), `particles` |
| `particles` | Restrained drifting glints for a showpiece beat | `count`, `color` (`accent` \| `white`), `x`/`y`/`w`/`h` |
| `headline` | Section chapter title; words rise from a mask line; one accent phrase as a green `box` (dark ink), green italic `serif`, drawn `underline` or `color` | `text` or `lines`, `accent`, `accent_style`, `size`, `align` |
| `statement` | Large kinetic words; optional `sync:"spoken"` reveals each word on its spoken time; accent words glow | `text`, `accent_words`, `accent_style`, `reveal` (`rise`/`pop`/`fade`), `size` |
| `card` | Glass/solid/accent/outline panel with icon, kicker, title, value, body or a real image; `changes` swap the value or mark `win`/`lose` on cue | `icon`, `kicker`, `title`, `value`, `body`, `image`, `variant`, `changes` |
| `stat` | Number counts from `from` to `value` on the spoken number (formatting, compact K/M/B, prefix/suffix), optional sparkline | `value`, `from`, `count_at`, `count_duration`, `prefix`, `suffix`, `decimals`, `compact`, `label`, `pill`, `sparkline` |
| `flow` | Nodes joined by connectors that draw on cue with a travelling pulse; dashed **slots** show the structure until each node arrives; focus ring moves between nodes; nodes can `win_at` or `dim_at` | `layout` (`row`, `column`, `zigzag`, `triangle`, `hub`, `custom`), `nodes[{id,label,sub,icon,image,style,at,win_at,dim_at}]`, `links[{from,to,at,label,style,bend}]`, `focus[{at,node}]`, `slots` |
| `orbit` | Centre card with satellites popping onto a drawn, slowly turning ring | `center{label,image}`, `items[{label,icon,image,at}]`, `spin`, `box_h` |
| `device` | Real screenshot or screen recording in a `phone`, `window` or `card` frame; 3D tilt entrance, camera `moves` inside the screen, `scroll`, `highlights` (box/ring with dimmed surround and label), `taps`, a counter `badge` | `media`, `media_start`, `device`, `aspect`, `fit`, `position`, `moves[{at,scale,x,y,duration}]`, `scroll{start,end,to}`, `highlights[{rect,at,end,label,shape}]`, `taps`, `badge`, `badge_at` |
| `chart` | Line/area chart drawing across a spoken span; pills pop as the line reaches them | `points`, `draw_start`, `draw_end`, `pills[{index,text,at}]`, `title`, `tone` |
| `checklist` | Rows arrive on cue; checks draw on `done_at`; `fail` rows get an X, strike and dim | `title`, `items[{text,at,done_at,state}]`, `numbered` |
| `compare` | Old way vs new way; the left side is struck and greyed on `strike_at`, the right side glows on `win_at` | `left{title,items,at}`, `right{...}`, `vs`, `strike_at`, `win_at` |
| `prompt` | Chat, script or terminal card that types the exact prompt across a spoken span (size reserved up front); optional send press | `text`, `style`, `label`, `type_start`, `type_end`, `send_at` |
| `spotlight` | Circle or box drawn around a frame region (a UI row, a result), with a label | `shape`, `x`/`y`/`w`/`h`, `label` |
| `badge` | Pill or rotated `number` badge (e.g. `#1` on the band seam) | `text`, `variant`, `icon`, `size` |
| `equation` | Hook tiles joined by operators; `?` slots are visible from the first frame and fill on each word; result line lands last | `terms[{label,icon,image,at}]`, `ops`, `result{text,accent_words,at}`, `slots` |
| `cta` | Keyword CTA in six distinct treatments: `chip`, `stamp`, `type`, `bubble`, `underline`, `fan` (real resource pages fan out behind the keyword). The build fails if the keyword is never spoken. End it on the last frame and it holds there instead of fading out | `keyword`, `keyword_at`, `prefix`, `suffix`, `style`, `pages` |

**Device framing.** Camera `moves` are absolute and zoom about 50% 35% of the screen, so a screen point `p` lands at `50 + (p - 50) * scale + x` across and `35 + (p - 35) * scale + y` down. Keep `35 - 35 * scale + y <= 0` and `35 + 65 * scale + y >= 100` (and the same across) or the frame's edge shows. The build warns when a move pushes a highlight, its label or a tap off the screen. Filmed screens drift, so check each highlight against the footage at its start and end. A device holding a video is shown with GSAP rather than clip timing, because HyperFrames rejects a timed `<video>` inside another timed element.

Icons are original line glyphs (`inbox`, `bot`, `calendar`, `mail`, `chat`, `sheet`, `database`, `workflow`, `dollar`, `chart`, `trend_up`, `target`, `bolt`, `rocket`, `briefcase`, `clock`, `check`, `x`, `search`, `code`, `doc`, `globe`, `phone`, `send`, `eye`, `heart`, `star`, `lock`, `spark`, `wand`, `cursor`, `plug`, `gear`, `layers`, `megaphone`, `question`, `alert`, `home`, `brain`, `users`, `user`, `link`, `play`, `flame`, `arrow`). Brand logos only come from supplied image files.

Legacy `editorial_graphics` still build and now render through the `statement` component (word reveal, exit animation), so the approved calibration timelines keep working.

**Depth (text behind Brandon).** Generate a matte for the span you need, then set `source.matte`:

```bash
ffmpeg -ss 0 -t 4 -i take.mp4 -c:v libx264 -crf 18 -an hook.mp4
python3 production/editor/hyperframes_cli.py remove-background hook.mp4 -o hook-matte.webm
```

```json
"source": {"path": "take.mp4", "segments": [...], "matte": {"path": "hook-matte.webm", "source_start": 0}}
```

Graphics with `"depth": "behind"` then sit between the room and his silhouette and move with the presenter camera. Use it for one hook word, not throughout. The matte costs about 1 s of CPU per frame.

## 5. Spoken captions

`spoken_captions.style`: `pop` (default: a one- or two-word group pops in white as it is spoken; a stressed word turns `#49cf26` with a slightly bigger pop), `reveal` (words appear as spoken; avoid on light b-roll) or `phrase` (legacy whole-phrase pop). `karaoke`, which changed color on every word, is retired: it still builds with a warning and the review fails it. `emphasis` lists the stressed words; at most one per group turns green (`emphasis_max_per_group`) and green words stay at least 1.6 s apart (`emphasis_min_gap`). Captions stay 1–2 words (`max_words`, `max_chars`, or reviewed `phrases`), uppercase, without terminal punctuation, and step aside while hero type is up (`hide_under_hero`). They sit at `spoken_captions.y` (lower third) in presenter shots and just above the band in stage shots, gliding with a layout morph. B-roll keeps the same anchor; over busy footage (a phone keyboard, a toolbar) give that shot a `caption_background` plate instead of moving the captions. Set `spoken_caption_visible: false` on a shot whose designed graphic already carries the line, so captions never hide under a panel.

## 6. Camera and transitions

`camera`: `{"kind": "push", "at", "scale", "x", "y", "duration"}` (slow push), `{"kind": "punch", "at", "scale"}` (cut-in on a pivot word), `{"kind": "shake", "at", "amount", "duration"}` (small wiggle for a hit; use once or twice a reel).

`transitions` (full-frame, `at` is the cut): `push_in` (a tracked push into `target` `[x, y]` that the next shot continues, for entering a screen), `match_move` (the outgoing shot leaves in `direction` and the incoming one arrives still moving that way), `shape_wipe` (a circle grows from `origin` and clears to the next shot; `color` carries a color from the shot, never accent green), `punch` (an energetic hard cut that lands pushed in), `whip` (directional motion blur), `zoom_blur`, `flash` (neutral), `blur_flash`, `light_leak` (a warm band that crosses the whole frame; `opacity`). Mix them with plain hard cuts; the planner spaces styled transitions at least 2.2 s apart (1.2 s for a section change or the payoff reveal) and never repeats one back to back. **Retired:** `green_wipe` (read as a green half-frame flash) and green `flashes`; the builder rejects them and `tools/migrate_brandon_config.py` converts old timelines. Kinetic rows no longer grow a bottom bar that read as a timer.

## 7. Sound

Components ask for sounds by role, and the house style picks the sound: `popup` → `bubble` (a soft rounded bubble in six pitch/texture variants, landing 70 ms after the graphic starts), `popup_soft`/`tap` → `bubble_soft`, `travel` → `whoosh_short`, `section` → `whoosh`, `reveal` → `impact_soft`; typing, counting, strikes and highlights are silent. The old `pop` and `tick` are retired (`pop` maps to the bubble). The synthesized kit is original and non-tonal.

The builder thins sounds before mixing: no pop where speech runs over 3.8 words a second, one pop for a cluster of arrivals under 0.55 s apart, whooshes at least 1 s apart, at most four effects in any ten seconds, at most two impacts 8 s apart; transitions and the hook's own sounds outrank later entrances (`sfx_policy` overrides). Gains sit each sound 12–18 LU under the recorded voice and are checked again through a 300 Hz–8 kHz phone-speaker band; both are reported in `motion_report.sfx_levels`. Explicit `sfx` entries always play. `sfx_auto:false` turns automatic sounds off. The render review levels every effect against speech; still listen on headphones and a phone speaker.

## 8. The build receipt is a checklist

`build-receipt.json → motion_report` records layout seconds, `presenter_visible_ratio`, graphics by type, a `timeline` of every graphic's resolved start/end (use it to pick frames to inspect), `graphics_meta` (box, variant, showpiece, caption hiding), the caption plan (`captions`), every kept sound (`sfx_events`) and dropped sounds with reasons, transitions, resolved cues, a reel `signature`, and warnings: complex panels shorter than 2 s, boxes that may collide with the lower-third captions or cover the stage caption on the band seam, three identical graphic types in a row, four identical entrances, a camera push or punch that starts during a presenter morph, Brandon visible under 70 %, full-screen over 30 %, empty stage time, bright media under captions, and repeats of `variation.avoid.hooks` / `variation.avoid.cta_styles` from recent reels. Treat every warning as a question to answer on the encoded frames, then run `review_reel.py` (below).

## 9. Build, check, render

```bash
python production/editor/plan_reel.py --draft draft.json --assets assets.json --out timeline.json   # beat map + draft
python production/editor/edit.py build --spec timeline.json --project /abs/comp
python production/editor/review_reel.py --project /abs/comp                                         # timeline checks
python production/editor/hyperframes_cli.py check /abs/comp          # lint + runtime + layout audit
python production/editor/edit.py render --project /abs/comp --output /abs/raw.mp4 --quality standard --workers 2
python production/editor/review_reel.py --project /abs/comp --video /abs/raw.mp4                    # picture + sound
python production/finalize_render.py --input /abs/raw.mp4 --output /abs/final.mp4 --receipt /abs/verification.json
```

`track_face.py VIDEO --out face.json` writes Brandon's face box over time (the review uses it to measure full-size presence).

`hyperframes_cli.py` reuses an installed Chrome Headless Shell (e.g. Playwright's) when HyperFrames has not downloaded its own. `hyperframes_cli.py snapshot /abs/comp --at 1.2,5.5 --no-end --describe false` renders single frames in seconds; use it to iterate on placement before a full render. Render a 720×1280 proxy while iterating, 1080×1920 for delivery. `edit.py render` refuses to overwrite a file the composition uses as a source. `production/editor/demo/` renders two stand-in timelines that together use every component.

## 10. Minimal example

```json
{
  "source": {"path": "take.mp4", "segments": [{"start": 0.4, "end": 31.2}]},
  "words_path": "words.json",
  "output": {"width": 1080, "height": 1920, "fps": 30},
  "audio_policy": {"music_required": false},
  "spoken_captions": {"emphasis": ["thousand", "agent"]},
  "shots": [
    {"start": 0, "end": "@website-0.25", "layout": "presenter", "frame": "tight"},
    {"start": "@website-0.25", "end": "@and then", "layout": "screen", "media": "site.mp4", "aspect": 0.5625,
     "focus": [{"at": "@website", "rect": [3, 30, 94, 25]}]},
    {"start": "@and then", "end": "@Map", "layout": "presenter", "frame": "space_left"},
    {"start": "@Map", "end": 31.2, "layout": "presenter", "frame": "center"}
  ],
  "graphics": [
    {"type": "hero", "variant": "stack", "text": "I TOLD CHATGPT", "accent_words": ["CHATGPT"], "start": "@told", "end": "@a thousand-0.1"},
    {"type": "hero", "variant": "slam", "lines": ["$1,000", "WEBSITE"], "accent_words": ["WEBSITE"], "zone": "top",
     "scrim": "plate", "impact": true, "start": "@a thousand", "end": "@and then-0.05"},
    {"type": "tag", "x": 7, "y": 42, "start": "@Map", "end": "@Comment-0.1",
     "items": [{"text": "Map the workflow", "icon": "workflow", "at": "@Map"},
               {"text": "Booked call", "icon": "calendar", "at": "@booked", "tone": "win"}]},
    {"type": "reveal", "media": "site.mp4", "title": "LIVE ON THE INTERNET", "accent_words": ["INTERNET"],
     "start": "@live-0.35", "end": "@Comment-0.1"},
    {"type": "cta", "style": "stamp", "start": "@Comment", "end": 31.2, "keyword": "AGENT", "keyword_at": "@AGENT#2"}
  ],
  "transitions": [{"kind": "push_in", "at": "@website-0.25", "duration": 0.4, "target": [50, 52]},
                  {"kind": "match_move", "at": "@and then", "duration": 0.4, "direction": "left"}],
  "camera": [{"kind": "push", "at": 0, "scale": 1.2, "duration": 1.5}],
  "variation": {"avoid": {"cta_styles": ["bubble"], "hooks": ["equation"], "icons": ["rocket", "dollar"]}}
}
```
