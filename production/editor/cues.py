"""Resolve word-anchored timing cues against the mapped (output-clock) transcript.

Any time field in the new motion system accepts either seconds or a cue:

    3.2                         absolute output seconds
    "@casino"                   start of the first spoken "casino"
    "@casino#2"                 start of the second occurrence
    "@first client"             start of the first consecutive "first client"
    "@casino:end"               end of that word (or phrase)
    "@casino+0.12" / "@casino-0.1"   offset in seconds (applied after the edge)
    "@w14"                      start of mapped word index 14
    {"word": "casino", "n": 2, "edge": "end", "offset": 0.1}
    {"word_index": 14, "edge": "start"}

Cues are resolved after source cuts are applied, so a retimed take only needs a
rebuilt word map: the cue strings stay the same and land on the same words.
"""
import math
import re

_CUE = re.compile(r"^@(?P<body>.+?)(?:#(?P<n>\d+))?(?::(?P<edge>start|end|mid))?(?P<offset>[+-]\d+(?:\.\d+)?)?$")
_TOKEN = re.compile(r"[^\W_]+(?:['’][^\W_]+)?", re.UNICODE)


def normalize(text):
    """Lowercase tokens without punctuation; keeps apostrophe contractions."""
    return [t.replace("’", "'") for t in _TOKEN.findall(str(text).casefold())]


class CueError(ValueError):
    pass


class CueResolver:
    def __init__(self, words, duration, fps=30):
        self.words = words
        self.duration = float(duration)
        self.fps = int(fps)
        # One normalized token list per word keeps phrase matching exact.
        self.tokens = []
        for index, word in enumerate(words):
            for token in normalize(word.get("word", "")):
                self.tokens.append((token, index))
        self.used = []

    def occurrences(self, phrase):
        wanted = normalize(phrase)
        tokens = [t for t, _ in self.tokens]
        hits = []
        for i in range(len(tokens) - len(wanted) + 1):
            if wanted and tokens[i:i + len(wanted)] == wanted:
                hits.append(float(self.words[self.tokens[i][1]]["start"]))
        return hits

    def _phrase(self, phrase, occurrence, after=None, strict=False):
        wanted = normalize(phrase)
        if not wanted:
            raise CueError(f"cue {phrase!r} has no words")
        if strict:
            hits = self.occurrences(phrase)
            if len(hits) > 1:
                listed = ", ".join(f"#{n + 1} at {t:.2f}s" for n, t in enumerate(hits))
                raise CueError(f"cue @{phrase} is ambiguous: it is spoken {len(hits)} times ({listed}); "
                               f"write @{phrase}#N or use a longer phrase")
        found = 0
        tokens = [t for t, _ in self.tokens]
        for i in range(len(tokens) - len(wanted) + 1):
            if tokens[i:i + len(wanted)] == wanted:
                first, last = self.tokens[i][1], self.tokens[i + len(wanted) - 1][1]
                if after is not None and float(self.words[first]["start"]) < after - .3:
                    continue
                found += 1
                if found == occurrence:
                    return first, last
        spoken = " ".join(tokens[:60])
        raise CueError(f"cue word {phrase!r} occurrence {occurrence} is not in the mapped transcript "
                       f"(found {found}); check spelling against the words file. First words: {spoken}")

    def resolve(self, value, label="cue", after=None, strict=False):
        """Return output seconds for a number or cue; raises CueError with context.

        ``after`` (seconds) makes an un-numbered word cue pick its first occurrence
        at or after that time; graphics use it so an item's "@first" means the next
        spoken "first", not the first one in the reel. "#n" always counts from the
        start of the reel.
        """
        if value is None:
            raise CueError(f"{label} is missing")
        if isinstance(value, bool):
            raise CueError(f"{label} must be seconds or a word cue")
        if isinstance(value, (int, float)):
            number = float(value)
            if not math.isfinite(number):
                raise CueError(f"{label} must be finite")
            return number
        edge, offset = "start", 0.0
        if isinstance(value, dict):
            edge = value.get("edge", "start")
            offset = float(value.get("offset", 0))
            if "word_index" in value:
                first = last = int(value["word_index"])
            elif "word" in value:
                first, last = self._phrase(value["word"], int(value.get("n", 1)), None if "n" in value else after,
                                           strict and "n" not in value and after is None)
            elif "at" in value:
                return self.resolve(value["at"], label, after, strict) + offset
            else:
                raise CueError(f"{label} object needs word, word_index or at")
        elif isinstance(value, str):
            text = value.strip()
            if not text.startswith("@"):
                try:
                    return self.resolve(float(text), label)
                except ValueError:
                    raise CueError(f"{label} {value!r} must be seconds or start with @") from None
            match = _CUE.match(text)
            if not match:
                raise CueError(f"{label} {value!r} is not a valid cue")
            body = match["body"].strip()
            edge = match["edge"] or "start"
            offset = float(match["offset"] or 0)
            # "@GPT-5" or "@24-7": a trailing number that belongs to a spoken word is not an offset.
            if match["offset"] and not match["n"] and not match["edge"] and self.occurrences(body + match["offset"]):
                body, offset = body + match["offset"], 0.0
            index_match = re.fullmatch(r"w(\d+)", body)
            if index_match:
                first = last = int(index_match[1])
            else:
                first, last = self._phrase(body, int(match["n"] or 1), None if match["n"] else after,
                                           strict and not match["n"] and after is None)
        else:
            raise CueError(f"{label} has unsupported type {type(value).__name__}")
        if not self.words:
            raise CueError(f"{label} uses a word cue but the timeline has no words_path")
        if not 0 <= first <= last < len(self.words):
            raise CueError(f"{label} word index is outside the mapped transcript")
        if edge not in {"start", "end", "mid"}:
            raise CueError(f"{label} edge must be start, end or mid")
        a, b = float(self.words[first]["start"]), float(self.words[last]["end"])
        seconds = a if edge == "start" else b if edge == "end" else (a + b) / 2
        result = seconds + offset
        self.used.append({"label": label, "cue": value if not isinstance(value, dict) else dict(value),
                          "seconds": round(result, 4), "word_start": first, "word_end": last})
        return result

    def frame(self, seconds):
        """Snap to the encoded frame grid so visual onsets land on real frames."""
        return round(float(seconds) * self.fps) / self.fps


def is_cue(value):
    return isinstance(value, str) and value.strip().startswith("@") or isinstance(value, dict)
