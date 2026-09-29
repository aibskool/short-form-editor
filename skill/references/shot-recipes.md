# Shot recipes: decide what happens on each spoken beat

Lock the edited words first. Map spoken beat → viewer question → visual job → asset/graphic → important word → reveal → reading hold → expected takeaway. Take Brandon's claims as given; do not run a claim-accuracy or supporting-evidence gate. The optional `production/editorial-map.schema.json` can record timing; its legacy fields never block an edit. Every word must belong to a beat; one shot can cover multiple related beats. Read the [house style](house-style.md) (the current direction) and [Brandon's observed profile](brandon-style-profile.md) before choosing treatments, then the [motion system](motion-system.md) for the components that render it. `production/editor/plan_reel.py` drafts the beat map and a first timeline from the words, his delivery and the footage inventory; start from it and sharpen.

## Place and size the shot

Find the important noun or verb in the final word list. Place the relevant visual change near that word; a short lead can orient the viewer, but write why it helps. Use the preceding beat to establish what the viewer is looking at when the crop needs all the next beat's time. Do not cut to an unrelated new image simply because two seconds elapsed.

As an initial estimate, reserve roughly 0.2 seconds for a reveal and 0.8–1.4 seconds of stillness for two to seven focal words. These are planning estimates, not automatic pass thresholds. If the reader needs more: show fewer required words, enlarge the crop, simplify the treatment or use more of the spoken beat. Do not count typing/scrolling time as a completed-text hold.

At 1080×1920, keep Brandon full size and put graphics over or beside him, reframing with `frame` (`space_left`, `space_right`, `tight`, `close`) to open negative space. When a capture needs the whole frame, cut to a `screen` shot for a few seconds, crop to the detail on the word, then return to him. A `stage` band is an occasional option for a diagram, 4 s at most; choose split only when both face and visual remain useful. Use the presenter for a personal claim, pivot, judgment or keyword CTA. Keep source attribution small but readable; explanatory editorial graphics are a separate larger text system from spoken captions.

## Opening energy and moving B-roll

**Make the hook legible immediately.** The first encoded frame should convey the topic and tension at phone size, whether Brandon is on camera, an action opens, or a sourced detail establishes a question. A payoff may develop with the spoken sentence; do not require every supporting fact in the first frame. Animation may reinforce meaning but should not hide the main subject. Use a real relevant visual instead of a paragraph card.

For a result-first hook, a short clip of the finished website, live domain or decisive captured action may precede the face while the original A-roll voice continues, then return to Brandon on the next meaningful phrase. Cue a bold claim from the recorded story and keep the result identifiable; use split only if both panes add information. Check the first three seconds at normal speed. Do not turn this into a required opening template.

Review the opening at 1× and phone size. Choose the duration of each shot from speech, movement, comprehension and readability. A useful continuous action may hold longer; a static shot may be powerful when Brandon's delivery or a clear claim carries it. Hidden/subpixel animation and changing captions alone do not rescue a confusing or inert visual. Record the observed first action and any avoidable dead span without applying a fixed cut interval.

Possible openings include Brandon face-to-camera, a physical action, or a relevant screen detail; draft at least two truthful hook treatments. Place the graphic around the focal subject. Split is an option only when both panes remain readable. If a dense screen crop needs more time, simplify the reading target rather than forcing another cut.

Make motion reinforce the already visible relationship/result and settle long enough to recognize it. Eye-catching scale and contrast should direct attention to that one idea. For Mobbin, busy category menus may show activity but fail to communicate the hook. A clearer treatment is **“600,000+ real app screens for Claude Code”**, supported by actual app-screen examples, a clear library-to-Claude relationship and source attribution. This is a sourced editorial graphic, not a claim of an executed Claude result. Confirm the count/source for the current script. This example is not a mandatory layout for every reel.

Use clear editorial framing for stats, collages, arrows and montages. Animate their entrances or internal states. A statement from Brandon is the story input; an absent capture is a motion-design problem, not grounds to remove his line. Do not add any disclaimer, status badge or production caveat on screen.

