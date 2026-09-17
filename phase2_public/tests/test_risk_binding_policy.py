"""Synthetic, reference-free regression tests for the opt-in policy."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from risk_binding_policy import audit_risk_binding
from llm_abstention_gate import apply_gate
from conclusion_contract_v2 import (INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM as U,
    REQUIRES_HUMAN_LEGAL_REVIEW as R)
from test_post_llm_gate_v2 import _finding, _runtime


def audit(finding, state=R, **kwargs):
    return audit_risk_binding(finding, canonical_input=state,
        usable_evidence=[{'chunk_id': 'law-1'}], risk_candidate=True, **kwargs)


def bound():
    value = _finding(conclusion=R)
    value['fact_law_comparison'] = {'supporting_chunk_id': 'law-1',
        'difference_summary': '所需证明与已提供文件存在待复核差异。'}
    return value


class RiskBindingTests(unittest.TestCase):
    def test_supported_structure_is_not_semantic_validation(self):
        result = audit(bound())
        self.assertFalse(result['force_insufficient'])
        self.assertFalse(result['legal_entailment_verified'])

    def test_empty_and_wrong_pointer(self):
        for pointer in ['', 'unseen-law', 123, ['law-1']]:
            finding = bound(); finding['fact_law_comparison']['supporting_chunk_id'] = pointer
            self.assertTrue(audit(finding)['force_insufficient'])

    def test_pool_membership_is_not_citation(self):
        finding = bound(); finding['legal_evidence'] = []
        self.assertTrue(audit(finding)['force_insufficient'])

    def test_no_difference_or_nonstrings(self):
        for diff in ['', None, {}, ['claim']]:
            finding = bound(); finding['fact_law_comparison']['difference_summary'] = diff
            self.assertTrue(audit(finding)['force_insufficient'])

    def test_raw_abstention_not_promoted_by_category(self):
        self.assertTrue(audit(bound(), U)['force_insufficient'])

    def test_explicitly_out_of_scope_not_positive(self):
        finding = bound(); finding['compliance_relation'] = 'out_of_scope_reference'
        self.assertTrue(audit(finding)['force_insufficient'])

    def test_uncertain_legal_interpretation_can_remain_potential_risk(self):
        finding = bound(); finding['compliance_relation'] = 'unresolved'
        self.assertFalse(audit(finding)['force_insufficient'])

    def test_runtime_only_overrides(self):
        self.assertFalse(audit(_finding(), U, runtime_relation_supported=True)['force_insufficient'])
        self.assertFalse(audit(_finding(), U, trusted_confirmation=True)['force_insufficient'])
        finding = _finding(); finding['runtime_override'] = True
        self.assertTrue(audit(finding, U)['force_insufficient'])

    def test_gate_default_unchanged_input_immutable(self):
        response = {'findings': [_finding(conclusion=U, relation='unresolved')]}
        runtime = _runtime(); originals = deepcopy((response, runtime))
        old = apply_gate(response, runtime)
        self.assertEqual(old, apply_gate(response, runtime, risk_binding=False))
        new = apply_gate(response, runtime, risk_binding=True)
        self.assertEqual(new['response']['findings'][0]['conclusion_type'], U)
        self.assertTrue(new['response']['findings'][0]['risk_binding_audit']['force_insufficient'])
        self.assertEqual((response, runtime), originals)

    def test_national_positive_with_nondecisive_location_missing(self):
        finding = bound(); finding['legal_element_coverage']['jurisdiction_and_scope'] = 'missing'
        new = apply_gate({'findings': [finding]}, _runtime(), risk_binding=True)
        self.assertEqual(new['response']['findings'][0]['conclusion_type'], R)

    def test_model_cannot_enable_candidate_flag(self):
        finding = bound()
        response = {'findings': [finding], 'risk_binding': True}
        self.assertNotIn('risk_binding_audit', apply_gate(response, _runtime())['response']['findings'][0])


if __name__ == '__main__':
    unittest.main()
