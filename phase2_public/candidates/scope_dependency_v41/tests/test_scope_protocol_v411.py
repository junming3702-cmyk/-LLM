"""Synthetic mode-binding regression; no project output repairs or provider calls."""
from copy import deepcopy
from unittest.mock import patch
import unittest

from test_scope_dependency_v41 import fixture, run, finding, add_gap
from scope_dependency_v41 import build_contract
from scope_dependency_v41_schema import SCHEMA, expected_review_target, normalize_response, render_task_mapping
from scope_dependency_v41_spec import validate_spec
from scope_dependency_v41_prompt import build_addendum

EXPECTED = {
    'clause_design': 'textual_pre_review',
    'text_response_comparison': 'document_response',
    'actual_submission_check': 'document_completeness',
    'actual_conduct_check': 'actual_conduct',
}


def mode_fixture(mode):
    if mode != 'actual_conduct_check':
        return fixture(mode)
    rt, f, spec = fixture('actual_submission_check')
    question = '项目经理是否实际到岗履约？'
    rt['project_context'].update(review_question=question, document_stage='actual_conduct')
    spec.update(review_mode=mode, question_verbatim=question)
    rt['review_task_contract_v41'] = build_contract(rt, spec)
    f['decision_basis'].update(review_question=question, review_target=EXPECTED[mode],
                              task_scope_sha256=rt['review_task_contract_v41']['input_scope_sha256'])
    return rt, f, spec


