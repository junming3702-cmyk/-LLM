from copy import deepcopy
import unittest
from run_fixed_packet_reasoning import select_runtime, smoke_indices


def fixture():
    return {'experimental_arm':'geo_task','issue_id':'SYN-001','runtime_input':{
        'issue_id':'SYN-001','project_id':'SYN-P1','contract_evidence':{'document_excerpt':'合成条款'},
        'scope_boundary_experiment':{'geographic_filter':True,'task_boundary':True}}}


class FixedPacketTests(unittest.TestCase):
    def test_original_immutable(self):
        source=fixture(); old=deepcopy(source)
        row=select_runtime(source); row['issue_id']='changed'
        self.assertEqual(source,old)

    def test_expert_label_rejected_recursively(self):
        source=fixture(); source['runtime_input']['project_context']={'expert_scores':[5]}
        with self.assertRaises(ValueError): select_runtime(source)

    def test_unknown_fields_rejected(self):
        source=fixture(); source['runtime_input']['final_llm_response']={}
        with self.assertRaises(ValueError): select_runtime(source)

    def test_partial_retrieval_rejected(self):
        source=fixture(); source['runtime_input']['hierarchy_retrieval_audit']={'cascade_failure_level':'Level 2'}
        with self.assertRaises(ValueError): select_runtime(source)

    def test_external_packet_rejected(self):
        source=fixture(); source['runtime_input']['external_sources_used']=['external']
        with self.assertRaises(ValueError): select_runtime(source)

    def test_first_per_project_smoke_not_outcome_selected(self):
        self.assertEqual(smoke_indices([{'project_id':x} for x in ['a','a','b','b','c']]),[0,2,4])


if __name__=='__main__': unittest.main()
