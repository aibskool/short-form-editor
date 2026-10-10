# Kallaway sound library

Two recorded takes per cue, 48 kHz mono 16-bit, peak-normalized to about -3 dBFS. `kind-1.wav` is the primary and `kind-2.wav` is the alternate. The editor rotates them. Nothing in this folder is copied from a Kallaway reel, and nothing here is a Kenney interface sound, a Mixkit tone, or a synth beep.

## License

Every file is from a [Sonniss GDC Game Audio Bundle](https://sonniss.com/gameaudiogdc/). The [bundle license](https://sonniss.com/gdc-bundle-license/) is royalty-free and allows commercial use in a finished application, film, or video (YouTube and TikTok included). Attribution is not required. Editing is allowed. The files may not be resold or redistributed as a standalone sound library, and they may not be used to train machine-learning models. They are vendored here so this editor can mix them into a reel, not as a sample pack.

The recordings were taken from the Internet Archive copies of the bundles:

- 2015 sample: https://archive.org/details/SonnissGameAudioGDC
- 2023: https://archive.org/details/sonniss-gdc-2023-game-audio-bundle-normalized
- 2024: https://archive.org/details/sonniss-gdc-2024-game-audio-bundle-normalized

InspectorJ clock ticks are the copies inside the 2023 Sonniss bundle, so they are used under the Sonniss license.

## Levels

Default mix level is how many dB the cue's momentary loudness sits under the voice. Each measured Kallaway average was made 2 dB louder, because these reels have no music bed. `under_db = -(average + 2)`.

| Kind | under voice | Kallaway average | Notes |
| --- | --- | --- | --- |
| pop | 7 dB | -9 dB | Scale-in pops |
| pop on a thumbnail grid | 19 dB | -21 dB | Same pop files, quieter cue |
| whoosh | 16 dB | -18 dB | |
| riser | 14 dB | -16 dB | Swoosh-up / slide-push |
| bass | 12 dB | -14 dB | |
| click | 21 dB | -23 dB | |
| paste | 13 dB | -15 dB | In the library. No motif fires it yet |
| ticking | 20 dB | -22 dB | |
| ding | 13 dB | -15 dB | |
| cash | 7 dB | -9 dB | Counter landing, was a ding |
| marker | 23 dB | -25 dB | |
| error | 24 dB | -26 dB | |
| vacuum | 6 dB | -8 dB | One cue replaces the old whoosh plus ding |
| typing | 19 dB | estimated | No separable clip. Set between click and paste |
| paper | 16 dB | estimated | No separable clip. Set next to the whoosh |

## Processing

Trim, a short fade (about 4–30 ms), and one peak normalize to -3 dBFS. No pitch shift, no EQ, no highpass, no lowpass, no time-stretch. The mixer does not low-pass these files either, so a bright swish keeps its air.

Realism is judged before similarity to the Kallaway reference. Spectral flatness is the geometric mean over the arithmetic mean of 24 log-frequency bands from 80 Hz to 12 kHz, on the loudest 120 ms. A naked sine scores about 0. Broadband air and paper score about 0.3–0.6. A real bell scores near 0 because it is a harmonic instrument; that is the bell, not a UI tone. Sub hits are judged by the share of energy under 120 Hz. Harmonicity is the autocorrelation peak. None of these files were time-stretched, so there is no grain to measure.

## What is not in the free bundles

No mouse-click recording and no cash-register drawer were in the 2015, 2023, or 2024 Sonniss bundles that were searched. Freesound downloads require a login, and Pixabay was behind a bot check, so those were not used. The shipped click is a real small mechanism plus a real pen click. The shipped cash cue is a real handbell plus real coins. If the exact object is required:

- Mouse: Pro Sound Effects, "Computer Mouse Click 01" (Soundrangers), 24-bit 48 kHz, $5. https://www.prosoundeffects.com/sound-effects/PSE_SR-COM/k2D19/computer-mouse-click-01
- Register: Pro Sound Effects, "Cash Register Bell Drawer Open Close" (Colin Lechner, Gen Collection Vol. 3), 24-bit 192 kHz, $5. https://www.prosoundeffects.com/sound-effects/PSE_GEN3/rXksL/cash-register-bell-drawer-open-close

## Files

| File | Source | Cut | Flatness | Centroid | Duration | Attack |
| --- | --- | --- | --- | --- | --- | --- |
| pop-1.wav | Soundopolis, Foley Plus, `Champagne_Cork_Pop_Fienup_001.wav` (2015) | whole cork pop, 0.15 s | 0.04 | 555 Hz | 0.10 s | 8 ms |
| pop-2.wav | Membrans, Pops Sound Pack 01, `Pop 31.wav` (2015) | first 0.12 s | 0.11 | 409 Hz | 0.03 s | 3 ms |
| whoosh-1.wav | Coll Anderson, Sliding Whoosh By, `EFX SD Sliding Whoosh By 06.wav` (2015) | 1.75–2.55 s | 0.31 | 436 Hz | 0.80 s | swell |
| whoosh-2.wav | Rogue Waves, Druid Magic, `SWSH_Dry Bamboo Leaf Swishes 1` (2023) | 1.98–2.52 s | 0.19 | 9.1 kHz | 0.34 s | 71 ms |
| riser-1.wav | Mechanical Wave, Hits Whoosh, `Fast Action Swish_HW 05.wav` (2015) | 0.58–0.82 s | 0.26 | 5.6 kHz | 0.08 s | 26 ms |
| riser-2.wav | Justsoundeffects, Transition Whooshes Vol. 1, `SWSH_Woodstick Swish 03` (2023) | 1.96–2.20 s | 0.51 | 1.1 kHz | 0.08 s | 20 ms |
| bass-1.wav | 344 Audio, Epic Impacts Vol. 1, `Impact 045.wav` (2023) | 0.00–1.05 s | sub 0.97 | 74 Hz | 1.00 s | 34 ms |
| bass-2.wav | 344 Audio, Epic Impacts Vol. 1, `Impact 038.wav` (2023) | 0.00–1.05 s | sub 0.93 | 134 Hz | 1.02 s | 99 ms |
| click-1.wav | Bluezone, Tiny Gears, `tiny_gears_small_mechanism_click_003.wav` (2024) | whole click, 0.05 s | 0.39 | 6.2 kHz | 0.04 s | 1 ms |
| click-2.wav | Lukas Tvrdon, Design Source 192, `Pen, Click.wav` (2023) | 1.40–1.50 s | 0.06 | 18 kHz | 0.06 s | 0.4 ms |
| typing-1.wav | Soundopolis, Foley Plus, `Computer_Keyboard_Type_Fienup_002.wav` (2015) | 0.205–0.275 s | 0.12 | 2.4 kHz | 0.02 s | 3 ms |
| typing-2.wav | same keyboard | 2.000–2.070 s | 0.33 | 2.2 kHz | 0.02 s | 5 ms |
| paste-1.wav | Dramatic Cat, Olivetti Linea 98, backspace key (2023) | 16.44–16.56 s | 0.35 | 5.9 kHz | 0.03 s | 13 ms |
| paste-2.wav | same typewriter | 8.41–8.53 s | 0.42 | 5.6 kHz | 0.03 s | 10 ms |
| ticking-1.wav | InspectorJ, Essentials 02 Clocks, `Clock-07` single tick (2023, via Sonniss) | 0.02–0.12 s | 0.07 | 3.7 kHz | 0.05 s | 12 ms |
| ticking-2.wav | InspectorJ, `Clock-03` ticking loop (2023, via Sonniss) | first tick, 0.10 s | 0.12 | 0.9 kHz | 0.06 s | 10 ms |
| ding-1.wav | Soundopolis, Percussion 01, `Bell_Waiter_Fienup_001.wav` (2015) | 0.00–0.70 s | bell | 6.4 kHz | 0.67 s | strike |
| ding-2.wav | Sonic Bat, Videogame Foley Essentials Vol. II, `SBvfe2_Glass 114.wav` (2024) | 0.00–0.42 s | 0.13 | 9.4 kHz | 0.37 s | 1 ms |
| cash-1.wav | Mechanical Wave, `BELLHand_Metallic Bell_ 22` (2024) | 0.00–0.65 s | bell | 8.1 kHz | 0.55 s | 3 ms |
| cash-2.wav | CB Sound Design, Essential Sounds Vol. 01 Coins, `coins_9.wav` (2023) | 0.02–0.55 s | 0.06 | 7.1 kHz | 0.49 s | 8 ms |
| marker-1.wav | CB Sound Design, Essential Sounds Vol. 02 Pencils, `marker_2.wav` (2023) | 0.02–0.55 s | 0.04 | 4.9 kHz | 0.50 s | 80 ms |
| marker-2.wav | same pack, `felt-tip_pencil_24.wav` | 0.08–0.36 s | 0.04 | 10.6 kHz | 0.13 s | 43 ms |
| error-1.wav | Bluezone, Steampunk Mechanical Sounds, metal alarm mechanism (2023) | 0.02–0.24 s | 0.22 | 3.1 kHz | 0.20 s | 6 ms |
| error-2.wav | same alarm, the closing clank | 2.52–2.84 s | 0.67 | 4.4 kHz | 0.27 s | 3 ms |
| vacuum-1.wav | Coll Anderson whoosh 15, 0.48–1.08 s, reversed, plus the cork pop | pop peaks at 0.58 s, 0.72 s total | 0.32 | 911 Hz | 0.64 s | 97 ms |
| vacuum-2.wav | same whoosh, 3.08–3.72 s, reversed, plus Membrans Pop 31 | pop peaks at 0.60 s, 0.73 s total | 0.49 | 610 Hz | 0.62 s | 169 ms |
| paper-1.wav | Mechanical Wave, Cardboard and Paper, large book page turn (2024) | 0.14–1.00 s | 0.33 | 3.0 kHz | 0.82 s | page |
| paper-2.wav | same pack, big cardboard box slide | 0.35–1.15 s | 0.34 | 5.1 kHz | 0.80 s | slide |

Pop-1 is a real champagne cork. Its flatness is low because the bottle rings; that resonance is in the recording. Ding-1 is a real waiter bell (partials near 2.8, 7.6, and 12.3 kHz). Cash-1 is a real handbell, not a register drawer. Bass energy under 120 Hz is 0.97 on Impact 045 and 0.93 on Impact 038; both sit on a 35–60 Hz body with no metal click. Whoosh-2 keeps energy above 8 kHz (about 0.59 of the loud window). Click-2 is almost entirely above 8 kHz, which is the pen mechanism, not a filter. The two error takes are two different hits of one metal alarm, not a sine horn.

A grid roll is not its own file. The editor fires single pops, and thumbnail-grid pops use under_db 19. The preview roll is seven of these pops with no pitch change. A ticker run and a typing burst in the preview are the same single hits sequenced, also with no pitch change. Vacuum is one file: the reversed whoosh rises, then the pop lands. The motif places that file at 0.20 s into the merge so the pop, about 0.58 s into the file, arrives near the old merge point.
