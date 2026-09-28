"""Tests for transcribe_parakeet.py word assembly (no model download needed).

python3 production/intake/test_transcribe_parakeet.py -v
"""
import unittest
from types import SimpleNamespace

import numpy as np

import transcribe_parakeet as tp


class WordsFromResultTests(unittest.TestCase):
    def test_tokens_join_into_words_and_ends_trim_to_speech(self):
        rate = tp.RATE
        audio = np.zeros(rate * 2, dtype=np.float32)
        audio[int(.10 * rate):int(.45 * rate)] = .3   # "hello"
        audio[int(.60 * rate):int(1.00 * rate)] = .3  # "world."
        result = SimpleNamespace(tokens=["▁hel", "lo", "▁world", "."], timestamps=[.10, .24, .60, .96], durations=[])
        words = tp.words_from_result(result, audio, 2.0)
        self.assertEqual([w["word"] for w in words], ["hello", "world."])
        self.assertAlmostEqual(words[0]["start"], .10)
        self.assertAlmostEqual(words[0]["end"], .45, delta=.011)   # not stretched to the next word at .60
        self.assertAlmostEqual(words[1]["end"], 1.00, delta=.011)  # not stretched toward the end of the file

    def test_token_durations_cap_the_word_end(self):
        rate = tp.RATE
        audio = np.full(rate, .001, dtype=np.float32)
        audio[int(.1 * rate):int(.8 * rate)] = .3  # he talks straight through both words
        result = SimpleNamespace(tokens=["▁go", "▁now"], timestamps=[.1, .7], durations=[.16, .2])
        words = tp.words_from_result(result, audio, 1.0)
        self.assertAlmostEqual(words[0]["end"], .1 + .16 + .08, delta=.011)  # token duration + one frame, not .7
        self.assertAlmostEqual(words[1]["end"], .8, delta=.011)


if __name__ == "__main__":
    unittest.main()
