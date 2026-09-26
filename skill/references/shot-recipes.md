# Shot recipes: decide what happens on each spoken beat

Lock the edited words first. Map spoken beat → viewer question → visual job → asset/graphic → important word → reveal → reading hold → expected takeaway. Take Brandon's claims as given; do not run a claim-accuracy or supporting-evidence gate. The optional `production/editorial-map.schema.json` can record timing, but its proof fields must not block an edit. Every word must belong to a beat; one shot can cover multiple related beats. Read [Brandon's observed profile](brandon-style-profile.md) before choosing treatments.

## Place and size the shot

Find the important noun or verb in the final word list. Place the relevant visual change near that word; a short lead can orient the viewer, but write why it helps. Use the preceding beat to establish source identity when the proof crop needs all the next beat's time. Do not cut to an unrelated new image simply because two seconds elapsed.

As an initial estimate, reserve roughly 0.2 seconds for a reveal and 0.8–1.4 seconds of stillness for two to seven focal words. These are planning estimates, not automatic pass thresholds. If the reader needs more: show fewer required words, enlarge the crop, simplify the treatment or use more of the spoken beat. Do not count typing/scrolling time as a completed-text hold.

At 1080×1920, choose split only when both face and visual remain useful. Use full-screen evidence when the required mechanism cannot be read in half a frame. Use the presenter for a personal claim, pivot, judgment or keyword CTA. Keep source attribution small but readable; explanatory editorial graphics are a separate larger text system from spoken captions.

## Opening energy and moving B-roll

**Make the hook legible immediately.** The first encoded frame should convey the topic and tension at phone size, whether Brandon is on camera, an action opens, or a sourced detail establishes a question. A payoff may develop with the spoken sentence; do not require every supporting fact in the first frame. Animation may reinforce meaning but should not hide the main subject. Use a real relevant visual instead of a paragraph card.

Review the opening at 1× and phone size. Choose the duration of each shot from speech, movement, comprehension and proof readability. A useful continuous action may hold longer; a static shot may be powerful when Brandon's delivery or a clear claim carries it. Hidden/subpixel animation and changing captions alone do not rescue a confusing or inert visual. Record the observed first action and any avoidable dead span without applying a fixed cut interval.

Possible openings include Brandon face-to-camera, a physical action, or a relevant screen detail; draft at least two truthful hook treatments. Place the graphic around the focal subject. Split is an option only when both panes remain readable. If a dense proof crop needs more time, simplify the reading target rather than forcing another cut.

Make motion reinforce the already visible relationship/result and settle long enough to recognize it. Eye-catching scale and contrast should direct attention to that one idea. For Mobbin, busy category menus may show activity but fail to communicate the hook. A clearer treatment is **“600,000+ real app screens for Claude Code”**, supported by actual app-screen examples, a clear library-to-Claude relationship and source attribution. This is a sourced editorial graphic, not a claim of an executed Claude result. Confirm the count/source for the current script. This example is not a mandatory layout for every reel.

Use clear editorial framing for stats, collages, arrows and montages. Animate their entrances or internal states. A statement from Brandon is the story input; an absent capture is a motion-design problem, not grounds to remove his line. Do not add any disclaimer, proof-status badge or production caveat on screen.

