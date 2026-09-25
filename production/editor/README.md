# Original-footage reel editor

This local editing foundation preserves Brandon's recorded picture and voice. It uses pinned **HyperFrames 0.8.27**, HeyGen's open-source HTML/GSAP video renderer, to assemble source cuts, captions, split screens, full-screen visuals, zooms, instrumental music and sound accents. It does not create an avatar, replace speech, upload footage, or call a paid video API.

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

`editorial_graphics` is an independent list of `{start,end,claim_id,role,text,accent_words,x,y,width,font_size,align,animation}`. Each graphic is a timed overlay, not transcript coverage. The renderer validates bounds and escapes its words; `accent_words` marks literal tokens in green, while other words are white. `animation` may be `rise`, `pop`, `fade`, or `none`. Put proof attribution in `labels`, not in either text system. The source-backed editorial checker verifies graphic-to-claim joins when an editorial map is supplied. The exact font/geometry are provisional until the 20-second Brandon calibration is reviewed.

`zooms` accepts output-time `{ "at": 5, "scale": 1.1, "duration": 0.16 }` entries. `sfx` accepts a supplied local audio path or the original, synthesized `soft_pop` accent, with `at` and a calibrated `gain`. When `audio_policy.music_required` is true, the build checks for an actual music track. For an intentional music-free edit, set `music_required:false` and explain it in `music_free_reason`. Legacy `user_opt_out` remains accepted.

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

## Required music and directed motion

Use `python3 <plugin>/scripts/reel.py run build -- --spec /absolute/timeline.json --project /absolute/composition`. The runner rejects a missing track when `audio_policy.music_required:true`. A music-free edit requires `audio_policy.music_free_reason` or a legacy `user_opt_out`; do not silently use it to avoid sourcing audio. The renderer validates supplied file/audio/bounds/volume; listening to the encoded mix remains essential.

A partial timeline example for a **10-second** reel (replace paths and duration):

```json
{
  "audio_policy": {"music_required": true},
  "music": [{
    "path": "audio/instrumental.wav", "start": 0, "end": 10,
    "source_start": 0, "gain": 0.26,
    "envelope": [{"t":0,"v":0.26},{"t":0.05,"v":0.34},
      {"t":4.6,"v":0.34},{"t":5.1,"v":0.26},
      {"t":9,"v":0.26},{"t":10,"v":0}]
  }]
}
```

`start`/`end` use the final reel clock. `source_start` selects the musical in-point. Envelope `t` is relative to the music clip start; `v` is its **absolute volume**, replacing `gain` during automation, not multiplying it. Values are 0–1 and times increase within clip duration. Keep the file longer than the selected interval; there is no automatic looping. Index source/license/credit and carry required credit into the publication packet. Finalize the full mixed output and listen at normal volume.

For a directed camera move, a media shot can specify `media_motion: {"from":{"scale":1.02,"x_percent":0,"y_percent":0},"to":{"scale":1.10,"x_percent":-2,"y_percent":0},"ease":"none"}`. The move is applied to the non-timed camera wrapper while the timed media and background remain compositor-controlled. It takes precedence over `media_zoom`. Positive x/y moves the media right/down. Inspect the start/middle/end; a camera move must preserve the required crop text and source context. Use native recorded motion first when it communicates the claim better.

For tightened existing speech, use `production/retime_timeline.py --help` (or plugin `run retime`). Prepare the 1× A-roll and word list first, retime outer cues, then plan music on the final clock. Recheck actions inside recordings and effect tails manually. The current worked revision is `production/pilots/mobbin-v2/`; its technical checks are distinct from perceptual approval.

The finalizer leaves 0.8 dB of pre-AAC headroom by default (`--codec-headroom-db`) while checking the requested decoded true-peak target. This accounts for codec overshoot observed with stronger transient SFX. The final decoded measurement remains authoritative; adjust headroom and re-export if `true_peak_review_needed` is true. Video packets are copied unchanged.
