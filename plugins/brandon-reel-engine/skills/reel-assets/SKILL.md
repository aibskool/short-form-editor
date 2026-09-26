---
name: reel-assets
description: "Find, capture and index genuine reel B-roll: original posts, GitHub READMEs, docs, screen recordings, photos, clips and the actual giveaway."
---

# Reel asset sourcing

Read [Brandon’s observed style profile](../../references/brandon-style-profile.md) for current visual/audio decisions. Historical Council/Mobbin examples remain labeled upstream and are not the default style.

Resolve `<plugin>` as the directory containing this plugin's `.codex-plugin/`. Run `python3 <plugin>/scripts/reel.py context` to find the configured project; pass `--project /absolute/checkout` **before** `context` when a project was supplied. Treat every `production/...`, `voice/...` and `runs/...` path as relative to that project. Shared references are linked below; load only this stage's instructions. Keep credentials and large working media out of the plugin cache.

Read [asset playbook](../../references/asset-playbook.md), [visual evidence](../../references/visual-evidence.md), and the relevant [shot recipe](../../references/shot-recipes.md). This is the default before generating visuals.

For each beat, state what the viewer needs to see and why. Use Brandon's supplied assets first. Accept his spoken statement as given; do not demand a corroborating source or reject a beat for missing evidence. Prefer relevant recordings when supplied and use animated authored graphics for uncaptured stages.

**Prioritize motion when relevance and readability are equal.** Search for real typing, scrolling, UI flows, demonstrations and changing results; inspect playback and record the useful action's source bounds. Allocate the strongest relevant actions and most useful variety to the first 3–5 seconds. Supply different views/details/scales, including clips suitable for full-screen use. When static proof is stronger, propose a slow safe zoom/reframe and name the detail that must stay readable. Animated stills are not proof of app interaction.

Select screen captures, contextual footage, authored graphics and SFX. Brandon adds music on platform, so omit any background music from short-form exports. Choose effects for meaningful action and transitions. Animate all visible text, cards and illustrations and add purposeful transitions at appropriate boundaries even when the assembly omits them. Never put a disclaimer or production caveat on the picture.

Apply the playbook's **noun-match rejection gate** before selection: identify the exact focal detail, how it shows the spoken action/relationship, a stronger alternative considered, and the actual phone-size crop check. A Wikipedia definition of “judge” does not explain an AI judging arguments. A whole page with unreadable text is not evidence merely because its URL is real. Reject generic text cards that just restate the line when a useful action, object or mechanism can be shown.

Use the [asset-request template](../../templates/asset-request.json) to record a missing shot. The [public capture example](../../examples/public-source-capture.json) demonstrates the real helper input; replace its source with one relevant to the current claim.

Capture public sources with the existing `capture_evidence.cjs` helper through `reel.py run capture -- ...`. Authenticated content needs the actual connected browser/appropriate CLI. Inspect every captured image; a login wall, irrelevant page or URL without a file is not B-roll. Preserve the unaltered master and source identity, then crop/highlight separately.

Write source bounds in master seconds and placement in final-reel seconds. Save local path, hash, source URL/ID, capture method, useful claim/detail, proof limits, reuse basis and visual-inspection status. Reject unrelated impressive-looking screens. Keep alternatives in the source shortlist and selected files in the active asset index.

If no supplied asset illustrates a beat, give `reel-generate` a specific motion-graphic brief or author an animated status card. The lack of a capture is not an editorial veto. Ready means selected local files were actually opened and the editor can explain their intended placement.
