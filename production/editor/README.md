# Original-footage reel editor

This local editing foundation preserves Brandon's recorded picture and voice. It uses pinned **HyperFrames 0.8.27**, HeyGen's open-source HTML/GSAP video renderer, to assemble source cuts, captions, split screens, full-screen visuals, zooms, sound accents and purposeful transitions. It does not create an avatar, replace speech, upload footage, or call a paid video API.

## Run

Use the project's pinned Python 3.11 environment, Node 22+, FFmpeg/FFprobe, and a Chrome runtime. From this directory:

```bash
npm ci
python3 edit.py build --spec timeline.json --project /absolute/path/to/composition
./node_modules/.bin/hyperframes check /absolute/path/to/composition --at 1,5,10 --json
./node_modules/.bin/hyperframes snapshot /absolute/path/to/composition --at 1,5,10 --no-end --describe false
python3 edit.py render --project /absolute/path/to/composition --output /absolute/path/to/pilot.mp4 --quality standard --workers 1
```

Review snapshots before the full render. `--describe false` keeps snapshot images out of optional external vision analysis. The build writes `index.html`, the editable input timeline, mapped word timings, and a build receipt. Rendering writes a probe receipt after verifying the MP4. Then run `python3 ../finalize_render.py --input /absolute/path/to/raw.mp4 --output /absolute/path/to/final.mp4 --receipt /absolute/path/to/verification.json` to normalize the actual mixed audio, decode the entire final file and record its hash/loudness. Use a new final output path; existing versions are preserved. Local media is hardlinked when possible and copied otherwise; keep source files unchanged while editing.

Use a 720×1280 proxy for the first visual pass or 1080×1920 for final delivery. The source may be portrait or landscape; `object_position` controls the authored crop. This is not automatic face tracking. Start with one render worker on memory-constrained machines; two is a reasonable initial choice for this 16 GB M1 Pro. Four may increase memory pressure. HyperFrames can download its Chrome runtime on the first render and cache it for later runs; dependencies/fonts can also require initial network access.

## Timeline contract

`timeline.example.json` is a renderer capability demo, not a production template: its generic text cards demonstrate fields, not preferred B-roll. Use the plugin's Brandon style profile and text preset for production. All paths resolve relative to that JSON file. `source.segments` is an ordered list of kept source ranges in seconds; picture, original audio, and supplied word timings follow the same cuts. Omit it to use the whole provided clip.

`words_path` accepts a word array, `{ "words": [...] }`, or Whisper-style `{ "segments": [{ "words": [...] }] }`. Every word needs `word` (or `text`), `start`, and `end`, in source-video seconds. Correct names and transcription errors before rendering. A trimmed proxy should normally have word times rebased to zero.

Shots use output-time seconds and one of three layouts:

- `presenter`: full portrait A-roll, with optional fixed `zoom`, `x_percent`, and `y_percent`.
- `split`: top visual and bottom presenter, with the seam set by `output.split_fraction`.
- `full_broll`: full-screen visual while Brandon's source audio continues.

For visual shots, use `media` for a local image/video or `graphic` for an explicitly labelled conceptual illustration. SVG remains vector artwork in the browser. Image/video `fit`, `source_start`, and `background` are configurable; `media_zoom: 1.04` adds a slow 1×→1.04× zoom over the shot. `caption_y` sets the caption block's top as a percentage per shot. A graphics card can contain an eyebrow, title, label/text cards, and footer. Do not label diagrams as real software outputs.

`spoken_captions` groups the actual word-timed speech in short lower-third phrases. Legacy `captions` still builds, but a timeline may not contain both keys. `font_size`, `font_family`, `font_path`, `accent`, `emphasis`, `phrases`, `hold`, `max_words`, `max_chars` and transparent `background` remain available. `caption_y` and `spoken_caption_visible` are shot-level adjustments. The default accent is Brandon's requested `#49cf26`; default size is smaller than the older Council example.

`editorial_graphics` is an independent list of `{start,end,claim_id,role,text,accent_words,x,y,width,font_size,align,animation}`. `claim_id` is a structural story-beat key, not a source-verification gate. Each graphic is a timed overlay, not transcript coverage. The renderer validates bounds and escapes its words; `accent_words` marks literal tokens in green, while other words are white. `animation` may be `rise`, `pop`, or `fade`; holds longer than two seconds receive a second scale change. Take Brandon's spoken claims as given; missing source material must not block the edit. Never put disclaimer or production-caveat labels on screen.

`zooms` accepts output-time punch-ins. `transitions` accepts `{at,duration,kind}` with `green_wipe`, `blur_flash` or `light_leak`; use selected semantic boundaries. `sfx` accepts local audio or original `soft_pop`, `soft_click`, `soft_whoosh`, and `soft_error` accents. Set `audio_policy.music_required:false` and omit `music` for every Brandon short-form export.

## Verification receipt

Run `python3 test_edit.py -v` for timing/grouping and independent editorial track tests. They cover source-cut/reorder mapping, excluded words, invalid timings, phrase breaks and independent graphic markup. The upstream synthetic four-second smoke render was verified as H.264 + AAC, 360×640, 30 fps, with 391,729 bytes; its extracted MP4 frame confirmed that the earlier captions and split graphic survived encoding. That historical check does not verify this fork's new editorial overlay or a Brandon filmed pilot.

