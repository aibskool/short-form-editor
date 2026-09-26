# Quality procedure: separate a playable export from a good edit

Read `production/editorial-judgment.md` for the five scored dimensions and hard failures. This procedure tells a smaller model what to inspect, what evidence to save, and what to do with a failure. A missing observation stays missing; do not fill review fields with assumed success.

## Before the expensive render

1. Check every planned beat against the actual words. Its asset must answer the viewer question; a relevant URL alone is not enough. Check every selected file exists, was inspected, and matches its indexed hash.
2. Check static source claims against the original source. Read the exact crop, not just its heading. Count figures/roles manually where a number matters. Read app/model names and compare input/output examples. Remove wrong or irrelevant evidence.
3. Check a frame near each shot's first useful moment and reading hold. Empty/black/covered B-roll, clipped faces, hidden captions and tiny required text are failures. If source text is dense, crop to the specific clause rather than shrinking a whole page.
4. Run HyperFrames check on the built project. Inspect its actual errors/warnings; do not call disabled motion assertions passed. The editorial checker checks structure and joins, not truth or readability.
5. Confirm `music` is empty and `audio_policy.music_required:false`; inspect animation of every on-screen text, card and illustration. Check purposeful transition effects at relevant boundaries, opening variety and moving B-roll source bounds.
6. Review intra-sentence idle gaps as well as false starts. For gaps above roughly 180 ms, inspect waveform and real word boundaries; shorten expendable silence toward 70–120 ms only where the phrase remains natural. Check the frame-aligned keep EDL preserves consonants, breaths that carry delivery, every intended word and the complete CTA. After any cut, confirm words, captions, shots, labels, transitions and SFX all use the new timebase. ASR gaps and silence-detector output propose cuts; they do not approve them.

Before approving a sourced shot, finish: **“At [time], I can read/recognize [exact focal detail]; it explains [specific spoken action/relationship].”** If the answer is only “the page is there” or “it says the same noun,” selection failed. Save the proposed crop and the rejected alternative. Compare reference/candidate caption frames at equal display size before rendering the full cut; matching resolution alone does not match typography or treatment.

Observed lower-tier regression: an eight-second test passed all render checks but showed a tiny full Wikipedia Judge page, an INVESTOR question card and opaque black caption panels. Those are a semantic fit/readability/style failure, not a successful proof-visual workflow. Replacing the screenshot with another whole page or making the captions larger does not repair the underlying issue.

## Review the actual encoded MP4

1. Run `production/finalize_render.py` on a new output path. It performs a complete decode, normalization and hash receipt. Council's working target was about -14.2 LUFS and -1 dBTP; it is a reference calibration, not a guarantee of identical perceived loudness. Check both stream durations and that the final spoken word remains intact.
2. Extract encoded frames at opening, each meaningful reveal, and the final CTA. Inspect the encoded output, not only HTML snapshots. A previous untimed opaque layer hid B-roll in the render even though browser checks were clean.
3. Watch the whole candidate at normal speed with sound. Check lip sync, first/last word, clause continuity, reading time, accents, abrupt audio ends and whether each reveal meets its spoken anchor. Then replay risky spans with the preceding/following sentence.
4. Check at phone size. Can the required source detail be read once without pausing? Does typing reach a useful state and hold? Do source overlays compete with captions? Does a platform control area cover something essential? Use the actual destination layout, not one universal safe-area number.
5. Record visible/audible observations with timecodes, dimensions scored 0–4, and specific repairs. Default editorial passage requires at least 16/20, every dimension at least 3, no hard failure, complete beat coverage and the actual render watched. If the model cannot perceive full playback/audio, deliver a candidate with those gates pending and request the missing review; it cannot certify itself from images or predicted scores.

## First-frame and two-second cold-view test

Before finalizing the intro, show a fresh reviewer **only the actual first encoded frame, paused at phone size**, withholding sound, script, brief and intended interpretation. Ask: **“What topic or tension do you recognize, and which visual made that clear?”** Save that answer before playback. Then show the first two seconds muted and with sound at normal speed to check how the claim develops.

Pass requires an immediate understandable subject or tension; the payoff may develop through Brandon's speech. A giant number still needs a unit or other context. If the response is only “some app menus” and the actual opening does not clarify the claim, repair hierarchy or crop. An operator already briefed on the script must not label a self-check as unbriefed. This checks comprehension, not guaranteed attention or virality.

