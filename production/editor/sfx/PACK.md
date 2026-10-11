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
peaks above 0 dBFS. Nothing quieter is turned up, except the two committed
defaults below. No EQ, pitch shift, time-stretch, or filter.
`04 Swishes & Swooshes/Backwards Swoosh.wav` peaks above full scale (about
+12 dBFS in the supplied copy; the pack note says +13.4) and is turned down
to 0 dBFS.

Three defaults are committed untouched in this directory and used even when
the rest of the pack is only in `SFX_PACK_DIR`:

- `Pop 1.mp3` (`27 Pops, Zaps & Switches/Pop 1.mp3`) on every pop-on, on the frame it appears. Pop 3, 4, and 5 are retired. Pop 1 peaks at −4.1 dBFS, 4 dB under full scale, so it does not pump the voice limiter. A real slide still uses a whoosh.
- `Wrong Answer.mp3` (`00 Viral Reels Essentials/Wrong Answer.mp3`) on a genuinely bad beat only. A win, money in, or "0 errors left" gets a bell or Ka-Ching even if the word is "errors". The file is not turned up. It sits about 4 dB under the voice, and lower when that would still ride the limiter.
- `Ui Sound 12.mp3` (`24 UI Sounds/Ui Sound 12.mp3`) is the count-up tick, one play per displayed number, the last on the landing frame. It replaces Ui 30 and peaks at −6.1 dBFS. A roll that would change faster than every 50 ms slows to about 8–10 steps over at least 0.4 s.

Pops do not count toward the 20-per-minute cap. A tick roll counts as one cue.

Levels follow playbook S5, relative to the voice, with no music:
pops, clicks, and ticks −10 to −16 dB, whooshes −8 to −12 dB, dings and the
cash register −8 to −12 dB, impacts −4 to −8 dB, counter beds −20 to −26 dB.
Face layout cuts stay silent. The master is −14 LUFS with a −1 dBTP ceiling.
