# Operator runbook: finish one reel without inventing the process

Use this when editing Brandon's original footage. Read [the observed style profile](brandon-style-profile.md). Work one reel and one stage at a time. The goal is a reviewable video built around his recorded story and visual rhythm.

## Resolve the job

In the plugin, run `python3 <plugin>/scripts/reel.py context`; it resolves the explicit project, `BRANDON_REEL_PROJECT`, local configuration, a legacy Samin configuration with a notice, or the source checkout. Use `python3 <plugin>/scripts/reel.py --project /absolute/checkout configure` to bind a known checkout. All `production/...` paths below are relative to the project, not this references folder or the installed plugin cache.

Collect from the existing conversation/files: reel ID, source recording or Drive folder, spoken script or transcript, reference reel, giveaway promise, current stage, and permitted destinations. Reuse already supplied inputs. Ask only for a missing input that prevents the next action. A missing optional preference is not a reason to stop.

Use a new `production/pilots/<reel-id>/` for metadata, `work/<reel-id>/` for originals/intermediates, and `outputs/` for final deliverables. Large media stays outside Git except intentional small reusable B-roll. Preserve prior renders and user edits. Do not copy Council's script, timestamps, reference soundtrack or giveaway into a different story.

Maintain one `operator-state.json` with `reel_id`, `stage`, `input_paths`, `completed_artifacts`, `current_issue`, `next_action`, `render_sha256`, and `review_status`. Store only observed state. A path, generation ID or queued job is not a finished asset. Update this record when a stage finishes so another model can resume without rediscovery.

Brandon's supplied reels combine original face-to-camera delivery, short lower-third spoken captions, a separate green/white editorial graphic system, screen captures, contextual footage, and selected effect accents. Accept Brandon's recorded claims as the script. Do not add claim-accuracy or supporting-evidence checks to the editing path, and do not let a missing capture veto a spoken beat. Background music is prohibited in Brandon short-form exports; he adds it on the platform. Record the opening, both text tracks, assets and actual review observations in `creative-review.json` using [quality procedure](quality-procedure.md).

## Repeatable order for a filmed reel

Use this short execution checklist when resuming with limited context. Each checked item needs its named artifact; do not substitute a prose promise.

1. **Resolve and preserve.** Read `operator-state.json`, locate the selected master/take, verify its identity and create a new revision directory. Save the source and current-render hashes. Read only the selected script, house-style notes and current failure.
2. **Finish speech first.** Inspect false starts and small intra-sentence pauses using the waveform and real words. Save the frame-aligned keep EDL, cut reasons, complete 1× A-roll and retimed word list. Review changed joins, then the entire selected speech including the CTA. A gap proposed by ASR is not an approved edit. If speech changes later, return here and regenerate all dependent timings.
3. **Plan hook and sound early.** Write the spoken subject/tension and at least two different hook treatments. Choose face-to-camera, a physical action or a relevant visual detail. The first frame must be understandable, and subsequent changes should follow useful action and comprehension. Split is optional. Obtain actual visual files and name source bounds, spoken anchors and selected audio accents before polishing.
4. **Build a short opening check.** Export and review at phone size and normal speed, muted and with sound. Record the first visible action, whether topic/tension is clear, and whether any unchanged span weakens comprehension. Repair actual failures, without a fixed one-second gate. Check both text tracks independently and listen for speech/effects.
5. **Complete and render.** Apply the same beat-to-visual method to the body and actual giveaway. Vary relevant actions/views and use full-screen motion where useful. Build, check, render and finalize on a new path. Record the real output hash and run the complete review below.
6. **Return a reviewed edit.** Complete `creative-review.json`, repair weak visual/audio spans, then re-export/recheck. Deliver `passed` only when the observed editing checks pass; otherwise deliver a review candidate with specific pending items. Background music, damaged speech, static authored graphics or missing purposeful transitions cannot be hidden by a successful encode. Do not place production disclaimers or caveats in the reel.

