# Kallaway sound library

Two recorded takes per cue, 48 kHz mono 16-bit, peak-normalized to about -3 dBFS. `kind-1.wav` is the primary match and `kind-2.wav` is the alternate. The editor rotates them. Nothing in this folder is copied from a Kallaway reel.

## Licenses

- Mixkit files: [Mixkit Sound Effects Free License](https://mixkit.co/license/#sfxFree). Commercial use is allowed. Attribution is not required. Download page: `https://mixkit.co/free-sound-effects/download/{id}/`. File: `https://assets.mixkit.co/active_storage/sfx/{id}/{id}.wav`.
- Kenney files: Interface Sounds, [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). Credit is optional. https://kenney.nl/assets/interface-sounds

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

## How close they are

Cosine is 24 log-frequency bands from 70 Hz to 12 kHz, comparing the take's peak-window spectrum with the reference difference spectrum (the flux peak minus the bed about 80 ms earlier). Centroid is energy-weighted in that window, so a thin harmonic tail does not pretend to be the body. Pitch is the peak FFT bin. Attack is 10–90% of the envelope. Duration is the time above -28 dB of the envelope peak.

Swoosh cosines stay low because the reference stems are bed-heavy; those takes were chosen to hit the written brightness (about 1–8 kHz, and a thinner 8–9 kHz alternate). Vacuum cosine is the peak window, which is the pop at the end of the suck; the swell row is the rising body on its own.

| File | Cosine | Centroid | Pitch | Duration | Attack | Decay to -20 dB |
| --- | --- | --- | --- | --- | --- | --- |
| pop-1 | 0.993 | 739 Hz | 785 Hz | 0.064 s | 3.8 ms | 31 ms |
| pop-2 | 0.730 | 739 Hz | 715 Hz | 0.058 s | 3.0 ms | 38 ms |
| whoosh-1 | 0.523 | 274 Hz | 82 Hz | 0.594 s | 308 ms | 175 ms |
| whoosh-2 | 0.398 | 951 Hz | 434 Hz | 0.516 s | 195 ms | 146 ms |
| riser-1 | 0.108 | 4010 Hz | 844 Hz | 0.240 s | 155 ms | 47 ms |
| riser-2 | 0.044 | 7820 Hz | 4137 Hz | 0.173 s | 40 ms | 84 ms |
| bass-1 | 0.941 | 68 Hz | 70 Hz | 0.729 s | 169 ms | 236 ms |
| bass-2 | 0.948 | 61 Hz | 59 Hz | 0.887 s | 36 ms | 103 ms |
| click-1 | 0.601 | 2069 Hz | 481 Hz | 0.015 s | 1.1 ms | 11 ms |
| click-2 | 0.123 | 2830 Hz | 1957 Hz | 0.034 s | 1.9 ms | 21 ms |
| paste-1 | 0.368 | 582 Hz | 551 Hz | 0.083 s | 2.3 ms | 60 ms |
| paste-2 | 0.269 | 1073 Hz | 668 Hz | 0.030 s | 3.8 ms | 9 ms |
| ticking-1 | 0.927 | 4536 Hz | 4547 Hz | 0.025 s | 15.3 ms | 6 ms |
| ticking-2 | 0.929 | 4802 Hz | 4852 Hz | 0.018 s | 1.6 ms | 12 ms |
| ding-1 | 0.871 | 4828 Hz | 3938 Hz | 0.466 s | 64 ms | 338 ms |
| ding-2 | 0.992 | 694 Hz | 656 Hz | 0.313 s | 3.5 ms | 285 ms |
| cash-1 | 0.937 | 4923 Hz | 4969 Hz | 0.260 s | 3.2 ms | 233 ms |
| cash-2 | 0.822 | 3848 Hz | 4863 Hz | 0.303 s | 93 ms | 196 ms |
| marker-1 | 0.868 | 14253 Hz | 11883 Hz | 0.265 s | 8.6 ms | 247 ms |
| marker-2 | 0.816 | 14764 Hz | 1617 Hz | 0.123 s | 4.2 ms | 41 ms |
| error-1 | 0.737 | 856 Hz | 1043 Hz | 0.329 s | 128 ms | 181 ms |
| error-2 | 0.053 | 1237 Hz | 1172 Hz | 0.371 s | 3.3 ms | 285 ms |
| vacuum-1 | 0.919 | 226 Hz | 106 Hz | 0.501 s | 209 ms | 82 ms |
| vacuum-1 swell | 0.653 | 157 Hz | 47 Hz | 0.343 s | 132 ms | |
| vacuum-2 | 0.704 | 314 Hz | 117 Hz | 0.389 s | 14 ms | 145 ms |
| vacuum-2 swell | 0.263 | 234 Hz | 164 Hz | 0.290 s | 88 ms | |

Bass energy under 120 Hz is 0.99 on both takes. Ding-2 is the rounder ~0.65 kHz chime, scored against that reference, not the 4 kHz bell. Error-2 matches the ~1.1 kHz pitch and loses the stem cosine; error-1 is the cosine winner. Paste is the closest woody hit found (cosine about 0.37). Typing and paper have no reference, so they have no cosine.

A grid roll is not its own file. The editor fires single pops. The preview roll is seven pops at 0, 0.08, 0.16, 0.25, 0.34, 0.44 and 0.54 s, with small pitch offsets. That gesture lasts about 0.60 s. A ticker run of sixteen single ticks lasts about 0.87 s and scores 0.93 against the ticker reference.

## Files

| Files | Source | Processing |
| --- | --- | --- |
| pop-1.wav | Mixkit 2364, Hard pop click | Pitch -4 st, highpass 160 Hz, lowpass 2200 Hz, trimmed to 0.20 s |
| pop-2.wav | Kenney `drop_002` | Pitch -2 st, highpass 140 Hz, lowpass 2000 Hz, trimmed to 0.18 s |
| whoosh-1.wav | Mixkit 1465, Vacuum swoosh transition | Highpass 120 Hz, lowpass 2000 Hz, 0.22 s fade in, fade out over the last 0.22 s, 0.72 s |
| whoosh-2.wav | Mixkit 164, Fast sweeping transition swoosh | Lowpass 2600 Hz, 0.18 s fade in, fade out from 0.46 s, 0.72 s |
| riser-1.wav | Mixkit 1469, Flying fast swoosh | Highpass 1400 Hz, lowpass 12 kHz, short fade in, fade out from 0.26 s, 0.42 s |
| riser-2.wav | Mixkit 3115, Fast transitions swoosh | Highpass 1800 Hz, slowed to 0.85×, 0.36 s. The thin ~8 kHz hiss |
| bass-1.wav | Mixkit 2302, Spring metal hit | Highpass 28 Hz, lowpass 110 Hz, 40 ms fade in, fade out from 0.70 s, 1.02 s. Chosen for the slow bloom |
| bass-2.wav | Mixkit 2300, Knocking sub bass | Highpass 30 Hz, lowpass 100 Hz, slowed to 0.75×, 1.00 s. Slightly higher cosine, faster attack |
| click-1.wav | Kenney `click_001` | Highpass 350 Hz, lowpass 14 kHz, 0.04 s |
| click-2.wav | Mixkit 2568, Cool interface click tone | Highpass 400 Hz, lowpass 14 kHz, 0.05 s |
| typing-1.wav | Mixkit 2533, Single key type | Highpass 120 Hz, lowpass 3800 Hz, 0.07 s |
| typing-2.wav | Mixkit 2541, Single key press in a laptop | Highpass 140 Hz, lowpass 4200 Hz, 0.07 s |
| paste-1.wav | Mixkit 2182, Wood hard hit | Pitch +4 st, highpass 180 Hz, lowpass 4500 Hz, 0.11 s |
| paste-2.wav | Mixkit 2542, Hard single key press in a laptop | Highpass 150 Hz, lowpass 3800 Hz, onset-trimmed to 0.09 s |
| ticking-1.wav | Kenney `tick_004` | Pitch +4 st, highpass 2 kHz, lowpass 10 kHz, 0.04 s |
| ticking-2.wav | Kenney `switch_001` | Highpass 1800 Hz, lowpass 9 kHz, 0.04 s |
| ding-1.wav | Mixkit 3109, Relaxing bell chime | Pitch +5 st, highpass 700 Hz, fade out from 0.40 s, 0.64 s. The 4 kHz bell |
| ding-2.wav | Kenney `confirmation_002` | Pitch -10 st, highpass 180 Hz, lowpass 2800 Hz, fade out from 0.24 s, 0.42 s |
| cash-1.wav | Mixkit 588, Service bell double ding | Pitch -4 st, highpass 1400 Hz, fade out from 0.20 s, 0.40 s |
| cash-2.wav | Mixkit 1981, Casino bells reward | Highpass 1 kHz, 15 ms fade in, fade out from 0.28 s, 0.46 s |
| marker-1.wav | Mixkit 2998, Pen marker line | Highpass 2200 Hz, short fade in, fade out from 0.20 s, 0.32 s |
| marker-2.wav | Kenney `scratch_003` | Highpass 1800 Hz, 0.18 s |
| error-1.wav | Mixkit 2866, Digital quick tone, plus a 20 ms hit from Mixkit 2568 | Tone pitched -12 st, highpass 200 Hz, lowpass 3500 Hz, 0.52 s. The hit is highpassed at 2 kHz and mixed at 0.4 |
| error-2.wav | Kenney `confirmation_002`, plus a 25 ms hit from Kenney `click_001` | Tone highpassed at 250 Hz and lowpassed at 4 kHz, 0.58 s. The click hit is highpassed at 1500 Hz and mixed at 0.5 |
| vacuum-1.wav | Mixkit 1465 reversed, plus pop-1 | Lowpass 800 Hz, highpass 70 Hz, slowed to 0.65×, forced rising envelope, pop at 0.58 s, 0.95 s |
| vacuum-2.wav | Mixkit 168, Fast air sweep transition, reversed, plus pop-2 | Lowpass 1100 Hz, highpass 90 Hz, slowed to 0.70×, same rising envelope, pop at 0.55 s, 0.95 s |
| paper-1.wav | Mixkit 1530, Paper slide | Highpass 200 Hz, lowpass 7 kHz, fade out from 0.18 s, 0.32 s |
| paper-2.wav | Mixkit 2380, Paper quick movement | Highpass 250 Hz, lowpass 8 kHz, 0.18 s |

Whooshes are low-passed again at 8 kHz in the mixer, which does not change these files. Risers are not low-passed, so the bright swoosh stays bright. The lo-fi bed is unchanged: `production/editor/music/kallaway-bed.ogg`.
