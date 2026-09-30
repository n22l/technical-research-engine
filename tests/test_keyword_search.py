"""Ranking fixtures measure retrieval behavior, not factual correctness."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from research_search import search, keyword_scores


class KeywordTests(unittest.TestCase):
    def rank(self, texts, query):
        return search([{'passage_id':str(i), 'passage':text} for i,text in enumerate(texts)], query)

    def test_question_words_do_not_retrieve_unrelated_passages(self):
        self.assertEqual(self.rank(['What is the purpose of this page?', 'Rocket news.'], 'Has China demonstrated booster reflight?'), [])

    def test_full_entity_and_date_match_beats_repetition(self):
        rows=self.rank(['Falcon 9 reflight in 2020. '*30, 'Falcon 9 reflight in 2025 was recorded.'], 'Falcon 9 reflight 2025')
        self.assertEqual(rows[0]['passage_id'], '1')

    def test_quoted_phrase_is_required(self):
        rows=self.rank(['The heavy vehicle is called Falcon.', 'Falcon Heavy launch record.'], '"Falcon Heavy" launch')
        self.assertEqual([r['passage_id'] for r in rows], ['1'])

    def test_chinese_character_only_overlap_is_not_enough(self):
        rows=self.rank(['火星新闻报道', '火箭回收试验完成'], '火箭回收')
        self.assertEqual([r['passage_id'] for r in rows], ['1'])

    def test_title_boost_and_stable_ties(self):
        scores=keyword_scores(['A launch record.', 'A launch record.'], 'Falcon reflight', ['News', 'Falcon reflight'])
        self.assertGreater(scores[1], scores[0])
        self.assertEqual([r['passage_id'] for r in self.rank(['Falcon reflight','Falcon reflight'],'Falcon reflight')], ['0','1'])

    def test_original_passage_is_unchanged(self):
        text='Falcon-9 reflight: original punctuation.'
        self.assertEqual(self.rank([text], 'Falcon 9 reflight')[0]['passage'], text)

    def test_bilingual_subject_terms_preserve_original_evidence(self):
        text = '中国重复使用火箭飞行试验。'
        rows = self.rank([text, 'An unrelated government technical report.'],
                         'Has China flown a reusable rocket?')
        self.assertEqual([r['passage_id'] for r in rows], ['0'])
        self.assertEqual(rows[0]['passage'], text)
        self.assertEqual(self.rank([text], '"reusable rocket"'), [])


if __name__=='__main__': unittest.main()
