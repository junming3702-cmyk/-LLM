import copy
from types import SimpleNamespace
import unittest
from run_controlled_reasoning import mask_retriever,title_match,attach_external,eligible


class ControlledReasoningTests(unittest.TestCase):
    def setUp(self):
        self.base=SimpleNamespace(corpus=[
            {'chunk_id':'a','title':'中华人民共和国建筑法 20190423','article':'第二十六条'},
            {'chunk_id':'b','title':'中华人民共和国建筑法 20190423','article':'第二十七条'},
            {'chunk_id':'c','title':'实务解读','article':'1','corpus_partition':'supplement'}],
            level_phase_indices={('Level 1','primary'):[0,1],('Level 3','supplement'):[2]})
        self.control={'candidate_allowlist':None}
        self.catalogue=[{'source_id':'BUILD','law_title':'中华人民共和国建筑法'}]

    def test_exact_title_no_topic_generalization(self):
        self.assertTrue(title_match('中华人民共和国建筑法 20190423','中华人民共和国建筑法'))
        self.assertFalse(title_match('建筑法实务手册','中华人民共和国建筑法'))

    def test_natural_no_global_withholding(self):
        base,audit=mask_retriever(self.base,self.control,self.catalogue,'natural')
        self.assertEqual(base.level_phase_indices,self.base.level_phase_indices)
        self.assertEqual(audit,[])

    def test_controlled_gap_exact_article_and_no_original_edit(self):
        before=copy.deepcopy(self.base.level_phase_indices)
        filtered,audit=mask_retriever(self.base,self.control,self.catalogue,'controlled_gap')
        self.assertEqual(filtered.level_phase_indices[('Level 1','primary')],[1])
        self.assertEqual(audit[0]['chunk_id'],'a')
        self.assertEqual(before,self.base.level_phase_indices)

    def test_prescribed_candidate_constraint_identical_all_arms(self):
        filtered,audit=mask_retriever(self.base,{'candidate_allowlist':['BUILD:第二十七条']},self.catalogue,'natural')
        self.assertEqual(filtered.level_phase_indices[('Level 1','primary')],[1])
        self.assertEqual(filtered.level_phase_indices[('Level 3','supplement')],[])

    def test_supplement_constraint_cannot_admit_primary(self):
        filtered,_=mask_retriever(self.base,{'source_class_hint':'supplement_only'},self.catalogue,'natural')
        self.assertEqual(filtered.level_phase_indices[('Level 1','primary')],[])

    def test_actual_external_state_no_live_network_claim(self):
        runtime={'retrieved_legal_evidence':[],'runtime_constraints':{}}
        result=attach_external(runtime,[{'chunk_id':'external:x'}],{'status':'ready'})
        self.assertFalse(result['runtime_constraints']['external_http_called'])
        self.assertFalse(result['runtime_constraints']['external_search_completed'])
        self.assertEqual(runtime['retrieved_legal_evidence'],[])

    def test_failure_cannot_trigger_as_successful_abstention(self):
        result={'execution_error':'ProxyError','post_llm_gate':{'response':{'findings':[
            {'conclusion_type':'insufficient_information_needs_human_confirm'}]}}}
        self.assertFalse(eligible(result))


if __name__=='__main__':unittest.main()
