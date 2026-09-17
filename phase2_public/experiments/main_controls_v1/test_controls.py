import copy
import unittest
from controls import method_order, METHODS, semantic_observation, ordered_unique
from experiment_integrity import validate_runtime

class ControlsTests(unittest.TestCase):
    def result(self, verdict='potential_risk'):
        parsed={'findings':[{'conclusion_type':verdict}]}
        return {'final_llm_response':{'ok':True,'finish_reason':'stop','parsed':parsed},
                'post_llm_gate':{'blocked':False,'response':copy.deepcopy(parsed)}}
    def test_rotation(self):
        orders=[method_order(i) for i in range(45)]
        for position in range(3):
            for method in METHODS:
                self.assertEqual(sum(o[position]==method for o in orders),15)
    def test_gate_ablation_uses_same_raw(self):
        r=self.result(); r['post_llm_gate']['response']['findings'][0]['conclusion_type']='insufficient_information_needs_human_confirm'
        self.assertEqual(semantic_observation(r,True)['verdict'],'R')
        self.assertEqual(semantic_observation(r)['verdict'],'U')
    def test_failure_not_abstention(self):
        r=self.result(); r['final_llm_response']['ok']=False
        self.assertEqual(semantic_observation(r)['status'],'execution_failed')
        self.assertIsNone(semantic_observation(r,True)['verdict'])
    def test_length_not_success(self):
        r=self.result();r['final_llm_response']['finish_reason']='length'
        self.assertEqual(semantic_observation(r)['status'],'invalid_output')
    def test_gate_blocked_raw_retained(self):
        r=self.result();r['post_llm_gate']['blocked']=True
        self.assertEqual(semantic_observation(r)['status'],'gate_blocked')
        self.assertEqual(semantic_observation(r,True)['status'],'completed')
    def test_cascade_failure_retained(self):
        r=self.result();r['runtime_input']={'hierarchy_retrieval_audit':{'cascade_failure_level':'Level 2'}}
        self.assertEqual(semantic_observation(r,True)['status'],'execution_failed')
    def test_unknown_not_correct(self):
        self.assertEqual(semantic_observation(self.result('anything'))['status'],'invalid_output')
    def test_multiple_findings_not_silently_first(self):
        r=self.result();r['final_llm_response']['parsed']['findings']*=2
        self.assertEqual(semantic_observation(r,True)['status'],'invalid_output')
    def test_label_guard(self):
        for key in ['gold_label','expected_relation','gold_legal_basis_chunk_ids']:
            with self.assertRaises(ValueError): validate_runtime({'nested':{key:['x']}})
    def test_rank_unique(self):
        self.assertEqual(ordered_unique(['b','a','b','c']),['b','a','c'])

if __name__=='__main__': unittest.main()
