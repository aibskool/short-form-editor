#!/usr/bin/env python3
"""Safely migrate the project pointer and optional legacy timeline JSON."""
import argparse
import json
from pathlib import Path

REQUIRED = ('skill/scripts/pipeline.py', 'production/editor/edit.py', 'production/check_editorial.py')


def read_json(path):
    return json.loads(path.read_text())


def migrate_config(legacy, target, dry_run=False):
    if not legacy.is_file():
        return {'status': 'legacy_missing', 'target': str(target)}
    old = read_json(legacy)
    root = Path(old['project_root']).expanduser().resolve(strict=True)
    if any(not (root / name).is_file() for name in REQUIRED):
        raise ValueError(f'legacy project_root is not a reel checkout: {root}')
    content = {'project_root': str(root)}
    if target.exists():
        current = read_json(target)
        if current != content:
            raise ValueError(f'conflicting project_root in {target}: {current.get("project_root")} != {root}')
        return {'status': 'already_migrated', 'target': str(target)}
    if not dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(content, indent=2) + '\n')
        target.chmod(0o600)
    return {'status': 'would_create' if dry_run else 'created', 'target': str(target)}


def migrate_timeline(source, target, dry_run=False):
    value = read_json(source)
    if not isinstance(value, dict):
        raise ValueError('timeline must be an object')
    if 'captions' in value and 'spoken_captions' in value:
        raise ValueError('timeline has both captions and spoken_captions; choose explicitly')
    changed = 'captions' in value
    if changed:
        value['spoken_captions'] = value.pop('captions')
    # Existing labels, scene, graphic, split_fraction, music and audio_policy retain their meanings.
    if target.exists():
        if read_json(target) != value:
            raise ValueError(f'existing target differs: {target}')
        return {'status': 'already_migrated', 'target': str(target)}
    if not dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value, indent=2) + '\n')
    return {'status': 'would_create' if dry_run else 'created', 'target': str(target),
            'legacy_captions_converted': changed, 'editorial_graphics_inferred': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--legacy-config', type=Path, default=Path.home()/'.config/samin-reel-engine/project.json')
    parser.add_argument('--new-config', type=Path, default=Path.home()/'.config/brandon-reel-engine/project.json')
    parser.add_argument('--timeline', type=Path, help='Optional legacy timeline JSON to migrate')
    parser.add_argument('--out', type=Path, help='New timeline path; defaults to <source>.brandon.json')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if args.out and not args.timeline:
        parser.error('--out requires --timeline')
    try:
        results = {'config': migrate_config(args.legacy_config, args.new_config, args.dry_run)}
        if args.timeline:
            target = args.out or args.timeline.with_name(args.timeline.stem + '.brandon.json')
            if target.resolve() == args.timeline.resolve():
                raise ValueError('timeline output must differ from input')
            results['timeline'] = migrate_timeline(args.timeline, target, args.dry_run)
        print(json.dumps(results, indent=2))
        return 0
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    raise SystemExit(main())
