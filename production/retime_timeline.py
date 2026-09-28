#!/usr/bin/env python3
"""Retime an existing supported edit after reviewed 1x pause removals.

Run prepare_take.py first. Supply its new video/word files and a JSON document
with source_duration and cuts [{start,end}] on the OLD output clock. Keep
background music absent from the Brandon export. Review internal B-roll actions again: shortening a shot
does not time-warp its source video or retime baked-in visual events.
"""
import argparse
import copy
import json
import math
from pathlib import Path


# Output-clock fields inside motion graphics (see production/editor/components.py).
NESTED_TIME_KEYS = {'at', 'end', 'done_at', 'fade_at', 'dim_at', 'win_at', 'count_at', 'type_start', 'type_end',
                    'send_at', 'draw_start', 'draw_end', 'badge_at', 'keyword_at', 'strike_at', 'start'}


def retime(spec, decision, source, words):
    spec = copy.deepcopy(spec)
    if spec.get('music'):
        raise ValueError('Migrate legacy music out of the timeline before retiming')
    total = float(decision['source_duration'])
    cuts = decision['cuts']
    cursor = 0
    for cut in cuts:
        a, b = float(cut['start']), float(cut['end'])
        if not all(map(math.isfinite, [a, b, total])) or not cursor <= a < b <= total:
            raise ValueError('Cuts must be ordered, disjoint, finite and within source duration')
        cursor = b
    old_duration = sum(float(s['end'])-float(s['start']) for s in spec['source']['segments'])
    if abs(old_duration-total) > 0.001:
        raise ValueError('Cut clock does not match the old timeline duration')

    def t(value):
        value = float(value)
        return value - sum(max(0, min(value, c['end'])-c['start']) for c in cuts)

    def remap(value):
        # Word cues ("@word", {"word": ...}) re-resolve against the rebuilt word map.
        return t(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else value

    def remap_nested(node, skip=()):
        """Remap every numeric output-clock time inside a motion graphic."""
        if isinstance(node, dict):
            for key, value in node.items():
                if key in skip:
                    continue
                if key in NESTED_TIME_KEYS:
                    node[key] = remap(value)
                elif isinstance(value, (dict, list)):
                    remap_nested(value)
        elif isinstance(node, list):
            for value in node:
                remap_nested(value)

    duration = t(total)
    for collection in ('shots', 'labels', 'editorial_graphics', 'graphics'):
        for item in spec.get(collection, []):
            item['start'], item['end'] = remap(item['start']), remap(item['end'])
            numeric = all(isinstance(item[k], (int, float)) for k in ('start', 'end'))
            if numeric and item['end'] <= item['start']:
                raise ValueError(f'{collection} item was entirely removed; make an editorial decision')
            if collection == 'graphics':
                remap_nested(item, skip=('start', 'end'))
            scene = item.get('scene', {}) if collection == 'shots' else {}
            for element in scene.get('items', []):
                for field in ('at', 'fade_at'):
                    if field in element:
                        element[field] = remap(element[field])
            for cue in scene.get('motion_cues', []):
                cue['at'] = remap(cue['at'])
    for collection in ('zooms', 'flashes', 'transitions', 'camera'):
        for item in spec.get(collection, []):
            if not isinstance(item['at'], (int, float)):
                continue
            at = float(item['at'])
            if 'duration' in item and collection != 'camera':
                item['duration'] = t(at + item['duration']) - t(at)
                if item['duration'] <= 0:
                    raise ValueError(f'{collection} event was entirely removed; re-author it')
            item['at'] = t(at)
    # SFX maintain their natural duration; only the onset follows the new clock.
    for sound in spec.get('sfx', []):
        sound['at'] = remap(sound['at'])
    spec['source']['path'] = str(Path(source).resolve())
    spec['source']['segments'] = [{'start': 0, 'end': duration}]
    spec['words_path'] = str(Path(words).resolve())
    spec['retime_review'] = {
        'removed_seconds': total-duration, 'cut_count': len(cuts),
        'speech_speed': 1, 'baked_visual_actions': 'must recheck against retimed speech',
        'music': 'none in Brandon short-form export',
        'spoken_captions': 'rebuilt from supplied retimed words; phrase word ranges preserved',
        'editorial_graphics': 'outer cue times remapped; recheck claim and animation against encoded speech',
        'graphics': 'numeric times remapped; @word cues re-resolve against the new word map'
    }
    return spec


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('spec', 'cuts', 'source', 'words', 'output'):
        parser.add_argument('--'+name, required=True, type=Path)
    args = parser.parse_args()
    result = retime(json.loads(args.spec.read_text()), json.loads(args.cuts.read_text()), args.source, args.words)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result['retime_review']))
