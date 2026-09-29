#!/usr/bin/env python3
"""Beat planner: find the story in Brandon's words before choosing any graphic.

Reads the words Brandon speaks (with timings), his voice, and an inventory of the footage
that exists, then:

1. splits the talk into beats (sentences, with their clauses),
2. finds the hook, the stressed words (from the wording and from how he says them),
   demonstrations, emotional turns, results, the payoff and the CTA,
3. matches each demonstration to footage by what it shows,
4. picks a treatment per beat from variant pools: presenter first, no stacked band by
   default, screens alternating with his performance, transitions rotated without
   back-to-back repeats, showpieces at the hook, the major reveal and the payoff,
5. writes a beat map and a draft timeline, every time a word cue, that edit.py builds.

    python3 production/editor/plan_reel.py --draft draft.json [--assets assets.json] \\
        [--out timeline.json] [--plan plan.json] [--seed N] [--no-tighten]

draft.json is a timeline header: title, source.path, optional source.segments,
words_path, optional variation.avoid (recent hooks, CTA styles, icons). The asset
inventory is described in skill/references/house-style.md. Brandon's narration is the
input: the planner illustrates what he says and never asks footage to prove it.
Read the plan, sharpen hero wording in his own words where needed, then build and run
review_reel.py.
"""
import argparse
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import style  # noqa: E402
from cues import CueResolver, emphasis_key  # noqa: E402

STOP = set("""a an the and or but so to of in on at for with from by as is are was were be been being it its it's
this that these those i i'm i've i'd me my we our you your he she they them their there here then than just very
really also about into over under up down out off do does did doing can could would should will shall may might must
have has had having get got gets what which who whom whose when where why how all any some such own same other
basically actually literally kind sort like um uh yeah okay ok gonna wanna going now anymore ever yet again too
either today even i'll you'll we'll they'll it'll he'll she'll that's there's here's what's you're we're they're
he's she's you've we've they've you'd we'd they'd let's""".split())
UNITS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
TEENS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
         "seventeen": 17, "eighteen": 18, "nineteen": 19}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
NUMBER_WORDS = {**UNITS, **TEENS, **TENS, "hundred": 100, "thousand": 1000, "million": 1_000_000, "billion": 1_000_000_000}
MULTIPLIERS = {"hundred": 100, "thousand": 1000, "million": 1_000_000, "billion": 1_000_000_000}
POWER = set("""crazy insane wild every everything one only never always free actually real own exact entire whole
completely zero personalized generic template instantly automatically live first best biggest fastest secret nobody
without everyone anything nothing entirely fully minutes seconds overnight instant""".split())
TURN_STRONG = ["but", "however", "except", "here's the thing", "the crazy part", "the best part", "the wild part",
               "plot twist", "to top it all off", "to top it off", "on top of that", "not only", "instead", "turns out",
               "what if", "the problem", "the catch", "wait", "that's when", "here's why", "isn't even", "the craziest",
               "isn't just", "not just", "no longer", "the difference"]
TURN_SOFT = ["and now", "now", "so", "and then", "then"]
IRREGULAR = {"found": "find", "wrote": "write", "written": "write", "sent": "send", "bought": "buy", "built": "build",
             "made": "make", "gave": "give", "given": "give", "told": "tell", "ran": "run", "paid": "pay",
             "sold": "sell", "took": "take", "taken": "take", "got": "get", "went": "go", "did": "do", "done": "do",
             "said": "say", "knew": "know", "thought": "think", "brought": "bring", "won": "win", "spent": "spend",
             "kept": "keep", "met": "meet", "saw": "see", "seen": "see", "came": "come", "began": "begin",
             "chose": "choose", "drew": "draw", "grew": "grow", "held": "hold", "led": "lead", "lost": "lose",
             "stood": "stand", "threw": "throw", "understood": "understand", "hit": "hit", "set": "set", "put": "put",
             "ai": "ai", "its": "it", "emails": "email", "email": "email", "sites": "site"}
ACTION = {"find", "write", "send", "research", "verify", "buy", "host", "deploy", "create", "make", "type", "click",
          "open", "generate", "launch", "scrape", "ask", "give", "use", "run", "build", "include", "hit", "book",
          "call", "email", "post", "upload", "connect", "automate", "search", "check", "tell", "pull", "add", "close",
          "sell", "pay", "publish", "design", "code", "draft", "reply", "schedule", "set", "fill", "submit", "list",
          "track", "record", "edit", "test", "prompt", "paste", "copy", "download", "install", "sign", "ship"}
RESULT = {"live", "finish", "result", "revenue", "client", "lead", "book", "sell", "pay", "profit", "money",
          "dollar", "percent", "everything", "sale", "customer", "own", "internet", "launch", "win", "online"}
GLUE = {"a", "an", "the", "their", "its", "his", "her", "my", "your", "our", "own", "one", "of"}
NEGATION = {"isn't", "not", "no", "never", "didn't", "don't", "doesn't", "wasn't", "can't", "won't", "aren't"}
CONJ = {"while", "because", "cause", "'cause", "if", "unless", "until", "since", "though", "although", "whether",
        "whenever", "wherever", "before", "after", "once"}
# A phrase never ends on a preposition, or on a verb whose object it cuts off.
TRAIL_PREP = {"without", "with", "for", "from", "into", "onto", "like", "through", "across", "behind"}
OBJECT_START = {"the", "a", "an", "my", "your", "their", "our", "his", "her", "its", "this", "that", "these", "those",
                "every", "each", "some", "any"}
PRONOUN_OBJECT = {"you", "me", "them", "us", "it", "him", "her"}
VERBS = {"give", "gives", "gave", "run", "runs", "ran", "make", "makes", "made", "use", "uses", "used", "tell", "tells", "told",
         "take", "takes", "took", "need", "needs", "want", "wants", "show", "shows", "showed", "let", "lets", "help", "helps",
         "keep", "keeps", "kept", "put", "puts", "turn", "turns", "turned", "bring", "brings", "brought", "pay", "pays", "paid"}
# Single words that mean nothing on their own as big type.
WEAK_SINGLE = {"one", "only", "every", "everything", "own", "first", "never", "always", "real", "actually", "whole",
               "entire", "exact", "completely", "fully", "entirely", "best", "instantly", "automatically", "without"}
CTA_PATTERNS = ["comment", "dm me", "link in bio", "follow for", "follow me", "save this", "type the word",
                "send you", "grab the", "get the prompt"]
ICONS = [({"find", "search", "research", "look"}, "search"), ({"write", "email", "mail", "draft", "reply"}, "mail"),
         ({"send", "hit", "submit", "ship"}, "send"), ({"build", "code", "create", "make", "generate", "design"}, "wand"),
         ({"buy", "domain", "host", "deploy", "live", "internet", "publish", "launch"}, "globe"),
         ({"verify", "check", "test", "confirm"}, "check"), ({"contact", "call", "phone"}, "phone"),
         ({"book", "schedule", "calendar", "meeting"}, "calendar"), ({"template", "doc", "page", "file"}, "doc"),
         ({"information", "data", "service", "detail"}, "database"), ({"prompt", "chat", "ask", "tell"}, "chat"),
         ({"chatgpt", "ai", "agent", "gpt", "claude", "astra", "bot"}, "bot"), ({"client", "customer", "user"}, "users"),
         ({"revenue", "profit", "grow", "sale"}, "trend_up"), ({"business", "company", "shop", "store"}, "briefcase")]
PRESENTER_FRAMES = ("center", "tight", "close", "space_left", "space_right")
ACTION_STEMS = RESULT_STEMS = POWER_STEMS = None  # filled once stem() is defined (below)


def stem(word):
    w = str(word).casefold().replace("’", "'")
    w = re.sub(r"'s$", "", w)
    w = re.sub(r"[^a-z0-9]", "", w)
    if w in IRREGULAR:
        w = IRREGULAR[w]
        return w[:-1] if w.endswith("e") and len(w) >= 4 else w
    for suffix, repl in (("ies", "y"), ("ied", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3 and not (suffix == "s" and w.endswith("ss")):
            base = w[:-len(suffix)] + repl
            if suffix in ("ing", "ed") and len(base) >= 4 and base[-1] == base[-2] and base[-1] not in "lsz":
                base = base[:-1]
            if suffix == "es" and not re.search(r"(s|x|z|ch|sh)$", base):
                base = w[:-1]
            return base[:-1] if base.endswith("e") and len(base) >= 4 else base
    return w[:-1] if w.endswith("e") and len(w) >= 4 else w


def _stems(words):
    return {stem(w) for w in words}


def key(word):
    return re.sub(r"[^\w'$%]", "", str(word).casefold().replace("’", "'"))


ACTION_STEMS, RESULT_STEMS, POWER_STEMS = _stems(ACTION), _stems(RESULT), _stems(POWER)


# --- inputs ----------------------------------------------------------------------
def read_words(path):
    data = json.loads(Path(path).read_text())
    if isinstance(data, list):
        return data
    if "words" in data:
        return data["words"]
    return [w for seg in data.get("segments", []) for w in seg.get("words", [])]


def map_words(words, segments):
    out, cursor = [], 0.0
    for seg in segments:
        a, b = float(seg["start"]), float(seg["end"])
        for w in sorted(words, key=lambda w: float(w["start"])):
            s, e = float(w["start"]), float(w["end"])
            if a <= (s + e) / 2 < b:
                text = str(w.get("word", w.get("text", ""))).strip()
                if text:
                    out.append({"word": text, "start": cursor + max(s, a) - a, "end": cursor + min(e, b) - a,
                                "src_start": s, "src_end": e})
        cursor += b - a
    for prev, word in zip(out, out[1:]):  # the pause Brandon actually left, before any tightening
        word["pause_before"] = word["src_start"] - prev["src_end"]
    return out


def tighten(words, segments, max_gap=.5, keep_after=.16, keep_before=.1):
    """Split segments inside pauses longer than max_gap (cut about half a second after a
    thought ends); returns new segments on the source clock."""
    out = []
    for seg in segments:
        a, b = float(seg["start"]), float(seg["end"])
        inside = sorted((w for w in words if a <= (float(w["start"]) + float(w["end"])) / 2 < b), key=lambda w: float(w["start"]))
        start = a
        for w, nxt in zip(inside, inside[1:]):
            gap = float(nxt["start"]) - float(w["end"])
            if gap > max_gap and gap - keep_after - keep_before > .15:
                out.append({"start": round(start, 3), "end": round(float(w["end"]) + keep_after, 3)})
                start = float(nxt["start"]) - keep_before
        out.append({"start": round(start, 3), "end": round(b, 3)})
    return out


def decode(path, rate, start, duration):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.4f}", "-i", str(path), "-t", f"{duration:.4f}",
                          "-vn", "-ac", "1", "-ar", str(rate), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)


def prosody(source, segments, words, rate=16000):
    """Loudness (dB) and stretch (spoken length over expected length) per word."""
    try:
        signal = np.concatenate([decode(source, rate, float(s["start"]), float(s["end"]) - float(s["start"]))
                                 for s in segments])
    except (subprocess.CalledProcessError, ValueError):
        return [(0.0, 1.0) for _ in words]
    out = []
    for w in words:
        a, b = int(w["start"] * rate), max(int(w["end"] * rate), int(w["start"] * rate) + 1)
        seg = signal[a:b]
        rms = float(np.sqrt(np.mean(seg ** 2))) if seg.size else 0.0
        letters = len(re.sub(r"[^a-z]", "", w["word"].casefold())) or 1
        out.append((20 * math.log10(max(rms, 1e-6)), (w["end"] - w["start"]) / (.08 + .055 * letters)))
    return out


# --- word cues ---------------------------------------------------------------------
class Cues:
    """Readable, unambiguous word cues ("@website#2") for mapped word indices."""

    def __init__(self, words, duration, fps):
        self.words = words
        self.resolver = CueResolver(words, duration, fps)
        tokens = [t for t, _ in self.resolver.tokens]
        first_pos = {}
        per_word = {}
        for pos, (tok, wi) in enumerate(self.resolver.tokens):
            per_word.setdefault(wi, []).append(tok)
            first_pos.setdefault(wi, pos)
        self.body = {}
        for wi, toks in per_word.items():
            n = sum(1 for p in range(first_pos[wi] + 1) if tokens[p:p + len(toks)] == toks)
            total = sum(1 for p in range(len(tokens)) if tokens[p:p + len(toks)] == toks)
            self.body[wi] = (" ".join(toks), n, total)

    def __call__(self, wi, offset=0.0, edge="start"):
        wi = self._nearest(wi)
        body, n, total = self.body[wi]
        cue = "@" + body + (f"#{n}" if total > 1 else "")
        if edge == "end":
            cue += ":end"
        if abs(offset) >= .005:
            cue += f"{offset:+.2f}"
        return cue

    def _nearest(self, wi):
        if wi in self.body:
            return wi
        return min(self.body, key=lambda k: abs(k - wi))

    def t(self, wi, offset=0.0, edge="start"):
        wi = self._nearest(wi)
        return float(self.words[wi]["end" if edge == "end" else "start"]) + offset