The command shapes below and linked playbooks implement these steps. The [quality procedure's pass/fail examples](quality-procedure.md#concrete-passfail-examples) show exactly what each observation must establish. This checklist is executable guidance for any operator; it does not claim that a model which cannot perceive audio/video can certify those observations.

## Execute the stages

| Stage | Read now | Do | Observable exit |
|---|---|---|---|
| Research/voice, if no filmed script | [pipeline operations](pipeline-operations.md), voice guide and three fitting samples | Ideas → clean script → giveaway; collect useful visuals | Draft and resource exist; shot requests have reasons |
| Intake | `production/intake/README.md` | Download complete selected recording, verify bytes/hash, transcribe/index, inspect take and CTA | Correct source and complete selected performance are identified |
| Select/edit speech | `production/prepare_take.py --help` and existing pilot EDL | Remove false starts and repeated lines; preserve the speaker's claim; retime words | Edited A-roll and words refer to the same source/timebase |
| Calibrate the reference | Existing measured reference profile and selected reference frames; see below | Compare presenter, metaphor, screen/typing and caption treatments | Record a concrete visual target and unacceptable deviations before sourcing |
| Visual plan | [asset playbook](asset-playbook.md) and [shot recipes](shot-recipes.md) | Map every spoken beat, plan the strongest opening action/variety and effect accents | No unassigned beat; proof/illustration distinguished; opening and audio plan recorded |
| Obtain assets | [asset playbook](asset-playbook.md); [generation recipes](generation-recipes.md) only for a real gap | Capture actual moving sources first where useful; obtain SFX; author only missing explanations | Selected visual/audio files opened, checked, indexed and hashed; no music and documented SFX |
| Assemble | [shot recipes](shot-recipes.md), `production/editor/README.md` | Build timeline, useful motion, short captions, no music and selected action accents; inspect and render | Playable MP4 has the intended voice and SFX, not only an audio stream |
| Judge/revise | [quality procedure](quality-procedure.md) | Inspect opening energy/diversity, useful motion, meaning, reading time and audible mix | Review names the exact render, voice/SFX observations and motion checks; limits explicit |
| Deliver | `production/delivery/README.md`, Skool/ManyChat references | Package video, assets, editable files, giveaway and verified task/release links | User can open the video; publishing/delivery states are reported separately |

Do not read every source transcript or the entire repository into context. Load the selected take, current beat/asset list, relevant recipe, and current failing receipt. For a revision, read its changed beat plus the preceding/following beats.

## Calibrate before choosing visuals

For Brandon's supplied references, read [Brandon's style profile](brandon-style-profile.md) and inspect the actual reels. Compare presenter, screen proof, illustrative footage, spoken captions, editorial graphics and CTA separately. The Council profile in `production/reference/council-human/` is a historical upstream example; its private files are not bundled and its measured layout is not a target for Brandon.

Save one comparison frame each for presenter, metaphor, UI/typing and source evidence when present. Record caption treatment, useful reading hold, framing and the action shown. Choose one short matching style sample before assembling the whole reel. An eight-second test with two mostly static information diagrams may improve semantic honesty but still fall short of this reference's motion and visual language.

For a new reference, create the same small profile from actual observed frames/playback and measured cut candidates; do not invent exact fonts or sound-effect identities. Keep observations separate from editorial interpretations. Reuse an existing profile only when it describes the supplied reference.

## Exact working commands

Run from the repository root. Replace example paths with existing files; use new output directories per run. These commands are helpers, not an unattended end-to-end agent.

```bash
# Optional: transcript/index for a NEW complete filming batch.
python3 production/intake/intake.py --source /absolute/master.mp4 \
  --drive-metadata production/intake-source.json \
  --out production/intake/runs/NEW-RUN --work-dir /absolute/work/NEW-RUN --threads 4

# Apply inspected source-relative trims and map the words.
python3 production/prepare_take.py --source /absolute/source.mp4 \
  --transcript /absolute/source-transcript.json --edit /absolute/edit-decisions.json \
  --output /absolute/work/NEW-RUN/aroll.mp4 --words-output /absolute/work/NEW-RUN/words.json

node production/capture_evidence.cjs --sources /absolute/sources.json --out /absolute/work/NEW-RUN/captures
python3 <plugin>/scripts/reel.py run build -- --spec /absolute/timeline.json --project /absolute/work/NEW-RUN/composition
production/editor/node_modules/.bin/hyperframes check /absolute/work/NEW-RUN/composition --at 1,5,10 --json
python3 production/editor/edit.py render --project /absolute/work/NEW-RUN/composition \
  --output /absolute/work/NEW-RUN/raw.mp4 --quality high --workers 2
python3 production/finalize_render.py --input /absolute/work/NEW-RUN/raw.mp4 \
  --output /absolute/outputs/NEW-RUN.mp4 --receipt /absolute/verification.json
python3 production/check_editorial.py --map /absolute/editorial-map.json
```

Set `audio_policy.music_required:false` and omit `music` for every Brandon short-form build. Copy `<plugin>/templates/creative-review.json` to the pilot directory and fill observations, including fixed lower-third placement, transcript cleanup, word-cued graphics, negative-state color/opacity, transitions and a useful change within every two-second custom UI span.

The intake requires a cached Whisper model and the Python packages in `production/requirements.txt`; read its setup before running. The editor's Node packages come from `npm ci` in `production/editor`. `prepare_take.py` currently uses macOS `h264_videotoolbox`; on another OS change only that encoder to available `libx264` after checking FFmpeg, then verify the output. It overwrites its named outputs: give it new paths. Do not repeatedly transcribe an unchanged batch.

