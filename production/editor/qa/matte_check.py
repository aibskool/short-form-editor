#!/usr/bin/env python3
"""matte_check.py - pre-delivery matte / cut-frame / caption-clearance check for the
split-card layout (card top y=1408, speaker popped above the card, 1080x1920 30 fps).

Full documentation (formulas, bands, colours, thresholds, calibration): MATTE_CHECK.md
in this folder. Summary of what is gated (exit code 1 if any FAIL):

  CUT WINDOWS = frames i, i+1, i+2 for every cut i (head-region picture cut, layout
  change, frame 0, and every time given with --cuts). Split frames only.
    rough  > 1.0 px            -> FAIL   (edge roughness RMS vs 15-col smoothed contour)
    green_in  > 0.03           -> FAIL   (green-hue fraction, 0..5 px inside the edge)
    green_out > 0.05           -> FAIL   (green-hue fraction, 1..6 px outside the edge)
    specks > 3                 -> FAIL   (small islands near the crown)
    dark_above > 0.05          -> FAIL   (dark rim 1-4 px outside the silhouette, above card)
    index_jump                 -> FAIL   (matte-index proxy, see MATTE_CHECK.md)
  ALL SPLIT FRAMES
    rough median > 1.0 px      -> FAIL ; jitter median > 1.0 px or p90 > 2.0 px -> FAIL
    plate dropout              -> FAIL   (side-plate mean jumps > 6 from local median)
    foliage patch (largest sharp-green blob in the card >= 120 px) -> FAIL
    split caption gap crown - caption bottom: any frame < 18 px, or segment median
      outside 25..50 px        -> FAIL
  FULL-FACE FRAMES (caption present)
    beard clearance (caption ink top - beard bottom) < 25 px -> FAIL
    pin clearance (pin top - caption baseline) < 20 px -> FAIL, 20..29 -> WARN

Usage:
  python matte_check.py VIDEO.mp4 [--cuts FILE_OR_TIMES ...] [--every 2.0]
                        [--csv per_frame.csv] [--quiet]
  --cuts accepts: a file (diff report 't=12.099' tokens, a receipt/JSON with time
  values, joins.txt, or one time per line) or a comma list of seconds.
"""
import sys, os, re, json, argparse, subprocess
import numpy as np, cv2

W, H, FPS = 1080, 1920, 30.0
CARD_TOP = 1408

TH = dict(rough=1.0, green_in=0.03, green_out=0.05, specks=3, dark_above=0.05,
          rough_med=1.0, jit_med=1.0, jit_p90=2.0, plate_jump=6.0, foliage_px=120,
          cap_gap_min=18, cap_gap_lo=25, cap_gap_hi=50, beard_min=25, pin_min=20,
          pin_ideal=30, index_px=5.0, index_ratio=2.0)

# ---------------------------------------------------------------- per-frame metrics
def is_split(V1200):
    """V1200 = HSV V channel of rows 1200..1419. Split = charcoal just above the card,
    brighter plate just inside it (same test as matte15.py)."""
    above = V1200[190:205, 100:250].mean(); incard = V1200[212:218, 100:250].mean()
    return above < 45 and incard > 35

def layout_state(im):
    """lay10.py rule on a 270x480 downscale: S if median V of x 5..14, y 150..324 <= 45."""
    sm = cv2.resize(im, (270, 480), interpolation=cv2.INTER_AREA)
    v = cv2.cvtColor(sm, cv2.COLOR_BGR2HSV)[150:325, 5:15, 2]
    return 'S' if np.median(v) <= 45 else 'F'

def green_frac(Hh, Ss, Vv):
    if len(Hh) == 0: return 0.0
    return float(np.mean((Hh >= 30) & (Hh <= 90) & (Ss > 50) & (Vv > 40)))

