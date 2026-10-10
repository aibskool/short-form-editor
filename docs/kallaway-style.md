# Kallaway-style talking-head edits

Use this path for a new raw talking-head. It is the default for that job: hard cuts only, a split graphic stage over a bottom face card with the head popped above it, full-screen and punch-in camera states, one-word lowercase captions, and a comment CTA. Colors and fonts come from the AI Builder School preset, not from Kallaway's red-and-black look.

The presenter-first house style stays on its own path. A timeline whose `style` value is an object (or is omitted) is a house-style edit: full-size presenter, kinetic type, no music. A timeline with `"style": "kallaway"` is this preset. The string is the flag. It is not a house-style override, and the house-style builder never sees it.

## What you need

| Input | Required | Notes |
|---|---|---|
| Raw talking-head video | Yes | One file. Picture and voice. The runner tightens pauses and levels the voice. |
| Word timings | Usual | JSON array, `{ "words": [...] }`, or Whisper `{ "segments": [...] }`. Each word needs `word` (or `text`), `start`, and `end` in source seconds. If you omit `--words` and Whisper is installed, the runner transcribes. Whisper is not bundled. |
| Spoken script | Optional | There is no separate script file. Correct names and spellings in the word JSON before the run. On-screen copy is generated from those words plus the flags below. |
| CTA keyword | Optional | Defaults to `VAULT`. The end header is `Comment {keyword}`. |
| Title | Optional | Defaults to the first three spoken words, in plain title case. Permanent Marker. |
| Theme | Optional | `dark` (default) or `light`. Override the whole preset with `--theme /path/preset.json`. |
| Stage plan | Optional | Per-reel graphic choices. See below. Without one, motifs rotate from a seed of the video path. |
| Emphasis map | Optional | JSON object of lowercase word to `normal`, `marker`, `green`, or `amber`. |
| Music | Off | Brandon adds music on the platform. `--music` mixes the CC0 bed. `--no-music` is the default. |

On-screen text is plain English. Em dashes and en dashes are stripped.

The default lead magnet is the AI Business Idea Vault: 30+ AI business ideas, each with an A to Z guide to landing the first client. The end header is `Comment VAULT` unless you pass another keyword. Change that copy in the theme file, not in code.

## Run it

From the repo root, after `npm ci` inside `production/editor`:

```bash
python3 production/editor/talking_head.py \
  --source /absolute/raw.mp4 \
  --words /absolute/words.json \
  --output /absolute/reel.mp4 \
  --cta-keyword VAULT \
  --title "This one change" \
  --theme-mode dark \
  --stage-plan /absolute/stages.json \
  --emphasis '{"secret":"marker","change":"green"}'
```

The plugin runner forwards the same flags:

```bash
python3 plugins/brandon-reel-engine/scripts/reel.py run talking-head -- \
  --source /absolute/raw.mp4 --words /absolute/words.json --output /absolute/reel.mp4
```

The command refuses to overwrite `--output`. Render goes through `production/editor/hyperframes_cli.py`, which turns telemetry off and reuses an installed Chrome when it finds one.

What the runner does:

1. Keeps each word through its energy decay. Broadband RMS and a 3–10 kHz band are each tracked to their own noise floor + 3 dB, searched 350 ms past the whisper end, then a 40 ms safety tail is added. The crossfade starts after that tail. A following word that starts while the fricative is still up stays in the same piece. Silence between phrases is cut down to about 20 ms. Each join gets a 12 ms equal-power crossfade. The voice stays at 1x. The style check fails a join whose last 20 ms is still more than 3 dB above the noise floor and has not fallen at least 18 dB from the vowel.
2. High-passes, boosts presence around 4 kHz, compresses about 4:1, and loudnorm-targets the voice at -14 LUFS.
3. Plays recorded SFX from the local Viral Reels pack on graphic entrances only. Split, full-face, and punch-in cuts stay silent, and exits stay silent. Whooshes lead panel slides, chapter-header swaps, and big graphic transitions by 4 frames. Files are unprocessed except for a trim, a 5 ms head fade, a 3-frame tail fade, and clip gain above 0 dBFS. A reel keeps at most three booms. Levels sit under the voice (`sfx_under_db`): pops, clicks, and ticks about 13 dB under, whooshes about 10, dings and the cash register about 10, impacts about 6. The mix is baked into the voice file. The lo-fi bed stays off unless you pass `--music`, in which case it sits about 25 dB under the voice.
4. Plans hook splits, a full-screen cut near 3s, body alternation, and a final split with the document fan.
5. Runs the style check, builds the HyperFrames composition, checks the HTML for brand colors and fonts, renders, and finalizes the mix.