An EDL uses source seconds, e.g. `{"speed":1,"segments":[{"start":2.2,"end":7.6},{"start":8.1,"end":13.4}]}`. These numbers are a format example, not approved cuts. Cut between words, preserve breath/natural cadence and inspect at least the last spoken sentence after a proposed ending. If `prepare_take.py` already made continuous A-roll, the renderer's source segments should normally be `[0, edited_duration]`; do not apply the original cuts a second time.

Use the actual waveform and verified word boundaries to inspect failed takes and distracting idle gaps in Brandon's delivery. Do not trim a deliberate pause just to reach a target cadence. Preserve every intended word, consonant, natural join and the full CTA; keep the original speaking speed unless Brandon asks otherwise. An ASR timing gap alone is not proof of silence.

Apply frame-aligned cuts to every expendable silence of 0.5 s or more, including swallowing, retaining the source ranges and reasons; verify each audio join in context. Distinguish actual waveform silence from imprecise word-map gaps. Any speech trim changes the timebase: rebuild the word map and retime **every** caption, shot, label, transition and SFX cue before rendering. Recheck late-reel sync and the final word; never keep old absolute placements after tightening the voice. Use the existing CFR workflow below and preserve a copy of the prior edit.

For an existing timeline, run `prepare_take.py` first to create the tightened A-roll and new word list. Then use the reusable retimer rather than shifting timeline timestamps by hand:

```bash
python3 <plugin>/scripts/reel.py --project /absolute/checkout run retime -- \
  --spec /absolute/old-timeline.json \
  --cuts /absolute/pause-removals.json \
  --source /absolute/new-aroll.mp4 \
  --words /absolute/new-words.json \
  --output /absolute/retimed-timeline.json
```

`pause-removals.json` has `{ "source_duration": OLD_OUTPUT_DURATION, "cuts": [{"start": REMOVED_START, "end": REMOVED_END}] }`, replacing the uppercase placeholders with measured seconds. Its cuts are ordered, disjoint removed intervals on the **old output clock**, not the original filming-master clock unless those clocks are identical. This removal list is separate from the keep EDL used to prepare the new A-roll. Its `source_duration` must match the old timeline's summed `source.segments` duration; the helper rejects a mismatch.

The retimer remaps shots, nested scene item/fade/motion cues, labels, zooms, flashes, transitions and SFX onset times; points `source` at the tightened clip; and uses the new words. Recheck every effect after pause removal. Legacy music timelines must be migrated to the current no-background-music policy before building.

The helper does **not** retime actions baked into B-roll, source-video offsets, generated scene internals or the natural duration of an SFX file. Recheck typing, cursor clicks, results and effect tails against the new spoken anchors; manually trim/re-author affected visuals when needed. A fully removed shot/event requires an editorial decision rather than a silent deletion. The emitted `retime_review` is a work reminder, not proof of audiovisual sync.

For a verified constant-frame-rate proxy, add `"frame_rate":30` (or its actual rate) to the EDL and place every cut on that source frame grid **after checking speech handles**. The helper validates the declared rate and boundaries, trims exact frame indices and bypasses tempo processing at speed 1. It rejects off-grid cuts instead of moving them silently. Probe metadata alone cannot establish constant frame rate; use a known CFR proxy. Legacy EDLs still use timestamp trims, whose video-frame padding can make later audio/words drift from the ideal summed duration. Verify actual output duration and joins before accepting their retimed captions.

Treat implausibly long ASR token spans (review ordinary single words over roughly 1.2 seconds), repeated zero-duration tokens or missing restart text as an intake defect to investigate. Transcribe the suspicious source interval with short surrounding handles, inspect its waveform and compare the repetitions before choosing a cut. Mobbin's 3.3-second `library` span hid a repeated sentence; a stretched `600,000` hid two failed starts. Do not just delete an apparent gap inside that token. After cutting, compare a fresh transcript of the actual A-roll with the selected speech, retaining the complete CTA. ASR/waveform checks do not constitute human listening approval.

## Reuse versus discovery

Council v2 is a **historical upstream example**: `production/pilots/council-v2/` and its private release are not bundled. Its data shapes can illustrate the earlier pipeline, but its visual grammar, duration, shot count and caption count are not Brandon targets. Calibrate a new Brandon render before making a style claim.

If a tool fails, read the error once, check its documented input, make a specific correction, then retry. After two materially different attempts fail, record that dependency as unavailable and take the recipe's fallback. Do not repeatedly guess selectors, generation flags, account IDs or download URLs. Continue independent work, and identify the exact missing dependency if it prevents delivery.

## Smaller-model handoff prompt

> Use Brandon Reel Engine, resolve the project with its runner, and read the operator runbook and style profile. Resume the existing reel stage. Preserve original speech; map each spoken claim to face-to-camera A-roll, actual readable screen proof, contextual footage or kinetic graphics. Keep short spoken captions independent from large green/white editorial graphics. Choose hooks and cuts by meaning, not a fixed interval or split. Finish the real audio plan and encoded review, record the exact hash, and leave style matching pending until Brandon reviews a 20-second calibration render.
