# Brandon house style

Every edit starts from one spec: `production/editor/style_spec.json` (`<project>/production/editor/style_spec.json`). The builder (`edit.py`), design tokens, components, the sound kit, the beat planner (`plan_reel.py`) and the acceptance review (`review_reel.py`) all read it. Change a number there and every future edit changes with it. A timeline can override a value under a top-level `"style"` key (for example `{"style": {"zones": {"caption": {"y": 70}}}}`); unknown keys fail the build.

This page says what the spec encodes and how a new edit uses it. It supersedes the stage-first direction and karaoke captions of the earlier September 28 notes.

## Brandon's words are the input

His script, narration and stated facts are authoritative. Illustrate what he says with relevant B-roll, a cropped screen or an original motion graphic. There is no proof step: never hold back, soften, cut or reword a claim because a recording doesn't show it, never ask for a receipt, transaction confirmation or evidence ledger, and never put a disclaimer, verification badge or caveat on screen. The review contains no claim check.

One line stays: don't manufacture a third-party record and present it as real (a fake tweet, review or customer receipt). An original graphic of what he says is always fine.

## The look, with the numbers the review checks

| Rule | Default | Where it lives |
| --- | --- | --- |
| **Keep him present.** Full size most of the reel; graphics over or beside him, using framings that open negative space (`frame`: `center`, `tight`, `close`, `space_left`, `space_right`). | Full size ≥ 50 %, on screen ≥ 72 %. Shrunk into a band (stage/split) ≤ 4 s at a time (the review warns above 4 s, fails above 6 s) and ≤ 18 % overall. Away (screens, full-frame graphics, the payoff reveal) ≤ 5.5 s at a time, 8 s for a showpiece, ≤ 28 % overall. The planner budgets screen time to fit and holds back the payoff reveal's share until it lands. | `layout` |
| **Design the first 3 s.** No equation card or slow title. | Something designed moves by 0.3 s, big key words by 1.2 s, a striking visual (result, interface action, showpiece) by 3 s. When the hook plan has none, the planner turns the first hero into a slam with glints or slams the strongest early word. | `hook` |
| **Sync to the word.** Every entrance, highlight and section change on the spoken word. | Word cues (`"@website#2"`); tolerance 0.1 s + one frame. | `motion` |
| **Two text systems.** Short captions low; hero type big on the chest or above the head, never in the caption band. | Captions `pop`: 1–2 words, white, uppercase, at most one green word per group, green words ≥ 1.6 s apart, at least 54 px. Hero type 104–200 px: the builder shrinks a long line to fit (never below 84 px), the review warns under 104 px, and the planner trims a phrase's leading words before it would shrink. Captions step aside while hero type says the same words. Karaoke (color change on every word) is retired. | `captions`, `zones`, `type` |
| **A visual arc.** Presenter → graphic over presenter → readable screen detail → result → payoff. A story with no footage runs its arc on framings (wide, close, a side with callouts) and type. | Same composition ≤ 7 s. Information holds ≥ 2 s (hero ≥ 0.9 s, screen ≥ 1.4 s) or is left out: a callout that can't hold 2 s is dropped. | `layout`, `motion.hold` |
| **Motion as the selling point.** The hook, a major reveal and the payoff are art-directed. | ≥ 2 showpieces per reel from `showpiece.types`: hero `slam`/`split`/`outline`/`depth`, the 2.5D `reveal`, the 2.5D `screen` shot, `push_in`/`shape_wipe`/`match_move`, `particles`. The closing third always holds one (the planner upgrades the last big phrase or lands glints on the CTA keyword when the story has no payoff footage). New imagery per story; the Astra rocket and money icons and a closing checklist are retired motifs. | `showpiece`, `variety` |
| **Transitions with a reason.** Hard cuts plus tracked pushes into screens, match movement, shape wipes that carry a color, occasional whip or blur; camera accents alternate a punch-in with a quick eased push. | No kind over 45 % (two of a kind is always fine), no back-to-back repeats, ≥ 2 kinds per 30 s, styled transitions ≥ 2.2 s apart (1.2 s for a section change or the payoff reveal), and about the calibration's pace (0.8–3.5 per 10 s: a beat after a long run of hard cuts gets a section transition). A green wipe or green flash fails the build; a timer or progress bar on a pop-up fails the review. | `transitions`, `forbidden` |
| **Useful screens.** Crop to the detail as he names it; highlight only to guide; alternate with his performance. | Focus crops land on words; soft captures ≤ 2.6 s, sharp ≤ 3.4 s; bright UI gets a caption backing; big type over a screen sits on a dark plate. | planner, `screen` layout |
| **Sound supports the edit.** | No music, no beeps. Pop-ups land with a soft rounded **bubble** (six pitch/texture variants) 70 ms after the graphic starts; travel and section moves get quiet whooshes; one restrained impact for a major reveal. Skipped in dense speech (> 3.8 words/s) and clusters (< 0.55 s apart). ≤ 4 effects per 10 s, ≤ 1 effect per 8 spoken words (0.12 per word), ≤ 2 impacts 8 s apart, nothing on captions or plain cuts; consecutive bubbles never repeat a variant. Levels sit 12–18 LU under the voice; the render review separates the effects from the voice and measures each one loudness-weighted (LU, as heard on headphones) and through a phone-speaker band (300 Hz–8 kHz). | `sound` |