`--skip-render` stops after the composition and the style check. Read `stage_slots` in the printed JSON (and in `timeline.json`) before a long encode. That is the right moment to write or revise a stage plan.

`finalize_render.py` treats any ffmpeg stderr as a failed decode. A shell `LD_LIBRARY_PATH` that prints a library warning can fail a valid file. The runner drops that variable for the finalize step.

## Theme preset

`production/editor/themes/ai-builder-school.json` is the only place colors, font files, layout fractions, loudness, the lead magnet, and SFX gains should change.

Dark is charcoal `#1A1A1A` with a `#3A3A3A` dot grid, surface cards `#242424`, warm white `#F2F2F0` Inter captions, and Builder green `#54C947` as the accent (Core `#43AD38`, Light `#7BE06F`). Amber `#ECC94B` is for negative emphasis. Light mode is ticket cream `#FBF8F1` with ink `#211C18`.

Bundled faces, all SIL Open Font License, files under `production/editor/fonts/`:

- Permanent Marker for titles and marker emphasis (Kallaway's italic serif, redrawn in the brand)
- Inter Black (900) and ExtraBold (800) for captions
- IBM Plex Mono Medium for labels, counters, and the CTA subline

## Write a stage plan

Graphics should change with the reel. A stage plan is how an agent authors that from the transcript. The schema is `production/editor/stage-plan.schema.json`. A filled example for the vault script is `production/editor/examples/vault-stage-plan.json`.

Each entry is one split shot before the closing fan. The last split is always `doc_fan` (the lead-magnet pages). Do not put `doc_fan` in the plan.

1. See the slots the cut will actually use. Before pause removal, this is a draft:

```bash
python3 production/editor/kallaway_plan.py \
  --words /absolute/words.json \
  --source /absolute/raw.mp4 \
  --slots
```

After a `--skip-render` run, use `stage_slots` in the composition `timeline.json`. Those times are on the tightened clock, which is the clock the render uses. Copy `spoken` or `word_range` from that list.

2. Write one stage per line you want to illustrate. Two shapes are accepted.

Object form, matched to the words (preferred). Every stage sets `spoken` or `word_range`:

```json
{
  "schema": "kallaway-stage-plan/v1",
  "stages": [
    {
      "spoken": "this one change",
      "motif": "line_chart",
      "why": "The hook names a change, so the line climbs."
    },
    {
      "spoken": "the secret",
      "motif": "highlight_box",
      "label": "the line that matters",
      "media": "screenshot.png"
    },
    {
      "word_range": [24, 28],
      "motif": "counter",
      "value": 30,
      "label": "ideas"
    }
  ]
}
```

`spoken` must appear inside that split slot's `spoken` text. `word_range` is `[start, end)` into the same word list, and the start word must fall in a split slot. `why` and `note` are for the next editor and are not drawn. `media` is a local image or clip for `phone_frame`, `broll_card`, or `highlight_box`. A relative media path is resolved from the plan file.

List form, in slot order. A string is a motif name. An object can carry the same content fields. Extra entries are an error. Fewer entries leave the remaining slots on the automatic rotation:

```json
["line_chart", {"motif": "highlight_box", "label": "the line that matters"}]
```

Motifs: `thumbnail_grid`, `phone_frame`, `broll_card`, `numbered_list`, `line_chart`, `bar_chart`, `counter`, `highlight_box`, `hand_circle`, `typing_ui`, `mind_map`, `logo_row`, `quote_card`, `offer_pair`, `flow_line`, `pill`, `cursor_mock`, `vacuum_merge`, `state_swap`. `doc_fan` stays reserved for the automatic closing shot, and an authored beat may use it mid-reel. `cursor_mock` eases a pointer onto a button and clicks. `vacuum_merge` slides a group into the center and pops the result. `state_swap` shows a wrong card, swipes it off, and pops the right card in green.

Content fields the renderer reads:

| Motif | Fields |
|---|---|
| `thumbnail_grid` | `items` (labels), `count` |
| `numbered_list` | `items` |
| `counter` | `value`, `label` |
| `bar_chart` | `count`, `heights`, `negative` |
| `highlight_box` | `label`, `media` |
| `hand_circle` | `label` |
| `typing_ui` | `text` |
| `mind_map` | `label`, `items` |
| `logo_row` | `items` |
| `phone_frame`, `broll_card` | `media`, `scroll` (`from`/`to`, 0 is the top of the image), `desaturate` (0 to 1), `callout` (circle), `highlight` (a popped line). `callout.target_text` is a phrase in the screenshot. The pan ends with that phrase centered in the phone. |
| `line_chart` | none |
| `numbered_list` | `items`, `hold`, `active` (the box stays on that row) |
| `counter` | `value`, `prefix`, `suffix`, `label` |
| `bar_chart` | `heights`, `labels`, `reveal` (`slice` rises the bars together), `negative` |
| `quote_card` | `text`, `strike` (an amber line through the quote) |
| `offer_pair` | `items` (two cards), `kicker`, `disclaimer` |
| `flow_line` | `items` (two labels and a dashed connector) |
| `pill` | `label` |

`chip` on a stage is a small corner label, `tone` `green` or `amber`. Entrances are a spring scale pop (GSAP `back.out`) or an ease-out slide (`cubic-bezier(0.25, 1, 0.5, 1)`). Layout changes are hard cuts. Each motif reports the same event times to the animation and the SFX list.

## Authored beats

Some reels are not an automatic alternation that ends on the document fan. A plan with `beats` is that cut. The example is `production/editor/examples/authored-beats.json`.

Each beat has `spoken` (a phrase from the transcript) and `layout` (`split`, `full`, or `punch_in`). A split also has a `motif`. The beat runs until the next beat's phrase, and the last beat ends on the last word. There is no inserted end card. Put the `Comment KEYWORD` header on the beat where the ask actually happens.

A beat longer than 5.4 seconds is cut on a word. The extra piece becomes a full-screen or punch-in, so the motif is not repeated. Two split shots in a row still cannot share a motif. `overlays` are extra motifs on the same split, timed with their own `spoken` phrase, and they cannot repeat the shot motif. `callout.spoken` and `highlight.spoken` name the word a circle or highlight belongs to. `callout.target_text` (and the same field on a highlight) is a phrase Tesseract finds in the screenshot. The box is that text in the image's pixel coordinates. `group: "surface"` grows it to the card around the words, such as a heading plus the field and button under it. The pan's end position is computed from that box so the target finishes centered in the phone, and the style check fails if the box is still outside the phone after the pan. Without `target_text`, `x`, `y`, `w`, and `h` stay fractions of the settled frame. The stroke waits until the phone or card has finished entering and any screenshot pan has settled with the target in view. If that word arrives first, the pan starts with the shot and is shortened so it can settle on the word; if it still cannot, the stroke waits. The circle is drawn in the screenshot's own coordinates, so it rides the pixels, and the marker sound starts with the stroke. Phone frames and b-roll cards do not draw a progress bar unless the beat sets `progress` to true. A highlight box on a card waits out the same entrance.

`music_drops` is a list of `{spoken, until, hit}`. It does nothing unless the reel was rendered with `--music`. With the bed on, it goes silent at `spoken` and returns at `until`. The last envelope point stays at full volume, so this is not an ending fade. `hit` adds a bass accent when the bed returns. `chips` are persistent corner labels: `from` is the word they appear on, `after` is a beat phrase and the chip starts when that beat ends. `disclaimer` on a beat stays on screen for the whole beat, including its full-screen pieces. `captions.keep_case` preserves tokens such as `PAID`, `AI`, and `ADA`. A word's own `display` field (for example `5%` or `$1,600`) is what the caption shows. `emphasis` colors a word, and an explicit color wins over the automatic amber list. `bed_bpm` sets this reel's bed tempo when `--music` is on. The bed is the CC0 loop at about 105 BPM. `punch_scale` and `object_position` override the theme for this plan. A shot can still set `scale`.

The style check treats `structure: authored` differently from an automatic cut. The first full-screen or punch-in must start by 8 seconds, and the layout or the motif must change by 4 seconds. Automatic cuts still need a full-screen cut between 2.2 and 4.0 seconds. Captions are not forced through CSS lowercase, so `keep_case` survives. The builder still lowercases every other word.

## Automatic fallback

When no plan is given, the picker does not key off the transcript. It walks `LIBRARY` in `production/editor/kallaway_plan.py`, starting at an index from a SHA-256 of the raw video path. The same path keeps the same order on a re-render. A different video starts somewhere else in the library. The same motif is not used on two split shots in a row, and a reel uses each motif once before any repeat. A partial plan can override some slots. If that would place the same motif on two neighboring splits, the unauthored neighbor moves.

Pass a stage plan for a client reel. The fallback is there so an unplanned cut still varies, not so it illustrates the sentence.

## Style check

```bash
python3 plugins/brandon-reel-engine/scripts/reel.py run check-style -- \
  --timeline /absolute/composition/timeline.json \
  --words /absolute/composition/words.json \
  --project /absolute/composition
```

Errors include a non-Kallaway style, em or en dashes, any transition that is not a hard cut, unknown layouts, shots longer than 5.5s or shorter than 0.4s, gaps or overlaps, a split with no stage, a missing full-screen cut between 2.2s and 4.0s on reels of 6s or more, caption groups over 3 words, uppercase captions, an ending more than 0.12s off the last word, a music fade longer than 0.2s when a bed is present, a callout or highlight that starts while its frame is still entering or its screenshot is still scrolling, a callout whose box is outside the phone after the pan, a stage event with no SFX within 0.12s, a missing Comment header, and HTML colors or fonts outside the preset. A missing music bed is not an error and not a warning. Kallaway's red, neon green, and near-black hexes are rejected.

Warnings cover body shots outside about 1.15-5.05s, and a timeline that was checked before HTML existed.

`production/check_editorial.py` and `review_reel.py` belong to the house style. Do not use them as the Kallaway style gate. Watch the rendered MP4 after the style check passes.

The house-style build gate still rejects music. A Kallaway timeline leaves the bed out unless the render was started with `--music`.

## Known gaps

- No face tracking. The split crop is a fixed `object-position` plus a scale. The face sits inside the card at about 215 px, and only the crown clears the card top by about 70 px. A close-up source scales down, so the card ground can show beside the shoulders. The graphic stage ends at y 1072 unless a higher crown pulls it up. Pop-out is split only. Full-screen and punch keep their own crops and hide the pop. `track_face.py` belongs to the house style.
- Motifs are stylized recreations, not his After Effects projects. Mind maps and dashed logo connectors are simple.
- The automatic motif picker rotates. It does not read the sentence. Pass `--stage-plan` and real screenshots when the graphic should match the line.
- Full-screen movie B-roll is not a default. B-roll stays in a card or phone.
- Slow push-ins stay off.
- The spring is GSAP `back.out`, which approximates an 80% to 110% to 100% pop. The slide ease is the spec cubic-bezier.
- The split card runs from y 1408 to y 1920 (1080×512), flush to the side edges and the bottom, with only the top corners rounded. The face is about 200–230 px inside the card and only the crown clears y 1408 (target 70 px). Graphics end around y 1072 and stay whole. Split captions are one Inter Black line at about 54 px, bottom 35 px above that segment's highest crown, drawn above the head. Full-face captions are Inter Black at about 67 px between the beard and the lapel pin. The pop-out matte is Robust Video Matting (resnet50) at full frame size, with the edge steadied, despilled, and feathered by about 1.5 px.
- The bed is off unless `--music` is passed. That bed is a CC0 lo-fi loop at about 105 BPM. SFX are the local Viral Reels SFX Pack (`SFX_PACK_DIR`), unprocessed except trim, a short fade, and clip gain. Levels are momentary loudness versus the voice's short-term loudness (`sfx_under_db`), baked into the voice. Sources are in `THIRD_PARTY_NOTICES.md`. A reach reel can set `omit_cta` so the style check does not require a Comment header. Phone and b-roll motifs play an mp4 (`media_start`, `playback_rate`). A phone screen fills about 80-90% of the panel. The bezel runs off the top and bottom of the panel, the recording stays full width so text is not cropped on the sides, and the camera pushes toward a callout before the circle draws. `target_text` can be measured on a video frame via `poster_time` or `target_time`, or on `target_still`. A stage `chip` with `"place": "bottom"` is the article credit. `@bjmeaux` is on every frame. `quote_card` variants `receipt` and `browser` are the dense invoice and offline-page compositions.
- Whisper is optional and not installed by this repo.
- `sample_talking_head.py` builds a synthetic proof take (espeak-ng, Pillow, numpy). Do not ship its output.
