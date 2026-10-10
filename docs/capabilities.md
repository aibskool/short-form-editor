# Capabilities and exact boundaries

The skills direct an agent; the helper commands execute specific local operations. A skill is not an always-running service or a replacement for provider credentials.

| Runner action | Included implementation | Boundary |
|---|---|---|
| `research` | Discovery and source records for new story ideas | Optional for filmed edits; never a claim-accuracy or supporting-evidence release gate |
| `pipeline` | Init, status and validation of the research → idea → script → resource packet | Structural readiness is not approval or publication |
| `script-check` | Spoken-word/beat counts and duration estimates | Actual voice timing comes from the recording |
| `intake` | Local Whisper transcription and script-take indexing | Needs local video, script samples and model dependencies |
| `assemble` | Joins the chosen takes into one master and remaps word timings | Take choice still needs a listen |
| `transcribe` | Word-timed transcription (Parakeet) | Correct names against the audio |
| `take` | Reviewed cuts, selected take and retimed word map | No automatic certification that a cut sounds natural |
| `retime` | Remap supported outer cues after speech edits | Native actions inside clips and effect tails need review |
| `capture` | Source captures through an isolated local Chrome session | Needs a Chrome executable and public source URLs; does not reuse signed-in cookies |
| `plan` | Beat map (hook, stressed words, demonstrations, turns, payoff, CTA) and a presenter-first draft timeline from the words, voice and footage inventory | A draft to sharpen; hero wording and footage choices still need an editor's eye |
| `build` | HyperFrames composition from timeline JSON, with word cues resolved and a `motion_report` | Requires actual media, a word map for `@` cues, and the assets called for by the declared audio policy |
| `review` | Acceptance review of a build (and with `--video`, its render) against `style_spec.json`: word sync, legibility, full-size presence, progression, transitions, showpieces, sparse sound, forbidden patterns, pacing, calibration regression | Measures the house style; it never checks claims and cannot judge taste |
| `track` | Face track of a video (full size, lowered, away) | Haar detection misses profiles and heavy blur; smoothing bridges short gaps |
| `render` | Local deterministic HTML/media rendering | Requires Node/HyperFrames, browser dependencies and FFmpeg |
| `finalize` | Audio mastering and encoded measurements | Signal metrics do not replace listening |
| `check` | Editorial schema, time coverage, joins and render-hash checks | Cannot certify source truth or visual quality |
| `talking-head` | Kallaway-style edit of one raw talking-head: pause cut, -14 LUFS voice, SFX, stage plan or seeded motif rotation, style check, HyperFrames render, finalize. The lo-fi bed is off unless `--music` is passed | Recommended default for a new talking-head. Does not replace the house-style planner. Refuses to overwrite `--output` |
| `check-style` | Kallaway contract: hard cuts, caption length, shot bounds, SFX coverage, ending on the last word, brand colors and fonts | Measures the Kallaway preset only. House-style reviews stay on `review` |
| `review-player` | Local video comparison/review page | User or agent still makes the perceptual judgments |
| `production/compare_style.py` | Frame-by-frame review of a 20-second Brandon calibration and manually selected reference intervals | Requires original footage and lawfully available reference files; it does not score or approve resemblance |
| `manychat-prepare` | Validated local handoff packet | No flow authoring, subscriber mutation or sending implementation |

Use `python plugins/brandon-reel-engine/scripts/reel.py run ACTION -- --help` for each action’s real arguments. The `build` action checks its required `--spec` before dispatch, so inspect `python production/editor/edit.py build --help` for build flags.

## Editing controls

Presenter-first layouts with full-size framings that open negative space, full-frame 2.5D screen shots with word-cued focus crops, full-screen B-roll, and optional stage and split layouts; source in/out ranges; pixel crops; image/video fitting; directed camera moves (push, punch, shake); independent short pop captions (white, at most one green word) and larger designed graphics; 19 word-cued motion components (hero in six variants, callout tags, the 2.5D payoff reveal, particles, headline, statement, card, stat, flow, orbit, device, chart, checklist, compare, prompt, spotlight, badge, equation, CTA); optional depth matte for a word behind Brandon; timed source labels; resource previews; authored explanatory scenes; synthesized, voice-relative SFX by role (soft bubble pops, quiet whooshes, one restrained impact) with sparse planning and a phone-speaker check; purposeful transitions (push-in, match move, shape wipe, punch, whip, zoom blur, full-frame light leak, iris/expand); no background music; a build `motion_report`; final encode and loudness receipts. Details: [motion system](../skill/references/motion-system.md).

## Source judgment

Map every beat to a viewer question, visual job, important spoken word, placement and reading hold. Accept Brandon's filmed statements as the script. Use supplied captures and animated graphics for comprehension without requiring a corroborating source. Never add production disclaimers to the picture.

## Creative quality

A legible opening; spoken-beat timing without a fixed cut interval; animated authored text/cards/illustrations and purposeful transitions even when not prescribed; speech-intelligible effects without background music; undamaged word boundaries; no caption/focal-detail collision or disclaimer overlay. Store what was observed, what failed and what was repaired. Check the current render rather than carrying a previous version’s pass forward.