See the packaged [Mobbin hook decision](https://github.com/Samin12/samin-reel-engine-plugin/blob/main/plugins/samin-reel-engine/examples/mobbin-hook.json) and [actual encoded phone-size frame](https://github.com/Samin12/samin-reel-engine-plugin/blob/main/plugins/samin-reel-engine/examples/mobbin-hook-frame.png) for a concrete hierarchy example. The still does not establish opening motion quality. Copy the hierarchy principle, not the claim, asset selection or unchanged hold length.

Before polishing, run the [muted cold-view test](quality-procedure.md#first-frame-and-two-second-cold-view-test). If the viewer cannot identify subject, payoff and focal detail, simplify/reframe the hook before adding cuts or effects. More action alone does not repair unclear meaning, and no visual test guarantees retention or virality.

Brandon's short-form exports contain speech and selected effects, with no background music. For **every** reel, animate every on-screen text/card/illustration and place purposeful transition effects at useful cut or section boundaries even when the assembly omits them. Plan the opening separately and avoid a fixed cut interval or mandatory split screen. Never render a disclaimer or production caveat.

An editorial-text list alone does not satisfy the motion brief. Across the complete reel, include visible pop-up UI cards, state changes, progress, comparisons or kinetic diagrams at the spoken beats where they explain the action. Give an authored card a real entrance, a word-cued internal change and an exit; inspect those changes in encoded frames, not only in the timeline specification. Keep the separate short spoken-caption system at its fixed lower-third position. Transition overlays must cross the intended picture, not collapse into a corner fragment. Favor a short, quiet airy whoosh at selected boundaries; do not use the small electronic beep/click as Brandon's default sound. Check the actual mix under his speech.

Prefer actual motion inside the B-roll: typing, scrolling to a relevant section, a cursor selecting an option, a changing app state, a demo result, or a physical action. Use moving B-roll full-screen freely when it reads better or creates a stronger moment; the presenter does not have to remain visible. Vary the visual experience through different relevant sources, source regions, shot scales and layouts. A close detail, wider context and actual action can create useful diversity within one source. Repeated zooms on the same unchanged screenshot do not provide the same diversity as a new useful view/action.

In the body, when a static proof image is the strongest source, normally add a **slow, directed zoom or reframe** instead of leaving it inert. Start around 1.00→1.03–1.08 scale over its 2–4-second shot, or move from source identity toward the relevant detail. These are starting ranges, not fixed requirements and do not override the opening's faster action rule. Keep required text, identity and qualifications inside the crop at both ends; inspect both encoded endpoints at phone size. Let a reveal settle before the important reading hold. For dense text, reduce or stop movement during reading rather than sacrificing legibility. Record an intentional still hold when motion would weaken the proof.

Mark each shot's visual action and each opening focal change in the edit's `creative-review.json` (fields in [quality procedure](quality-procedure.md)). Maximize relevant visible action, not random movement. Never fabricate product behavior, fake scrolling/typing proof, flash unrelated assets, or speed up a measured demonstration without making the time compression clear.

## Pick a recipe

| Recipe | Sequence and timing | Sound/motion | Reject when |
|---|---|---|---|
| Repo/README proof | Establish original repo/owner → tighter relevant heading or command → hold | One small sweep for the crop change; gentle 1.00→1.03 image scale if useful | README is irrelevant, text is microscopic, or stars substitute for capability proof |
| Tweet/announcement | Show author/date/source identity → focus exact clause → hold through spoken claim | Brief pop on reveal; static text during reading | Quote/context is missing, source is fabricated, or a statement is presented as a measured result |
| Real input/action/result | Orient in app → enter concise input → execute → hold actual result | Audible light typing clicks only while typing; one distinct click at the action | Only typing was captured but narration implies a successful result |
| Before/after | Same relevant area and example → change state → hold difference | Hard cut or restrained transition; one accent at the change | Inputs differ or the comparison implies an unsupported performance claim |
| Roles/counts | Show exactly the narrated entities → emphasize the active one on its name | One small emphasis per role, stable design across related shots | Count changes, roles drift, or animation creates a fifth “extra” entity |
| Diagram/mechanism | Reveal input → active step → output while those steps are spoken | Directional highlight/crop follows the relationship | Arrows/labels become an unreadable whole-page diagram |
| AI/stock metaphor | One recognizable object/action for the concept, then return to evidence or presenter | Short visual action; avoid a competing narrative | It impersonates a real product result or needs explanation itself |
| Giveaway/CTA | Actual resource title/contents → useful exact excerpt → presenter/keyword | Paper flick or soft accent; concise caption keyword | Preview is unrelated, filename is invented, or a local file implies successful delivery |

Council examples: GitHub at 4.37s, evaluator diagram at 21.43s, session heading at 27.73s, actual follow-up prompt at 30.17s. Their job is evidence about documented mechanisms/resource contents, not proof of an executed four-agent product. The pixel characters are reference illustrations. Do not reuse these source claims in a different script without checking relevance.

## Use the existing timeline renderer

Paths resolve from the timeline JSON. Supported layouts are `presenter`, `split`, `full_broll`. Video media uses `source_start` in seconds; images use nondestructive `media_crop: [x,y,width,height]` in source pixels. `media_zoom` is a subtle wrapper scale, not a source-content change. A source label goes in the top-level `labels` list. Use the actual asset index to supply IDs/provenance; timeline media paths alone do not document evidence.

```json
{
  "id":"shot-04", "start":4.4, "end":6.8, "layout":"split",
  "caption_y":44.7, "media":"broll/actual-readme.png",
  "media_crop":[660,705,2100,570], "background":"#f6f8fa", "media_zoom":1.03
}
```

This crop is an example for the saved Council image; remeasure source pixels for every other image. Out-of-bounds crops fail the build. Do not paste this rectangle onto a different resolution. For a video shot, use `"media":"broll/recording.mp4", "source_start":2.1, "fit":"contain"` and verify that the remaining clip covers the shot. `contain` preserves required edges; `cover` can remove them.

For the actual giveaway, `scene.kind: "artifact_preview"` displays filenames and exact excerpts. See `production/editor/editorial_scenes.py` and the Council timeline. Read the real files before filling `files`, `active`, `excerpt` and `reveals`. This is an authored resource preview, not a captured app. Show a short excerpt; do not paste an entire prompt into the frame.

## Independent spoken captions and editorial graphics

The three supplied reels show short spoken captions low on screen and a separate, larger green/white editorial system for hook, mechanism, emphasis and CTA. These must be independently positioned, timed, animated and optionally hidden. Start with legible white spoken captions and selective `#49cf26` emphasis; style the editorial track in larger green/white type. Exact font identities are not established. Test text against Brandon's face and the real screen detail.

Use `<plugin>/templates/brandon-text-preset.json` as an adjustable starting point, not a measured match. This is a partial timeline:

```json
{
  "output": {"width":720,"height":1280,"fps":30},
  "spoken_captions": {
    "font_size":34,"font_family":"Arial Black","accent":"#49cf26",
    "uppercase":true,"hold":0.06,"max_words":3,"max_chars":24,
    "omit_terminal_punctuation":true,"background":"rgba(0,0,0,0)",
    "emphasis":[]
  },
  "editorial_graphics": [{"start":0,"end":2.2,"claim_id":"hook","role":"hook",
    "text":"One verified idea","accent_words":["verified"],"x":6,"y":14,"animation":"rise"}]
}
```

Fill `emphasis` with a few actual meaningful words from the current script. Setting `accent` without selecting words produces no green emphasis. Keep a transparent backing unless a shot needs localized contrast. Put spoken captions low when unobstructed and move per shot when a source label or key result occupies that area. Place editorial graphics around the face and proof focal detail; do not treat `caption_y` as their anchor.

Group by spoken meaning, generally two to four words. Avoid splitting a product name, a negation and its verb, or the CTA keyword. Keep at most two useful lines. `spoken_captions.phrases[].word_range` uses zero-based start-inclusive/end-exclusive indices. The complete list must cover each actual word exactly once. `line_breaks` are positions within that phrase; `lead_in:true` softens its first line. Retiming speech requires rebuilding these groups from the updated word map. Editorial graphics use their own start/end and `claim_id`; they do not count as transcript coverage.

**Explicit `phrases` bypass `max_words` and `max_chars`.** Count words in every manual range. Two six-word ranges do not become three-word captions when you change `max_words`. `lead_in:true` applies to the entire first line: use it on a real connector, not a whole emphasized sentence. A longer inseparable name may justify an exception; record and inspect it.

Do not manually add an unspoken word to fix a weak sentence. Correct an ASR spelling only after checking the audio. Do not let a caption sit over an essential UI label. Move the caption or change layout for that shot rather than shrinking everything.

## Music, beats, SFX and VFX

Brandon's current audio policy is categorical: `audio_policy.music_required:false`, no `music` entries and no background music in the encoded short-form video. He may add music on the platform. Keep the current voice intelligible and use selected SFX to mark real actions or reveals. Index each SFX source and listen to the final voice/effect mix at phone volume. Never reuse old narration. Historical Samin pilot music notes remain in its labeled case study, not as an active Brandon requirement.

For each spoken beat, choose A-roll, supplied screen capture, contextual footage, kinetic graphics or a combination that makes it understandable. Animate editorial words, cards, labels and illustrations with a readable entrance or meaningful internal change. A still source can use a directed camera move. Use a wipe, blur flash or light leak at selected boundaries, with a reason in the shot map; do not stamp the same effect onto every cut. Keep all production notes outside the video.

Use hard cuts, small punch-ins, directed crop moves and restrained caption pops to support the words. Include some purposeful transition effects across the edit without imposing one on every cut or a fixed interval. In the renderer, crop backgrounds must be timed clips; an opaque untimed layer once hid earlier B-roll despite passing browser checks. Verify encoded frames after any layering change.

## Word-cued custom graphics

Record the word onset, item entrance, negative-state change, counter start and corresponding SFX in the final reel clock. At 30 fps, align to the nearest frame; do not promise sub-frame precision from a video export. Positive ranks can brighten, while an omitted fourth result should enter visibly then dim to about 30% on the spoken consequence. Keep lower-third captions at a fixed Y position across shots and ensure each custom UI holds no more than two seconds without an authored visual change. A count-up for a sourced figure begins when the figure is spoken. Check that an earlier-year value is not displayed before Brandon says it.

For Brandon short-form, remove expendable silence that lasts 0.5 s or more after a spoken phrase, including swallowing. Place a cut on verified quiet frames, preserve a short natural lead into the next word, then retime every caption, scene item, counter, effect and transition to the new source clock. This is a speech-gap rule, not a fixed visual cut interval.
