# Capabilities and exact boundaries

The skills direct an agent; the helper commands execute specific local operations. A skill is not an always-running service or a replacement for provider credentials.

| Runner action | Included implementation | Boundary |
|---|---|---|
| `research` | Primary GitHub discovery/release collection and source records | Agent evaluates relevance and checks claims; not an automatic news truth engine |
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

Presenter-only, split and full-screen B-roll layouts; source in/out ranges; pixel crops; image/video fitting; directed camera moves; independent short spoken captions and larger green/white editorial graphics; timed source labels; resource previews; authored explanatory scenes; local SFX; continuous music with volume envelopes; final encode and loudness receipts.

## Source judgment

Map every beat to a viewer question, visual job, claim, source, important spoken word, placement and reading hold. Keep repo/author/context visible when it matters. Treat product marketing as a claim, not an independent measured result. Keep screenshots, demonstrations and authored illustrations distinguishable.

## Creative quality

A legible opening; claim-led timing without a fixed cut interval; actual readable proof; speech-intelligible music and effects; undamaged word boundaries; no caption/focal-detail collision; real giveaway contents. Store what was observed, what failed and what was repaired. Check the current render rather than carrying a previous version’s pass forward.
