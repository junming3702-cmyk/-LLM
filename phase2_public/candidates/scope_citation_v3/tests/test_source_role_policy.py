"""Isolated engineering fixtures, not a new legal ground truth."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from source_role_policy import normalize_source, prepare_runtime, SourceRoleGuardRetriever
from llm_abstention_gate import apply_gate
from external_fallback_v2 import is_usable_legal_basis
from test_post_llm_gate_v2 import _runtime, _finding
from conclusion_contract_v2 import (
    INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM as U,
    REQUIRES_HUMAN_LEGAL_REVIEW as R)


def supplementary():
    row = _runtime()['retrieved_legal_evidence'][0]
    row.update(source_role='supplementary_document', corpus_partition='supplement',
        independent_evidence=True, citation_ready=True)
    return row


class SourceRoleTests(unittest.TestCase):
    def test_role_dominates_contradictory_positive_flags(self):
        row = supplementary(); before = deepcopy(row); out = normalize_source(row)
        self.assertEqual(row, before)
        self.assertFalse(out['independent_legal_evidence'])
        self.assertFalse(out['independent_evidence'])
        self.assertFalse(out['citation_ready'])
        self.assertFalse(is_usable_legal_basis(out))
        self.assertEqual(out['citation_mode'], 'contextual_only')
        for key in ('chunk_id','law','article','legal_quote','source_locator','normative_level','source_role'):
            self.assertEqual(out[key], row[key])

    def test_each_declared_restriction(self):
        for fields in ({'source_role':'practice_material_only'},
                       {'corpus_partition':'warning'}, {'corpus_partition':'supplement'},
                       {'legal_evidence_eligibility':'supplement_only'}):
            row = _runtime()['retrieved_legal_evidence'][0]; row.update(fields)
            self.assertFalse(is_usable_legal_basis(normalize_source(row)))

    def test_missing_or_unknown_role_not_inferred_from_title(self):
        for role in ('primary_source','unknown','', None):
            row = _runtime()['retrieved_legal_evidence'][0]
            row.update(source_role=role, law='某强制性技术标准/某法规附件')
            self.assertEqual(normalize_source(row), row)

    def test_does_not_promote_explicit_denials(self):
        for field in ('independent_legal_evidence','independent_evidence'):
            row = _runtime()['retrieved_legal_evidence'][0]; row[field] = False
            self.assertFalse(is_usable_legal_basis(normalize_source(row)))

    def test_normalization_idempotent(self):
        row = supplementary()
        self.assertEqual(normalize_source(normalize_source(row)), normalize_source(row))
        runtime = _runtime(chunk=row)
        self.assertEqual(prepare_runtime(prepare_runtime(runtime)), prepare_runtime(runtime))

    def test_default_gate_and_inputs_unchanged(self):
        runtime = _runtime(chunk=supplementary()); raw = {'findings':[_finding()]}
        before = deepcopy((runtime,raw))
        self.assertEqual(apply_gate(raw,runtime),apply_gate(raw,runtime,source_role_guard=False))
        apply_gate(raw,runtime,source_role_guard=True)
        self.assertEqual((runtime,raw),before)

    def test_only_supplement_cannot_independently_support_risk(self):
        runtime = _runtime(chunk=supplementary()); raw = {'findings':[_finding(conclusion=R)]}
        out = apply_gate(raw,runtime,source_role_guard=True)['response']['findings'][0]
        self.assertEqual(out['conclusion_type'],U)
        self.assertEqual(len(out['legal_evidence']),1)
        self.assertFalse(out['legal_evidence'][0]['independent_legal_evidence'])

    def test_only_supplement_cannot_establish_compliance(self):
        raw = {'findings':[_finding(conclusion='no_supported_issue_found_within_review_scope',
            category='no_issue_identified', relation='explicitly_satisfied')]}
        out = apply_gate(raw,_runtime(chunk=supplementary()),source_role_guard=True)
        self.assertEqual(out['response']['findings'][0]['conclusion_type'],U)

    def test_real_independent_evidence_not_removed_with_supplement(self):
        runtime = _runtime(); supp = supplementary(); supp['chunk_id'] = 'supp-2'
        runtime['retrieved_legal_evidence'].append(supp)
        raw = {'findings':[_finding(conclusion=R, evidence_ids=['law-1','supp-2'])]}
        out = apply_gate(raw,runtime,source_role_guard=True)['response']['findings'][0]
        self.assertEqual(out['conclusion_type'],R)
        self.assertEqual([x['independent_legal_evidence'] for x in out['legal_evidence']],[True,False])

    def test_runtime_controls_not_model_relabeling(self):
        raw = {'findings':[_finding(conclusion=R)]}
        raw['findings'][0]['legal_evidence'][0].update(source_role='primary_source',
            independent_legal_evidence=True, independent_evidence=True)
        out = apply_gate(raw,_runtime(chunk=supplementary()),source_role_guard=True)
        self.assertEqual(out['response']['findings'][0]['conclusion_type'],U)

    def test_external_supplement_also_denied(self):
        row = supplementary(); row.update(external_source=True,human_confirmation_status='confirmed')
        self.assertFalse(is_usable_legal_basis(normalize_source(row)))

    def test_retriever_adapter_keeps_order_rank_and_base(self):
        original = [supplementary(), _runtime()['retrieved_legal_evidence'][0]]
        original[0]['rank'] = 1; original[1]['rank'] = 2
        before = deepcopy(original)
        class Fake:
            embedding_model_name = 'test'
            def retrieve(self, *args, **kwargs): return original
            def retrieve_many(self, *args, **kwargs): return original
        retriever = SourceRoleGuardRetriever(Fake())
        for method in (retriever.retrieve, retriever.retrieve_many):
            out = method('test',level='Level 1')
            self.assertEqual([r['rank'] for r in out],[1,2])
            self.assertFalse(out[0]['independent_legal_evidence'])
            self.assertTrue(out[1]['independent_legal_evidence'])
        self.assertEqual(original,before)
        self.assertEqual(len(retriever.audit),2)

    def test_final_request_receives_denial_before_reasoning(self):
        import run_hierarchy_gated_llm_smoke as runner
        raw = {'findings':[_finding(conclusion=R)]}; runtime = _runtime(chunk=supplementary())
        def request(_key,_prompt,supplied,**kwargs):
            self.assertFalse(supplied['retrieved_legal_evidence'][0]['independent_legal_evidence'])
            return {'parsed':deepcopy(raw),'ok':True,'finish_reason':'stop'}
        with patch.object(runner,'model_request',side_effect=request):
            _,gate = runner.run_final_reasoning(api_key='synthetic',prompt='test',
                runtime_input=runtime,max_tokens=10,source_role_guard=True)
        self.assertEqual(gate['response']['findings'][0]['conclusion_type'],U)


if __name__ == '__main__':unittest.main()