Historical upstream HyperFrames checks passed for its native-graphic and SVG compositions. For this conversion, a synthetic composition builds and the comparison tool processes a 20-second synthetic file; native encoding remains unverified here because the available environment has no Chrome binary. Run a new encoded overlay check and review real footage for caption, crop, source claim and audio quality.

## Tool choice and current API findings

Checked September 4, 2026 against primary documentation:

- [HyperFrames official repository](https://github.com/heygen-com/hyperframes) documents local HTML/CSS/media composition, deterministic browser capture, and FFmpeg encoding under Apache 2.0. Its [creator editing recipes](https://github.com/heygen-com/hyperframes/blob/main/skills/hyperframes-core/references/creator-editing-recipes.md) support source trims, matched audio cuts, crop wrappers, and zooms. This is the chosen engine.
- [HeyGen Studio API](https://developers.heygen.com/studio-videos) composes whole-frame scenes through `POST /v3/videos` with `type: "studio"`. Its documented caption source coverage and single-scene layout do not establish this exact simultaneous split-screen A-roll editing workflow.
- [HeyGen AI Clipping API](https://developers.heygen.com/ai-clipping) accepts source video and can create captioned highlight clips. It uses HeyGen authentication and account billing; no such job was submitted here.
- [HeyGen's developer entry point](https://developers.heygen.com/) documents API-key and OAuth CLI routes. No HeyGen CLI was present on PATH during inspection. The local HyperFrames route needs no HeyGen login or subscription purchase.

The original upstream environment had Node 22.23.1, FFmpeg 8.0.1 and cached Chrome; these are historical measurements, not a guarantee for a new checkout. The local HyperFrames route renders captions in the browser. Confirm the actual installed browser/runtime with `doctor` and a smoke render.

## Fast motion and semantic captions

`output.split_fraction` controls an optional split seam; the historical pilot used 0.4648. `spoken_captions.phrases` can define complete, ordered `word_range: [start,endExclusive]` spans, relative `line_breaks`, mixed-case `lead_in` and progressive second-line reveals. The builder rejects omitted or duplicated words. Five tests include phrase coverage. Caption text can omit terminal punctuation while the spoken transcript stays intact.

A shot may use `scene` instead of `media`: the original prompt workspace in `motion_scenes.py` animates real giveaway prompt excerpts with typed text, role tabs and scrolling. It is visibly labeled PROMPT DEMO; it is not a screen recording of Claude. `kind: prompt_scroll` and `block_layout: grid` are optional. `flashes` adds brief, low-opacity radial transition light leaks. The pilot's `sfx/` folder contains a deterministic generator, four original WAVs and their measurement/provenance index. Actual product recordings can be substituted through `media` without changing the rest of the pipeline.

## Evidence-driven inserts

V2 adds `media_crop: [x,y,width,height]` in original source pixels. The builder verifies bounds, preserves aspect ratio, and clips the source nondestructively. Source screenshots retain their original pixels; author/date/repo identity and source limitations belong in the asset index. Use an overview followed by a meaningful close crop when a full README would be illegible on a phone. `labels` carries small timed source labels; `spoken_captions.background` overrides the transparent default.

`scene.kind: artifact_preview` shows actual filenames and exact giveaway excerpts; it is a resource preview, never a fabricated model response. Its `reveals` are deterministic text states. Use sparingly: real application/source captures take priority. The v2 reference calibration already carries its original sound effects in the A-roll audio; keep `sfx` empty to avoid doubling them.

## No music, animated graphics and directed transitions

The builder rejects background music entries and `music_required:true`. Brandon adds music on platform. Keep the actual recorded voice and selected effects clear. Use `scene.kind` `kinetic_ranking`, `kinetic_stat` or `kinetic_comparison` with `title`, optional `tag`/`source`, and 1–5 `items` (`label`, `value`, optional `accent`). The scene animates title and rows. Each item may set `at` (absolute final clock), `anchor_word_index`, `cue_offset`, `count_to`, `fade_at`, `fade_anchor_word_index`, `accent` or `negative`. Word anchors are validated within one encoded frame; `motion_cues` keep custom UI visually active within two-second spans. Positive items stay green; negative items use subdued grey/red, and a `fade_at` row dims to 30%. All editorial text and labels animate. `spoken_captions.y` fixes one lower-third anchor across scenes, including B-roll; shot-level `caption_y` no longer moves it. Scrub the word list against the recorded speech. Every image-based card or illustration needs a directed `media_zoom` or `media_motion`; check its actual endpoint. **Every reel must use animated on-screen graphics and purposeful transitions at appropriate boundaries even if the assembly does not request them.** There is no fixed cut interval or mandatory split screen. Never render disclaimer overlays.

For tightened speech, create a frame-aligned keep EDL with `production/prepare_take.py`, then use `production/retime_timeline.py --help`. The retimer now remaps nested kinetic item, fade and motion cues as well as outer shots; re-author effects partially swallowed by a cut and check the encoded joins. On non-macOS systems `prepare_take.py` uses libx264. Historical upstream pilots with music remain labeled examples, not Brandon export instructions.
