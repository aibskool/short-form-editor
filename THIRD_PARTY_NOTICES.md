# Third-party notices

Brandon Reel Engine is a maintained fork of Samin Yasar's [Samin Reel Engine](https://github.com/Samin12/samin-reel-engine-plugin). The original project copyright and source-available terms remain in [LICENSE](LICENSE). Historical Council/Mobbin examples and release records describe upstream work; renaming this fork does not transfer their authorship or media rights.

- HyperFrames is installed as a dependency, pinned in production/editor/package.json. Its upstream license applies: https://github.com/heygen-com/hyperframes
- GSAP 3.13 is installed as a dependency, including the DrawSVG, MotionPath, CustomEase and CustomWiggle plugins that the motion components load. It is distributed under GreenSock's Standard "no charge" license: https://gsap.com/standard-license
- Fonts bundled into each composition come from the npm `@fontsource` packages pinned in production/editor/package.json and are licensed under the SIL Open Font License 1.1: Inter Tight (Copyright 2022 The Inter Project Authors), Instrument Serif (Copyright 2022 The Instrument Serif Project Authors), Archivo Black (Copyright 2017 The Archivo Black Project Authors) and JetBrains Mono (Copyright 2020 The JetBrains Mono Project Authors). The build copies each family's license text next to its font files.
- HyperFrames' optional `remove-background` command (used for depth mattes) downloads its segmentation model on first use; that model comes under the terms HyperFrames documents for it.
- The motion icons (production/editor/icons.py), the synthesized sound effects (production/editor/sfx_kit.py) and the demo presenter and placeholder screens (production/editor/demo/) are original to this fork. No brand logos or third-party samples are included.
- Kallaway talking-head faces are bundled under `production/editor/fonts/` and licensed under the SIL Open Font License 1.1, with the license text next to each file: Permanent Marker (Copyright 2010 Font Diner), Inter Black and Inter ExtraBold (Copyright 2016 The Inter Project Authors), IBM Plex Mono Medium (Copyright 2017 IBM Corp., reserved font name "Plex").
- Kallaway talking-head music and sound effects are committed CC0 recordings, not synthesis. The bed is `production/editor/music/kallaway-bed.ogg`. The cues are `production/editor/sfx/kallaway/*.wav` (two or three takes per cue, trimmed tight and peak-normalized to about -3 dBFS). Full file-by-file notes are in `production/editor/sfx/kallaway/SOURCES.md`. Every file below is [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/), so commercial use does not require attribution. Attribution here is a record of provenance.
  - Bed, native about 105 BPM, no vocals: "Chill lofi inspired" by isaiah658, loop edit by qubodup. https://opengameart.org/content/chill-lofi-inspired and https://opengameart.org/content/chill-lofi-inspired-loop-edit
  - Whooshes: qubodup megaswosh 1 and 2 from https://opengameart.org/content/wind-hit-time-morph (highpassed and trimmed). Third whoosh: a 0.4 s slice of https://opengameart.org/content/air-whoosh by pyranostudios.
  - Risers: the same wind recordings, played back with a rising rate so the noise sweeps up.
  - Pops: pop1, pop2, pop3 from "3 Pop Sounds" by megaboots. https://opengameart.org/content/3-pop-sounds
  - Clicks: mouseclick1.wav and click1.wav from "51 UI sound effects" by gopherapps, https://opengameart.org/content/51-ui-sound-effects-buttons-switches-and-clicks ; click_001.ogg from Kenney Interface Sounds, https://kenney.nl/assets/interface-sounds
  - Typing: keypress 003, 011, and 022 from "Keyboard Soundpack #1" by unicaegames (Cherry KC 1000 recorded with a Shure SM7B). https://opengameart.org/content/keyboard-soundpack-1-typing-and-single-keystrokes
  - Ticker: tick_001, tick_002, tick_004 from Kenney Interface Sounds.
  - Bells: bell ding 1 and 2 by pwl, https://opengameart.org/content/bell-dingschimes ; pleasing-bell by BjarneK_92, https://opengameart.org/content/pleasing-bell-sound-effect
  - Sub hits: impactSoft_heavy_000, impactSoft_heavy_002, and impactPunch_heavy_001 from Kenney Impact Sounds, lowpassed around 200 Hz. https://kenney.nl/assets/impact-sounds
  - Marker: three slices of pencil_write.ogg by antumdeluge. https://opengameart.org/content/pencil-sounds
  - Paper: Paper Sound 1, 2, and 3 by Luckius. https://opengameart.org/content/various-paper-sound-effects
  - Negative cues: scratch_003 and scratch_001 plus error_002 from Kenney Interface Sounds.
- The vendored Hold Your Voice helper retains its MIT license in tools/hold-your-voice/LICENSE. Source: https://github.com/Samin12/hold-your-voice
- The finished Mobbin showcase contains third-party app/source visuals as contextual examples. Those are not a reusable stock library; raw third-party assets are not included in this public repository.
- Showcase music: “Rocket Power” — Kevin MacLeod (incompetech.com), licensed under CC BY 4.0: https://creativecommons.org/licenses/by/4.0/. Trimmed, tempo-adjusted, EQ’d, and mixed beneath narration. Source: https://incompetech.com/music/royalty-free/index.html?Search=Search&isrc=USUAN1600038

Individual dependencies retain their own licenses. A plugin installation does not supply provider subscriptions, account access or media rights.
