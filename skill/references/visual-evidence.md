# Choose visuals that earn their place

Choose visuals for the spoken beat. Supplied screen captures show real interactions; animated authored UI, confirmations, sent-email screens and illustrative footage can show uncaptured steps in Brandon's account. Source links can supply contextual visuals when useful. Record each asset's origin in production notes. Brandon's narration is the input: no visual has to corroborate it, and nothing on screen qualifies it.

Use the project's [editorial judgment guide](../../production/editorial-judgment.md) and [editorial map schema](../../production/editorial-map.schema.json) for production decisions and review. These links resolve within the repository. In an installed skill, find the same `production/` files under the project root configured in `~/.config/brandon-reel-engine/project.json` or by the runner's `context` command.

## Select by the viewer's question

For every beat, write the question the viewer needs answered, the visual's job, and the exact detail they should notice. Choose a supplied capture, authored screen, explanation, metaphor or presenter deliberately. A relevant screenshot can do more than several elaborate shots.

- **Supplied screen capture:** show the relevant input, action or result when Brandon provided a recording.
- **Authored state change:** animate an email sent state, purchase confirmation or other UI from Brandon's stated account when a capture is unavailable. Keep creation details in the production notes.
- **Resource contents:** show the actual promised file or page when it is available.
- **Abstract mechanism:** animate a sparse diagram, metaphor or illustration when it makes the claim easier to follow.

Reject a screenshot when it answers the wrong viewer question. Keep third-party authorship, marks and licensing intact in sourced visuals. Do not make a supplied screen capture appear to be a different source.

## Capture and frame honestly

Save an unaltered master with its URL, capture time and hash. Retain required author names, publication dates, repository/product identity, version and surrounding qualifications. Record missing fields as unknown. Preserve the original saved-item date separately from the original publication/event date.

Apply crops, highlights, arrows and captions as separate reversible presentation layers. Do not rewrite source text, numbers, results or attribution inside a supplied screenshot. Authored UI is a separate visual element, and its asset record identifies it as created for the edit.

For a long page: briefly establish the source, move to a legible crop of the relevant field, then highlight the clause being spoken. The viewer should know what they are looking at and what to read. Do not require them to read the entire page. Use a screenshot with an animated crop when the information is static; use a screen recording when interaction or progression is the point.

Align the reveal to the important spoken noun or action using the final word timestamps. Separate transition time from a stable reading hold. Check the focal text at phone size and normal playback speed; shorten the required reading, enlarge the crop or extend the hold if necessary. Scrolling, typing and zooming should guide attention, not consume the whole reading interval. Keep captions, faces and platform controls outside the required focal detail.

## Reusable research shot queue

Keep `research/shot-queue.json` as a drafting record. Each entry should carry the fields below; unknown timing stays null until the take is edited. This queue is not a new validated production schema. Promote its assets into the existing asset index and its beat decisions into `editorial-map.json`, following those schemas rather than adding unsupported fields.

| Field group | Record |
|---|---|
| Identity | `asset_id`, `story_id`, `reel_id`, `beat_id` when known |
| Provenance | `source_url`, Eden `saved_item_id`, original author/owner, usage basis |
| Dates | `publication_date`, `event_date`, `saved_at`, `captured_at`; retain uncertainty |
| Story | spoken beat and visual purpose; optional reference URL when useful |
| Capture | `asset_path`, master SHA-256, capture method, viewport/resolution, source media in/out if relevant |
| Framing | crop rectangle with coordinate system, focal field, required names/dates/context that must remain visible |
| Editorial purpose | viewer question, visual job, expected takeaway, reason this asset fits |
| Timing | spoken anchor text; final word index/time, reveal time, duration and stable hold when available |
| Status | requested/captured/created/inspected; unresolved capture or readability issues |

A source URL without a local capture is still a request for that specific asset. A supplied capture or authored screen needs visual inspection for readability. Keep asset hashes and paths synchronized when versions change; an absent source URL never blocks an authored graphic or the reel.

## Two concrete applications

**Astra: "it bought the domain and hosted it on Netlify."** Brandon's line is the beat. The capture of the domain search is soft and filmed off a monitor, so the edit punches into the domain field for about two seconds on the word "domain," returns to Brandon for "hosted it on Netlify" with a callout on his words, and saves the finished site for the payoff reveal. Nothing waits on a checkout screen, and nothing on screen qualifies what he said.

**A tool launch.** When Brandon says a new tool transcribes locally, show the product's own page or repository if it helps the viewer recognize the tool, crop to the heading he names as he names it, then show the action: his recording if he made one, otherwise an original motion graphic of audio going in and text coming out. Keep third-party names, marks and licenses intact in anything taken from their pages.

## Reference matching and the quality gate

For Brandon, use the three supplied reels and [observed style profile](brandon-style-profile.md), then compare the original-footage calibration. For the historical Council example only, the same-script human edit [DcwJ9MymNSv](https://www.instagram.com/p/DcwJ9MymNSv/) and its [measured profile](https://github.com/Samin12/samin-reel-engine-plugin/blob/main/docs/showcase.md) precede the older Apple Design reference. Its 35.9-second duration is evidence about that edit, not a Brandon duration or shot-count quota.

Keep reference audio for calibration distinct from reusable isolated effects. Brandon short-form exports must have no background music, including a bed unintentionally retained in a source clip. An extracted side channel may retain music or speech; inspect and record that limitation. Only label an effect isolated when supported by the extraction and listening evidence. Record newly synthesized approximations as original assets, not ripped stems.

Judge the actual hashed render for spoken-beat clarity, timing, caption safety, motion and audio; run `review_reel.py` for the measurable part (see the [quality procedure](quality-procedure.md)). Technical validation, motion quantity and contact sheets cannot certify a style match. Record what was actually watched, flag unreadable or mistimed beats, and revise. Do not run a claim-accuracy or supporting-evidence gate. Never mark sound or full-playback review complete from still images alone.