## How a new edit uses the defaults

1. **Assemble and transcribe.** `reel.py run assemble` joins takes; `reel.py run transcribe` produces word timings. Correct the words against the audio.
2. **Inventory the footage** in `assets.json` (format below). Tag each capture with the words Brandon uses for what it shows, mark `quality` (`sharp` or `soft`), mark `result` on footage of an outcome, and add `moments` with the frame-percent `rect` of each useful detail.
3. **Plan.** `reel.py run plan -- --draft draft.json --assets assets.json` finds the hook, stressed words (wording plus delivery), demonstrations, emotional turns, results, the payoff and the CTA, then drafts a presenter-first timeline: screens only where footage matches the words, callouts over Brandon where it doesn't, a result preview or showpiece in the hook, a 2.5D reveal for the payoff, rotated transitions and CTA styles, pauses over 0.5 s cut. It prints the beat map; the draft's `variation.avoid` lists the last reels' hooks, CTA styles and icons. The draft is built to pass its own review: full-screen time stays inside the 28 % budget with the payoff reveal's share held back, hero phrases stay verbatim and at house size (never ending on a preposition or a verb whose object was cut), a contrast ("isn't just X, it's actually Y") lands on Y, the first 3 s and the closing third each get an art-directed moment, transitions and camera accents alternate, and a callout that can't hold 2 s is left out. Paths in the planned timeline are written relative to the file it writes.
4. **Sharpen.** Read the beat map. Keep hero wording in Brandon's own words, fix any phrase that reads awkwardly, swap footage where you know a better moment.
5. **Build and review the timeline.** `reel.py run build -- --spec timeline.json --project build/`, answer `motion_report` warnings, then `reel.py run review -- --project build/`. Fix every fail.
6. **Render and review the picture and sound.** Check with `hyperframes_cli.py check`, look at snapshots, render, then `reel.py run review -- --project build/ --video raw.mp4`. The render pass tracks his face (full size, lowered or small, away), finds long mostly-black spans, near-static stretches and silences over 0.5 s, and separates the effects from the voice to level each one on full band and phone band.
7. **Finalize and watch.** `reel.py run finalize`, then watch the whole reel with sound on headphones and a phone speaker. The review can't judge taste.

### `assets.json`

```json
{"assets": [
  {"id": "site", "path": "media/site.mp4", "quality": "sharp", "aspect": 0.5625, "result": true, "color": "#f3efe8",
   "tags": ["website", "built", "personalized", "services"],
   "moments": [{"at": 0.6, "label": "their site", "rect": [3, 30, 94, 25], "tags": ["website", "built"]}]}
]}
```

`at` is seconds into the clip; `rect` is `[x, y, w, h]` in percent of the capture frame; `color` is carried by a shape wipe leaving or entering the capture; `aspect` is width over height.

## Regression reference

The approved 20-second calibration is kept as measurements in `production/editor/reference/calibration-20s.json` (`<project>/production/editor/reference/calibration-20s.json`); the video stays private and out of the repository. The review compares each edit's first visual change, styled-transition rate, caption and title scale and graphic density with it. It does not copy the calibration's full-screen grid panels, green wipe or row bars, which Brandon later retired. With the file in hand, `review_reel.py --measure Brandon-Reel-Engine-20s-review.mp4 --out production/editor/reference/calibration-20s.render.json` records its render metrics.

## What changed on September 28, 2026

| Before (Astra export) | Now |
| --- | --- |
| Brandon shrunk into a stage band under small screen captures for 9–11 s at a time (38 % of the reel) | Presenter first; stage is optional and capped at 4 s; screens go full frame in 2.5D, then return to him |
| Opened on an equation card held 5 s | Key words by 1.2 s and a result preview or showpiece by 3 s |
| Karaoke captions changing color on every word | Short white `pop` captions with at most one green word |
| Pop and tick on nearly every graphic (33 effects, 9 in one 10 s window) | Soft bubble family, ≤ 4 per 10 s, skipped in dense speech and clusters |
| Conservative, repeated card entrances; no showpieces | Hero variants (stack, slam, split, outline, card, depth), callout tags, 2.5D screen and reveal, particles, new transitions |
| Ended on a recap checklist | The payoff is a 2.5D reveal of the result under Brandon's own words |
| Rules and review codes that asked footage to back up his claims | Removed; his narration is the input |
