---
name: reel-edit
description: "Edit Brandon's original footage into a source-backed reel with independent spoken captions and animated green/white editorial graphics."
---

# Reel editing

Resolve the project with `<plugin>/scripts/reel.py context`; read [Brandon's style profile](../../references/brandon-style-profile.md), [operator runbook](../../references/operator-runbook.md), [shot recipes](../../references/shot-recipes.md) and `<project>/production/editor/README.md`.

Preserve original footage and voice. Choose the take, verify words and remove only failed takes or genuinely distracting pauses. Rebuild word timings and all dependent cues after any speech trim. For each spoken claim, record its source, what is actually proved, the viewer's question, the useful visual job, and the important word that anchors a reveal. Use A-roll for personal assertion, pivot, judgment and CTA; recorded screen proof for an asserted action/result; contextual footage for a recognizable setting; kinetic graphics to simplify a verified mechanism. A mock interface is never evidence of a completed action.

Prepare at least two different filmable hooks for the same supported claim. Select based on the footage and first-frame clarity. Cut when meaning or visible action changes, never to a fixed schedule. `presenter`, `full_broll` and `split` are choices; use split only when both face and proof can be read. Keep the face and required UI text inside safe areas.

Build two *independent* timeline systems: `spoken_captions` for short exact word-timed lower-third phrases, and `editorial_graphics` for larger green/white statements tied to a `claim_id`. Each has its own timing, position, style and visibility. Use `#49cf26` as Brandon's requested accent, not a measured reference value. Graphics may paraphrase a supported statement but may not convert a draft, proposal or possible future action into proof. Keep source labels distinct.

Choose a rights-cleared bed when the current audio plan calls for music; set `audio_policy.music_required:true` and provide a valid track. An intentional music-free edit has `music_required:false` and `music_free_reason`. Add effects where they help a reveal and listen at phone volume to preserve consonants. Do not reuse an old voice track or duplicate a full mixed reference soundtrack.

Build with `reel.py run build -- --spec TIMELINE --project COMPOSITION`, render and finalize the MP4. Inspect encoded frames after layer/crop changes, and watch with sound at normal speed. Record observed word coverage, source readability, graphic/caption collisions, face visibility, audible bed/effects and final hash. Make a 20-second calibration from original Brandon filming, compare each frame to relevant intervals from the three references, and leave the style approval pending Brandon's review. Send the current output, timeline, words, asset index and review record to `reel-review`; a successful encode does not approve an edit.
