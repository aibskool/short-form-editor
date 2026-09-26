import unittest
from edit import map_words, caption_groups, phrase_groups, escape, validate_editorial_graphics, editorial_words, validate_scene_cues
from kinetic_scenes import kinetic_markup


class TimelineTests(unittest.TestCase):
    def test_cut_and_reordered_source_times_preserve_word_sync(self):
        words=[{"word":"first","start":1.1,"end":1.5},{"word":"middle","start":5.2,"end":5.6},{"word":"later","start":6.7,"end":7.1}]
        mapped=map_words(words,[{"start":5,"end":7},{"start":1,"end":2}])
        self.assertEqual([w["word"] for w in mapped],["middle","later","first"])
        self.assertAlmostEqual(mapped[0]["start"],.2)
        self.assertAlmostEqual(mapped[1]["end"],2)
        self.assertAlmostEqual(mapped[2]["start"],2.1)

    def test_removed_words_do_not_leak_into_captions(self):
        words=[{"word":"cut","start":0,"end":1},{"word":"keep","start":2,"end":3}]
        self.assertEqual([w["word"] for w in map_words(words,[{"start":2,"end":3}])],["keep"])

    def test_invalid_times_are_rejected(self):
        with self.assertRaises(ValueError):
            map_words([{"word":"bad","start":2,"end":1}],[{"start":0,"end":3}])

    def test_caption_group_breaks_at_pauses_and_length(self):
        words=[{"word":str(n),"start":n*.2,"end":n*.2+.15} for n in range(6)]
        words[4]["start"],words[4]["end"]=2,2.15
        words[5]["start"],words[5]["end"]=2.2,2.35
        groups=caption_groups(words,max_words=3,max_chars=27)
        self.assertEqual([len(g) for g in groups],[3,1,2])
        self.assertNotIn("<script>",escape("<script>"))

    def test_reviewed_phrases_preserve_every_spoken_word(self):
        words=[{"word":str(i),"start":i,"end":i+.8} for i in range(6)]
        groups=phrase_groups(words,[{"word_range":[0,4],"line_breaks":[2]}, {"word_range":[4,6]}])
        self.assertEqual([w["word"] for group in groups for w in group], [str(i) for i in range(6)])
        for phrases in ([{"word_range":[0,3]}], [{"word_range":[0,4]}, {"word_range":[3,6]}], [{"word_range":[0,6],"line_breaks":[6]}]):
            with self.assertRaises(ValueError):
                phrase_groups(words,phrases)

    def test_editorial_graphics_are_independent_claim_linked_and_escaped(self):
        graphic={'claim_id':'hook','text':'Real <screen> proof','accent_words':['Real'],
                 'start':0,'end':2,'x':7,'y':14,'width':86,'animation':'rise'}
        self.assertEqual(validate_editorial_graphics([graphic],3),[graphic])
        markup=editorial_words(graphic)
        self.assertIn('editorial-accent',markup)
        self.assertIn('&lt;screen&gt;',markup)
        for invalid in ({**graphic,'claim_id':''},{**graphic,'start':3},
                        {**graphic,'x':90,'width':20},{**graphic,'animation':'blink'},
                        {**graphic,'animation':'none'}):
            with self.assertRaises(ValueError):
                validate_editorial_graphics([invalid],3)

    def test_kinetic_cards_animate_each_item_and_escape_claim_text(self):
        markup, motion = kinetic_markup({'kind':'kinetic_stat','title':'Trust <now>',
            'items':[{'label':'Recent survey','value':'45%','accent':True,'count_to':45}],
            'motion_cues':[{'at':3.5}],
            'source':'BrightLocal · 2026'}, 'test-scene', 2, 5, 720, 1280)
        self.assertIn('Trust &lt;now&gt;', markup)
        self.assertIn('BrightLocal · 2026', markup)
        self.assertTrue(any('row-0' in cue and 'fromTo' in cue for cue in motion))
        self.assertTrue(any('bar-0' in cue and 'scaleX:0' in cue for cue in motion))
        self.assertTrue(any('Math.round' in cue for cue in motion))

    def test_cues_must_align_to_spoken_words_and_ui_must_keep_changing(self):
        words=[{'word':'45%','start':2.0,'end':2.4}]
        shot={'scene':{'kind':'kinetic_stat','items':[{'label':'Use','value':'45%',
            'at':2.0,'anchor_word_index':0}]}}
        validate_scene_cues([shot],words,30)
        shot['scene']['items'][0]['at']=2.1
        with self.assertRaisesRegex(ValueError,'misses spoken cue'):
            validate_scene_cues([shot],words,30)
        with self.assertRaisesRegex(ValueError,'more than 2 seconds'):
            kinetic_markup({'kind':'kinetic_stat','items':[{'label':'Use','value':'45%',
                'at':2.1}]}, 'idle-scene', 2, 5, 720, 1280)

    def test_omitted_rank_fades_on_declared_cue(self):
        _, motion=kinetic_markup({'kind':'kinetic_ranking','title':'Results',
            'items':[{'label':'Your business','value':'04','at':4.0,'fade_at':5.5}],
            'motion_cues':[{'at':4.8,'kind':'scan'}]},'rank-scene',3.5,6,720,1280)
        self.assertTrue(any('opacity:.30' in cue and '},5.5)' in cue for cue in motion))
        self.assertTrue(any('strike-0' in cue and '},5.5)' in cue for cue in motion))


if __name__=="__main__":
    unittest.main()
