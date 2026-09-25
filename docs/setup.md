# Setup and first run

Follow the installation block in the root README. The public package is separate from private production data and does not install credentials. Keep local footage, scripts and credentials out of Git.

1. Install Python 3.11, Node.js, Git and FFmpeg/FFprobe.
2. Create the virtual environment and install `production/requirements.txt`.
3. Run `npm ci --prefix production/editor` for the pinned renderer.
4. Configure the project path with the runner, register this checkout as a Codex marketplace, and add `brandon-reel-engine@brandon-reel-engine`.
5. Start a new Codex task. Run `doctor`; it reports local dependencies but does not verify provider login.
6. Add your own voice samples and scripts locally. Use `tools/hold-your-voice/hold_voice.py profile --help` to create your profile.
7. Supply a local filmed take or an authorized source, a script and a visual reference. Start with `reel-director`.

For transcription, install `python -m pip install -r production/requirements-intake.txt`. The existing intake helper expects a Whisper model file; inspect `python production/intake/intake.py --help` and pass your model path. Platform-specific PyTorch installation may need the appropriate wheel for your machine. The pinned intake environment reflects the tested Python 3.11 setup.

For source screenshots, use an installed Chrome executable; the helper opens an isolated temporary profile for public pages; inspect `python plugins/brandon-reel-engine/scripts/reel.py run capture -- --help` for the current capture contract. It does not reuse your signed-in browser.

## First checks

```bash
python plugins/brandon-reel-engine/scripts/reel.py doctor
python plugins/brandon-reel-engine/scripts/reel.py run pipeline -- --help
python production/editor/edit.py build --help
python production/check_editorial.py --help
```

`configure` stores a project path in `~/.config/brandon-reel-engine/project.json`. Explicit `--project PATH` takes precedence over the environment variable and saved configuration. If you already use a private Brandon Reel Engine checkout, use an explicit project path when testing this public distribution so you choose the intended data workspace.

## Local-only inputs

`voice/samples/`, `voice/voice-profile.json`, `runs/`, `work/`, raw media and environment files are ignored. An empty public checkout is ready to operate the pipeline, but cannot imitate a voice, find a private bookmark or render a recorded speaker until those inputs are supplied.

## Existing Samin configuration and timelines

Run `python tools/migrate_brandon_config.py --dry-run` before migrating `~/.config/samin-reel-engine/project.json` to `~/.config/brandon-reel-engine/project.json`. The old file is never deleted. Use `--timeline OLD.json --out NEW.json` to copy a legacy timeline, converting `captions` to `spoken_captions` without changing word timing, `labels`, `graphic`, `scene`, `output.split_fraction`, music or shot semantics. Editorial graphics must be added explicitly from supported claims. A conflict between legacy/new project roots fails rather than silently selecting a checkout.

Resolution order: explicit `--project`, `BRANDON_REEL_PROJECT`, new saved configuration, legacy `SAMIN_REEL_PROJECT`, then legacy saved configuration. Remove the old marketplace/plugin ID when switching installations; then add `brandon-reel-engine@brandon-reel-engine`. Keep upstream examples and notices intact.

For the full file/key inventory, safe migration steps and calibration gates, see [Brandon migration and acceptance](brandon-migration.md).