Record `opening.cold_view` with `status`, `first_frame_path`, `first_two_seconds_path`, `display_width_px`, `muted`, `brief_hidden`, `reviewer`, `subject_response`, `payoff_response`, `focal_detail_response`, `first_frame_subject_visible`, and `limitations`. Put a developing payoff observation in the two-second playback note, not in an invented first-frame answer. Use `passed`, `failed` or `pending`; keep missing responses null. The evidence belongs to the current `render_sha256`.

### Opening motion at scrolling speed

Play the first 3–5 seconds at **1× and phone size**, then identify the first useful action and each hold. Assess whether a change or hold serves the spoken claim. There is no fixed cut interval or hold limit. Tiny hidden movements or caption changes alone do not repair an unrelated or confusing image. Brandon's face-to-camera delivery can carry an intentional longer shot.

Record `opening.motion_cadence` from the actual export: `first_visible_action_seconds`, `first_visible_action`, `shot_spans`, `unchanged_visual_spans`, `max_observed_unchanged_seconds`, `split_intro`, `normal_speed_checks` and `status`. Each span contains `{start,end,duration,observed}` in reel seconds. `split_intro` records `{used,duration_seconds,reason}` only when chosen. Each normal-speed check records `{start,end,display_width_px,observed,evidence_path,reviewer}`. Numeric timing alone does not prove usefulness or retention.

## Check audio, opening energy and motion explicitly

Complete these checks against the encoded final render:

| Check | What to inspect and record | Repair when weak |
|---|---|---|
| No background music | Listen across the full export for a musical bed, including source audio. Confirm the timeline contains no music. | Remove the bed and rerender. Brandon adds music on platform. |
| Speech and SFX | Listen at phone volume to intro, body and ending; log actual audible onset against the spoken word and graphic frame, and consonant clarity. | Move, shorten or rebalance a selected effect. |
| First frame/opening | Run the cold-view and normal-speed motion checks; compare claim clarity with all supplied reels. | Choose a stronger physical action, face delivery or relevant proof. |
| Animated graphics | Inspect entrances and internal motion of every visible text/card/illustration, including labels. For custom UI cards/grids/stats log any span exceeding two seconds without a useful change. | Animate a word-cued reveal, count, contrast change or camera move; remove inert decoration. |
| Transitions | Record the boundary, effect and why it helps the new section; inspect actual frames around it. | Add or revise purposeful blur, wipe or light leak; avoid repetitive effects at every cut. |
| Proof and variety | Inspect real screen details, illustrative footage, face and full-screen choices against each spoken claim. | Crop relevant proof, change view or simplify when weak. |

Copy `<plugin>/templates/creative-review.json` beside the timeline. Record the exact render hash, source-backed claim checks, no-music listening check, word-to-frame graphic cues, negative-state contrast, fixed lower-third safety, animation and transition spans, caption and editorial graphic checks, SFX, cold-view and full playback observations. A planned cue is not observed playback. Historical Samin/Mobbin notes below describe that earlier pilot and do not change Brandon's audio policy.

## Concrete pass/fail examples

These are **illustrative decisions**, not claims that a particular render already passed. Apply them to the current reel's actual times and files.

| Gate | A pass establishes | Fail or pending example |
|---|---|---|
| No background music | Full playback confirms voice and selected effects without any music, including music embedded in source audio. | Any audible bed or a `music` timeline entry: **failed**. Unreviewed audio: **pending**. |
| Beats and stronger SFX | The reviewer hears a distinct intro accent at the important visual reveal, plus clear body action accents, and can understand the nearby words. Cue records identify actual visual/audible-onset times. | SFX file starts at 1.40 s but its silence delays the click until 1.85 s after the visible action; move its useful onset. A louder whoosh hides a word: **failed** until repaired. |
| Opening hierarchy | An unbriefed viewer can recognize topic or tension from the first frame; subsequent speech and visuals develop the payoff. The Mobbin hierarchy is historical upstream context, not a mandatory Brandon layout. | A giant number lacks its unit, or unrelated menus remain the only visual clue: **failed** if the actual opening stays unclear. Informed self-check only: unbriefed test **pending**. |
| Opening motion | The chosen hook establishes topic and tension, then changes view or action when the spoken claim calls for it. Split is optional. Actual spans and first action are recorded. | A clear graphic stays substantially unchanged for 4 seconds with only a 1% zoom: **failed**, even if every encoded frame technically differs. An unchanged hold fails only when it obscures meaning or loses attention; a file called “video” is no substitute for observed action. |
| Moving proof and diversity | A real recording shows the relevant settings action and resulting state, with enough time to recognize it. Another beat uses a different useful view/detail; full-screen motion is used when it improves the result. | An `.mp4` contains a frozen screenshot, or the same tiny crop repeats under several claims: motion/diversity is not established. An unrelated impressive demo does not become proof because it moves. |
| Static-proof zoom | Start, moving and end frames retain the product/source context and exact supporting clause at phone size. A gentle move leads attention and settles for reading. | The count/qualification is cropped out at the end, or constant panning prevents one reading: **failed**. Stop or redirect the move; an intentional readable hold can pass. |
| Pause cuts and 1× speech | A verified 300 ms quiet gap is shortened to roughly 100 ms using valid frame boundaries, the adjacent words sound complete at 1×, and every later cue uses the rebuilt time map. A deliberate pause can remain with a reason. | A silence detector removes the start of a soft consonant, a 1.1× speed-up is substituted without instruction, the CTA loses its last syllable, or captions retain old times: **failed**. No actual listening: **pending**. |

