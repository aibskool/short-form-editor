# Capabilities and exact boundaries

The skills direct an agent; the helper commands execute specific local operations. A skill is not an always-running service or a replacement for provider credentials.

| Runner action | Included implementation | Boundary |
|---|---|---|
| `research` | Discovery and source records for new story ideas | Optional for filmed edits; never a claim-accuracy or supporting-evidence release gate |
| `pipeline` | Init, status and validation of the research → idea → script → resource packet | Structural readiness is not approval or publication |
| `script-check` | Spoken-word/beat counts and duration estimates | Actual voice timing comes from the recording |
| `intake` | Local Whisper transcription and script-take indexing | Needs local video, script samples and model dependencies |
| `take` | Reviewed cuts, selected take and retimed word map | No automatic certification that a cut sounds natural |
| `retime` | Remap supported outer cues after speech edits | Native actions inside clips and effect tails need review |
| `capture` | Source captures through an isolated local Chrome session | Needs a Chrome executable and public source URLs; does not reuse signed-in cookies |
| `build` | HyperFrames composition from timeline JSON | Requires actual media and the assets called for by the declared audio policy |
| `render` | Local deterministic HTML/media rendering | Requires Node/HyperFrames, browser dependencies and FFmpeg |
| `finalize` | Audio mastering and encoded measurements | Signal metrics do not replace listening |
| `check` | Editorial schema, time coverage, joins and render-hash checks | Cannot certify source truth or visual quality |
| `review-player` | Local video comparison/review page | User or agent still makes the perceptual judgments |
| `production/compare_style.py` | Frame-by-frame review of a 20-second Brandon calibration and manually selected reference intervals | Requires original footage and lawfully available reference files; it does not score or approve resemblance |
| `manychat-prepare` | Validated local handoff packet | No flow authoring, subscriber mutation or sending implementation |

Use `python plugins/brandon-reel-engine/scripts/reel.py run ACTION -- --help` for each action’s real arguments. The `build` action checks its required `--spec` before dispatch, so inspect `python production/editor/edit.py build --help` for build flags.

## Editing controls

Presenter-only, split and full-screen B-roll layouts; source in/out ranges; pixel crops; image/video fitting; directed camera moves; independent short spoken captions and larger green/white editorial graphics; timed source labels; resource previews; authored explanatory scenes; local SFX and purposeful transitions; no background music; final encode and loudness receipts.

## Source judgment

Map every beat to a viewer question, visual job, important spoken word, placement and reading hold. Accept Brandon's filmed statements as the script. Use supplied captures and animated graphics for comprehension without requiring a corroborating source. Never add production disclaimers to the picture.

## Creative quality

A legible opening; spoken-beat timing without a fixed cut interval; animated authored text/cards/illustrations and purposeful transitions even when not prescribed; speech-intelligible effects without background music; undamaged word boundaries; no caption/focal-detail collision or disclaimer overlay. Store what was observed, what failed and what was repaired. Check the current render rather than carrying a previous version’s pass forward.
