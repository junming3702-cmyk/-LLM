from copy import deepcopy
import unittest
from result_contract import finalize_metadata


class MetadataTests(unittest.TestCase):
    def sample(self):
        return {'run_status':'completed','ready_for_human_delivery':True,
            'final_llm_response':{'ok':True,'finish_reason':'stop','parsed':{}},
            'post_llm_gate':{'response':{'findings':[{'conclusion_type':'requires_human_legal_review'}]}},
            'external_recheck':{'attempted':False,'attempt_count':0,'final_reasoning_rerun':False},
            'p3_one_shot_audit':{'attempted':True,'rounds':1,'new_final_generation':True,'admitted_count':1}}
    def test_source_untouched_and_actual_audit_projected(self):
        r=self.sample();old=deepcopy(r);out=finalize_metadata(r)
        self.assertEqual(r,old)
        self.assertTrue(out['external_recheck']['attempted'])
        self.assertTrue(out['external_recheck']['final_reasoning_rerun_completed'])
        self.assertEqual(out['post_llm_gate'],r['post_llm_gate'])
    def test_invalid_final_cannot_keep_local_ready(self):
        r=self.sample();r['final_llm_response']['finish_reason']='length'
        out=finalize_metadata(r)
        self.assertFalse(out['ready_for_human_delivery'])
        self.assertEqual(out['run_status'],'invalid_output')
        self.assertFalse(out['external_recheck']['final_reasoning_rerun_completed'])
    def test_transport_failure_cannot_keep_ready(self):
        r=self.sample();r['final_llm_response']['ok']=False
        self.assertEqual(finalize_metadata(r)['run_status'],'execution_failed')
    def test_no_evidence_no_second_generation(self):
        r=self.sample();r['p3_one_shot_audit'].update(new_final_generation=False,admitted_count=0)
        out=finalize_metadata(r)
        self.assertFalse(out['external_recheck']['final_reasoning_rerun_dispatched'])
    def test_bad_round_count_denied(self):
        r=self.sample();r['p3_one_shot_audit']['rounds']=2
        with self.assertRaises(ValueError):finalize_metadata(r)


if __name__=='__main__':unittest.main()