Run the final gates in this order: **complete speech and timing → source honesty/readability → opening and motion → music/SFX mix → whole-reel normal-speed review**. Repair in that order when defects interact: changing speech after a sound pass invalidates its cue timing, and changing the mix invalidates prior listening approval. A missing observation stays `pending`; a known violation is `failed`. Both prevent a claim of final editorial passage. Continue useful repairs, and show a candidate with its exact remaining review need when perceptual access is unavailable.

Judge representation from the actual graphic. An obvious sourced montage/stat card does not fail for lacking an “illustration” badge. Require explicit reconstruction/illustration labelling only when a viewer could mistake authored content for a live UI or generated/executed result; preserve clear attribution and reject any false execution claim.

## Synchronized comparison tool

For two aligned versions of the same performance:

```bash
python3 production/build_review.py --reference /absolute/reference.mp4 \
  --candidate /absolute/candidate.mp4 --out /absolute/outputs/REEL-comparison \
  --title 'Reel comparison' --moments /absolute/review-moments.json
```

`review-moments.json` is a list such as `[{"time":4.4,"label":"README reveal"}]`. Open the output `index.html` in a browser. Play both together, choose one soundtrack, seek to a relevant beat, or select Candidate only for a larger phone-like view. The package contains original MP4 copies and their hashes. Equal duration does not prove alignment; establish that separately. Compare an unrelated style reference independently instead.

The player, successful playback automation, a contact sheet, ASR, loudness analysis and provider scene descriptions do not automatically set editorial approval. The review record must state what the reviewer actually observed.

## Optional automated second opinion

Higgsfield's scene analysis can supply a whole-clip scene/audio summary. Its timestamps are coarse and its visual interpretation can be wrong. On Council v2 it reported five characters in a four-character illustration; direct frames at 6.98, 7.50, 8.20 and 8.90 seconds showed four. Preserve that discrepancy as a rejected machine finding. Do not edit a correct shot solely to satisfy a model's mistaken description.

An available hook/attention predictor can inform creative experiments, but its score is not evidence of actual retention, virality or editorial correctness. Record its provider, exact input hash, status, findings and limitations separately from the editorial rubric. Compare suggestions to actual frames, narration and sources before changing the edit.

Use this prompt for an independent reviewer with the actual video and source manifest:

> Inspect the provided final reel and all three Brandon style references. For every spoken beat, describe what is actually visible and the viewer question it answers. Evaluate presenter, real screen proof, illustrative footage and kinetic graphics by their claim; check lower-third spoken captions separately from larger green/white editorial graphics. Check the chosen hook, face-to-camera keyword CTA, absence of background music, purposeful effects and readable holds. Identify unsupported proof, wrong entities/counts, illegible focal details, repetitive or inert shots, mistimed reveals, text collisions and sound that masks speech. Report exact timecodes and one actionable repair per defect. Distinguish observations from uncertainty. Do not infer live product execution from a reconstructed interface. Do not assume the source manifest proves the rendered pixels match it. State whether you watched the full video with sound, what phone-size checks you performed, and any tool limits. Score only dimensions you can actually assess.

## Repair table