def matte_metrics(im):
    """matte15.py, unchanged in definition. Returns dict or None."""
    hsv = cv2.cvtColor(im[1200:1420], cv2.COLOR_BGR2HSV)
    Hc, Sc, V = hsv[..., 0], hsv[..., 1], hsv[..., 2].astype(float)
    fg = V > 70
    n, lab, st, _ = cv2.connectedComponentsWithStats(fg[:208].astype(np.uint8), 8)
    cand = [i for i in range(1, n) if st[i, cv2.CC_STAT_TOP] + st[i, cv2.CC_STAT_HEIGHT] >= 205
            and st[i, cv2.CC_STAT_WIDTH] > 60]
    if not cand: return None
    hi = max(cand, key=lambda i: st[i, cv2.CC_STAT_AREA]); m = lab == hi
    x0 = st[hi, cv2.CC_STAT_LEFT]; x1 = x0 + st[hi, cv2.CC_STAT_WIDTH]
    cols = np.arange(x0, x1); top = np.array([np.argmax(m[:, c]) for c in cols], float)
    crown = 1200 + top.min()
    ok = top < 200; c2 = cols[ok]; t2 = top[ok]
    if len(t2) < 40: return None
    sm = np.convolve(t2, np.ones(15) / 15, mode='same'); res = (t2 - sm)[7:-7]
    rough = float(np.sqrt(np.mean(res ** 2)))
    cx = int((c2[0] + c2[-1]) / 2)
    prof = {int(c - cx): r for c, r in zip(c2[7:-7], res)}          # residual profile (jitter)
    absprof = {int(c - cx): 1200 + tp for c, tp in zip(c2, t2)}     # absolute edge y (index proxy)
    fw = []
    for c, tp in zip(c2[::6], t2[::6]):
        col = V[:, c]; i = int(tp)
        if i < 12 or i > 195: continue
        bgv = np.median(col[max(0, i - 12):i - 6]); fgv = np.median(col[i + 6:i + 12])
        if fgv - bgv < 60: continue
        seg = col[i - 6:i + 7]; lo = bgv + 0.1 * (fgv - bgv); hiv = bgv + 0.9 * (fgv - bgv)
        fw.append(int(np.sum((seg > lo) & (seg < hiv))))
    bi = [[], [], []]; bo = [[], [], []]
    for c, tp in zip(c2, t2):
        i = int(tp)
        ji = np.arange(i, min(i + 6, 208)); jo = np.arange(max(0, i - 6), i)
        for k, arr in enumerate((Hc, Sc, V)):
            bi[k].append(arr[ji, c]); bo[k].append(arr[jo, c])
    gin = green_frac(*[np.concatenate(b) for b in bi]); gout = green_frac(*[np.concatenate(b) for b in bo])
    spk = 0
    for i in range(1, n):
        if i == hi: continue
        a = st[i, cv2.CC_STAT_AREA]; y = st[i, cv2.CC_STAT_TOP] + st[i, cv2.CC_STAT_HEIGHT]
        if a < 200 and x0 - 30 <= st[i, cv2.CC_STAT_LEFT] <= x1 + 30 and y > top.min() - 25: spk += 1
    return dict(crown=crown, rough=rough, prof=prof, absprof=absprof,
                feather=float(np.median(fw)) if fw else -1.0, green_in=gin, green_out=gout,
                specks=spk, width=int(x1 - x0))

def dark_rim(im):
    """darkfringe.py (reel08 v8): rows y 1290..1407 (above the card) every 2nd row; left and
    right end of the skin run; rim = 1..4 px outside, bg = 8..14 px outside.
    dark = min(rim V) < median(bg V) - 15 and min(rim V) < 70. Returns fraction above card."""
    reg = im[1290:CARD_TOP, 200:880].astype(int); B, G, R = reg[..., 0], reg[..., 1], reg[..., 2]
    V = reg.max(2)
    skin = (R > G + 12) & (R > B + 20) & (V > 90)
    skin = cv2.morphologyEx(skin.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)) > 0
    n = d = 0
    for y in range(0, skin.shape[0], 2):
        xs = np.where(skin[y])[0]
        if len(xs) < 20: continue
        for x, s in ((xs[0], -1), (xs[-1], 1)):
            rim = [x + s * k for k in (1, 2, 3, 4)]; bg = [x + s * k for k in range(8, 15)]
            if min(rim + bg) < 0 or max(rim + bg) >= skin.shape[1]: continue
            rv = V[y, rim].min(); bv = np.median(V[y, bg]); n += 1
            d += 1 if (rv < bv - 15 and rv < 70) else 0
    return d / n if n else 0.0

def plate_means(im):
    L = im[1300:1900, 0:300]; R = im[1300:1900, 780:1080]
    return float(L.mean()), float(R.mean())

