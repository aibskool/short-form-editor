# Motion system demo

Two timelines that render the earlier motion components (the stage layout, flows, devices, charts and the rest) without private footage; their captions use the house `pop` style. The presenter-first house style itself is what `plan_reel.py` drafts from real footage (see `skill/references/house-style.md`); `test_house_style.py` plans and builds two synthetic stories with it. They double as a regression check after renderer changes: build them, run `hyperframes check`, render, and look at the frames.

| Timeline | Recipe | Shows |
| --- | --- | --- |
| `stage-explainer.json` | Stage Explainer | Headline hook, word-synced statements, checklist with fail strikes, presenter→stage morph, scaled card, flow with slots and a win state, device window with zoom and highlight, CTA `fan`; `zoom_blur`, `light_leak`, push and shake camera; `snap` feel, dot stage |
| `receipts-first.json` | Equation hook → receipts | Equation with `?` slots, typed chat prompt, full-frame inbox with `expand` entrance and spotlight (auto dark caption backing), whip into a grid stage, count-up stat, drawn chart, compare with strike and win, orbit, seam number badge, CTA `stamp`; `glide` feel, `variation.avoid` in use |

The presenter is a flat illustrated stand-in whose mouth follows a synthetic word map, with a speech-shaped noise track at voice level so sound-effect levels are realistic. It is not a person or a voice. The app screens in `assets/` are drawn placeholders, and the scripts make no result claims; a real reel uses Brandon's own recordings and only the numbers he says.

```bash
python3 make_demo.py            # writes work/<name>.mp4 and work/<name>.words.json (about a minute)
python3 make_demo.py --render   # also builds, runs hyperframes check and renders draft MP4s into work/
```

Or step by step, from `production/editor/`:

```bash
python3 edit.py build --spec demo/receipts-first.json --project "$PWD/demo/work/receipts-first"
python3 hyperframes_cli.py check "$PWD/demo/work/receipts-first"
python3 edit.py render --project "$PWD/demo/work/receipts-first" --output "$PWD/demo/work/receipts-first-render.mp4" --quality draft --workers 2
```

`work/` is ignored by Git. Each build writes `build-receipt.json` with the `motion_report`; both demos build without warnings except the expected note that the inbox shot received a dark caption backing.
