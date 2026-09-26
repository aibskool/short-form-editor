# Brandon Reel Engine migration inventory

This fork keeps Samin Yasar's copyright, source-available terms, third-party notices and original examples. A renamed directory is not a new license or a claim that the historical examples were made for Brandon. Make changes to maintained `skill/references/` first; regenerate the plugin copies with `python tools/build-plugin.py` and inspect `plugins/brandon-reel-engine/reference-build.json`.

| Former Samin-specific surface | Brandon replacement or disposition |
| --- | --- |
| `.agents/plugins/marketplace.json`: `samin-reel-engine` marketplace/plugin ID and `./plugins/samin-reel-engine` source path | `brandon-reel-engine` ID and `./plugins/brandon-reel-engine`; remove the previous installation and register the new one. |
| `plugins/samin-reel-engine/.codex-plugin/plugin.json`: manifest name/display, description, author/developer, repository and color | New manifest under `plugins/brandon-reel-engine/`; repository points to this fork and accent to `#49cf26`. The original copyright remains in `LICENSE`. |
| `plugins/samin-reel-engine/skills/` and `references/`; links in README, setup, capabilities and ClickUp docs | Same skill names under `plugins/brandon-reel-engine/`; links and the packaging target in `tools/build-plugin.py` changed. The installed runner resolves the configured checkout. |
| `plugins/samin-reel-engine/templates/council-caption-preset.json` | Retired as an active preset; `templates/brandon-text-preset.json` specifies independent `spoken_captions` and `editorial_graphics`. Historical Council examples stay labeled upstream. |
| `~/.config/samin-reel-engine/project.json`, `SAMIN_REEL_PROJECT` | New config `~/.config/brandon-reel-engine/project.json`, `BRANDON_REEL_PROJECT`; read-only legacy fallback with conflict detection. Run the migration command below. |
| Timeline `captions` | Renamed to `spoken_captions` in a copied timeline. The runtime still accepts the legacy key alone; both keys together fail. Word timing, phrases, punctuation, emphasis, font, location and audio policy are preserved. |
| Legacy `graphic`, `scene`, `labels`, `output.split_fraction`, `music`, `audio_policy.user_opt_out` | Preserve labels, scenes, graphics and split fraction. The migration removes music from the new timeline, preserving the original file and reporting removed entries. Do not automatically convert conceptual illustrations or source labels into editorial claims. `editorial_graphics` is authored separately with claim IDs. |
| `audio_policy.music_required` build gate and previous unconditional music expectation | Every new Brandon short-form timeline sets `music_required:false` and omits `music`; the runner and editor reject music. Brandon adds it on the platform. |
| `production/editor/package.json` and lockfile package name | `brandon-reel-editor`; renderer dependency pins retained. |
| `production/editor/edit.py`, `motion_scenes.py`, `editorial_scenes.py`, `kinetic_scenes.py`, `timeline.example.json` | Fixed lower-third caption anchor, word-cued green/white animated scenes with negative-state contrast and two-second custom-UI motion gate, purpose-timed transitions, no-music build gate and neutral demonstration labels. Legacy shot-level `caption_y` remains in copied configurations but no longer changes the anchor. The old Council shot structure is not the Brandon default. |
| `production/editorial-map.schema.json`, `asset-index.schema.json`, `check_editorial.py`, `retime_timeline.py` | Optional claim, graphic, proof and CTA fields; graphic joins and keyword/resource checks; retime both text systems. Existing schema version 1 data remains valid. |
| `skill/references/{shot-recipes,operator-runbook,quality-procedure,asset-playbook,voice-guide,curated-resource-reels,pipeline-operations,templates,saved-resources,skool,generation-recipes}.md` and generated counterparts | Active instructions now point to Brandon's three reels and claim-led choices. Council/Mobbin specifics are labeled historical examples. `visual-evidence.md` additionally identifies Brandon as the active comparison. |
| Fixed 0.5/1-second opening hold rule in `production/editorial-judgment.md` and earlier shot/runbook prescriptions | Removed as a gate. Cuts now follow changes in spoken meaning, visible action, source proof and reading time; split is optional. |
| Historical `plugins/.../examples/council-readme-beat.json`, `mobbin-hook.json`, PNG, `docs/showcase.md`, `docs/assets/opening.gif`, `verification/public-release.json` and upstream links | Retained under the renamed plugin or original docs, with truthful authorship and historical labels. Old upstream URLs intentionally keep their original path. They are not Brandon calibration evidence. |
| `LICENSE`, `THIRD_PARTY_NOTICES.md`, `tools/hold-your-voice/LICENSE` | Original copyright and third-party terms preserved; fork attribution added to notices. |

## Migrate an existing checkout

1. Keep a backup of the original timeline and configuration. Run `python tools/migrate_brandon_config.py --dry-run --timeline /path/old.json --out /path/new.json`; inspect the reported target and any conflict.
2. Run the same command without `--dry-run`. It never deletes or overwrites the old file; rerunning identical input reports `already_migrated`. If the old and new project roots disagree, select the intended checkout explicitly and resolve the conflict rather than silently merging them.
3. Install the new marketplace/plugin ID as shown in [setup](setup.md). `BRANDON_REEL_PROJECT` or `--project` can select a checkout; remove `SAMIN_REEL_PROJECT` after migration. Existing installation entries are not changed by the script.
4. Read the copied timeline and add source-backed `editorial_graphics`, real proof sources, hook variants and an exact spoken/displayed keyword CTA. Verify the output with `production/check_editorial.py` and an encoded render. The migration cannot infer a true claim or make old footage match Brandon's style.

## Acceptance checklist

| Gate | Pass evidence | Current conversion status |
| --- | --- | --- |
| Plugin packaging | Maintained sources rebuilt, hashes recorded, no active old plugin path | Passed in source checkout. |
| Migration | Dry run, repeat run, target conflict, original file preservation and removal of music from copied timeline | Automated tests pass. |
| Two text systems | Lower-third spoken words and separately timed green/white claim graphics; mobile crop and collision review | Structural build/tests pass; encoded pixels need review. |
| Claim and proof | Each beat has a precise claim, source scope and corresponding real screen or labeled illustration | Contract/checker ready; depends on selected story assets. |
| Hook and CTA | At least two truthful opening choices; final face-to-camera spoken/displayed keyword and ready matching resource | Planned/checker ready; requires Brandon's filmed story. |
| Audio and motion | Recorded voice intact; no background music; visual changes based on meaning; effect levels checked by listening | Structural checks pass; encoded listening pending. |
| Calibration | Exactly 20 seconds of original Brandon footage, render hash, every encoded frame compared with selected intervals of all three source reels and audio listened to | **Rendered calibration underway** with original Brandon footage and all three supplied references. Human visual/audio comparison and Brandon review remain pending. `production/compare_style.py` emits `pending_human_review`, never a match score. |

Do not label the output a Brandon style match until the calibration row passes and Brandon has reviewed the render.
