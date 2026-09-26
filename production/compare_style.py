#!/usr/bin/env python3
"""Create a frame-by-frame visual review of Brandon calibration and selected reference intervals.

Reference files must be lawfully supplied. This tool extracts frames for local review;
it does not score resemblance or approve a style match.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def run(command):
    subprocess.run(command, check=True, capture_output=True, text=True)


def duration(path):
    data = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_format', '-of', 'json', str(path)],
                                     check=True, capture_output=True, text=True).stdout)
    return float(data['format']['duration'])


def frames(path, output, start, end, fps):
    output.mkdir(parents=True, exist_ok=True)
    run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-ss', str(start), '-i', str(path),
         '-t', str(end-start), '-vf', f'fps={fps},scale=270:-2', '-q:v', '4',
         str(output / '%05d.jpg')])
    found = sorted(output.glob('*.jpg'))
    if not found:
        raise ValueError(f'no frames decoded from {path}')
    return [f'{output.name}/{p.name}' for p in found]


def create(candidate, references, out, fps=30, allow_tightened=False):
    if len(references) != 3 or len({name for name, *_ in references}) != 3:
        raise ValueError('calibration needs three distinctly named local reference intervals')
    length = duration(candidate)
    if allow_tightened:
        if not 10 <= length <= 20 + 1/fps + .02:
            raise ValueError(f'tightened calibration must be 10–20 seconds; found {length:.3f}s')
    elif abs(length-20) > 1/fps + .02:
        raise ValueError(f'calibration must be 20 seconds within one frame; found {length:.3f}s')
    if out.exists() and any(out.iterdir()):
        raise ValueError(f'comparison output must be new/empty: {out}')
    out.mkdir(parents=True, exist_ok=True)
    clips = [{'name':'Brandon calibration','source':str(candidate),'start':0,'end':length,
              'frames':frames(candidate,out/'candidate',0,length,fps)}]
    for i, (name, path, start, end, job) in enumerate(references):
        if not 0 <= start < end <= duration(path) + .03:
            raise ValueError(f'invalid reference interval for {name}')
        clips.append({'name':name,'source':str(path),'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                      'start':start,'end':end,'visual_job':job,
                      'frames':frames(path,out/f'reference-{i+1}',start,end,fps)})
    total = len(clips[0]['frames'])
    mapping = [{'candidate_frame':i,'candidate_time':round(i/fps,4),
                'reference_frames':{c['name']:round(i*(len(c['frames'])-1)/max(1,total-1)) for c in clips[1:]}}
               for i in range(total)]
    digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
    result = {'candidate_sha256':digest,'fps':fps,'status':'pending_human_review',
              'candidate_duration_seconds':length,'tightened_from_20s':bool(allow_tightened and length<19.9),
              'alignment':'Normalized progress within manually selected intervals of the same visual job; not a pixel similarity score',
              'clips':clips,'frame_mapping':mapping,'audio_review':'pending_listening'}
    (out/'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
    data = json.dumps({'clips':[{'name':c['name'],'frames':c['frames'],'job':c.get('visual_job','calibration')} for c in clips],
                       'mapping':mapping})
    html = '''<!doctype html><meta charset="utf-8"><title>Brandon calibration frame review</title>
<style>body{font:16px Arial;background:#161b17;color:white;margin:2rem} main{display:flex;gap:1rem;flex-wrap:wrap} section{width:270px} img{width:270px;display:block} small{color:#b7d9ba} input{width:95%}</style>
<h1>Frame-by-frame calibration review</h1><p>Different stories are aligned by manually selected visual job and normalized interval. Listen to original audio separately. This page does not certify a style match.</p>
<label>Frame <output id="n">0</output><input id="seek" type="range" min="0" max="0" value="0"></label><main id="views"></main>
<script>const data=__DATA__;const seek=document.getElementById('seek'),views=document.getElementById('views');seek.max=data.mapping.length-1;
function show(){let i=+seek.value;document.getElementById('n').textContent=i+' / '+data.mapping.length;views.innerHTML='';for(let j=0;j<data.clips.length;j++){let c=data.clips[j],idx=j?data.mapping[i].reference_frames[c.name]:i;let section=document.createElement('section');let h=document.createElement('h2');h.textContent=c.name;let img=document.createElement('img');img.src=c.frames[idx];let note=document.createElement('small');note.textContent=c.job+' · frame '+idx;section.append(h,img,note);views.append(section)}}
seek.oninput=show;document.onkeydown=e=>{if(e.key==='ArrowRight'||e.key==='ArrowLeft'){seek.value=Math.max(0,Math.min(+seek.max,+seek.value+(e.key==='ArrowRight'?1:-1)));show()}};show();</script>'''
    (out/'index.html').write_text(html.replace('__DATA__',data.replace('</', '<\\/')))
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--candidate',required=True,type=Path)
    ap.add_argument('--reference',action='append',required=True,nargs=5,
                    metavar=('NAME','PATH','START','END','VISUAL_JOB'))
    ap.add_argument('--out',required=True,type=Path)
    ap.add_argument('--fps',type=int,default=30)
    ap.add_argument('--allow-tightened',action='store_true',help='Compare an intentionally shortened 10–20 s cut after speech cleanup')
    args=ap.parse_args()
    if not 1<=args.fps<=60: ap.error('--fps must be 1–60')
    try:
        refs=[(name,Path(path),float(start),float(end),job) for name,path,start,end,job in args.reference]
        result=create(args.candidate,refs,args.out,args.fps,args.allow_tightened)
        print(json.dumps({'status':result['status'],'candidate_sha256':result['candidate_sha256'],
                          'frame_count':len(result['frame_mapping']),'review':str(args.out/'index.html')},indent=2))
    except (OSError,ValueError,subprocess.CalledProcessError) as exc:
        ap.error(str(exc))


if __name__=='__main__': main()
