# Kallaway-style talking-head edits

Use this path for a new raw talking-head. It is the default for that job: hard cuts only, a split graphic stage with a floating speaker card, full-screen and punch-in camera states, one-to-two-word captions, and a comment CTA. Colors and fonts come from the AI Builder School preset, not from Kallaway's red-and-black look.

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
| Music | Optional | On by default. `--no-music` records an opt-out and skips the bed. |

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

1. Drops pauses longer than 0.1s on word boundaries and keeps the voice at 1x.
2. High-passes, boosts presence around 4 kHz, compresses about 4:1, and loudnorm-targets the voice at -14 LUFS.
3. Writes an original lo-fi bed about 25 dB under the voice, and original SFX for every graphic-stage event.
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

Motifs: `thumbnail_grid`, `phone_frame`, `broll_card`, `numbered_list`, `line_chart`, `bar_chart`, `counter`, `highlight_box`, `hand_circle`, `typing_ui`, `mind_map`, `logo_row`.

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
| `phone_frame`, `broll_card` | `media` |
| `line_chart` | none |

Entrances are a spring scale pop (GSAP `back.out`) or an ease-out slide (`cubic-bezier(0.25, 1, 0.5, 1)`). Layout changes are hard cuts. Each motif reports the same event times to the animation and the SFX list.

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

Errors include a non-Kallaway style, em or en dashes, any transition that is not a hard cut, unknown layouts, shots longer than 5.5s or shorter than 0.4s, gaps or overlaps, a split with no stage, a missing full-screen cut between 2.2s and 4.0s on reels of 6s or more, caption groups over 4 words, uppercase captions, an ending more than 0.12s off the last word, music missing without an opt-out, a music fade longer than 0.2s, a stage event with no SFX within 0.12s, a missing Comment header, and HTML colors or fonts outside the preset. Kallaway's red, neon green, and near-black hexes are rejected.

Warnings cover body shots outside about 1.15-5.05s, caption groups of 3-4 words, and a timeline that was checked before HTML existed.

`production/check_editorial.py` and `review_reel.py` belong to the house style. Do not use them as the Kallaway style gate. Watch the rendered MP4 after the style check passes.

The house-style build gate still rejects music. A Kallaway timeline may include the bed. Through `reel.py run build`, a Kallaway timeline needs a `music` entry or `audio_policy.user_opt_out`.

## Known gaps

- No face tracking. The crop is a fixed `object-position` (default `50% 32%`) plus wide, tight (+15%), and punch-in (+16%) scales. `track_face.py` belongs to the house style.
- Motifs are stylized recreations, not his After Effects projects. Mind maps and dashed logo connectors are simple.
- The automatic motif picker rotates. It does not read the sentence. Pass `--stage-plan` and real screenshots when the graphic should match the line.
- Full-screen movie B-roll is not a default. B-roll stays in a card or phone.
- Slow push-ins stay off.
- The spring is GSAP `back.out`, which approximates an 80% to 110% to 100% pop. The slide ease is the spec cubic-bezier.
- Music and SFX are original synthesis (CC0), not a commercial lo-fi track or a named sample library.
- Whisper is optional and not installed by this repo.
- `sample_talking_head.py` builds a synthetic proof take (espeak-ng, Pillow, numpy). Do not ship its output.