| Failure | First repair | If still weak |
|---|---|---|
| Real source is irrelevant or misleading | Replace it with evidence for the actual claim; narrow claim if needed | Presenter or identified explanation; keep evidence gap explicit |
| Required source words are tiny | Crop tightly while retaining needed identity/qualification | Full-screen insert, fewer required words or longer hold |
| Typing/scrolling finishes too late | Cut dead setup/waiting and hold the completed useful state | Before/after stills with honest presentation, or a different shot |
| Too much text | Keep one focal phrase; use short captions; remove redundant graphic copy | Show a concrete action/object instead |
| Weak proof timing | Move reveal/crop to the important noun or action | Split the beat into setup and payoff |
| Generated count/identity changes | Revise with an approved still and explicit count/action | Deterministic illustration or relevant real asset |
| Background music in a Brandon export | Remove it and listen to the full render | Deliver only a review candidate until the rerender is clean |
| Intro is static or visually weaker than the body | Lead with the strongest relevant motion/result and a useful detail/payoff | Reframe static proof deliberately; preserve reading time and source context |
| Repetitive B-roll or gratuitous motion | Change the relevant action, source region, scale or full-screen/split treatment | Replace weak footage; keep an intentional still when it gives stronger proof |
| SFX too quiet to register | Raise the selected accent while listening with voice | Choose a clearer/shorter effect or move it into a gap |
| SFX masks a word | Lower or move that effect; listen in context | Remove it; voice clarity takes precedence |
| Intra-sentence pauses make the delivery drag | Verify the actual quiet gap and shorten it with a frame-aligned keep EDL | Preserve a natural join; retain the pause if it carries meaning or protects speech |
| Tightening clips a consonant or causes later cues to drift | Restore speech handles and rebuild the complete time map/cues | Recheck every changed join, late sync and the final CTA at normal speed |
| Blank or frozen visual | Inspect timed layers, media duration/source offset and renderer output | Replace/fix the asset; do not silently loop broken footage |
| Last syllable missing/audio tail wrong | Check sample/timestamp continuity and actual decoded tail | Correct finalizer/input timing, then re-export and verify |
| Goal requires playback the model cannot assess | Keep review pending and provide an easy comparison artifact | Obtain the missing perceptual review; never fabricate a pass |

After a repair, inspect the changed span and its neighboring beats, then re-render. A changed output hash invalidates prior full-render approval. Unchanged encoded video packets can preserve frame observations through an audio-only remux, but audio observations need refreshing. Run `production/check_editorial.py --map /absolute/editorial-map.json` after updating the real map; its output must still say semantic review is required.

## Finish the handoff

### Lessons from the Mobbin blind edit

The Mobbin pilot used another raw take without a matching finished reel. Its first-frame review caught three practical errors before delivery: a welcome screen used for the word “profiles,” a desktop typing strip too small to read, and a count buried under a larger generic headline. Replace an adjacent category with the exact visible noun (avatar/name/Profile controls), punch into the active instruction, and crop the original count clause at the count's spoken moment. A source being authentic does not make its placement useful.

For full-screen phone clips, inspect both outer edges in the actual render. `object-fit: contain` on a video can leave the presenter visible at the sides in the native compositor even when the video element has a CSS background. The editor now places a separately timed full-panel background behind every media insert. Verify that it disappears when the presenter returns. Keep the source recording's audio muted and align deliberate SFX to the recorded or illustrated action.

The editable example and its proof inventory live at `<project>/production/pilots/mobbin-v1/`. Its original redesign illustration is explicitly labelled; official product demos are attributed and never described as an authenticated run performed by this pipeline. The real MAP giveaway contains setup guidance and original prompts, not a copy of the third-party screenshot library. Frame inspection and mechanical checks remain separate from Samin's playback approval.

Samin's playback feedback on that historical pilot identified a missing music bed and requested stronger SFX, more opening action, slow zooms on static evidence, more diverse views and more moving/full-screen B-roll. A technical/audio-stream pass did not catch the missing creative layer. Use it as an example of why a render needs human review, not as Brandon's required edit prescription; judge the new edit by its own actual render and Brandon references.

Deliver the final/candidate MP4, optional comparison package, editable timeline, source/asset index, real giveaway and review receipt. Push the skill/code/metadata to the existing local project repository; use release assets for large review exports. Verify uploaded sizes/hashes. Update existing Multica records with the exact version and observed status. Keep credentials out of Git. A private release is not an Instagram post, Skool post or ManyChat delivery. Use the existing delivery workflow when publication is actually requested.

The system's smaller-model usability should be tested with a fresh model and a bounded new reel/shot assignment. Keep its output and errors, then refine the instructions. Until such a test succeeds, describe this as a detailed, checked playbook—not a proven guarantee that every weaker model produces the same quality.
