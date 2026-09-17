import unittest
from analyse_p3_controlled import ranked_metrics,summarize_rank

class P3MetricsTests(unittest.TestCase):
    def test_recall_not_hit_rate(self):
        r=ranked_metrics(['x','a'],['a','b'])
        self.assertEqual(r['recall_at_5'],.5)
        self.assertEqual(r['reciprocal_rank'],.5)
    def test_zero_relevance_excluded(self):
        self.assertIsNone(ranked_metrics([],[]))
        self.assertEqual(summarize_rank([None])['denominator'],0)
    def test_retrieval_failure_counts_zero_when_relevant(self):
        r=ranked_metrics([],['a'])
        self.assertEqual(r['recall_at_5'],0)
        self.assertEqual(r['reciprocal_rank'],0)
    def test_mrr_over_full_returned_ranking_not_only_five(self):
        r=ranked_metrics(['a','b','c','d','e','f'],['f'])
        self.assertEqual(r['recall_at_5'],0)
        self.assertEqual(r['reciprocal_rank'],1/6)
    def test_duplicate_ids_denied(self):
        with self.assertRaises(ValueError):ranked_metrics(['a','a'],['a'])

if __name__=='__main__':unittest.main()