class ModeBindingSingleSourceTests(unittest.TestCase):
    def test_exact_four_modes_and_derived_enum(self):
        self.assertEqual({k: v['review_target'] for k, v in SCHEMA['task_modes'].items()}, EXPECTED)
        self.assertEqual(SCHEMA['basis']['review_target']['enum'], list(EXPECTED.values()))

    def test_generated_prompt_contains_every_mode_target_pair(self):
        rendered = render_task_mapping()
        self.assertIn(rendered, build_addendum())
        for mode, target in EXPECTED.items():
            self.assertIn('| '+mode+' | '+target+' |', rendered)
        self.assertIn('review_task_contract_v41.expected_review_target', build_addendum())

    def test_all_mode_contracts_lock_target_before_inference(self):
        for mode, target in EXPECTED.items():
            with self.subTest(mode=mode):
                rt, _, spec = mode_fixture(mode)
                self.assertEqual(validate_spec(rt, spec), [])
                self.assertEqual(rt['review_task_contract_v41']['expected_review_target'], target)

    def test_all_correct_pairs_pass_target_binding(self):
        for mode in EXPECTED:
            with self.subTest(mode=mode):
                rt, f, spec = mode_fixture(mode)
                result = run(rt, f, spec)
                audit = finding(result)['nu_boundary_audit']
                self.assertTrue(result['protocol_diagnostics']['raw']['valid'])
                self.assertTrue(audit['contract_bound'])
                self.assertNotIn('response_target_not_locked_mode', audit.get('schema_errors', []))

    def test_all_twelve_wrong_pairs_are_blocked(self):
        for mode, expected in EXPECTED.items():
            for wrong in set(EXPECTED.values()) - {expected}:
                with self.subTest(mode=mode, wrong=wrong):
                    rt, f, spec = mode_fixture(mode)
                    f['decision_basis']['review_target'] = wrong
                    before = deepcopy(f)
                    result = run(rt, f, spec)
                    audit = finding(result)['nu_boundary_audit']
                    self.assertTrue(result['protocol_diagnostics']['raw']['valid'])
                    self.assertTrue(result['blocked'])
                    self.assertEqual(result['valid_legal_verdicts'], [])
                    self.assertIn('response_target_not_locked_mode', audit['schema_errors'])
                    self.assertEqual(audit['expected_review_target'], expected)
                    self.assertEqual(audit['observed_review_target'], wrong)
                    self.assertEqual(result['raw_response']['findings'][0], before)
                    self.assertEqual(f, before)

    def test_normalizer_does_not_substitute_another_valid_target(self):
        rt, f, spec = fixture()
        f['decision_basis']['review_target'] = 'textual_pre_review'
        normalized, audit = normalize_response({'findings': [f]}, True)
        self.assertEqual(normalized['findings'][0]['decision_basis']['review_target'], 'textual_pre_review')
        self.assertEqual(audit['actions'], [])
        result = run(rt, f, spec, normalize_protocol_v41=True)
        self.assertTrue(result['blocked'])
        self.assertEqual(result['valid_legal_verdicts'], [])

    def test_missing_expected_target_in_runtime_is_stale_not_backfilled(self):
        rt, f, spec = fixture()
        rt['review_task_contract_v41'].pop('expected_review_target')
        before = deepcopy(rt)
        result = run(rt, f, spec)
        self.assertTrue(result['blocked'])
        self.assertIn('missing_stale_or_untrusted_v41_contract', finding(result)['nu_boundary_audit']['schema_errors'])
        self.assertEqual(rt, before)

    def test_tampered_expected_target_does_not_authorize_response(self):
        rt, f, spec = fixture()
        rt['review_task_contract_v41']['expected_review_target'] = 'textual_pre_review'
        f['decision_basis']['review_target'] = 'textual_pre_review'
        result = run(rt, f, spec)
        self.assertTrue(result['blocked'])
        self.assertEqual(result['valid_legal_verdicts'], [])

    def test_legacy_mapping_and_validator_cannot_control_v411(self):
        import scope_dependency_v4 as legacy
        rt, _, spec = fixture()
        with patch.dict(legacy.TARGETS, {}, clear=True), patch.object(legacy, 'validate_spec', side_effect=AssertionError('legacy validator used')):
            self.assertEqual(validate_spec(rt, spec), [])
            self.assertEqual(build_contract(rt, spec)['expected_review_target'], 'document_response')

    def test_unknown_or_malformed_mode_has_no_default(self):
        for mode in ('unknown', None, [], {}):
            rt, _, spec = fixture()
            spec['review_mode'] = mode
            self.assertIsNone(expected_review_target(mode))
            self.assertIn('invalid_scope_mode', validate_spec(rt, spec))
            with self.assertRaises(ValueError):
                build_contract(rt, spec)

    def test_stage_mismatch_is_not_corrected(self):
        for mode in EXPECTED:
            rt, _, spec = mode_fixture(mode)
            rt['project_context']['document_stage'] = 'unknown_stage'
            self.assertIn('scope_mode_stage_conflict', validate_spec(rt, spec))

    def test_factual_modes_cannot_inherit_text_exclusions(self):
        for mode in ('actual_submission_check', 'actual_conduct_check'):
            rt, _, spec = mode_fixture(mode)
            spec['excluded_dependencies'] = ['authenticity']
            self.assertIn('factual_task_cannot_use_text_exclusions', validate_spec(rt, spec))

    def test_dependency_and_question_guards_preserved(self):
        rt, _, spec = fixture()
        spec['excluded_dependencies'] = ['applicable_rule']
        self.assertIn('invalid_scope_exclusion', validate_spec(rt, spec))
        rt, _, spec = fixture()
        spec['required_claims'][0]['required_dependencies'] = ['invented']
        self.assertIn('invalid_claim_dependencies', validate_spec(rt, spec))
        rt, _, spec = fixture()
        rt['project_context']['review_question'] = spec['question_verbatim'] = '证明文件是否已提交？'
        self.assertIn('text_scope_conflicts_with_positive_or_ambiguous_factual_question', validate_spec(rt, spec))

    def test_right_target_does_not_bypass_relation_guard(self):
        rt, f, spec = fixture()
        add_gap(f, detail='最终递交包完整性与补遗未核验。')
        result = run(rt, f, spec)
        self.assertTrue(result['scope_review_required'])
        self.assertEqual(result['valid_legal_verdicts'], [])

    def test_frozen_version_contract_is_not_silently_upgraded(self):
        rt, f, spec = fixture()
        rt['review_task_contract_v41']['version'] = 'scope-dependency-v4.1-candidate'
        before = deepcopy(rt)
        self.assertTrue(run(rt, f, spec)['blocked'])
        self.assertEqual(rt, before)

    def test_handoff_version_recognition_is_explicit_and_shared(self):
        from scope_dependency_v41_schema import is_protocol_handoff, VERSION
        for version in ('scope-dependency-v4.1-candidate', VERSION):
            self.assertTrue(is_protocol_handoff({'version': version}))
        for version in ('scope-dependency-v4-candidate', 'scope-dependency-v999', None, []):
            self.assertFalse(is_protocol_handoff({'version': version}))

    def test_current_mode_mismatch_is_displayed_as_technical_not_legal_U(self):
        from export_review_excel import flatten_record
        rt, f, spec = fixture()
        f['decision_basis']['review_target'] = 'textual_pre_review'
        result = run(rt, f, spec)
        self.assertEqual(result['response']['review_table'][0]['conclusion']['conclusion_type'], 'schema_blocked')
        for include in (True, False):
            row = list(flatten_record({'gate_result': result, 'runtime_input': rt}, include_handoff=include))[0]
            self.assertIn('schema_blocked', row[3])

    def test_historical_handoff_display_remains_technical(self):
        from export_review_excel import flatten_record
        rt, f, spec = fixture()
        add_gap(f, 'other_undetermined', 'undetermined')
        result = run(rt, f, spec)
        finding(result)['review_handoff']['version'] = 'scope-dependency-v4.1-candidate'
        row = list(flatten_record({'gate_result': result, 'runtime_input': rt}))[0]
        self.assertIn('scope_review_required', row[3])


if __name__ == '__main__':
    unittest.main()
