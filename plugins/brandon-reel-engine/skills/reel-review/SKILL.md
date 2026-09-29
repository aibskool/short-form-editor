---
name: reel-review
description: "Review an encoded Brandon reel against the house style: run the acceptance review, then watch it with sound at phone size and record fixes."
---

# Reel quality review

Read the [house style](../../references/house-style.md), the [quality procedure](../../references/quality-procedure.md), [Brandon's style profile](../../references/brandon-style-profile.md) and `<project>/production/editorial-judgment.md`. Review the current hashed MP4, not a planned timeline or a still from another render.

**Run the acceptance review first.** `reel.py run review -- --project BUILD --video RAW.mp4` writes `review.json` and `review.md` with every check's result, the measured value and the limit, a list of what to fix first and a presenter strip (one mark per half second: full size, small or lowered, away). It covers word sync; mobile legibility (caption style and size, hero and caption zones, platform controls, text sizes); full-size presenter presence (from the layouts and a face track of the render); visual progression (composition runs and range, reading holds, variety, retired motifs, a designed payoff, dark card spans, static stretches); transition variety; standout motion (showpieces, one in the hook); sparse sound (no music, retired sounds, the bubble family, density, impacts, effects on cuts, each effect's level against his voice on full band and a phone-speaker band); forbidden patterns (disclaimers, timer bars, green wipes and flashes, karaoke captions); pacing; and a comparison with the approved calibration. A fail blocks delivery. A warning needs a look and a reason in your notes.

**Take Brandon's statements as given.** Do not check claims, ask for supporting evidence or mark an edit down because a capture doesn't show a spoken event. Flag the opposite instead: a claim the edit softened, cut or captioned with a caveat.

**Then watch it.** Play the opening and the whole edit at 1× with sound, on headphones and a phone speaker. Judge what the review can't: whether each graphic helps the viewer follow the story, whether the hook earns the next second, whether the payoff feels designed rather than listed, whether hero type and captions read at phone size, whether sounds sit under the words and land with the motion. Confirm the displayed CTA keyword matches the spoken one and Brandon is face-to-camera for it. Listen for intact first and last words and any music bed.

For a calibration, compare the encoded render frame by frame with relevant intervals of [Astra](https://www.instagram.com/p/DdpOfqtgr8a/), [photographer](https://www.instagram.com/p/DdsBCNtB6LW/) and [GovDeals](https://www.instagram.com/p/DdkZiwiuDPv/) by visual job, and with the approved calibration's measurements. Keep timecoded frames, audio notes, repairs and the final SHA-256. Mark `pending_review` until Brandon has watched the final version.
