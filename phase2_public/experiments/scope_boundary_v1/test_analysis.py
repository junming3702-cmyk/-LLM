import unittest
from analyse_factorial import metrics, paired, distribution

class MetricTests(unittest.TestCase):
    def row(self,uid,ref,v,status='completed',arm='baseline'):
        return dict(unit_id=uid,reference=ref,verdict=v,status=status,arm=arm,stage='gated')

    def test_failures_not_dropped_or_abstentions(self):
        data=[self.row('a','N','N'),self.row('b','R',None,'execution_failed'),self.row('c','U','U')]
        m=metrics(data)
        self.assertEqual(m['planned_n'],3)
        self.assertEqual(m['agreement_all_planned'],2/3)
        self.assertEqual(m['risk_recall'],0)
        self.assertIsNone(m['risk_precision'])
        self.assertEqual(m['confusion_including_failures']['R->FAIL'],1)

    def test_unsupported_upgrade_and_overalert_separate(self):
        m=metrics([self.row('a','N','R'),self.row('b','U','N'),self.row('c','R','N')])
        self.assertEqual((m['false_R_from_N'],m['unsupported_upgrade_from_U'],m['false_N_from_R']),(1,1,1))

    def test_paired_uses_same_denominators(self):
        rows=[self.row('a','N','R'),self.row('a','N','N',arm='geo_only'),
            self.row('b','U','U'),self.row('b','U',None,'invalid_output','geo_only')]
        m=paired(rows,'baseline','geo_only','gated')
        self.assertEqual(m['agreement_delta'],0)
        self.assertEqual(m['counts'],{'improved':1,'worsened':1})

    def test_empty_and_percentile(self):
        self.assertIsNone(metrics([])['agreement_all_planned'])
        self.assertEqual(distribution(list(range(1,11)))['p90_nearest_rank'],9)

if __name__=='__main__': unittest.main()
