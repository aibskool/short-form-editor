# Viral Reels SFX Pack

Kallaway reels use the Viral Reels SFX Pack by sfxreels. The sounds are
royalty-free inside a video. They are not redistributed with this repository.

Set `SFX_PACK_DIR` to the folder that contains `mapping.json` and the numbered
category directories. The default path is `production/editor/sfx/viral-pack/`,
which is gitignored.

```bash
export SFX_PACK_DIR=/path/to/viral-reels-sfx-pack
```

`viral-mapping.json` is the committed category map (primary file and
alternates). The mixer reads the audio from `SFX_PACK_DIR` only.

Files are used as supplied. Allowed edits are a start or end trim on the
timeline, a short fade where a long file is cut, and clip gain when a file
peaks above 0 dBFS. Nothing quieter is turned up. No EQ, pitch shift,
time-stretch, or filter. `04 Swishes & Swooshes/Backwards Swoosh.wav` peaks
above full scale (about +12 dBFS in the supplied copy; the pack note says
+13.4) and is turned down to 0 dBFS.

Levels follow playbook S5, relative to the voice, with no music:
pops, clicks, and ticks −10 to −16 dB, whooshes −8 to −12 dB, dings and the
cash register −8 to −12 dB, impacts −4 to −8 dB, counter beds −20 to −26 dB.
Face layout cuts stay silent. The master is −14 LUFS with a −1 dBTP ceiling.
