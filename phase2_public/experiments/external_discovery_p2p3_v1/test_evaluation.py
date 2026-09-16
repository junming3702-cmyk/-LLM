import copy
import unittest
from discovery import canonical_hash
from p3_evaluation import evaluate, MATCHED_CONTROLS
from run_llm_smoke import select_response

class EvaluationTests(unittest.TestCase):
    def fixture(self):
        spec={'tasks':[{'id':'ONE'},{'id':'TWO'}]}
        labels={'status':'human_confirmed_locked','task_spec_sha256':canonical_hash(spec),
                'reviewer_id':'FIXTURE_NOT_REAL_HUMAN','locked_at':'2026-09-17','reference_snapshot_sha256':'fixture',
                'cases':{'ONE':{'status':'confirmed','relevant_evidence_ids':['a','b'],'conclusion':'risk','must_abstain':False},
                         'TWO':{'status':'confirmed','relevant_evidence_ids':[],'conclusion':'insufficient','must_abstain':True}}}
        arm={'controls':dict.fromkeys(MATCHED_CONTROLS,'FIXTURE'), 'cases':[
            {'id':'ONE','ranked_evidence_ids':['x','a'],'conclusion':'risk','citation_count':1,'traceable_citation_count':1},
            {'id':'TWO','ranked_evidence_ids':[],'conclusion':'insufficient','unsupported_independent_citation':False}]}
        arms={key:copy.deepcopy(arm) for key in ('A_local','B_fixed_access','C_article_discovery')}
        return spec,labels,arms

    def test_true_recall_not_hit_rate(self):
        result=evaluate(*self.fixture())['A_local']
        self.assertEqual(result['macro_evidence_recall_at_5'], .5)
        self.assertEqual(result['mrr_over_returned_ranking'], .5)
        self.assertEqual(result['retrieval_denominator'], 1)

    def test_no_gold_no_metrics(self):
        spec,labels,arms=self.fixture(); labels['status']='pending'
        with self.assertRaisesRegex(ValueError,'human_reference_lock'): evaluate(spec,labels,arms)

    def test_stale_gold(self):
        spec,labels,arms=self.fixture();spec['changed']=True
        with self.assertRaisesRegex(ValueError,'human_reference_lock'): evaluate(spec,labels,arms)

    def test_mismatched_controls(self):
        spec,labels,arms=self.fixture(); arms['C_article_discovery']['controls']['model']='different'
        with self.assertRaisesRegex(ValueError,'unmatched_control_model'): evaluate(spec,labels,arms)

    def test_missing_arm(self):
        spec,labels,arms=self.fixture();arms.pop('B_fixed_access')
        with self.assertRaisesRegex(ValueError,'three_comparison'): evaluate(spec,labels,arms)

    def test_duplicate_rows(self):
        spec,labels,arms=self.fixture(); arms['A_local']['cases'][1]=arms['A_local']['cases'][0]
        with self.assertRaisesRegex(ValueError,'arm_case_coverage'): evaluate(spec,labels,arms)

    def test_duplicate_ranks(self):
        spec,labels,arms=self.fixture();arms['A_local']['cases'][0]['ranked_evidence_ids']=['a','a']
        with self.assertRaisesRegex(ValueError,'duplicate_ranked'): evaluate(spec,labels,arms)

    def test_reasoning_priority(self):
        out,diag=select_response({'reasoning_content':'{"conclusion":"one"}', 'content':'{"conclusion":"two"}'})
        self.assertEqual(out['conclusion'],'one')
        self.assertEqual(diag['selected_channel'],'reasoning_content')

    def test_content_fallback(self):
        out,diag=select_response({'reasoning_content':'not JSON','content':'```json\n{"conclusion":"two"}\n```'})
        self.assertEqual(out['conclusion'],'two')
        self.assertEqual(diag['selected_channel'],'content')

    def test_invalid_channels(self):
        out,diag=select_response({'reasoning_content':'incomplete {','content':'bad'})
        self.assertIsNone(out)

if __name__=='__main__': unittest.main()
