from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tests'))
from test_post_llm_gate_v2 import _finding, _runtime
from llm_abstention_gate import apply_gate
from replay_source_roles import replay_one


class ReplayTests(unittest.TestCase):
    def sample(self):
        runtime=_runtime()
        runtime['retrieved_legal_evidence'][0].update(source_role='supplementary_document')
        raw={'findings':[_finding()]}
        return {'issue_id':'ISSUE-001','runtime_input':runtime,
            'final_llm_response':{'parsed':raw,'ok':True,'finish_reason':'stop'},
            'post_llm_gate':apply_gate(raw,runtime)}

    def test_fixed_response_denial_not_new_generation(self):
        source=self.sample();before=deepcopy(source);row,gate=replay_one(source)
        self.assertTrue(row['default_gate_exact_reproduction'])
        self.assertEqual(row['original']['verdict'],'R')
        self.assertEqual(row['candidate']['verdict'],'U')
        self.assertEqual(row['contradictory_final_citations_after'],0)
        self.assertEqual(source,before)

    def test_default_drift_is_fatal(self):
        source=self.sample();source['post_llm_gate']['status']='changed'
        with self.assertRaisesRegex(ValueError,'default_gate_mismatch'):replay_one(source)

    def test_failed_generation_not_repaired(self):
        source=self.sample();source['final_llm_response']['ok']=False
        row,gate=replay_one(source)
        self.assertIsNone(row['default_gate_exact_reproduction'])
        self.assertFalse(row['verdict_or_status_changed'])
        self.assertEqual(row['candidate']['status'],'execution_failed')
        self.assertEqual(gate,source['post_llm_gate'])

    def test_truncation_not_repaired(self):
        source=self.sample();source['final_llm_response']['finish_reason']='length'
        row,_=replay_one(source)
        self.assertEqual(row['candidate']['status'],'invalid_output')
        self.assertFalse(row['verdict_or_status_changed'])


if __name__=='__main__':unittest.main()