def foliage(im):
    """Largest connected blob of sharp green in the card (y 1420..1899, x 250..829)."""
    reg = im[1420:1900, 250:830]
    hsv = cv2.cvtColor(reg, cv2.COLOR_BGR2HSV).astype(np.float32)
    g = cv2.cvtColor(reg, cv2.COLOR_BGR2GRAY).astype(np.float32)
    mu = cv2.blur(g, (5, 5)); sd = np.sqrt(np.maximum(cv2.blur(g * g, (5, 5)) - mu * mu, 0))
    green = (hsv[..., 0] >= 30) & (hsv[..., 0] <= 90) & (hsv[..., 1] > 50) & (hsv[..., 2] > 40)
    m = cv2.morphologyEx((green & (sd > 10)).astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    # ignore the accepted 15-30 px fade at the source edges (x 340..369 and 712..741)
    m[:, 340 - 250:370 - 250] = 0; m[:, 712 - 250:742 - 250] = 0
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    if n <= 1: return 0, None
    k = 1 + int(np.argmax(st[1:, 4]))
    return int(st[k, 4]), (int(st[k, 0]) + 250, int(st[k, 1]) + 1420)

def split_caption(im):
    """capgap15.py: crown (head mask, caption pixels removed) minus bottom row of the
    lowest caption text block above the crown. Returns (crown, captop, capbot, mindist)."""
    Y0 = 1100
    hsv = cv2.cvtColor(im[Y0:1420], cv2.COLOR_BGR2HSV); Hh = hsv[..., 0].astype(int)
    S = hsv[..., 1].astype(int); V = hsv[..., 2].astype(int)
    cap = ((S < 45) & (V > 200)) | ((Hh >= 18) & (Hh <= 35) & (S > 110) & (V > 170)) | \
          ((Hh >= 40) & (Hh <= 85) & (S > 110) & (V > 140))
    head = (V > 70) & ~cap
    n, lab, st, _ = cv2.connectedComponentsWithStats(head[:308].astype(np.uint8), 8)
    cand = [i for i in range(1, n) if st[i, 1] + st[i, 3] >= 305 and st[i, 2] > 60]
    if not cand: return None
    hi = max(cand, key=lambda i: st[i, 4]); hm = lab == hi
    crown = Y0 + int(np.where(hm.any(1))[0].min())
    cm = cap.copy(); cm[:, :120] = False; cm[:, 960:] = False; cm[crown - Y0 - 1:] = False
    rows = np.where(cm.sum(1) >= 4)[0]
    if len(rows) == 0: return (crown, None, None, None, None)
    blocks = []; s = rows[0]; pv = rows[0]
    for r in rows[1:]:
        if r > pv + 4: blocks.append((s, pv)); s = r
        pv = r
    blocks.append((s, pv)); bt = blocks[-1]
    if bt[1] - bt[0] < 20: return (crown, None, None, None, None)
    cb = np.zeros_like(cm); cb[bt[0]:bt[1] + 1] = cm[bt[0]:bt[1] + 1]
    hm2 = np.zeros(cm.shape, bool); hm2[:308] = hm
    dist = cv2.distanceTransform((~hm2).astype(np.uint8), cv2.DIST_L2, 3)
    md = float(dist[cb].min()) if cb.any() else None
    rc = cm[bt[0]:bt[1] + 1].sum(1)
    base = Y0 + bt[0] + int(np.where(rc >= 0.5 * np.median(rc[rc > 0]))[0].max())
    return (crown, Y0 + bt[0], Y0 + bt[1], md, base)

def fullface_caption(im):
    """Full-face caption vs beard and mic pin. Returns dict or None (no caption found).

    v2 (2026-10-11, QA reel 08 v9): the v1 detector required a caption block >=20 rows and
    >=1200 white px and took the block with the most white px. Small full-face captions
    (x-height ~17 px, ~300-800 px) were rejected, and the white mic pin logo (~45 rows,
    ~1000 px) or bright hands at the frame edge won instead, so on 08 v9 only 6 of 319
    full-face frames were 'measured' and all 6 were false (x 150..320, no beard/pin).
    v2 masks pin-shaped components before looking for text, accepts blocks 8..110 rows
    with >=80 px, requires the block to be horizontally centred (centre x 340..740) and,
    when a pin is found, takes the lowest qualifying block above the pin."""
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV).astype(np.int32)
    Hh, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    white = im.min(2) >= 225
    # 1. mic pin candidates (same colour/shape rule as before) anywhere in the chest band
    pin_all = ((S < 60) & (V >= 110)).astype(np.uint8)
    PY0, PY1, PX0, PX1 = 900, 1750, 250, 830
    pmA = cv2.morphologyEx(pin_all[PY0:PY1, PX0:PX1], cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(pmA, 8)
    pins = [(st[i, 1] + PY0, st[i, 0] + PX0, st[i, 2], st[i, 3], st[i, 4]) for i in range(1, n)
            if st[i, 4] >= 300 and 28 <= st[i, 2] <= 100 and 28 <= st[i, 3] <= 100 and 0.6 <= st[i, 2] / st[i, 3] <= 1.6
            and 350 <= st[i, 0] + PX0 + st[i, 2] / 2 <= 730]
    wm = white.copy()
    for (py, px, pw, ph, _) in pins:
        wm[max(0, py - 6):py + ph + 6, max(0, px - 6):px + pw + 6] = False
    pin_top_any = max(pins, key=lambda p: p[4])[0] if pins else None   # the mic pin = largest pin-shaped blob
    # 2. caption text blocks
    Y0, Y1, X0, X1 = 700, 1500, 200, 880
    w = wm[Y0:Y1, X0:X1]; rc = w.sum(1)
    rows = np.where(rc >= 2)[0]
    if len(rows) == 0: return None
    blocks = []; s = rows[0]; p = rows[0]
    for r in rows[1:]:
        if r > p + 4: blocks.append((s, p)); s = r
        p = r
    blocks.append((s, p))
    cand = []
    for a, b in blocks:
        h = b - a + 1; cnt = int(rc[a:b + 1].sum())
        if not (8 <= h <= 110) or cnt < 80: continue
        cols = np.where(w[a:b + 1].any(0))[0] + X0
        cx = (cols.min() + cols.max()) / 2
        if not (340 <= cx <= 740) or cols.max() - cols.min() < 12: continue
        if pin_top_any is not None and Y0 + b >= pin_top_any: continue
        cand.append((a, b, cnt))
    if not cand: return None
    if pin_top_any is not None:
        a, b, cnt = max(cand, key=lambda z: z[1])          # lowest block above the pin
    else:
        a, b, cnt = max(cand, key=lambda z: z[2])
    top = Y0 + a; bot = Y0 + b
    sub = rc[a:b + 1]; base = Y0 + a + int(np.where(sub >= 0.5 * np.median(sub[sub > 0]))[0].max())
    cols = np.where(w[a:b + 1].any(0))[0] + X0; x0, x1 = int(cols.min()), int(cols.max())
    BGR = im.astype(np.int32)
    capd = cv2.dilate(white.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    beard = (Hh >= 4) & (Hh <= 22) & (S >= 140) & (V >= 90) & (V <= 200) & \
            ((BGR[..., 1] - BGR[..., 0]) >= 28) & ~capd
    # beard bottom within the caption's x-range; for narrow (short-word) captions widen to >=160 px
    bx0, bx1 = x0, x1
    if bx1 - bx0 < 160: c_ = (bx0 + bx1) // 2; bx0, bx1 = c_ - 80, c_ + 80
    bc = beard[700:bot + 61, bx0:bx1 + 1].sum(1); bi = np.where(bc >= 0.15 * (bx1 - bx0 + 1))[0]
    btip = 700 + int(bi.max()) if len(bi) else None
    pin = ((S < 60) & (V >= 110) & ~capd).astype(np.uint8)
    ys, ye = bot + 2, min(bot + 450, H - 1); xs, xe = max(x0 - 200, 0), min(x1 + 200, W - 1)
    pm = cv2.morphologyEx(pin[ys:ye, xs:xe], cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(pm, 8)
    cands = [i for i in range(1, n) if st[i, 4] >= 300 and 28 <= st[i, 2] <= 100 and
             28 <= st[i, 3] <= 100 and 0.6 <= st[i, 2] / st[i, 3] <= 1.6]
    ptop = None
    if cands:
        k = max(cands, key=lambda i: st[i, 4]); rw = (lab == k).sum(1)
        ptop = ys + int(np.where(rw >= 0.35 * st[k, 2])[0].min())
    return dict(captop=top, baseline=base, inkbot=bot, x0=x0, x1=x1, beard=btip, pin=ptop, caph=bot - top + 1,
                beard_clear=None if btip is None else top - btip,
                pin_clear=None if ptop is None else ptop - base,
                pin_clear_desc=None if ptop is None else ptop - bot)

# ---------------------------------------------------------------- helpers
def read_cut_times(specs):
    out = []
    for s in specs or []:
        if os.path.exists(s):
            txt = open(s, errors='ignore').read()
            hits = re.findall(r'\bt=([0-9]+\.?[0-9]*)', txt)
            if not hits and s.endswith('.json'):
                def walk(o):
                    if isinstance(o, dict):
                        for k, v in o.items():
                            if k in ('t', 'time', 'start', 'cut', 'cut_time') and isinstance(v, (int, float)): hits.append(v)
                            else: walk(v)
                    elif isinstance(o, list):
                        for v in o: walk(v)
                try: walk(json.loads(txt))
                except Exception: pass
            if not hits:   # joins.txt "edit 12.345 ..." or one float per line
                for line in txt.splitlines():
                    m = re.match(r'\s*(?:edit\s+)?([0-9]+\.[0-9]+)', line)
                    if m: hits.append(m.group(1))
            out += [float(h) for h in hits]
        else:
            out += [float(x) for x in s.split(',') if x.strip()]
    return sorted(set(round(t, 3) for t in out))

def prof_diff(a, b, minc=20):
    if a is None or b is None: return None
    common = [d for d in a if d in b]
    if len(common) <= minc: return None
    return float(np.median([abs(a[d] - b[d]) for d in common]))

def fmt(x, nd=3):
    if x is None: return 'NA'
    if isinstance(x, float): return f'{x:.{nd}f}'
    return str(x)

# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('video'); ap.add_argument('--cuts', action='append', default=[])
    ap.add_argument('--every', type=float, default=2.0, help='also list a frame every N s (default 2)')
    ap.add_argument('--csv'); ap.add_argument('--quiet', action='store_true')
    a = ap.parse_args()

    p = subprocess.Popen(['ffmpeg', '-loglevel', 'error', '-i', a.video, '-f', 'rawvideo',
                          '-pix_fmt', 'bgr24', '-'], stdout=subprocess.PIPE)
    F = []; prevg = None; k = 0
    while True:
        b = p.stdout.read(W * H * 3)
        if len(b) < W * H * 3: break
        im = np.frombuffer(b, np.uint8).reshape(H, W, 3)
        g = cv2.cvtColor(im[1250:1920, 360:720], cv2.COLOR_BGR2GRAY).astype(np.float32)
        r = dict(f=k, t=k / FPS, D=0.0 if prevg is None else float(np.abs(g - prevg).mean()))
        prevg = g
        V1200 = cv2.cvtColor(im[1200:1420], cv2.COLOR_BGR2HSV)[..., 2].astype(float)
        r['lay'] = layout_state(im); r['split'] = is_split(V1200)
        if r['lay'] == 'S':
            r['plateL'], r['plateR'] = plate_means(im)
        if r['split']:
            r['m'] = matte_metrics(im); r['dark_above'] = dark_rim(im)
            r['fol'], r['fol_xy'] = foliage(im)
            r['cap'] = split_caption(im)
        elif r['lay'] == 'F':
            r['ff'] = fullface_caption(im)
        F.append(r); k += 1
    p.wait()
    N = len(F)
    if N == 0: print('could not decode', a.video); sys.exit(2)

    # jitter (consecutive split frames with metrics) and index proxy profiles
    for i in range(N):
        m = F[i].get('m'); pm = F[i - 1].get('m') if i > 0 else None
        F[i]['jit'] = prof_diff(m['prof'], pm['prof']) if (m and pm) else None

    # layout runs
    runs = []; st = 0
    for i in range(1, N + 1):
        if i == N or F[i]['lay'] != F[st]['lay']: runs.append((F[st]['lay'], st, i)); st = i

    # cuts: frame 0, layout changes, head-region picture cuts (cut3 rule), --cuts times
    D = np.array([r['D'] for r in F]); cuts = {0}
    for _, s0, _ in runs: cuts.add(s0)
    for i in range(1, N):
        if F[i]['lay'] == 'S' and D[i] > max(5, 3 * np.median(D[max(0, i - 15):i + 15])): cuts.add(i)
    user = read_cut_times(a.cuts)
    for t in user:
        cuts.add(int(round(t * FPS)))
    cuts = sorted(c for c in cuts if 0 <= c < N)
    window = {}
    for c in cuts:
        for j in (c, c + 1, c + 2):
            if j < N: window.setdefault(j, f'cut{fmt(c / FPS)}+{j - c}')

    # plate dropout (platescan.py): split frames not within 1 frame of a split-run edge
    splitidx = [i for i in range(N) if F[i]['split']]
    pl = [i for i in range(1, N - 1) if F[i - 1]['lay'] == 'S' and F[i]['lay'] == 'S' and F[i + 1]['lay'] == 'S']
    if pl:
        A = np.array([[F[i]['plateL'], F[i]['plateR']] for i in pl])
        for n_, i in enumerate(pl):
            lo, hi = max(0, n_ - 5), min(len(pl), n_ + 6)
            dL = abs(A[n_, 0] - np.median(A[lo:hi, 0])); dR = abs(A[n_, 1] - np.median(A[lo:hi, 1]))
            F[i]['plate_dev'] = max(dL, dR)

    fails = []; warns = []
    def fail(i, what): fails.append((i, what)); F[i].setdefault('fails', []).append(what)
    def warn(i, what): warns.append((i, what)); F[i].setdefault('warns', []).append(what)

    # cut-window gates
    for j, lab in window.items():
        m = F[j].get('m')
        if not m: continue
        if m['rough'] > TH['rough']: fail(j, f"rough {m['rough']:.2f}")
        if m['green_in'] > TH['green_in']: fail(j, f"green_in {m['green_in']:.3f}")
        if m['green_out'] > TH['green_out']: fail(j, f"green_out {m['green_out']:.3f}")
        if m['specks'] > TH['specks']: fail(j, f"specks {m['specks']}")
        if F[j]['dark_above'] > TH['dark_above']: fail(j, f"dark_above {F[j]['dark_above']:.3f}")
    # matte-index proxy: only at picture-cut frames (head-region diff spike, cutframes rule)
    pic = [i for i in range(1, N) if F[i]['lay'] == 'S' and D[i] > max(5, 3 * np.median(D[max(0, i - 15):i + 15]))]
    for c in pic:
        if c + 1 >= N: continue
        mp, m0, mn = F[c - 1].get('m'), F[c].get('m'), F[c + 1].get('m')
        if not (mp and m0 and mn): continue
        dprev = prof_diff(m0['absprof'], mp['absprof']); dnext = prof_diff(m0['absprof'], mn['absprof'])
        F[c]['idx'] = (dprev, dnext)
        if dnext is not None and dprev is not None and dnext >= TH['index_px'] and dnext >= TH['index_ratio'] * max(dprev, 1.0):
            fail(c, f"index_jump next {dnext:.1f}px vs prev {dprev:.1f}px")
    # all split frames
    for i in pl:
        if F[i].get('plate_dev', 0) > TH['plate_jump']: fail(i, f"plate dropout: side-plate mean dev {F[i]['plate_dev']:.1f}")
    for i in splitidx:
        if F[i]['fol'] >= TH['foliage_px']: fail(i, f"foliage blob {F[i]['fol']}px at {F[i]['fol_xy']}")
        m = F[i].get('m')
        if m and i not in window and (m['green_in'] > TH['green_in'] or m['green_out'] > TH['green_out'] or m['rough'] > TH['rough']):
            warn(i, f"steady-state edge outlier rough {m['rough']:.2f} gin {m['green_in']:.3f} gout {m['green_out']:.3f}")
    # split caption gap per frame and per split run (baseline-based, spec_common)
    for lay, s0, e0 in runs:
        if lay != 'S': continue
        gaps = []
        for i in range(s0, e0):
            c = F[i].get('cap')
            if c and c[4] is not None:
                gp = c[0] - c[4]; F[i]['capgap'] = gp; F[i]['capgap_ink'] = c[0] - c[2]; F[i]['capdist'] = c[3]
                gaps.append(gp)
                if gp < TH['cap_gap_min']: fail(i, f"split caption baseline gap {gp}px < {TH['cap_gap_min']}")
                if c[3] is not None and c[3] <= 1: fail(i, "split caption touches head (2D dist <=1px)")
        if gaps:
            med = float(np.median(gaps))
            if not (TH['cap_gap_lo'] <= med <= TH['cap_gap_hi']):
                fail(s0, f"split run {s0/FPS:.2f}-{e0/FPS:.2f} caption baseline gap median {med:.0f}px outside 25..50")
    # full-face (skip first and last frame of each F run)
    for lay, s0, e0 in runs:
        if lay != 'F': continue
        for i in range(s0 + 1, e0 - 1):
            ff = F[i].get('ff')
            if not ff: continue
            if ff['beard_clear'] is not None and ff['beard_clear'] < TH['beard_min']:
                fail(i, f"beard clearance {ff['beard_clear']}px < 25")
            if ff['pin_clear'] is not None:
                if ff['pin_clear'] < TH['pin_min']: fail(i, f"pin clearance {ff['pin_clear']}px < 20")
                elif ff['pin_clear'] < TH['pin_ideal']: warn(i, f"pin clearance {ff['pin_clear']}px < 30 (ideal)")

    # steady-state reel stats
    R = np.array([F[i]['m']['rough'] for i in splitidx if F[i].get('m')])
    J = np.array([F[i]['jit'] for i in splitidx if F[i].get('jit') is not None])
    reel = []
    if len(R):
        reel.append(('rough median', float(np.median(R)), TH['rough_med']))
        if np.median(R) > TH['rough_med']: fail(splitidx[0], f"reel rough median {np.median(R):.2f}")
    if len(J):
        reel.append(('jitter median', float(np.median(J)), TH['jit_med']))
        reel.append(('jitter p90', float(np.percentile(J, 90)), TH['jit_p90']))
        if np.median(J) > TH['jit_med'] or np.percentile(J, 90) > TH['jit_p90']:
            fail(splitidx[0], f"reel jitter med {np.median(J):.2f} p90 {np.percentile(J,90):.2f}")

    # ------------------------------------------------------------ report
    every = max(1, int(round(a.every * FPS)))
    listed = sorted(set(window) | set(range(0, N, every)) | {i for i, _ in fails} | {i for i, _ in warns})
    hdr = ('frame', 't', 'lay', 'why', 'rough', 'jit', 'g_in', 'g_out', 'dark', 'specks', 'feath',
           'idx(prev/next)', 'plate_dev', 'foliage', 'capgap(base/ink)', 'ff_beard', 'ff_pin(base/desc)', 'result')
    lines = ['\t'.join(hdr)]
    for i in listed:
        r = F[i]; m = r.get('m'); ff = r.get('ff')
        why = window.get(i, 'every%.0fs' % a.every if i % every == 0 else 'flag')
        idx = r.get('idx'); res = 'FAIL' if r.get('fails') else ('WARN' if r.get('warns') else 'ok')
        if not r['split'] and not ff and not r.get('fails'): res = 'n/a'
        row = (str(i), f"{r['t']:.3f}", 'S' if r['split'] else r['lay'], why,
               fmt(m['rough'], 2) if m else '-', fmt(r.get('jit'), 2), fmt(m['green_in']) if m else '-',
               fmt(m['green_out']) if m else '-', fmt(r.get('dark_above')) if r['split'] else '-',
               str(m['specks']) if m else '-', fmt(m['feather'], 1) if m else '-',
               (f"{fmt(idx[0],1)}/{fmt(idx[1],1)}" if idx else '-'),
               fmt(r.get('plate_dev'), 1), str(r['fol']) if r.get('fol') is not None else '-',
               (f"{fmt(r.get('capgap'))}/{fmt(r.get('capgap_ink'))}" if r.get('capgap') is not None else '-'), fmt(ff['beard_clear']) if ff else '-',
               (f"{fmt(ff['pin_clear'])}/{fmt(ff['pin_clear_desc'])}" if ff else '-'),
               res + ('' if not r.get('fails') else ' ' + '; '.join(r['fails'])) +
               ('' if not r.get('warns') or r.get('fails') else ' ' + '; '.join(r['warns'])))
        lines.append('\t'.join(row))
    if not a.quiet: print('\n'.join(lines))
    if a.csv:
        with open(a.csv, 'w') as fo: fo.write('\n'.join(lines) + '\n')

    def peak(vals):
        v = [(x, i) for x, i in vals if x is not None]
        return max(v) if v else (None, None)
    W_ = [j for j in window if F[j].get('m')]
    print('\n=== SUMMARY', os.path.basename(a.video))
    print(f"frames {N} | split {len(splitidx)} | layout runs " + ' '.join(f"{l}:{s/FPS:.3f}-{e/FPS:.3f}" for l, s, e in runs))
    print(f"cuts {len(cuts)} ({len(user)} from --cuts) | cut-window split frames checked {len(W_)}")
    for nm, key, lim in (('rough', 'rough', TH['rough']), ('green_in', 'green_in', TH['green_in']),
                         ('green_out', 'green_out', TH['green_out']), ('specks', 'specks', TH['specks'])):
        v, i = peak([(F[j]['m'][key], j) for j in W_])
        print(f"  cut-window peak {nm:10s} {fmt(float(v) if v is not None else None)} at f{i} (limit {lim})")
    v, i = peak([(F[j]['dark_above'], j) for j in W_]); print(f"  cut-window peak dark_above {fmt(v)} at f{i} (limit {TH['dark_above']})")
    v, i = peak([(F[c]['idx'][1] - TH['index_ratio'] * max(F[c]['idx'][0], 1.0) if F[c].get('idx') and None not in F[c]['idx'] else None, c) for c in pic])
    print(f"  index proxy worst margin {fmt(v,1)} px at f{i} (fail if next>={TH['index_px']} and next>={TH['index_ratio']}x prev; {len(pic)} picture cuts)")
    for nm, val, lim in reel: print(f"  reel {nm:14s} {val:.2f} (limit {lim})")
    if len(R): print(f"  reel rough p90 {np.percentile(R,90):.2f} max {R.max():.2f}; jitter max {J.max() if len(J) else float('nan'):.2f}")
    v, i = peak([(F[j].get('plate_dev'), j) for j in pl]); print(f"  plate max deviation {fmt(v,1)} at f{i} (limit {TH['plate_jump']})")
    v, i = peak([(F[j]['fol'], j) for j in splitidx]); print(f"  foliage largest blob {v} px at f{i} (limit <{TH['foliage_px']})")
    cg = [(F[j]['capgap'], j) for j in splitidx if F[j].get('capgap') is not None]
    if cg:
        g = np.array([x for x, _ in cg]); mn = min(cg)
        print(f"  split caption gap crown-baseline median {np.median(g):.0f} p10 {np.percentile(g,10):.0f} min {mn[0]} at f{mn[1]} (25..50, never <18)")
        gi = [(F[j]['capgap_ink'], j) for j in splitidx if F[j].get('capgap_ink') is not None]; mi = min(gi)
        cd = [(F[j]['capdist'], j) for j in splitidx if F[j].get('capdist') is not None]; md_ = min(cd)
        print(f"  split caption gap crown-ink bottom (incl. descenders) median {np.median([x for x,_ in gi]):.0f} min {mi[0]} at f{mi[1]}; 2D min dist {md_[0]:.0f}px at f{md_[1]} (info / touch gate <=1)")
    fb = [(F[j]['ff']['beard_clear'], j) for j in range(N) if F[j].get('ff') and F[j]['ff']['beard_clear'] is not None]
    fp = [(F[j]['ff']['pin_clear'], j) for j in range(N) if F[j].get('ff') and F[j]['ff']['pin_clear'] is not None]
    if fb: mn = min(fb); print(f"  full-face beard clearance min {mn[0]} at f{mn[1]} (>=25)")
    if fp: mn = min(fp); print(f"  full-face pin clearance (baseline) min {mn[0]} at f{mn[1]} (>=20, ideal 30)")
    ff_frames = sum(1 for r in F if r.get('ff'))
    ff_inner = [i for lay, s0, e0 in runs if lay == 'F' for i in range(s0 + 1, e0 - 1)]
    ff_meas = sum(1 for i in ff_inner if F[i].get('ff'))
    print(f"  full-face frames with caption measured: {ff_frames} (inner F frames {ff_meas} of {len(ff_inner)})")
    hs = [F[i]['ff']['caph'] for i in ff_inner if F[i].get('ff')]
    if hs: print(f"  full-face caption ink height median {np.median(hs):.0f} px (text block incl. ascenders/descenders; 67 px type ~ 49 px cap height)")
    if ff_inner and ff_meas < 0.6 * len(ff_inner):
        print(f"  WARN: full-face caption detected on only {ff_meas}/{len(ff_inner)} inner F frames - check clearances BY EYE")
    ff_ = sorted({i for i, _ in fails}); wf = sorted({i for i, _ in warns} - set(ff_))
    print(f"FAIL frames: {len(ff_)}  WARN frames: {len(wf)}")
    if ff_: print('  ' + ', '.join(f"f{i}({F[i]['t']:.3f})" for i in ff_[:80]))
    verdict = 'FAIL' if fails else 'PASS'
    print('RESULT:', verdict)
    sys.exit(1 if fails else 0)

if __name__ == '__main__':
    main()
