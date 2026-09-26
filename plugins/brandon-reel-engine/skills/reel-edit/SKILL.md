---
name: reel-edit
description: "Edit Brandon's original footage with independent spoken captions and animated green/white editorial graphics."
---

# Reel editing

Resolve the project with `<plugin>/scripts/reel.py context`; read [Brandon's style profile](../../references/brandon-style-profile.md), [operator runbook](../../references/operator-runbook.md), [shot recipes](../../references/shot-recipes.md) and `<project>/production/editor/README.md`.

Preserve original footage and voice. Choose the take, correct the transcript against speech and remove failed takes or distracting pauses. Rebuild word timings and all dependent cues after any speech trim. Accept Brandon's spoken story without checking claim accuracy or demanding supporting evidence. Map each beat to the viewer's question, the useful visual job and the word that anchors a reveal. Use A-roll for personal assertion, pivot, judgment and CTA; supplied screen captures, contextual footage and kinetic graphics wherever they make the story clear. A missing capture must not suppress a spoken beat.

Prepare at least two hook treatments for the same spoken story. Select based on the footage and first-frame clarity. Cut when meaning or visible action changes, never to a fixed schedule. `presenter`, `full_broll` and `split` are choices; use split only when both views can be read. Keep the face and required UI text inside safe areas.

Build two *independent* timeline systems: `spoken_captions` for short exact word-timed lower-third phrases, and `editorial_graphics` for larger green/white statements tied to a story beat. Each has its own timing, position, style and visibility. Use `#49cf26` as Brandon's requested accent, not a measured reference value. Animate cards or status graphics around the spoken words. Do not add disclaimer or verification-status labels to the video.

Never mix background music into Brandon short-form exports. Set `audio_policy.music_required:false` and omit `music`; Brandon adds music on the platform. **Every reel must animate on-screen text, cards, labels and illustrations and use purposeful visual transitions at appropriate cut or section boundaries, even when the assembly omits them.** Never render disclaimers or production caveats in the picture. Add effects where they help a reveal and listen at phone volume to preserve consonants. Do not reuse an old voice track or duplicate a full mixed reference soundtrack.

Build with `reel.py run build -- --spec TIMELINE --project COMPOSITION`, render and finalize the MP4. Inspect encoded frames after layer/crop changes, and watch with sound at normal speed. Record observed word coverage, visual readability, graphic/caption collisions, face visibility, audible bed/effects and final hash. Make a calibration from original Brandon filming, compare relevant frames to the three references, and leave style approval pending Brandon's review. Send the current output, timeline, words and review record to `reel-review`; a successful encode does not approve an edit.