# --- beats ---------------------------------------------------------------------------
def split_beats(words, pause=.45):
    """Sentences, plus a break at a pause that follows a clause ("... website, [pause] and then").
    A pause inside a phrase ("What if you [pause] could build") keeps the sentence together."""
    ends = lambda w: re.search(r"[.?!]['\"]?$", w["word"])
    beats, cur = [], []
    for i, w in enumerate(words):
        gap = w.get("pause_before", w["start"] - words[i - 1]["end"] if i else 0)
        clause_end = i > 0 and re.search(r"[,;:]['\"]?$", words[i - 1]["word"])
        if cur and gap > pause and (clause_end or len(cur) >= 5 or gap > 1.2):
            beats.append(cur)
            cur = []
        cur.append(i)
        if ends(w):
            beats.append(cur)
            cur = []
    if cur:
        beats.append(cur)
    # In a punctuated transcript a pause that ends no sentence or clause is a breath mid-sentence;
    # without punctuation, pauses are the only sentence marks, so only short fragments rejoin.
    punctuated = sum(1 for w in words if ends(w)) >= max(1, len(words) // 40)
    merged = []
    for b in beats:
        short = words[b[-1]]["end"] - words[b[0]]["start"] < .9 and len(b) <= 2
        open_end = merged and not ends(words[merged[-1][-1]]) and not re.search(r"[,;:]['\"]?$", words[merged[-1][-1]]["word"])
        dangling = open_end and (len(merged[-1]) <= 5 or (punctuated and len(merged[-1]) + len(b) <= 30))
        if merged and (short or dangling):
            merged[-1] += b  # a very short fragment joins the beat before; a dangling one joins what follows
        else:
            merged.append(b)
    # A lead-in ("Okay.", "So.") is not the hook: it joins the first real beat.
    if len(merged) > 1 and len(merged[0]) <= 2:
        merged[1] = merged[0] + merged[1]
        merged.pop(0)
    return merged


def clauses(words, idx):
    """Clauses split at commas and at 'and' + an action verb ("bought the domain and hosted it")."""
    out, cur = [], []
    for n, i in enumerate(idx):
        nxt = idx[n + 1] if n + 1 < len(idx) else None
        if (cur and key(words[i]["word"]) in {"and", "then"} and nxt is not None
                and stem(key(words[nxt]["word"])) in ACTION_STEMS and len(cur) >= 3):
            out.append(cur)
            cur = []
        cur.append(i)
        if re.search(r"[,;:]$", words[i]["word"]):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def text_of(words, idx):
    return " ".join(words[i]["word"] for i in idx)


def has_phrase(text, phrase):
    return re.search(r"(^|\W)" + re.escape(phrase) + r"(\W|$)", text) is not None


def lexical(words, i, beat_first, vocab):
    raw = words[i]["word"]
    k = key(raw)
    if not k:
        return -5.0
    s = stem(k)
    score = 0.0
    if k in STOP or k in NEGATION or k in CONJ or k in TRAIL_PREP:
        score -= 2
    elif len(k) >= 4:
        score += 1
    if re.search(r"\d|\$|%", raw) or (k in NUMBER_WORDS and k not in {"one"}):
        score += 3
    if k in POWER or s in POWER_STEMS:
        score += 2
    if (raw[:1].isupper() and i != beat_first and k not in {"i", "i'm", "i've", "i'd"}) or (len(raw) >= 2 and raw.isupper()):
        score += 2
    if s in vocab:
        score += 1.5
    return score


def zscores(values):
    arr = np.array(values, dtype=float)
    if arr.size < 2 or float(np.std(arr)) < 1e-6:
        return [0.0] * len(values)
    return list((arr - arr.mean()) / arr.std())


def analyze(words, pros, assets, duration):
    vocab = {stem(t) for a in assets for tag in a.get("tags", []) for t in tag.split()}
    beats = []
    for n, idx in enumerate(split_beats(words)):
        text = text_of(words, idx)
        low = text.casefold().replace("’", "'")
        head = " ".join(key(words[i]["word"]) for i in idx[:5])
        stems = [stem(key(words[i]["word"])) for i in idx]
        tags = set()
        if any(has_phrase(head if len(p.split()) == 1 else low, p) for p in TURN_STRONG):
            tags.add("turn")
        elif any(head.startswith(p + " ") for p in TURN_SOFT) and n > 0:
            tags.add("soft_turn")
        actions = [i for i, s in zip(idx, stems) if s in ACTION_STEMS]
        if actions:
            tags.add("demo")
        if any(re.search(r"\d|\$|%", words[i]["word"]) for i in idx) or any(s in RESULT_STEMS for s in stems) \
                or any(key(words[i]["word"]) in MULTIPLIERS for i in idx):
            tags.add("result")
        # A short reel's CTA can take a bigger share of it.
        if any(p in low for p in CTA_PATTERNS) and words[idx[0]]["start"] >= duration * (.55 if duration >= 20 else .4):
            tags.add("cta")
        # English puts the main stress on the last content word of a clause.
        nuclear = {next((i for i in reversed(c) if key(words[i]["word"]) not in STOP | NEGATION), None)
                   for c in clauses(words, idx)} - {None}
        rms = zscores([pros[i][0] for i in idx])
        stretch = zscores([min(3.0, pros[i][1]) for i in idx])
        scores = {}
        for j, i in enumerate(idx):
            lex = lexical(words, i, idx[0], vocab)
            voice = .5 * max(-1.5, min(1.5, rms[j])) + .35 * max(-1.5, min(1.5, stretch[j]))
            scores[i] = lex + (voice if lex > -1 else 0) + (.6 if i in nuclear else 0)
        beats.append({"n": n, "idx": idx, "start": words[idx[0]]["start"], "end": words[idx[-1]]["end"], "text": text,
                      "clauses": clauses(words, idx), "tags": tags, "scores": scores, "actions": actions,
                      "energy": float(np.mean([pros[i][0] for i in idx]))})
    if not beats:
        raise ValueError("no words to plan from")
    beats[0]["tags"].add("hook")
    # The payoff: the strongest result beat in the back half, before the CTA.
    cta_at = min((b["start"] for b in beats if "cta" in b["tags"]), default=duration)
    long_reel = duration >= 25
    back = [b for b in beats if b["start"] >= duration * .45 and b["end"] <= cta_at + .01 and "cta" not in b["tags"]]
    if not long_reel and not any("result" in b["tags"] for b in back):
        # A short clip may state its result up front: then the hook can carry the payoff.
        back = [b for b in beats if b["end"] <= cta_at + .01 and "cta" not in b["tags"]]
    weight = lambda b: (("result" in b["tags"]) * 2 + sum(1 for i in b["idx"] if stem(key(words[i]["word"])) in RESULT_STEMS) / 3
                        + len(b["text"].split()) / 40 + (b["energy"] - beats[0]["energy"]) / 20)
    strength = lambda b: sum(1 for i in b["idx"] if stem(key(words[i]["word"])) in RESULT_STEMS
                             or re.search(r"\d|\$", words[i]["word"]) or key(words[i]["word"]) in MULTIPLIERS)
    if back and duration >= 12:
        best = max(back, key=weight)
        if long_reel or strength(best) >= 2 or ("result" in best["tags"] and duration >= 15):
            best["tags"].add("payoff")
    for b in beats:
        for role in ("payoff" if "hook" in b["tags"] and "payoff" in b["tags"] else "hook", "cta", "payoff", "turn", "demo",
                     "result", "soft_turn"):
            if role in b["tags"]:
                b["role"] = "claim" if role == "soft_turn" else role
                break
        else:
            b["role"] = "claim"
        b["stress"] = pick_stress(words, b)
    return beats


def pick_stress(words, beat):
    length = beat["end"] - beat["start"]
    want = 1 if length < 2.2 else 2 if length < 4.5 else 3
    ranked = sorted(beat["scores"].items(), key=lambda kv: -kv[1])
    chosen = []
    for i, s in ranked:
        if s < 1.5 or len(chosen) >= want:
            break
        if all(abs(words[i]["start"] - words[j]["start"]) > .6 for j in chosen):
            chosen.append(i)
    return sorted(chosen)


# --- display text --------------------------------------------------------------------
DIGITS = {"zero": 0, "oh": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
          "nine": 9}


def money(tokens):
    """Read a spoken amount exactly, or not at all: 'a thousand dollar' -> '$1,000',
    'thirteen thousand dollars' -> '$13,000', 'a hundred and fifty dollars' -> '$150',
    'one point five million' -> '1.5M', '5 thousand dollars' -> '$5,000'. A sequence that is
    not one number ('one two three') stays as spoken. Returns (display, consumed) or None."""
    total, group, used, is_money, last = 0, 0, 0, False, None
    n = 0
    while n < len(tokens):
        raw, k = tokens[n], key(tokens[n])
        nxt = key(tokens[n + 1]) if n + 1 < len(tokens) else ""
        if used == 0 and k in {"a", "an"}:
            # "a thousand" is 1,000; in "a two thousand dollar app" the article is just an article.
            if nxt in MULTIPLIERS:
                group, used, last, n = 1, 1, "unit", n + 1
                continue
            return None
        written = re.sub(r"[.,!?;:]+$", "", str(raw)).casefold()
        if used == 0 and re.fullmatch(r"\$?\d[\d,]*(\.\d+)?[km]?", written):
            if written[-1] in "km" or not (nxt in MULTIPLIERS or nxt in {"dollar", "dollars", "bucks"}):
                return (raw, 1)  # written digits read as written
            group, is_money, last = float(written.lstrip("$").replace(",", "")), written.startswith("$"), "digits"
        elif k == "point" and last in {"unit", "teen", "ten"} and nxt in DIGITS:
            m, frac = n + 1, ""
            while m < len(tokens) and key(tokens[m]) in DIGITS:
                frac += str(DIGITS[key(tokens[m])])
                m += 1
            group = float(f"{int(group)}.{frac}")
            used, n, last = used + (m - n), m, "decimal"
            continue
        elif k in UNITS and last in {None, "ten", "hundred", "big", "and"}:
            group, last = group + UNITS[k], "unit"
        elif k in TEENS and last in {None, "hundred", "big", "and"}:
            group, last = group + TEENS[k], "teen"
        elif k in TENS and last in {None, "hundred", "big", "and"}:
            group, last = group + TENS[k], "ten"
        elif k == "hundred" and last in {"unit", "teen", "ten"}:
            group, last = group * 100, "hundred"
        elif k in MULTIPLIERS and k != "hundred" and last in {"unit", "teen", "ten", "hundred", "digits", "decimal"}:
            total, group, last = total + group * MULTIPLIERS[k], 0, "big"
        elif k == "and" and last in {"hundred", "big"} and (nxt in UNITS or nxt in TEENS or nxt in TENS):
            last = "and"
        elif k in {"dollar", "dollars", "bucks"} and last not in {None, "and"}:
            is_money, used = True, used + 1
            break
        else:
            break
        used += 1
        n += 1
    value = total + group
    if not value or used == 0 or (value == 1 and not is_money):
        return None
    if value >= 1_000_000 and round(value) % 100_000 == 0:
        text = f"{value / 1e6:g}M"
    elif value != int(value):
        text = f"{value:,.2f}".rstrip("0").rstrip(".")
    else:
        text = f"{int(value):,}"
    return ("$" + text if is_money else text), used


# Words that change the amount that follows them ("half a million", "a few thousand"): keep as spoken.
QUANTIFIERS = {"half", "quarter", "few", "couple", "several", "hundreds", "thousands", "millions", "dozens", "tens",
               "point"}


AMOUNT_WORDS = set(NUMBER_WORDS) | {"and", "point", "dollar", "dollars", "bucks", "percent", "k"} | set(DIGITS)


def number_runs(words, clause):
    """(first, last) positions in a clause of each spoken amount, with the words that change it:
    "a hundred and fifty dollars", "half a million dollars", "a few thousand". A phrase on screen
    takes a run whole or not at all, so his numbers are never cut in two."""
    runs, n = [], 0
    k = lambda j: key(words[clause[j]]["word"])
    digit = lambda j: bool(re.fullmatch(r"\$?\d[\d,.]*[km%]?", k(j)))
    while n < len(clause):
        start = n
        while n < len(clause) and (k(n) in QUANTIFIERS - {"point"} or k(n) in {"a", "an"}):
            n += 1
        if n < len(clause) and (k(n) in NUMBER_WORDS or digit(n)):
            end = n
            while end + 1 < len(clause) and (k(end + 1) in AMOUNT_WORDS or digit(end + 1)):
                if k(end + 1) == "and" and not (end + 2 < len(clause) and k(end + 2) in NUMBER_WORDS):
                    break
                end += 1
                if re.search(r"[,.;:!?]$", words[clause[end]]["word"]):
                    break
            while start < n and k(start) in {"a", "an"} and not (k(start + 1) in QUANTIFIERS or k(start + 1) in MULTIPLIERS):
                start += 1  # an article before a plain number is not part of it
            if end > start or k(start) in QUANTIFIERS:
                runs.append((start, end))
            n = end + 1
        else:
            n = max(n, start + 1)
    return runs


def display_words(tokens):
    return [t for t, _ in display_map(tokens)]


def display_map(tokens):
    """(display token, source positions): spoken money folds into "$2,000"; trailing
    punctuation goes."""
    out, i = [], 0
    while i < len(tokens):
        # Not after a word that changes the amount, nor inside a longer spoken number ("twenty twenty four").
        m = money(tokens[i:]) if not (i and (key(tokens[i - 1]) in QUANTIFIERS or key(tokens[i - 1]) in NUMBER_WORDS)) else None
        if m and m[1] > 1:
            out.append((m[0], list(range(i, i + m[1]))))
            i += m[1]
            continue
        t = re.sub(r"[.,!?;:]+$", "", tokens[i])
        if t:
            out.append((t, [i]))
        i += 1
    return out


def phrase_around(words, beat, wi, most=4, glue=GLUE):
    """A verbatim span of Brandon's words around a stressed word: the noun phrase or
    verb + object it belongs to, 1-4 words, never crossing 'to', 'that', 'and'."""
    clause = next((c for c in beat["clauses"] if wi in c), beat["idx"])
    pos = clause.index(wi)
    k = lambda j: key(words[clause[j]]["word"])
    solid = lambda j: (k(j) not in STOP or k(j) in NUMBER_WORDS or k(j) in NEGATION or k(j) in {"own", "one"}) and k(j) not in CONJ
    lo = hi = pos
    while hi + 1 < len(clause) and hi - lo + 1 < most:
        if solid(hi + 1) and k(hi + 1) not in NEGATION:
            hi += 1
        elif k(hi + 1) in glue and hi + 2 < len(clause) and (solid(hi + 2) or (k(hi + 2) in glue and hi + 3 < len(clause)
                and solid(hi + 3) and hi - lo + 3 < most)) and hi - lo + 2 < most:
            if not solid(hi + 2):
                hi += 1
            hi += 2
        else:
            break
        if re.search(r"[,.;:!?]$", words[clause[hi]]["word"]):
            break
    while lo > 0 and hi - lo + 1 < most:
        if solid(lo - 1) and not re.search(r"[,.;:!?]$", words[clause[lo - 1]]["word"]):
            lo -= 1
        elif k(lo - 1) in GLUE and lo - 2 >= 0 and solid(lo - 2) and hi - lo + 2 < most:
            lo -= 2
        elif k(lo - 1) in GLUE | {"i"} and hi - lo + 1 < most:
            lo -= 1
            break
        else:
            break
    while lo < pos and k(lo) in {"and", "but", "so", "then", "of", "even", "just", "really", "actually", "basically",
                                 "literally", "still", "also"}:
        lo += 1
    # Complete a noun phrase cut off after its determiner or "own" ("LIVE ON ITS OWN DOMAIN"), and a
    # verb's pronoun object ("NOBODY TELLS YOU").
    ends = lambda j: re.search(r"[,.;:!?]$", words[clause[j]]["word"])
    if hi + 1 < len(clause) and k(hi) in GLUE | {"own"} and solid(hi + 1) and not ends(hi):
        hi += 1
    elif (hi + 1 < len(clause) and k(hi + 1) in PRONOUN_OBJECT and not ends(hi)
          and (k(hi) in VERBS or stem(k(hi)) in ACTION_STEMS or k(hi) in {"tells", "told", "tell", "gives", "gave", "shows"})):
        hi += 1
    while hi > pos:
        last = k(hi)
        cut_verb = hi + 1 < len(clause) and k(hi + 1) in OBJECT_START and (last in VERBS or stem(last) in ACTION_STEMS)
        pronoun_end = last in PRONOUN_OBJECT and hi > lo and (k(hi - 1) in VERBS or stem(k(hi - 1)) in ACTION_STEMS
                                                              or k(hi - 1) in {"tells", "told", "tell"})
        if pronoun_end:
            break
        if (last in STOP and last not in {"own", "one"} | NEGATION) or last in CONJ or last in TRAIL_PREP or cut_verb:
            hi -= 1
        else:
            break
    for a, b in number_runs(words, clause):
        if a <= hi and b >= lo and (a < lo or b > hi):
            lo, hi = min(lo, a), max(hi, b)
    span = clause[lo:hi + 1]
    return span, display_words([words[j]["word"] for j in span])


def balanced(tokens):
    """Two lines with the most even character counts."""
    best = min(range(1, len(tokens)), key=lambda c: max(len(" ".join(tokens[:c])), len(" ".join(tokens[c:]))))
    return [" ".join(tokens[:best]), " ".join(tokens[best:])]


def lines_for(tokens, variant):
    tokens = [t.upper() if variant != "card" else t for t in tokens]
    if variant == "card" or len(tokens) <= 1:
        return [" ".join(tokens)]
    if variant == "slam":
        return [" ".join(tokens[:-1]), tokens[-1]]
    if variant == "split":
        return balanced(tokens)
    text = " ".join(tokens)
    return [text] if len(text) <= 13 else balanced(tokens)


def clause_label(words, clause):
    toks = [words[i]["word"] for i in clause]
    while toks and key(toks[0]) in {"and", "then", "it", "they", "i", "we", "also", "just", "so", "but", "he", "she"}:
        toks = toks[1:]
    toks = display_words(toks)[:4]
    while toks and key(toks[-1]) in STOP:
        toks = toks[:-1]
    text = " ".join(toks)
    return text[:1].upper() + text[1:] if text else ""


def icon_for(words, clause, banned):
    stems = {stem(key(words[i]["word"])) for i in clause}
    for group, icon in ICONS:
        if stems & _stems(group) and icon not in banned:
            return icon
    return None


# --- footage ---------------------------------------------------------------------------
def load_assets(path):
    if not path:
        return [], None
    path = Path(path).resolve()
    data = json.loads(path.read_text())
    items = data.get("assets", data) if isinstance(data, dict) else data
    out = []
    for a in items:
        a = dict(a)
        media = Path(a["path"]).expanduser()
        a["path"] = str(media if media.is_absolute() else (path.parent / media).resolve())
        a.setdefault("kind", "screen")
        a.setdefault("quality", "sharp")
        a.setdefault("tags", [])
        a.setdefault("moments", [])
        a["vocab"] = {stem(t) for tag in a["tags"] for t in tag.split()}
        for m in a["moments"]:
            m["vocab"] = {stem(t) for tag in m.get("tags", []) + [m.get("label", "")] for t in tag.split()} - {""}
        out.append(a)
    return out, path


def asset_fit(words, idx, asset):
    stems = {stem(key(words[i]["word"])) for i in idx if key(words[i]["word"]) not in STOP}
    return len(stems & asset["vocab"])


def best_moment(words, clause, asset, used=()):
    stems = {stem(key(words[i]["word"])) for i in clause if key(words[i]["word"]) not in STOP}
    ranked = sorted(asset["moments"], key=lambda m: (-len(stems & m["vocab"]), id(m) in used))
    return ranked[0] if ranked and (stems & ranked[0]["vocab"] or not used) else None


# --- plan ----------------------------------------------------------------------------
class Planner:
    def __init__(self, words, beats, assets, duration, fps, spec, rng, avoid, cues):
        self.w, self.beats, self.assets, self.duration, self.fps = words, beats, assets, duration, fps
        self.spec, self.rng, self.avoid, self.cue = spec, rng, avoid, cues
        self.blocks = []        # composition blocks: {start, start_cue, layout, ...}
        self.graphics, self.transitions, self.camera = [], [], []
        self.last_transition = None
        self.last_hero = None
        self.used_assets = {}
        self.banned_icons = set(spec["variety"].get("retired_motifs", {}).get("icons", [])) | set(avoid.get("icons", []))
        self.notes = []
        self.frame_cycle = self.rng.sample(["center", "tight"], 2)
        # Full-screen time is a budget: screens earn their seconds, then Brandon comes back.
        # The payoff reveal covers the frame too, so its share is held back until it lands.
        lay = spec["layout"]
        self.away_budget = min(lay["fullscreen_max_share"], 1 - lay["presenter_visible_min"]) * duration - .25
        self.away = 0.0
        revealable = any(a.get("result") or a.get("quality") == "sharp" for a in assets)
        self.payoff_reserve = 2.6 if revealable and any(b["role"] == "payoff" for b in beats) else 0.0
        self.pushes = 0  # eased camera accents (punches alternate with them)
        self.margin = 1 / fps + .005  # starts and ends snap to frames at build time
        self.showy = {t.split(":", 1)[1] for t in spec["showpiece"]["types"] if t.startswith("hero:")}

    # --- helpers
    def away_spans(self):
        """(start, end) of what hides Brandon so far: screen shots and payoff reveals."""
        blocks = sorted(self.blocks, key=lambda b: b["t"])
        spans = [(b["t"], nb["t"] if nb else self.duration) for b, nb in zip(blocks, blocks[1:] + [None])
                 if b["layout"] == "screen"]
        spans += [(self.seconds(g["start"]), self.seconds(g["end"])) for g in self.graphics if g["type"] == "reveal"]
        return sorted(spans)

    def run_start(self, t):
        """Where the run away from Brandon that a new full-frame moment at t would join begins."""
        start = t
        for a, z in sorted(self.away_spans(), key=lambda x: -x[1]):
            if start - .35 <= z <= start + .05 and a < start:
                start = a
        return start

    def room(self):
        """Full-screen seconds left for screens, with the payoff reveal's share kept back."""
        return self.away_budget - self.away - self.payoff_reserve

    def at(self, wi, offset=0.0, edge="start"):
        t = self.cue.t(wi, offset, edge)
        if t < 0:
            return 0.0, 0
        last = self.duration - 1 / self.fps
        if t > last:
            return last, round(last, 3)
        return t, self.cue(wi, offset, edge)

    def moves(self):
        """(seconds, kind) of every camera accent and styled transition planned so far."""
        out = [(self.seconds(c["at"]), c["kind"]) for c in self.camera
               if c["kind"] == "punch" or (c["kind"] == "push" and c.get("duration", 1.2) <= .8)]
        return out + [(t["at"], t["kind"]) for t in self.transitions]

    def accent(self, at, scale, x=0, y=3, hard=False):
        """Camera emphasis on a stressed word: an instant punch-in or a quick eased push,
        alternated with the move before it so the edit never leans on one move."""
        t = self.seconds(at)
        before = [k for s0, k in sorted(self.moves()) if s0 < t - 1e-3]
        punches = sum(1 for _, k in self.moves() if k == "punch")
        cap = max(2, math.floor(self.spec["transitions"]["max_share"] * (len(self.moves()) + 1)))
        after = [k for s0, k in sorted(self.moves()) if s0 > t + 1e-3]
        options = [k for k in ("punch", "push") if k not in set(before[-1:]) | set(after[:1])]
        if not options and not hard:
            return  # a punch and a push on either side: this word keeps the frame still
        if hard:
            kind = "punch"
        elif len(options) == 1:
            kind = options[0]
        elif punches >= cap:
            kind = "push"
        else:
            kind = "punch" if punches <= self.pushes else "push"
        move = {"kind": kind, "at": at, "scale": scale, "y": y}
        if x:
            move["x"] = x
        if kind == "push":
            move.update({"duration": .55, "ease": "power3.out"})
            self.pushes += 1
        self.camera.append(move)

    def choose(self, pool, avoid=()):
        options = [p for p in pool if p not in avoid] or list(pool)
        return self.rng.choice(options)

    def transition(self, t, kind, priority=False, **extra):
        """Styled transitions are spaced out; between them the edit hard-cuts."""
        if kind == "cut" or kind is None:
            return
        half = .2
        if t - half < .05 or t + .4 > self.duration:
            return
        spacing = 1.2 if priority else 2.2
        if any(abs(x["at"] - t) < spacing for x in self.transitions):
            return
        item = {"kind": kind, "at": round(t, 3), "duration": .4 if kind != "punch" else .2}
        item.update(extra)
        self.transitions.append(item)
        self.last_transition = kind

    def extras(self, kind, asset=None, target=(50, 52)):
        """Parameters that make a transition kind carry something across the cut."""
        if kind == "push_in":
            return {"target": list(target)}
        if kind == "shape_wipe":
            return {"origin": [50, 60], "color": (asset or {}).get("color", "#0b0e0c")}
        if kind in {"whip", "match_move"}:
            return {"direction": self.rng.choice(["left", "right"])}
        return {}

    def choose_fresh(self, pool, avoid):
        """Pick from the pool, favoring kinds this reel has used least (camera accents count);
        no kind goes past its share of the reel's moves."""
        used = [k for _, k in self.moves()]
        cap = max(2, math.floor(self.spec["transitions"]["max_share"] * (len(used) + 1)))
        options = [k for k in pool if k not in avoid and (k == "cut" or used.count(k) < cap)] \
            or [k for k in pool if k not in avoid] or list(pool)
        weights = [1 / (1 + 2 * used.count(k)) for k in options]
        return self.rng.choices(options, weights=weights, k=1)[0]

    def pick_transition(self, context, at=None):
        pools = {"enter_screen": ["push_in", "push_in", "shape_wipe", "zoom_blur", "cut"],
                 "leave_screen": ["match_move", "punch", "cut", "whip"],
                 "section": ["whip", "zoom_blur", "match_move", "light_leak", "punch"],
                 "reveal": ["push_in", "shape_wipe", "zoom_blur"],
                 "cta": ["punch", "zoom_blur", "whip", "light_leak"]}
        avoid = set(self.avoid.get("transitions", []))
        if at is None:
            avoid.add(self.last_transition)
        else:  # never the same move as the one just before or just after this moment
            # ...counting camera accents, and among the styled transitions alone.
            for moves in (sorted(self.moves()), sorted((x["at"], x["kind"]) for x in self.transitions)):
                before = [k for s0, k in moves if s0 < at - 1e-3]
                after = [k for s0, k in moves if s0 > at + 1e-3]
                avoid |= set(before[-1:]) | set(after[:1])
        return self.choose_fresh(pools[context], avoid)

    def block(self, t, cue, layout="presenter", soft=False, **extra):
        """Start a composition at t. A soft block (the return to Brandon after a screen) gives
        way to any later beat that starts a composition earlier than it."""
        for b in [b for b in self.blocks if b.get("soft") and b["t"] >= t - .05 and not soft]:
            self.blocks.remove(b)
            self.transitions = [x for x in self.transitions if abs(x["at"] - b["t"]) > .06]
        same = [b for b in self.blocks if abs(b["t"] - t) < 1e-3]
        if same:
            same[-1].update({"layout": layout, **extra})
            if not soft:
                same[-1].pop("soft", None)
            return
        self.blocks.append({"t": t, "cue": cue, "layout": layout, **({"soft": True} if soft else {}), **extra})

    def next_frame(self, side=None):
        if side:
            return side
        frame = self.frame_cycle[0]
        self.frame_cycle.reverse()
        return frame

    def fitted(self, lines, variant):
        """Rendered size of hero lines on the narrowest hero zone (the builder's own fit)."""
        from motion_kit import fit_size, hero_line_scales
        return fit_size(lines, 136, 1080 * .80, 84, hero_line_scales(variant, lines))

    def hero_variant(self, pool):
        """A variant from the pool: never the last one used, favoring the least used so far."""
        used = [g.get("variant") for g in self.graphics if g["type"] == "hero"]
        cap = max(2, math.floor(.4 * (len(used) + 1)))
        options = [v for v in pool if v != self.last_hero and used.count(v) < cap] \
            or [v for v in pool if v != self.last_hero] or list(pool)
        weights = [1 / (1 + 2 * used.count(v)) for v in options]
        variant = self.rng.choices(options, weights=weights, k=1)[0]
        self.last_hero = variant
        return variant

    def best_phrase(self, beat, after=None):
        """The beat's strongest verbatim phrase with two or more content words."""
        best = None
        for c in beat["clauses"]:
            for i in c:
                if key(self.w[i]["word"]) in STOP | GLUE or (after is not None and self.cue.t(i) < after):
                    continue
                span, tokens = phrase_around(self.w, beat, i)
                content = [j for j in span if key(self.w[j]["word"]) not in STOP | GLUE]
                if len(content) >= 2:
                    score = sum(beat["scores"][j] for j in content)
                    if best is None or score > best[0]:
                        best = (score, max(content, key=lambda j: beat["scores"][j]))
        return best[1] if best else None

    def contrast_span(self, beat):
        """"It isn't just X, it's actually Y": the words that carry the turn are Y's."""
        for a, b in zip(beat["clauses"], beat["clauses"][1:]):
            if not any(key(self.w[i]["word"]) in NEGATION for i in a):
                continue
            filler = {"to", "it's", "it", "actually", "just", "really", "and", "but", "so", "now", "that's", "is", "was"}
            span = list(b)
            for _ in range(2):  # the clause without its lead-in, at most five words
                while span and key(self.w[span[0]]["word"]) in filler:
                    span = span[1:]
                span = span[-5:]
            while len(span) > 1 and key(self.w[span[-1]]["word"]) in (STOP | CONJ | TRAIL_PREP) - PRONOUN_OBJECT:
                span = span[:-1]
            if span and any(key(self.w[i]["word"]) not in STOP | GLUE for i in span):
                return span
        return None

    def add_hero(self, gid, beat, wi, end_t, end_cue, pool, zone="chest", beat_name=None, place=None, impact=False,
                 not_before=None, fallback=True, span=None):
        if span is not None:  # a phrase chosen by the caller (a turn's contrast): one content word is enough
            tokens = display_words([self.w[j]["word"] for j in span])
            return self._place_hero(gid, beat, wi, span, tokens, end_t, end_cue, pool, zone, beat_name, place, impact,
                                    not_before)
        span, tokens = phrase_around(self.w, beat, wi)
        weak = not tokens or (len([t for t in tokens if key(t) not in STOP | GLUE]) < 2
                              and not re.search(r"\d|\$", " ".join(tokens))
                              and not any((t.isupper() and len(t) > 2) or key(t) in POWER for t in tokens))
        if weak and fallback:
            alt = self.best_phrase(beat, after=not_before)
            if alt is not None and alt != wi:
                return self.add_hero(gid, beat, alt, max(end_t, self.cue.t(alt) + 1.0), end_cue if end_t >= self.cue.t(alt) + 1.0
                                     else round(self.cue.t(alt) + 1.0, 3), pool, zone, beat_name, place, impact, not_before,
                                     fallback=False)
        if not tokens:
            return None
        content = [t for t in tokens if key(t) not in STOP | GLUE]
        strong_word = re.search(r"\d|\$", " ".join(tokens)) or any(t.isupper() and len(t) > 2 for t in tokens) \
            or any(key(t) in POWER - WEAK_SINGLE for t in tokens)
        if len(content) < 2 and not strong_word:
            return None
        return self._place_hero(gid, beat, wi, span, tokens, end_t, end_cue, pool, zone, beat_name, place, impact,
                                not_before)

    def _place_hero(self, gid, beat, wi, span, tokens, end_t, end_cue, pool, zone, beat_name, place, impact, not_before):
        if end_t > self.duration:
            end_t, end_cue = self.duration, round(self.duration, 3)
        # Big type stays big: a phrase too long to fit at the house minimum loses its outer words.
        hero_min = self.spec["type"]["hero_px"]["min"]
        options = lambda toks: [v for v in pool if v != "split" or len(toks) >= 2] or ["stack"]
        best = lambda toks: max(self.fitted(lines_for(toks, v), v) for v in options(toks))
        words_by = self.spec["hook"]["hero_words_by"]
        clause = next((c for c in beat["clauses"] if span[0] in c), beat["idx"])
        amounts = {clause[q] for a, b in number_runs(self.w, clause) for q in range(a, b + 1)}
        while best(tokens) < hero_min and len(span) > 2:
            far = span[0] if span[0] != wi else span[-1]  # leading words go first; the phrase keeps its head
            if far in amounts:
                far = span[-1] if far == span[0] and span[-1] not in amounts and span[-1] != wi else None
            if far is None:
                break  # his number stays whole, at a smaller size
            if (far == span[0] and span[-1] != wi and beat_name == "hook"
                    and self.w[span[0]]["start"] <= words_by < self.w[span[1]]["start"]):
                far = span[-1]  # hook type keeps its first word inside the key-word deadline
            span = [j for j in span if j != far]
            # A trimmed phrase still never ends on a function word, preposition or conjunction.
            while len(span) > 1 and span[-1] != wi and (key(self.w[span[-1]]["word"]) in (STOP | CONJ | TRAIL_PREP | GLUE) - PRONOUN_OBJECT):
                span = span[:-1]
            tokens = display_words([self.w[j]["word"] for j in span])
        variant = self.hero_variant(options(tokens))
        if self.fitted(lines_for(tokens, variant), variant) < hero_min:
            variant = max(options(tokens), key=lambda v: self.fitted(lines_for(tokens, v), v))
            self.last_hero = variant
        accent = [t for t, pos in display_map([self.w[j]["word"] for j in span]) if wi in [span[q] for q in pos]] or tokens[-1:]
        start_t, start_cue = self.at(span[0], -.03)
        if not_before is not None and start_t < not_before:
            # Words already spoken land together on the next spoken word (the floor itself when a
            # word starts there); hook type never slips past the key-word deadline for it.
            k = next((j for j in range(span[0], len(self.w)) if self.w[j]["start"] >= not_before - .06), None)
            snap = self.cue.t(k, -.03) if k is not None else None
            late = (beat_name == "hook" and not_before <= self.spec["hook"]["hero_words_by"]
                    and snap is not None and snap > self.spec["hook"]["hero_words_by"])
            if k is not None and snap > not_before + .06 and snap <= not_before + .4 and not late:
                start_t, start_cue = self.at(k, -.03)
            else:
                start_t, start_cue = not_before, round(not_before, 3)
        hold = self.spec["motion"]["hold"]["hero_min"]
        if self.duration - start_t < hold + self.margin:
            return None  # too close to the end to be read
        if end_t - start_t < hold + self.margin:
            end_t = min(self.duration, start_t + max(1.0, hold + .1))
            end_cue = round(end_t, 3)
        g = {"id": gid, "type": "hero", "variant": variant, "lines": lines_for(tokens, variant),
             "accent_words": [a.upper() if variant != "card" else a for a in accent], "start": start_cue, "end": end_cue,
             "zone": zone, "beat": beat_name or beat["role"]}
        if place:
            g.update(place)
        if variant == "slam" and impact:
            g["impact"] = True
        self.graphics.append(g)
        return g, start_t, end_t

    # --- treatments
    def plan(self):
        self.block(0.0, 0, "presenter", frame="tight")
        hook_kinds = [k for k in self.spec["variety"]["hook_kinds"] if k not in self.avoid.get("hooks", [])]
        for n, beat in enumerate(self.beats):
            role = beat["role"]
            if n == 0:
                self.hook(beat, hook_kinds, payoff=role == "payoff")
            elif role == "cta":
                self.cta(beat)
            elif role == "payoff":
                self.payoff(beat)
            elif "demo" in beat["tags"] and self.match(beat):
                self.demo(beat, self.match(beat))
            elif role == "turn":
                self.turn(beat)
            elif role in {"demo"}:
                self.demo_graphic(beat)
            elif role == "result":
                self.result(beat)
            else:
                self.claim(beat)
        self.pace_sections()
        self.rhythm()
        return self.timeline_parts()

    def pace_sections(self):
        """A beat that opens after a long run of hard cuts gets a section transition, so the
        styled-transition pace stays near the approved calibration's."""
        for beat in self.beats[1:]:
            t = self.cue.t(beat["idx"][0], -.04)
            block = next((b for b in self.blocks if abs(b["t"] - t) < 1e-3 and b["layout"] == "presenter"), None)
            if block is None or t < .6 or t > self.duration - 1.0:
                continue
            if any(t - 4.5 < x["at"] < t + 2.2 for x in self.transitions):
                continue
            kind = self.pick_transition("section", t)
            self.transition(t, kind, **self.extras(kind))

    def match(self, beat):
        scored = []
        for a in self.assets:
            fit = asset_fit(self.w, beat["idx"], a)
            if fit >= 1:
                scored.append((fit - .6 * self.used_assets.get(a["id"], 0) + (.4 if a.get("quality") == "sharp" else 0), a))
        return max(scored, key=lambda s: s[0])[1] if scored else None

    def keyscore(self, beat, i):
        """Stress plus a bonus for the words that carry a promise: numbers and results."""
        k = key(self.w[i]["word"])
        promise = re.search(r"\d|\$|%", self.w[i]["word"]) or (k in NUMBER_WORDS and k != "one") or stem(k) in RESULT_STEMS
        return beat["scores"][i] + (1.5 if promise else 0)

    def anchor_for(self, beat, assets, before=None):
        """(stressed word, asset) whose phrase the result footage shows best."""
        best = None
        for i in beat["idx"]:
            if beat["scores"][i] < 1 or (before is not None and self.w[i]["start"] > before):
                continue
            span, _ = phrase_around(self.w, beat, i)
            stems = {stem(key(self.w[j]["word"])) for j in span}
            for a in assets:
                fit = len(stems & a["vocab"]) + .3 * (a.get("quality") == "sharp") - .5 * self.used_assets.get(a["id"], 0)
                if fit >= 1 and (best is None or fit + beat["scores"][i] / 10 > best[0]):
                    best = (fit + beat["scores"][i] / 10, i, a)
        return (best[1], best[2]) if best else (None, None)

    def hook(self, beat, kinds, payoff=False):
        """The first beat: key words staged at once, something striking inside 3 s."""
        w = self.w
        stress = beat["stress"] or [max(beat["idx"], key=lambda i: beat["scores"][i])]
        results = [a for a in self.assets if a.get("result")]
        options = []
        for k in kinds:
            if k == "action_first" and (not any(a.get("quality") == "sharp" for a in self.assets) or self.room() < 1.6):
                continue
            if k == "result_preview" and (not results or (self.room() < self.spec["motion"]["hold"]["screen_min"] and not payoff)):
                continue
            if k == "question" and "?" not in beat["text"]:
                continue
            options.append(k)
        # A result the viewer can see beats a promise; prefer it when the footage exists.
        if results and "result_preview" in options and (payoff or self.rng.random() < .7):
            kind = "result_preview"
        else:
            kind = self.choose(options or ["hero_slam"])
        self.hook_kind = kind + ("+payoff" if payoff else "")
        end_t, end_cue = self.at(beat["idx"][-1], .12, "end")
        hold = self.spec["motion"]["hold"]["hero_min"]
        payoff_by = self.spec["hook"]["payoff_by"]
        first_frame = "close" if kind == "cold_open" else self.rng.choice(["center", "tight"])
        self.blocks[0]["frame"] = first_frame
        if first_frame != "close":
            self.camera.append({"kind": "push", "at": 0.0, "scale": 1.12 if first_frame == "center" else 1.2,
                                "duration": 1.5, "ease": "power2.out", "y": 2})
        else:  # the close cold open creeps in so the first frame is already moving
            self.camera.append({"kind": "push", "at": 0.0, "scale": 1.06, "duration": 2.0, "ease": "sine.out"})
        busy = []  # (start, end) of staged hero text, so heroes never overlap

        def free_from(t):
            return max([t] + [e + .05 for s0, e in busy if s0 <= t < e + .05])

        visual = None  # (t0, t1) of the striking visual
        cap = end_t - .3
        pay_i = None
        if payoff:
            late = [i for i in beat["idx"] if beat["scores"][i] >= 1 and self.cue.t(i) > 2.2]
            if late:
                pay_i = max(late, key=lambda i: self.keyscore(beat, i))
                pay_span, _ = phrase_around(w, beat, pay_i, glue=GLUE | {"on", "in", "for", "with", "to"})
                cap = min(cap, self.cue.t(pay_span[0]) - .4)
        # The hook's hit is its strongest word before the payoff phrase (that one gets the reveal).
        early = [i for i in stress if i != pay_i and self.cue.t(i) < cap]
        if payoff and not early:
            early = [i for i in beat["idx"] if beat["scores"][i] >= 1.5 and i != pay_i and self.cue.t(i) < cap]
        key_i = max(early or stress, key=lambda i: self.keyscore(beat, i))
        if kind == "result_preview":
            anchor, asset = self.anchor_for(beat, results, before=min(payoff_by + 1.5, cap))
            if anchor is None:
                anchor, asset = key_i, max(results, key=lambda a: a.get("quality") == "sharp")
            span, _ = phrase_around(w, beat, anchor)
            t0 = max(.35, min(self.cue.t(span[0]) - .22, payoff_by - .6))
            screen_min = self.spec["motion"]["hold"]["screen_min"] + self.margin
            t1 = min(t0 + 2.4, max(t0 + 1.45, self.cue.t(span[-1], .35, "end")), cap, t0 + max(screen_min, self.room()))
            meets = payoff and cap - t1 < 1.0
            if meets:
                t1 = cap + .4  # run straight into the payoff reveal instead of flashing back to Brandon
            if t1 - t0 >= screen_min:
                self.screen(asset, beat, t0, round(t0, 3), t1, round(t1, 3), preview=True, clause_list=[span],
                            exit_transition=not meets)
                visual = (t0, cap if meets else t1)
                self.notes.append(f"hook previews {asset['id']} at {t0:.1f}s on \"{' '.join(w[j]['word'] for j in span)}\"")
        elif kind == "action_first":
            asset = max((a for a in self.assets if a.get("quality") == "sharp"), key=lambda a: asset_fit(w, beat["idx"], a))
            t1 = max(1.6, min(self.cue.t(key_i) - .05, 2.4, self.room()))
            self.screen(asset, beat, 0.0, 0, t1, round(t1, 3), preview=True)
            visual = (0.0, t1)
            self.notes.append(f"hook opens on {asset['id']} before cutting to Brandon")
        # Opening words: the first phrase worth staging, inside the first second.
        key_t = self.cue.t(phrase_around(w, beat, key_i)[0][0])
        words_by = self.spec["hook"]["hero_words_by"]
        if visual and visual[0] <= words_by and key_t > words_by - .05 and kind in {"result_preview", "action_first"}:
            opener = anchor if kind == "result_preview" else max(
                (i for i in beat["idx"] if key(w[i]["word"]) not in STOP | GLUE | CONJ and self.cue.t(i) < key_t - .3),
                key=lambda i: beat["scores"][i], default=None)
            span, tokens = phrase_around(w, beat, opener) if opener is not None else ([], [])
            if span:
                # On the phrase's first word, or the next word spoken once the visual has landed.
                floor = visual[0] + .24
                j = next((j for j in range(span[0], len(w)) if self.cue.t(j, -.03) >= floor - 1e-3), None)
                s_t, s_c = self.at(span[0], -.03) if self.cue.t(span[0], -.03) >= floor else (
                    self.at(j, -.03) if j is not None and self.cue.t(j, -.03) <= floor + .4 else (floor, round(floor, 3)))
                e_t = min(key_t - .08, visual[1] - .02)
                if tokens and e_t - s_t >= hold + self.margin:
                    variant = self.hero_variant(["stack", "outline"])
                    self.graphics.append({"id": "hook-open", "type": "hero", "variant": variant,
                                          "lines": lines_for(tokens, variant), "accent_words": [tokens[-1].upper()],
                                          "start": s_c, "end": round(e_t, 3), "zone": "top", "beat": "hook",
                                          "scrim": "plate"})
                    busy.append((s_t, e_t))
        late = key_t > words_by - .05

        def place_card():
            clause = [i for i in beat["clauses"][0] if w[i]["start"] < key_t - .05][:9] or beat["clauses"][0][:6]
            while len(clause) > 2 and key(w[clause[-1]]["word"]) in STOP | GLUE | CONJ | TRAIL_PREP:
                clause = clause[:-1]
            while clause and key(w[clause[0]]["word"]) in {"and", "but", "so", "now", "then", "okay", "ok", "alright",
                                                           "hey", "um", "uh", "well", "yeah", "look", "guys"}:
                clause = clause[1:]
            tokens = display_words([w[i]["word"] for i in clause])
            if not tokens:
                return False
            tokens[0] = tokens[0][:1].upper() + tokens[0][1:]
            card_end = max(1.5, min(key_t - .06, (visual[0] - .06) if visual and visual[0] > 1.5 else 99,
                                    w[clause[-1]]["end"] + .45))
            best = max((i for i in clause if key(w[i]["word"]) not in STOP | GLUE), key=lambda i: beat["scores"][i],
                       default=None)
            accent = [re.sub(r"[.,!?;:]+$", "", w[best]["word"])] if best is not None else tokens[-1:]
            self.graphics.append({"id": "hook-card", "type": "hero", "variant": "card", "text": " ".join(tokens),
                                  "accent_words": accent, "start": 0, "end": round(card_end, 3), "zone": "top",
                                  "beat": "hook"})
            self.last_hero = "card"
            busy.append((0.0, card_end))
            return True

        if kind in {"hero_card", "question"} or (late and not busy and (not visual or visual[0] > words_by)):
            opening = [i for i in beat["idx"] if w[i]["start"] <= 1.0 and beat["scores"][i] >= 1.5 and i != key_i]
            staged = None
            for i in sorted(opening, key=lambda i: -beat["scores"][i]):
                span, tokens = phrase_around(w, beat, i)
                strong = len(tokens) >= 2 or re.search(r"\d|\$", " ".join(tokens)) or w[i]["word"][:1].isupper()
                limit = min([x for x in (visual[0] if visual else None, key_t) if x is not None]) - .06
                if strong and limit - self.cue.t(span[0]) >= hold and kind not in {"hero_card", "question"}:
                    made = self.add_hero("hook-open", beat, i, limit, round(limit, 3),
                                         ["outline", "stack"] if kind == "cold_open" else ["stack", "split", "outline"],
                                         beat_name="hook", zone="top" if kind == "action_first" else "chest")
                    if made:
                        staged = made
                        busy.append((made[1], made[2]))
                    break
            if staged is None:
                place_card()
        if late and not busy:
            place_card()  # nothing else lands big type by the deadline (the card rides a preview on its plate)
        # The key phrase lands as the hook's hit, over the visual when one is up.
        k_end = self.split_end(beat, key_i, end_t, end_cue)
        start_floor = free_from(key_t - .03)
        if visual and visual[0] <= key_t <= visual[1]:
            start_floor = max(start_floor, visual[0] + .24)
            k_end = (min(k_end[0], visual[1] - .02), round(min(k_end[0], visual[1] - .02), 3))
        hit = None
        if not payoff or self.cue.t(key_i) < payoff_by:
            over = bool(visual and visual[0] <= key_t <= visual[1])
            hit = self.add_hero("hook-hit", beat, key_i, k_end[0], k_end[1], ["slam"] if kind == "cold_open" else ["slam", "split"],
                                beat_name="hook", impact=True, not_before=start_floor, zone="top" if over else "chest",
                                place={"scrim": "plate"} if over else None)
        if hit:
            busy.append((hit[1], hit[2]))
            if not (visual and visual[0] - .05 <= hit[1] <= visual[1] + .35):
                self.accent(hit[0]["start"], 1.22, y=5, hard=True)
                self.graphics.append({"id": "hook-glints", "type": "particles", "start": hit[0]["start"],
                                      "end": round(min(hit[2], hit[1] + 1.8), 3), "x": 8, "y": 24, "w": 84, "h": 44})
        if payoff:
            self.payoff(beat, after=visual[1] if visual else None, skip_block=True, target=pay_i)
            return
        # A later stressed word in a long hook gets its own beat of type.
        last = max([e for _, e in busy] + [visual[1] if visual else 0])
        later = [i for i in stress if i != key_i and self.cue.t(i) > last + .1]
        if later and end_t - self.cue.t(later[0]) >= hold:
            made = self.add_hero("hook-tail", beat, later[0], end_t, end_cue, ["stack", "outline", "split"], beat_name="hook",
                                 not_before=free_from(self.cue.t(phrase_around(w, beat, later[0])[0][0]) - .03))
            if made and visual and made[1] < visual[1]:
                made[0]["start"] = round(visual[1] + .05, 3)

    def split_end(self, beat, wi, end_t, end_cue):
        """End a hero at the close of its clause (it must not ride the whole beat)."""
        clause = next((c for c in beat["clauses"] if wi in c), beat["idx"])
        t, c = self.at(clause[-1], .25, "end")
        if t - self.cue.t(wi) < 1.1:
            t, c = end_t, end_cue
        return (t, c) if t <= end_t else (end_t, end_cue)

    def screen(self, asset, beat, t0, c0, t1, c1, preview=False, clause_list=None, enter="enter_screen", exit_transition=True):
        """A full-frame 2.5D capture shot with focus crops landing on spoken words."""
        w = self.w
        used = set()
        focus, highlights, first = [], [], None
        clause_list = clause_list or beat["clauses"]
        for clause in clause_list:
            anchor = next((i for i in clause if i in beat["stress"]), clause[0])
            if not t0 - .05 <= w[anchor]["start"] < t1 - .4:
                continue
            m = best_moment(w, clause, asset, used)
            if m is None or not m.get("rect"):
                continue
            used.add(id(m))
            at_t, at_c = self.at(anchor, -.08)
            if at_t < t0 + .15:
                at_t, at_c = t0 + .15, round(t0 + .15, 3)
            focus.append({"at": at_c, "rect": m["rect"], "duration": .7 if not focus else .6})
            first = first or (m, at_t)
            if m.get("label") and asset.get("quality") == "sharp" and len(highlights) < 2 and t1 - at_t > 1.2 and not preview:
                highlights.append({"rect": m["rect"], "at": at_c if isinstance(at_c, str) else round(at_t + .3, 3),
                                   "label": m["label"]})
        if not focus and asset["moments"] and asset["moments"][0].get("rect"):
            m = best_moment(w, [i for c in clause_list for i in c], asset) or asset["moments"][0]
            focus.append({"at": round(t0 + .45, 3), "rect": m["rect"], "duration": .8})
            first = (m, t0 + .45)
        source_start = float(asset.get("source_start", 0))
        is_image = asset["path"].lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
        if first and first[0].get("at") is not None and not is_image:
            # The clip reaches the moment as the word that names it is spoken.
            source_start = max(0.0, float(first[0]["at"]) - (first[1] - t0) - .15)
        tilts = [[10, -8], [8, 9], [12, -4], [7, 12]]
        shot = {"layout": "screen", "media": asset["path"], "source_start": round(source_start, 3),
                "aspect": asset.get("aspect", .5625), "plane_w": 86 if asset.get("quality") == "sharp" else 94,
                "tilt": self.rng.choice(tilts), "focus": focus, "asset": asset["id"]}
        if asset.get("quality") != "sharp":
            shot["fill"] = 1.15
        if highlights:
            shot["highlights"] = highlights
        self.block(t0, c0, **shot)
        self.away += max(0.0, t1 - t0)
        kind = self.pick_transition(enter, t0) if t0 > .3 else "cut"
        self.transition(t0, kind, **self.extras(kind, asset))
        self.block(t1, c1, "presenter", soft=True, frame=self.next_frame())
        if exit_transition:
            back = self.pick_transition("leave_screen", t1)
            self.transition(t1, back, **self.extras(back, asset))
        self.used_assets[asset["id"]] = self.used_assets.get(asset["id"], 0) + 1

    def demo(self, beat, asset):
        """Show the capture while the steps are named, then return to Brandon with the rest
        as callouts (screens alternate with his performance; soft footage stays short)."""
        w = self.w
        steps = [c for c in beat["clauses"] if any(i in beat["actions"] for i in c)] or beat["clauses"]
        t0, c0 = self.at(steps[0][0], -.08)
        for a, z in self.away_spans():
            if a - .05 <= t0 < z:  # a reveal still holds the frame: the capture waits for it
                t0, c0 = z + .05, round(z + .05, 3)
        limit = 3.4 if asset.get("quality") == "sharp" else 2.6
        limit = min(limit, self.room(), self.spec["layout"]["away_max_seconds"] - .1 - (t0 - self.run_start(t0)))
        end_beat = beat["end"] + .1
        t1 = min(end_beat, t0 + limit)
        # End the screen on a clause boundary when one is near.
        bounds = [w[c[-1]]["end"] + .12 for c in steps if t0 + 1.6 < w[c[-1]]["end"] + .12 <= t1]
        if bounds and t1 < end_beat - .3:
            t1 = bounds[-1]
        if t1 - t0 < self.spec["motion"]["hold"]["screen_min"] + self.margin:
            self.demo_graphic(beat)
            return
        turn = "turn" in beat["tags"] and beat["start"] > .6
        if turn and t0 - beat["start"] > .8:
            # The turn words stay on Brandon in big type; the capture arrives with the first step.
            b0, bc = self.at(beat["idx"][0], -.04)
            self.block(b0, bc, "presenter", frame="close")
            kind = self.pick_transition("section", b0)
            self.transition(b0, kind, priority=True, **self.extras(kind))
            lead = [i for i in beat["idx"] if w[i]["start"] < t0 - .05]
            tokens = display_words([w[i]["word"] for i in lead])
            while tokens and key(tokens[0]) in {"and", "but", "so", "then", "to", "the"}:
                tokens = tokens[1:]
            last_word = max((w[i]["start"] for i in lead), default=b0)
            if 1 <= len(tokens) <= 4 and t0 - .06 - max(b0 + .1, last_word - .5) >= self.spec["motion"]["hold"]["hero_min"] * .8:
                variant = self.hero_variant(["outline", "split", "stack"])
                self.graphics.append({"id": f"turn-{beat['n']}", "type": "hero", "variant": variant,
                                      "lines": lines_for(tokens, variant), "accent_words": [tokens[-1].upper()],
                                      "start": bc, "end": round(t0 - .06, 3), "zone": "chest", "beat": "turn"})
            turn = False
        self.screen(asset, beat, t0, c0, t1, round(t1, 3), clause_list=steps, enter="section" if turn else "enter_screen")
        rest = [c for c in steps if w[c[0]]["start"] >= t1 - .05]
        if rest and beat["end"] - t1 >= 1.6:
            # Brandon names the middle steps; the capture comes back for the last one when it shows it.
            last = rest[-1]
            m = best_moment(w, last, asset)
            back_t = self.cue.t(last[0], -.08)
            back_len = beat["end"] + .1 - back_t
            later_demos = any("demo" in b["tags"] and b["start"] > beat["end"] and self.match(b) for b in self.beats)
            room = self.room() - back_len - (2.2 if later_demos else 0)
            if (len(rest) >= 2 and m is not None and m.get("rect") and len(set(m["vocab"]) & {stem(key(w[i]["word"])) for i in last})
                    and back_len >= self.spec["motion"]["hold"]["screen_min"] + self.margin and back_t - t1 >= 2.2 and room >= 0):
                self.callouts(beat, rest[:-1], t1, side=self.blocks[-1].get("frame"), until=back_t - .06)
                self.screen(asset, beat, back_t, self.cue(last[0], -.08), beat["end"] + .1, round(beat["end"] + .1, 3),
                            clause_list=[last])
            else:
                self.callouts(beat, rest, t1, side=self.blocks[-1].get("frame"))

    def callouts(self, beat, steps, t_from, side=None, until=None):
        w = self.w
        frame = side if side in {"space_left", "space_right"} else self.rng.choice(["space_left", "space_right"])
        if self.blocks and self.blocks[-1]["layout"] == "presenter":
            self.blocks[-1]["frame"] = frame
        first_i = next((i for i in steps[0] if i in beat["actions"]), steps[0][0])
        first_t = self.cue.t(first_i, -.04)
        if first_t >= t_from + .05:
            start_t, start_c = first_t, self.cue(first_i, -.04)
        else:  # the first step was spoken under the screen: the stack lands on the next spoken word
            nxt = next((i for c in steps for i in c if self.cue.t(i, -.04) >= t_from + .05), None)
            start_t, start_c = (self.cue.t(nxt, -.04), self.cue(nxt, -.04)) if nxt is not None else (t_from + .1, round(t_from + .1, 3))
        items = []
        for c in steps[:3]:
            label = clause_label(w, c)
            if not label:
                continue
            anchor = next((i for i in c if i in beat["actions"]), c[0])
            at_t = self.cue.t(anchor, -.04)
            item = {"text": label, "at": self.cue(anchor, -.04) if at_t >= start_t - 1e-3 else round(start_t + .05 + .25 * len(items), 3)}
            icon = icon_for(w, c, self.banned_icons)
            if icon:
                item["icon"] = icon
            items.append(item)
        if not items:
            return
        end_t = max(beat["end"] + .35, first_t + self.spec["motion"]["hold"]["info_min"] + .4 * (len(items) - 1))
        next_beat = min((b["start"] for b in self.beats if b["start"] > beat["start"] + .01), default=self.duration)
        end_t = min(end_t, self.duration, until if until is not None else self.duration, next_beat - .06)
        left = frame == "space_left"
        g = {"id": f"steps-{beat['n']}", "type": "tag", "items": items, "x": 7 if left else 93, "y": 40, "size": 50,
             "align": "left" if left else "right", "start": start_c, "end": round(end_t, 3), "beat": beat["role"]}
        if end_t - start_t > 3.5 and len(items) >= 2 and isinstance(items[-1]["at"], str):
            # A long stack of callouts gets one push on the last step so the frame keeps moving.
            self.accent(items[-1]["at"], 1.2, x=3 if left else -3)
            if self.camera[-1]["kind"] == "punch":
                self.last_transition = "punch"  # the next section change should not punch again
        if items and self.rng.random() < .5:
            g["items"][-1]["tone"] = "win"
        self.graphics.append(g)

    def demo_graphic(self, beat):
        """No footage for these steps: an authored callout stack over Brandon."""
        steps = [c for c in beat["clauses"] if any(i in beat["actions"] for i in c)]
        t0, c0 = self.at(beat["idx"][0], -.05)
        if "turn" in beat["tags"] and beat["start"] > .6:
            kind = self.pick_transition("section", beat["start"] - .02)
            self.transition(beat["start"] - .02, kind, **self.extras(kind))
        if len(steps) >= 2:
            self.block(t0, c0, "presenter", frame=self.rng.choice(["space_left", "space_right"]))
            self.callouts(beat, steps, t0, side=self.blocks[-1]["frame"])
        else:
            self.claim(beat)

    def turn(self, beat):
        """An emotional turn: a punch in, big type on the turn phrase, a section transition."""
        t0, c0 = self.at(beat["idx"][0], -.04)
        close_used = any(b.get("frame") == "close" for b in self.blocks)
        self.block(t0, c0, "presenter", frame="close" if not close_used or self.rng.random() < .6 else "tight")
        if t0 > .6:
            kind = self.pick_transition("section", t0)
            self.transition(t0, kind, priority=True, **self.extras(kind))
        target = beat["stress"][-1] if beat["stress"] else beat["idx"][len(beat["idx"]) // 2]
        end_t, end_cue = self.at(beat["idx"][-1], .15, "end")
        contrast = self.contrast_span(beat)
        if contrast and self.add_hero(f"turn-{beat['n']}", beat, contrast[-1], end_t, end_cue, ["outline", "split", "slam"],
                                      span=contrast):
            return
        self.add_hero(f"turn-{beat['n']}", beat, target, end_t, end_cue, ["outline", "split", "slam"], impact=False)

    def result(self, beat):
        target = max(beat["stress"], key=lambda i: self.keyscore(beat, i)) if beat["stress"] else beat["idx"][0]
        t0, c0 = self.at(beat["idx"][0], -.04)
        self.block(t0, c0, "presenter", frame=self.next_frame())
        end_t, end_cue = self.at(beat["idx"][-1], .15, "end")
        self.add_hero(f"result-{beat['n']}", beat, target, end_t, end_cue, ["slam", "split", "stack"], impact=False)

    def claim(self, beat):
        """Brandon carries the claim; the strongest phrases land as big type on their words."""
        w = self.w
        t0, c0 = self.at(beat["idx"][0], -.04)
        self.block(t0, c0, "presenter", frame=self.next_frame())
        strong, taken = [], set()
        for i in beat["stress"]:  # one hero per phrase: two stressed words in one amount share it
            span = set(phrase_around(w, beat, i)[0])
            if beat["scores"][i] >= 2.8 and not span & taken:
                strong.append(i)
                taken |= span
        if beat["end"] - beat["start"] < 3.0:
            strong = strong[:1]
        end_t, end_cue = self.at(beat["idx"][-1], .15, "end")
        placed = []
        for n, i in enumerate(strong[:2]):
            limit = (self.cue.t(phrase_around(w, beat, strong[n + 1])[0][0]) - .08) if n + 1 < len(strong[:2]) else end_t
            e_t, e_c = self.split_end(beat, i, end_t, end_cue)
            e_t, e_c = (limit, round(limit, 3)) if limit < e_t else (e_t, e_c)
            made = self.add_hero(f"claim-{beat['n']}-{n}", beat, i, e_t, e_c,
                                 ["stack", "outline", "split"] if n == 0 else ["split", "slam", "outline"],
                                 not_before=(placed[-1][2] + .05) if placed else None)
            if made:
                placed.append(made)
                if n == 1:
                    self.accent(made[0]["start"], self.rng.choice([1.12, 1.18]))

    def payoff(self, beat, after=None, skip_block=False, target=None):
        """The payoff: the result rises in 2.5D with his words as the title."""
        w = self.w
        results = [a for a in self.assets if a.get("result")] or [a for a in self.assets if a.get("quality") == "sharp"]
        cands = [i for i in beat["idx"] if beat["scores"][i] >= 1 and (after is None or self.cue.t(i) > after + .3)]
        if target is None:
            target = max(cands, key=lambda i: self.keyscore(beat, i)) if cands else beat["idx"][len(beat["idx"]) // 2]
        if not skip_block:
            t0, c0 = self.at(beat["idx"][0], -.04)
            self.block(t0, c0, "presenter", frame=self.next_frame())
            if "turn" in beat["tags"] and t0 > .6:
                kind = self.pick_transition("section", t0)
                self.transition(t0, kind, **self.extras(kind))
        end_t, end_cue = self.at(beat["idx"][-1], .2, "end")
        if not results:
            hero = self.add_hero("payoff", beat, target, end_t, end_cue, ["slam", "split"], impact=True,
                                 not_before=(after + .05) if after else None)
            if hero:
                self.graphics.append({"id": "payoff-glints", "type": "particles", "start": hero[0]["start"], "end": hero[0]["end"],
                                      "x": 6, "y": 26, "w": 88, "h": 44})
            return
        fresh = [a for a in results if not self.used_assets.get(a["id"])] or results
        asset = max(fresh, key=lambda a: (asset_fit(w, beat["idx"], a), a.get("quality") == "sharp"))
        span, tokens = phrase_around(w, beat, target, most=4, glue=GLUE | {"on", "in", "for", "with", "to"})
        rt, rc = self.at(span[0], -.35)
        if after is not None and rt < after + .05:
            rt, rc = after + .05, round(after + .05, 3)
        self.payoff_reserve = 0.0
        if self.duration - rt < 2.2:
            # Too close to the end for the reveal to land and hold: his words carry the payoff.
            hero = self.add_hero("payoff", beat, target, end_t, end_cue, ["slam", "split"], impact=True,
                                 not_before=(after + .05) if after else None)
            if hero:
                self.graphics.append({"id": "payoff-glints", "type": "particles", "start": hero[0]["start"],
                                      "end": hero[0]["end"], "x": 6, "y": 26, "w": 88, "h": 44})
            return
        end_r = max(rt + 3.2, self.cue.t(span[-1]) + 1.6)
        end_r = min(end_r, rt + self.spec["layout"]["showpiece_away_max_seconds"] - .5, max(end_t, rt + 2.6), self.duration,
                    rt + max(2.6, self.away_budget - self.away))
        joined = self.run_start(rt)
        if joined < rt - .01:
            # Straight after a capture: the whole run away from Brandon stays within its limit.
            lay = self.spec["layout"]
            end_r = min(end_r, joined + lay["showpiece_away_max_seconds"] - .3)
            if end_r - rt < (end_r - joined) / 2:
                end_r = max(rt + 2.2, min(end_r, joined + lay["away_max_seconds"] - .1))
        self.away += end_r - rt
        moment = best_moment(w, span, asset) or (asset["moments"][0] if asset["moments"] else {})
        g = {"id": "payoff", "type": "reveal", "media": asset["path"], "title": " ".join(t.upper() for t in tokens),
             "accent_words": [tokens[-1].upper()] if tokens else [], "start": rc, "end": round(end_r, 3), "beat": "payoff",
             "variant": self.choose(["tilt", "float", "phone"] if asset.get("aspect", 1) < .7 else ["tilt", "float"]),
             "aspect": asset.get("aspect", .5625)}
        if moment.get("at") is not None:
            g["media_start"] = max(0.0, float(moment["at"]) - .3)
        self.graphics.append(g)
        if after is None or rt - after > .3:
            kind = self.pick_transition("reveal", rt + .02)
            self.transition(rt + .02, kind, priority=True, **self.extras(kind, asset, (50, 45)))
        self.used_assets[asset["id"]] = self.used_assets.get(asset["id"], 0) + 1
        self.notes.append(f"payoff reveals {asset['id']} under \"{g['title']}\"")
        if end_r < self.duration - .3:
            self.block(end_r, round(end_r, 3), "presenter", frame=self.next_frame())

    def cta(self, beat):
        w = self.w
        t0, c0 = self.at(beat["idx"][0], -.04)
        self.block(t0, c0, "presenter", frame="center")
        if t0 > .6:
            kind = self.pick_transition("cta", t0)
            self.transition(t0, kind, **self.extras(kind))
        if any(g["type"] == "cta" for g in self.graphics):
            self.claim(beat)  # one keyword CTA per reel; a second CTA sentence stays on Brandon
            return
        low = [key(w[i]["word"]) for i in beat["idx"]]
        keyword_i = None
        for n, k in enumerate(low):
            if k not in {"word", "comment", "type", "dm", "keyword"}:
                continue
            j = n + 1
            while j < len(low) and low[j] in {"the", "word", "me"}:
                j += 1  # "comment the word ASTRA", "DM me AGENT"
            if j < len(low) and low[j] not in STOP | {"i'll", "i'm", "i've", "below", "down", "now", "it", "this"}:
                keyword_i = beat["idx"][j]
                break
        if keyword_i is None:
            self.claim(beat)
            return
        styles = [s for s in self.spec["variety"]["cta_styles"] if s != "fan" and s not in self.avoid.get("cta_styles", [])] \
            or [s for s in self.spec["variety"]["cta_styles"] if s != "fan"]
        keyword = re.sub(r"[^\w'-]", "", w[keyword_i]["word"])
        self.graphics.append({"id": "cta", "type": "cta", "style": self.choose(styles), "keyword": keyword.upper(),
                              "keyword_at": self.cue(keyword_i), "start": c0, "end": round(self.duration, 3), "beat": "cta"})

    # --- rhythm and assembly
    def rhythm(self):
        """Keep compositions changing: long presenter spans get a reframe on a stressed word."""
        limit = self.spec["layout"]["same_composition_max_seconds"] - 1.5
        stressed = sorted(i for b in self.beats for i in b["stress"])
        blocks = sorted(self.blocks, key=lambda b: b["t"])
        for a, b in zip(blocks, blocks[1:] + [{"t": self.duration}]):
            if a["layout"] != "presenter" or b["t"] - a["t"] <= limit:
                continue
            cursor = a["t"]
            for i in stressed:
                t = self.cue.t(i, -.03)
                if any(abs(t - s0) < 1.5 for s0, _ in self.moves()):
                    continue
                if cursor + 2.5 < t < b["t"] - 1.5:
                    self.accent(self.cue(i, -.03), self.rng.choice([1.1, 1.14]))
                    cursor = t
        self.camera.sort(key=lambda c: self.cue.resolver.resolve(c["at"]) if isinstance(c["at"], str) else c["at"])

    def settle(self):
        """Big type stays readable: it never rides from Brandon into a screen or over a callout
        stack, sits on a dark plate at the top while a screen plays, and never overlaps other
        big type (the earlier one is trimmed, or dropped when too short to read)."""
        hold = self.spec["motion"]["hold"]["hero_min"]
        blocks = sorted(self.blocks, key=lambda b: b["t"])

        def on_screen(t):
            active = [b for b in blocks if b["t"] <= t + 1e-3]
            return bool(active) and active[-1]["layout"] == "screen"

        def plate(g):
            g["scrim"], g["zone"] = "plate", "top"

        drop = set()
        tags = [(self.seconds(t["start"]), self.seconds(t["end"])) for t in self.graphics if t["type"] == "tag"]
        for g in self.graphics:
            if g["type"] != "hero":
                continue
            s0, e0 = self.seconds(g["start"]), self.seconds(g["end"])
            if any(a <= s0 + .05 < z - .1 for a, z in tags):
                drop.add(g["id"])  # a callout stack already holds that side of the frame
                continue
            start_screen = on_screen(s0)
            if start_screen:
                plate(g)
            screen_stops = [b["t"] for b in blocks if s0 + .05 < b["t"] < e0 - .02 and (b["layout"] == "screen") != start_screen]
            tag_stops = [a for a, _ in tags if s0 + .05 < a < e0 - .02]
            if not screen_stops and not tag_stops:
                continue
            cut = min(screen_stops + tag_stops) - .05
            if cut - s0 >= hold + self.margin:
                g["end"] = round(cut, 3)
            elif tag_stops and min(tag_stops) - .05 - s0 < hold + self.margin:
                drop.add(g["id"])
            else:
                plate(g)  # too short to trim at the screen: it plays on across it, legibly
                if tag_stops:
                    g["end"] = round(min(tag_stops) - .05, 3)
        big = sorted((g for g in self.graphics if g["type"] in {"hero", "reveal", "cta"} and g["id"] not in drop),
                     key=lambda g: self.seconds(g["start"]))
        for a, b in zip(big, big[1:]):
            a_end, b_start = self.seconds(a["end"]), self.seconds(b["start"])
            if a_end > b_start - .04:
                if b_start - .05 - self.seconds(a["start"]) < hold + self.margin:
                    drop.add(a["id"])
                else:
                    a["end"] = round(b_start - .05, 3)
        # Callouts hold long enough to read or are left out.
        info = self.spec["motion"]["hold"]["info_min"]
        for t in [g for g in self.graphics if g["type"] == "tag" and g["id"] not in drop]:
            s0, e0 = self.seconds(t["start"]), self.seconds(t["end"])
            if e0 - s0 >= info + self.margin:
                continue
            nxt = min([self.seconds(g["start"]) for g in self.graphics if g is not t and g["id"] not in drop
                       and g["type"] in {"hero", "reveal", "cta", "tag"} and self.seconds(g["start"]) > s0 + .05]
                      + [self.duration + .05])
            end = min(s0 + info + self.margin, nxt - .05, self.duration)
            if end - s0 >= info + self.margin - 1e-6:
                t["end"] = round(end, 3)
            elif e0 - s0 < info:
                drop.add(t["id"])  # information holds two seconds or is left out
        dropped_starts = {g["start"] for g in self.graphics if g["id"] in drop}
        self.graphics = [g for g in self.graphics if g["id"] not in drop
                         and not (g["type"] == "particles" and g["start"] in dropped_starts)]

    def secure_hook(self):
        """The first three seconds always hold an art-directed moment: an early hero becomes a
        slam with glints, or the strongest early phrase gets one (a hook card gives way)."""
        by = self.spec["hook"]["payoff_by"]
        hold = self.spec["motion"]["hold"]["hero_min"]
        showy = self.showy
        if any(self.seconds(g["start"]) <= by and (g["type"] in {"reveal", "particles", "stat", "device"}
                                                  or (g["type"] == "hero" and g.get("variant") in showy))
               for g in self.graphics):
            return
        if any(t["at"] <= by and t["kind"] in {"push_in", "shape_wipe", "match_move"} for t in self.transitions):
            return
        if any(b["t"] <= by and b["layout"] in {"screen", "full_broll"} for b in self.blocks):
            return
        early = sorted((g for g in self.graphics if g["type"] == "hero" and self.seconds(g["start"]) <= by),
                       key=lambda g: self.seconds(g["start"]))
        target = next((g for g in early if g.get("variant") != "card"), None)
        if target is None:
            beat = self.beats[0]
            card = next((g for g in early if g.get("variant") == "card"), None)
            floor = self.seconds(card["start"]) + hold + .05 if card else .3
            later = [self.seconds(g["start"]) for g in self.graphics
                     if g["type"] in {"hero", "reveal", "cta", "tag"} and g is not card and self.seconds(g["start"]) > floor]
            ceiling = min(later + [self.duration]) - .05
            cands = []
            for i in beat["idx"]:
                if key(self.w[i]["word"]) in STOP | GLUE:
                    continue
                span, tokens = phrase_around(self.w, beat, i)
                content = [t for t in tokens if key(t) not in STOP | GLUE]
                if self.cue.t(span[0], -.03) < floor or len(content) < 2:
                    span, tokens = [i], display_words([self.w[i]["word"]])  # the word alone
                t0 = self.cue.t(span[0], -.03)
                if tokens and floor <= t0 <= by - .1 and ceiling - t0 >= hold:
                    cands.append((self.keyscore(beat, i) + (.5 if len(span) > 1 else 0), i, span, tokens, t0))
            if not cands:
                self.notes.append("hook has no art-directed moment in the first 3 s: add one by hand")
                return
            _, i, span, tokens, t0 = max(cands, key=lambda c: c[0])
            end_t = min(ceiling, max(t0 + 1.4, self.seconds(card["end"]) if card else 0), t0 + 2.4)
            if card:
                card["end"] = round(t0 - .05, 3)
            target = {"id": "hook-slam", "type": "hero", "variant": "slam", "lines": lines_for(tokens, "slam"),
                      "accent_words": [re.sub(r"[.,!?;:]+$", "", self.w[i]["word"]).upper()],
                      "start": self.cue(span[0], -.03), "end": round(end_t, 3), "zone": "chest", "beat": "hook"}
            self.graphics.append(target)
        elif target.get("variant") not in showy:
            tokens = " ".join(target["lines"]).split()
            target["variant"] = "slam"
            target["lines"] = lines_for(tokens, "slam")
        if not any(g["id"] == "hook-glints" for g in self.graphics):
            end = min(self.seconds(target["end"]), self.seconds(target["start"]) + 1.8)
            self.graphics.append({"id": "hook-glints", "type": "particles", "start": target["start"], "end": round(end, 3),
                                  "x": 8, "y": 24, "w": 84, "h": 44})
        self.notes.append(f"hook: {target['id']} set as a slam so the first 3 s carry an art-directed moment")

    def secure_ending(self):
        """The closing third builds to a designed moment: without a reveal or showpiece there,
        its last big phrase becomes a split or slam with glints, or the CTA keyword lands with
        glints."""
        if self.duration < 20:
            return
        edge = self.duration * .65
        if any(self.seconds(g["end"]) > edge and (g["type"] in {"reveal", "particles"}
                                                  or (g["type"] == "hero" and g.get("variant") in self.showy))
               for g in self.graphics):
            return
        if any(t["at"] >= edge and t["kind"] in {"push_in", "shape_wipe", "match_move"} for t in self.transitions):
            return
        hero_min = self.spec["type"]["hero_px"]["min"]
        heroes = [g for g in self.graphics if g["type"] == "hero" and g.get("variant") != "card" and self.seconds(g["end"]) > edge]
        if heroes:
            g = max(heroes, key=lambda g: self.seconds(g["start"]))
            tokens = " ".join(g["lines"]).split()
            options = (["split"] if len(tokens) >= 2 else []) + ["slam"]
            g["variant"] = max(options, key=lambda v: (self.fitted(lines_for(tokens, v), v) >= hero_min, -options.index(v)))
            g["lines"] = lines_for(tokens, g["variant"])
            end = min(self.seconds(g["end"]), self.seconds(g["start"]) + 1.8)
            self.graphics.append({"id": "closing-glints", "type": "particles", "start": g["start"], "end": round(end, 3),
                                  "x": 8, "y": 26, "w": 84, "h": 44})
            self.notes.append(f"closing: {g['id']} set as a {g['variant']} so the ending builds to a designed moment")
            return
        cta = next((g for g in self.graphics if g["type"] == "cta"), None)
        if cta is not None:
            at = self.seconds(cta["keyword_at"])
            end = min(self.duration, at + 1.6)
            if end - at >= .8:
                self.graphics.append({"id": "cta-glints", "type": "particles", "start": cta["keyword_at"],
                                      "end": round(end, 3), "x": 10, "y": 50, "w": 80, "h": 30})
                return
        self.notes.append("the closing third has no designed moment: add one by hand")

    def seconds(self, value):
        return float(value) if isinstance(value, (int, float)) else self.cue.resolver.resolve(value)

    def fit_zones(self):
        """In a close framing his chin sits where chest type goes, so big type that plays over
        any close framing moves lower."""
        blocks = sorted(self.blocks, key=lambda b: b["t"])
        for g in self.graphics:
            if g["type"] != "hero" or g.get("zone", "chest") != "chest":
                continue
            s0, e0 = self.seconds(g["start"]), self.seconds(g["end"])
            spans = [(b, (blocks[n + 1]["t"] if n + 1 < len(blocks) else self.duration)) for n, b in enumerate(blocks)]
            if any(b.get("layout") == "presenter" and b.get("frame") == "close" and b["t"] < e0 - .05 and end > s0 + 1e-3
                   for b, end in spans):
                g["zone"] = "low"

    def clamp(self):
        """Nothing outlives the reel (a fallback phrase can reach past a tightly trimmed end)."""
        for g in self.graphics:
            if self.seconds(g["end"]) > self.duration:
                g["end"] = round(self.duration, 3)
        self.graphics = [g for g in self.graphics if self.seconds(g["start"]) < self.seconds(g["end"]) - .05]

    def timeline_parts(self):
        self.clamp()
        self.settle()
        self.secure_hook()
        self.secure_ending()
        self.fit_zones()
        blocks = sorted(self.blocks, key=lambda b: b["t"])
        kept = [b for n, b in enumerate(blocks)
                if ((blocks[n + 1]["t"] if n + 1 < len(blocks) else self.duration) - b["t"] >= .2) or n == 0]
        shots = []
        for a, b in zip(kept, kept[1:] + [None]):
            shot = {k: v for k, v in a.items() if k not in {"t", "cue", "asset", "soft"}}
            if shot.get("layout") != "presenter":
                shot.pop("frame", None)
            shot["start"] = a["cue"] if a["t"] > 0 else 0
            shot["end"] = b["cue"] if b else round(self.duration, 3)
            if shot.get("layout") == "presenter":
                shot.setdefault("frame", "center")
            shots.append(shot)
        # merge consecutive identical presenter shots
        merged = []
        for s in shots:
            if merged and s.get("layout") == merged[-1].get("layout") == "presenter" and s.get("frame") == merged[-1].get("frame"):
                merged[-1]["end"] = s["end"]
            else:
                merged.append(s)
        return merged


def plan_reel(draft_path, assets_path=None, seed=None, tighten_gaps=True):
    draft_path = Path(draft_path).resolve()
    draft = json.loads(draft_path.read_text())
    base = draft_path.parent
    spec = style.load(draft.get("style"))
    source = Path(draft["source"]["path"]).expanduser()
    source = source if source.is_absolute() else (base / source).resolve()
    words_path = Path(draft["words_path"]).expanduser()
    words_path = words_path if words_path.is_absolute() else (base / words_path).resolve()
    raw_words = read_words(words_path)
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(source)],
                                      capture_output=True, text=True, check=True).stdout)
    segments = draft["source"].get("segments") or [{"start": 0, "end": float(probe["format"]["duration"])}]
    if tighten_gaps:
        segments = tighten(raw_words, segments)
    words = map_words(raw_words, segments)
    duration = sum(float(s["end"]) - float(s["start"]) for s in segments)
    fps = int(draft.get("output", {}).get("fps", 30))
    assets, assets_file = load_assets(assets_path)
    pros = prosody(source, segments, words)
    beats = analyze(words, pros, assets, duration)
    if seed is None:
        seed = int(hashlib.sha256((draft.get("title", "") + " ".join(w["word"] for w in words)).encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    avoid = draft.get("variation", {}).get("avoid", {})
    cues = Cues(words, duration, fps)
    planner = Planner(words, beats, assets, duration, fps, spec, rng, avoid, cues)
    shots = planner.plan()
    emphasis = []
    for b in beats:
        for i in sorted(b["stress"], key=lambda i: -b["scores"][i])[:2]:
            k = re.sub(r"[^\w'$%-]", "", words[i]["word"])
            if emphasis_key(k) and emphasis_key(k) not in {emphasis_key(e) for e in emphasis}:
                emphasis.append(k)
    timeline = {k: v for k, v in draft.items() if k not in {"shots", "graphics", "transitions", "camera"}}
    # Absolute paths here; main() rewrites them relative to wherever the timeline is written.
    timeline["source"] = dict(draft["source"], path=str(source), segments=segments)
    timeline["words_path"] = str(words_path)
    timeline.setdefault("output", {"width": 1080, "height": 1920, "fps": fps})
    timeline["audio_policy"] = {"music_required": False}
    captions = dict(draft.get("spoken_captions", {}))
    captions.setdefault("emphasis", emphasis)
    timeline["spoken_captions"] = captions
    timeline["shots"] = shots
    timeline["camera"] = planner.camera
    timeline["transitions"] = sorted(planner.transitions, key=lambda t: t["at"])
    timeline["graphics"] = sorted(planner.graphics, key=lambda g: cues.resolver.resolve(g["start"]) if isinstance(g["start"], str) else g["start"])
    timeline["planner"] = {"version": spec["version"], "seed": seed, "hook": getattr(planner, "hook_kind", None),
                           "assets": str(assets_file) if assets_file else None}
    plan = {"title": draft.get("title"), "duration": round(duration, 3), "seed": seed, "segments": segments,
            "hook_kind": getattr(planner, "hook_kind", None), "notes": planner.notes,
            "beats": [{"n": b["n"], "start": round(b["start"], 2), "end": round(b["end"], 2), "role": b["role"],
                       "tags": sorted(b["tags"]), "text": b["text"],
                       "stressed": [{"word": words[i]["word"], "at": round(words[i]["start"], 2), "score": round(b["scores"][i], 2)}
                                    for i in b["stress"]],
                       "footage": (planner.match(b) or {}).get("id") if "demo" in b["tags"] else None}
                      for b in beats]}
    return timeline, plan


def summary(plan):
    lines = [f"{plan['title']}: {plan['duration']:.1f}s, hook {plan['hook_kind']}, seed {plan['seed']}"]
    for b in plan["beats"]:
        stressed = ", ".join(s["word"] for s in b["stressed"])
        lines.append(f"{b['start']:6.2f}-{b['end']:6.2f}  {b['role']:<7} [{stressed}] {b['text'][:70]}"
                     + (f"  -> {b['footage']}" if b.get("footage") else ""))
    lines += [f"note: {n}" for n in plan["notes"]]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--draft", required=True, help="timeline header: title, source, words_path, variation")
    ap.add_argument("--assets", help="footage inventory (assets.json)")
    ap.add_argument("--out", help="write the planned timeline here (default: <draft dir>/timeline.planned.json)")
    ap.add_argument("--plan", help="write the beat map here (default: next to the timeline)")
    ap.add_argument("--seed", type=int, help="variation seed (default: derived from the words)")
    ap.add_argument("--no-tighten", action="store_true", help="keep pauses longer than half a second")
    a = ap.parse_args()
    timeline, plan = plan_reel(a.draft, a.assets, a.seed, not a.no_tighten)
    out = (Path(a.out) if a.out else Path(a.draft).resolve().parent / "timeline.planned.json").resolve()
    # The builder resolves paths against the timeline's folder, so they follow the output.
    timeline["source"]["path"] = os.path.relpath(timeline["source"]["path"], out.parent)
    timeline["words_path"] = os.path.relpath(timeline["words_path"], out.parent)
    out.write_text(json.dumps(timeline, indent=2) + "\n")
    plan_path = Path(a.plan) if a.plan else out.with_name(out.stem + ".plan.json")
    plan_path.write_text(json.dumps(plan, indent=2) + "\n")
    print(summary(plan))
    print(json.dumps({"timeline": str(out), "plan": str(plan_path)}))


if __name__ == "__main__":
    main()