See the packaged [Mobbin hook decision](https://github.com/Samin12/samin-reel-engine-plugin/blob/main/plugins/samin-reel-engine/examples/mobbin-hook.json) and [actual encoded phone-size frame](https://github.com/Samin12/samin-reel-engine-plugin/blob/main/plugins/samin-reel-engine/examples/mobbin-hook-frame.png) for a concrete hierarchy example. The still does not establish opening motion quality. Copy the hierarchy principle, not the claim, asset selection or unchanged hold length.

Before polishing, run the [muted cold-view test](quality-procedure.md#first-frame-and-two-second-cold-view-test). If the viewer cannot identify subject, payoff and focal detail, simplify/reframe the hook before adding cuts or effects. More action alone does not repair unclear meaning, and no visual test guarantees retention or virality.

Brandon's short-form exports contain speech and selected effects, with no background music. For **every** reel, animate every on-screen text/card/illustration and place purposeful transition effects at useful cut or section boundaries even when the assembly omits them. Plan the opening separately and avoid a fixed cut interval or mandatory split screen. Never render a disclaimer or production caveat.

Map the key spoken numbers, entities, actions and punchlines to a separate editorial emphasis track across the **whole** reel. The lower-third transcript and visible screen recordings do not replace that emphasis. When a capture shows the action, keep it visible and use a brief, well-placed green/white callout to tell the viewer what matters; do not cover the source detail they need to read. Animate plain pop-up text in and out without a default square container, countdown or timer bar. A lightweight word-cued text accent may be shorter than two seconds. An authored UI card, comparison, stat or diagram needs a useful visual job and enough uninterrupted time to read it, generally at least two to three seconds; omit a complex panel if its beat is shorter or it duplicates the capture. A compact mid-frame icon or two-stage status change may support a longer spoken beat. Inspect the entrances, internal changes and exits in encoded frames. Keep the separate short spoken-caption system at its fixed lower-third position (in a stage section it sits on the seam above Brandon's band). Transition effects should cross the intended picture at selected meaningful joins, not collapse into a corner fragment. A pop-up lands with a soft bubble (skipped when speech is dense or pop-ups cluster); travel and section changes get short, quiet whooshes; a major reveal may take one restrained impact. Avoid beeps, repeated loud impacts or a sound on every label, caption or cut. Check the actual mix under his speech.

For a multi-step result, carry a consistent numbered/check-mark motif through the relevant spoken milestones. Show completed steps when they are earned; reveal email sent or live domain on those exact words rather than putting a crowded four-row panel into a short beat. Move callouts higher or into a compact side-card when their visual position clashes with the fixed spoken captions or source UI. A side-card has its own entrance and useful internal change, without a timer bar. Let the final face-to-camera keyword remain visible through the spoken CTA; a restrained pulse can renew it without adding a silent tail after Brandon finishes.

**Calibration transfer:** Brandon approved the final 17.07-second tight-cut calibration as the target for full reels. Its first second is a face hook with a large rising phrase; the next full-frame dark radial grid uses a green kicker, a large white heading and spacious staged rows. A later full-frame stat counts on the spoken number; the final comparison delays its second value until that phrase is spoken. Carry those spatial proportions, row motion, contrast, low fixed captions, a motivated full-frame section transition and restrained UI sound through suitable longer beats. (The calibration's green wipe is retired; use a whip, zoom blur, iris/expand or layout morph.) The full reel must contain substantive authored scenes where the speech calls for them; a handful of tiny checks, small side badges or plain text labels over every source shot will not recreate this style. Keep the actual capture legible between such scenes, and choose the duration for each visual job from speech and reading time. Compare the encoded candidate with the exact approved calibration by visual job before asking Brandon to judge the full reel.

**Full-reel correction after review:** The v7 cut had too many full-screen grid sequences even though the motion language was closer. Recreate its sizable staged graphics **over moving A-roll with Brandon visible** whenever both can read clearly. Position them around the face and hands, use a modest local vignette or glow, and let the graphic build, change and depart while his performance continues. Reserve an occasional full-screen grid for a mechanism that needs the whole frame or a deliberate chapter transition. Review the proportion of presenter-visible footage across the full timeline; avoid both extremes of uninterrupted talking head and repetitive full-frame cards. For long-form video, let the assembly decide captions, music and overall pacing; the short-form caption and no-music prescriptions do not automatically carry over.

Prefer actual motion inside the B-roll: typing, scrolling to a relevant section, a cursor selecting an option, a changing app state, a demo result, or a physical action. Use moving B-roll full-screen freely when it reads better or creates a stronger moment; the presenter does not have to remain visible. Vary the visual experience through different relevant sources, source regions, shot scales and layouts. A close detail, wider context and actual action can create useful diversity within one source. Repeated zooms on the same unchanged screenshot do not provide the same diversity as a new useful view/action.

When the only supplied screen source is a camera filming a monitor, crop and use a gentle directed pan/zoom without pretending glare and moiré have become a native capture. Ask for a native screen recording in a later filming/capture pass if crisp UI is essential. A browser/phone frame can organize a clean capture, but a mock-up alone does not restore lost pixels. For future A-roll with a black shirt, chair and brick background, plan a real rim light or background accent during filming; a post-process glow is not a replacement for the light on the subject.

In the body, when a static screenshot is the strongest source, normally add a **slow, directed zoom or reframe** instead of leaving it inert. Start around 1.00→1.03–1.08 scale over its 2–4-second shot, or move from source identity toward the relevant detail. These are starting ranges, not fixed requirements and do not override the opening's faster action rule. Keep required text, identity and qualifications inside the crop at both ends; inspect both encoded endpoints at phone size. Let a reveal settle before the important reading hold. For dense text, reduce or stop movement during reading rather than sacrificing legibility. Record an intentional still hold when motion would weaken the reading.

Mark each shot's visual action and each opening focal change in the edit's `creative-review.json` (fields in [quality procedure](quality-procedure.md)). Maximize relevant visible action, not random movement. Never pass an authored animation off as a recording of someone else's product, flash unrelated assets, or speed up a measured benchmark without making the time compression clear. An original motion graphic of a step Brandon describes is always fine.

## Pick a recipe

| Recipe | Sequence and timing | Sound/motion | Reject when |
|---|---|---|---|
| Repo/README detail | Establish original repo/owner → tighter relevant heading or command → hold | One small sweep for the crop change; gentle 1.00→1.03 image scale if useful | README is irrelevant, text is microscopic, or a star count stands in for the feature |
| Tweet/announcement | Show author/date/source identity → focus exact clause → hold through spoken claim | Brief pop on reveal; static text during reading | Quote/context is missing, source is fabricated, or a statement is presented as a measured result |
| Real input/action/result | Orient in app → enter concise input → execute → hold actual result | Audible light typing clicks only while typing; one distinct click at the action | The input or result is illegible at phone size, or cut so the action can't be followed |
| Before/after | Same relevant area and example → change state → hold difference | Hard cut or restrained transition; one accent at the change | The two states show different areas or examples, so the change can't be seen |
| Roles/counts | Show exactly the narrated entities → emphasize the active one on its name | One small emphasis per role, stable design across related shots | Count changes, roles drift, or animation creates a fifth “extra” entity |
| Diagram/mechanism | Reveal input → active step → output while those steps are spoken | Directional highlight/crop follows the relationship | Arrows/labels become an unreadable whole-page diagram |
| AI/stock metaphor | One recognizable object/action for the concept, then return to the screen or presenter | Short visual action; avoid a competing narrative | It impersonates a real product result or needs explanation itself |
| Giveaway/CTA | Actual resource title/contents → useful exact excerpt → presenter/keyword | Paper flick or soft accent; concise caption keyword | Preview is unrelated, filename is invented, or a local file implies successful delivery |

Council examples: GitHub at 4.37s, evaluator diagram at 21.43s, session heading at 27.73s, actual follow-up prompt at 30.17s. Their job was to show documented mechanisms and resource contents. The pixel characters are reference illustrations. Do not reuse these source claims in a different script without checking relevance.

## Map beats to motion components

Pick the component by the beat's visual job, then cue it to the word that names it. Field details are in [motion-system.md](motion-system.md); the five sequences in the [breakdown](stage-reference-breakdown.md#several-ways-to-apply-the-style) show how they combine without repeating.

| Spoken beat | Component | Cue it on | Watch for |
|---|---|---|---|
| Proposition or section takeaway | `headline` at the top (accent: `box`, `serif`, `underline` or `color`; vary within a reel) | the first word of the section | It names the section; it never repeats the caption |
| Punchline or pivot word | `statement` (`reveal: pop`, or `sync: "spoken"` for a short sentence) | the word itself | One or two words big beats a sentence small |
| "A + B = outcome" hook | `equation` with `?` slots | each term's noun, result last | Slots show from the first frame so the hook reads before it fills |
| Process, pipeline, agent workflow | `flow` (`row`, `column`, `zigzag`, `hub`) with slots | each node's noun; links on the verb between them | About five nodes read on a phone (the component allows nine); `win_at` for the payoff node |
| Tools around one idea | `orbit` | each tool's name | Only tools that are actually spoken |
| Screen detail | `screen` layout, or `device` (`phone`/`window`) with `moves`, `highlights`, `scroll` | the noun for the detail being highlighted | Zoom to the region; a static full page is too small |
| A number Brandon states | `stat` (counts on the number), optional `chart` | the number | Only numbers he says; never invent a result |
| Steps or a list | `checklist` (`done_at`, `fail` rows) or seam `badge` numbers | each step | Fail rows dim and strike; wins stay green |
| Old way vs new way | `compare` | `strike_at` on the old way's verdict, `win_at` on the new | Keep both columns to three short items |
| The exact prompt or message | `prompt` (`chat`, `script`, `terminal`) | typing across the words that describe it | Type only the real prompt; hold the finished text |
| A single fact or tool | `card` (icon or real image), `changes` for a state flip | the fact's noun | Size it to read at phone size |
| Point at something already on screen | `spotlight` | the word for it | Circle for faces/objects, box for UI rows |
| Keyword CTA | `cta` (`chip`, `stamp`, `type`, `bubble`, `underline`, `fan`) | the spoken keyword | Change the style from the last reel; `fan` needs the real resource page titles |

## Use the existing timeline renderer

Paths resolve from the timeline JSON. Supported layouts are `presenter`, `screen`, `full_broll`, `split`, `stage`; shot `enter`/`exit` motions and word-cued times are in [motion-system.md](motion-system.md). Video media uses `source_start` in seconds; images use nondestructive `media_crop: [x,y,width,height]` in source pixels. `media_zoom` is a subtle wrapper scale, not a source-content change. A source label goes in the top-level `labels` list. Use the actual asset index to supply IDs and origin; timeline media paths alone do not document provenance.

```json
{
  "id":"shot-04", "start":4.4, "end":6.8, "layout":"split",
  "media":"broll/actual-readme.png",
  "media_crop":[660,705,2100,570], "background":"#f6f8fa", "media_zoom":1.03
}
```

This crop is an example for the saved Council image; remeasure source pixels for every other image. Out-of-bounds crops fail the build. Do not paste this rectangle onto a different resolution. For a video shot, use `"media":"broll/recording.mp4", "source_start":2.1, "fit":"contain"` and verify that the remaining clip covers the shot. `contain` preserves required edges; `cover` can remove them.

For the actual giveaway, `scene.kind: "artifact_preview"` displays filenames and exact excerpts. See `production/editor/editorial_scenes.py` and the Council timeline. Read the real files before filling `files`, `active`, `excerpt` and `reveals`. This is an authored resource preview, not a captured app. Show a short excerpt; do not paste an entire prompt into the frame.

## Independent spoken captions and editorial graphics

The three supplied reels show short spoken captions low on screen and a separate, larger green/white editorial system for hook, mechanism, emphasis and CTA; the September 28 reference adds Title Case section headlines. These must be independently positioned, timed, animated and optionally hidden. Captions default to `pop`: one or two white words per group, with `#49cf26` on at most one stressed word (the karaoke style that changed color on every word is retired). Style the designed layer (hero type, statements, tags) in larger green/white type in its own zone. The renderer bundles its fonts (Archivo Black captions, Inter Tight display, Instrument Serif accents) so a Mac and a Linux render match; exact reference font identities are not established. Test text against Brandon's face and the real screen detail.

Use `<plugin>/templates/brandon-text-preset.json` as an adjustable starting point, not a measured match. This is a partial timeline:

```json
{
  "output": {"width":1080,"height":1920,"fps":30},
  "spoken_captions": {"emphasis":[]},
  "shots": [{"start":0,"end":2.4,"layout":"presenter","frame":"tight"}],
  "graphics": [{"id":"hook","type":"hero","variant":"slam","start":"@first-key-word","end":2.4,
    "lines":["REPLACE WITH","THE HOOK WORDS"],"accent_words":["HOOK"],"impact":true,"beat":"hook"}],
  "camera": [{"kind":"push","at":0,"scale":1.2,"duration":1.5}],
  "variation": {"avoid": {"hooks":[],"cta_styles":[],"icons":["rocket","dollar"]}}
}
```

Caption style, size, color and position come from `style_spec.json`; set them in the timeline only with a reason. Fill `emphasis` with the stressed words from the beat map; at most one per caption group turns green and pops on its spoken frame. Setting `accent` without selecting words produces no green emphasis. Keep a transparent backing unless a shot needs localized contrast (bright B-roll under the captions gets a dark backing automatically). Put spoken captions low when unobstructed. Place designed graphics around the face and the screen's focal detail; do not treat `caption_y` as their anchor. Replace the preset's `hook` headline with the real hook, and list the last reels' hook types and CTA styles under `variation.avoid`.

Group by spoken meaning, generally two to four words. Avoid splitting a product name, a negation and its verb, or the CTA keyword. Keep at most two useful lines. `spoken_captions.phrases[].word_range` uses zero-based start-inclusive/end-exclusive indices. The complete list must cover each actual word exactly once. `line_breaks` are positions within that phrase; `lead_in:true` softens its first line. Retiming speech requires rebuilding these groups from the updated word map. Editorial graphics use their own start/end and `claim_id`; they do not count as transcript coverage.

**Explicit `phrases` bypass `max_words` and `max_chars`.** Count words in every manual range. Two six-word ranges do not become three-word captions when you change `max_words`. `lead_in:true` applies to the entire first line: use it on a real connector, not a whole emphasized sentence. A longer inseparable name may justify an exception; record and inspect it.

Do not manually add an unspoken word to fix a weak sentence. Correct an ASR spelling only after checking the audio. Do not let a caption sit over an essential UI label. Move the caption or change layout for that shot rather than shrinking everything.

## Music, beats, SFX and VFX

Brandon's current audio policy is categorical: `audio_policy.music_required:false`, no `music` entries and no background music in the encoded short-form video. He may add music on the platform. Keep the current voice intelligible and use selected SFX to mark real actions or reveals. Index each SFX source and listen to the final voice/effect mix at phone volume. Never reuse old narration. Historical Samin pilot music notes remain in its labeled case study, not as an active Brandon requirement.

For each spoken beat, choose A-roll, supplied screen capture, contextual footage, kinetic graphics or a combination that makes it understandable. Animate editorial words, cards, labels and illustrations with a readable entrance or meaningful internal change. A still source can use a directed camera move. Use a tracked `push_in` into a screen, a `match_move`, a `shape_wipe` that carries a color, a whip, zoom blur, iris/expand or full-frame light leak at selected boundaries, with a reason in the shot map, and plain hard cuts between them; do not stamp the same effect onto every cut. Keep all production notes outside the video.

Use hard cuts, small punch-ins, directed crop moves and restrained caption pops to support the words. Include some purposeful transition effects across the edit without imposing one on every cut or a fixed interval. In the renderer, crop backgrounds must be timed clips; an opaque untimed layer once hid earlier B-roll despite passing browser checks. Verify encoded frames after any layering change.

## Word-cued custom graphics

Record the word onset, item entrance, negative-state change, counter start and corresponding SFX in the final reel clock. At 30 fps, align to the nearest frame; do not promise sub-frame precision from a video export. Positive ranks can brighten, while an omitted fourth result should enter visibly then dim to about 30% on the spoken consequence. Keep lower-third captions at a fixed Y position across shots (stage sections move them to the band seam) and ensure each custom UI holds no more than two seconds without an authored visual change. Write these times as word cues (`"@word"`, `"@word#2"`, `"@word:end+0.1"`) so a retime or a transcript fix moves them with the speech. A count-up for a sourced figure begins when the figure is spoken. Check that an earlier-year value is not displayed before Brandon says it.

For Brandon short-form, remove expendable silence that lasts 0.5 s or more after a spoken phrase, including swallowing. Place a cut on verified quiet frames, preserve a short natural lead into the next word, then retime every caption, scene item, counter, effect and transition to the new source clock. This is a speech-gap rule, not a fixed visual cut interval.
