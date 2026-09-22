"""Synthetic engineering tests only. No real contract/expert payloads."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from scope_boundary_policy import (ARMS, ScopePolicy, geographic_decision,
    prepare_runtime, task_contract, boundary_audit, make_scope_registry,
    ContextFilteredRetriever, TASK_PROMPT)
from llm_abstention_gate import apply_gate
from test_post_llm_gate_v2 import _runtime, _finding


def context(province='四川省', stage='招标文件条款预审'):
    return {'project_location': {'country': '中国', 'province': province,
        'city': '成都市' if province == '四川省' else province,
        'human_confirmation': 'confirmed'}, 'project_type': '建筑工程施工',
        'document_stage': stage, 'review_question': '预审当前条款', 'evidence_boundary': '仅文字'}


def local():
    return {'chunk_id': 'synthetic-local', 'law': '四川省示例地方规则',
        'normative_level': 'Level 4', 'scope_classification': 'local_regional',
        'geographic_scope': {'province': '四川省'},
        'project_type_scope': 'construction_activity', 'applicability_status': 'matched',
        'legal_quote': '示例规则，应核对当前材料。', 'source_locator': '示例第一条',
        'independent_legal_evidence': True, 'legal_evidence_eligibility': 'independent_candidate'}


class GeographyTests(unittest.TestCase):
    def test_exact_and_alias_positive(self):
        for province in ['四川省', '四川']:
            self.assertTrue(geographic_decision(local(), context(province))['allowed'])

    def test_wrong_province_overrides_stale_matched(self):
        self.assertFalse(geographic_decision(local(), context('天津市'))['allowed'])

    def test_missing_unconfirmed_unknown_type(self):
        for key in ['province', 'human_confirmation']:
            ctx = context(); ctx['project_location'].pop(key)
            self.assertFalse(geographic_decision(local(), ctx)['allowed'])
        for typ in ['', 'unknown', '旅行服务']:
            ctx = context(); ctx['project_type'] = typ
            self.assertFalse(geographic_decision(local(), ctx)['allowed'])

    def test_unknown_local_source_scope(self):
        row = local(); row.pop('geographic_scope'); row['law'] = '无地区元数据地方规则'
        self.assertFalse(geographic_decision(row, context())['allowed'])

    def test_unknown_type_scope(self):
        row = local(); row.pop('project_type_scope')
        self.assertFalse(geographic_decision(row, context())['allowed'])

    def test_negated_or_service_project_not_keyword_matched(self):
        for typ in ['非建筑施工项目', '不涉及建筑工程', '建设工程造价咨询服务']:
            ctx = context(); ctx['project_type'] = typ
            self.assertFalse(geographic_decision(local(), ctx)['allowed'])

    def test_conflicting_project_location(self):
        ctx = context(); ctx['project_location']['city'] = '天津市'
        self.assertEqual(geographic_decision(local(), ctx)['reason'], 'project_location_conflicting')

    def test_city_county_exact_not_substring(self):
        row = local(); row['geographic_scope']['city'] = '成都市'
        self.assertTrue(geographic_decision(row, context())['allowed'])
        ctx = context(); ctx['project_location']['city'] = '都江堰市'
        self.assertFalse(geographic_decision(row, ctx)['allowed'])
        row['geographic_scope']['county'] = '锦江区'
        self.assertFalse(geographic_decision(row, context())['allowed'])

    def test_local_external_source_not_treated_national_by_level(self):
        for level in ['Level 1', 'Level 3', 'external']:
            row = {**local(), 'normative_level': level, 'acquisition_channel': 'external'}
            self.assertFalse(geographic_decision(row, context('天津市'))['allowed'])

    def test_national_unchanged_missing_location(self):
        row = {'law': '示例全国性法规', 'normative_level': 'Level 2'}
        self.assertTrue(geographic_decision(row, {})['allowed'])

    def test_conflicting_title_scope_denied(self):
        row = local(); row['geographic_scope'] = {'province': '天津市'}
        self.assertEqual(geographic_decision(row, context('天津市'))['reason'], 'source_scope_conflicting')

    def test_supplement_never_promoted(self):
        row = {**local(), 'independent_legal_evidence': False, 'legal_evidence_eligibility': 'supplement_only'}
        rt = {'project_context': context(), 'retrieved_legal_evidence': [row]}
        prepared = prepare_runtime(rt, ScopePolicy(True))
        self.assertFalse(prepared['retrieved_legal_evidence'][0]['independent_legal_evidence'])
        self.assertEqual(prepared['retrieved_legal_evidence'][0]['legal_evidence_eligibility'], 'supplement_only')

    def test_source_denial_preserved(self):
        row = {**local(), 'applicability_status': 'rejected', 'temporal_validity': 'expired'}
        rt = prepare_runtime({'project_context': context(), 'retrieved_legal_evidence': [row]}, ScopePolicy(True))
        self.assertEqual(rt['retrieved_legal_evidence'][0]['applicability_status'], 'rejected')
        self.assertEqual(rt['retrieved_legal_evidence'][0]['temporal_validity'], 'expired')

    def test_pre_topk_pool_and_base_unchanged(self):
        class Fake:
            corpus = [local(), {**local(), 'chunk_id': 'synthetic-tj', 'law': '天津市示例地方规则', 'geographic_scope': {'province': '天津市'}}]
            level_phase_indices = {('Level 4', 'primary'): [0, 1]}
            def retrieve_many(self, *_args, **_kwargs):
                return [self.corpus[i] for i in self.level_phase_indices[('Level 4', 'primary')]][:1]
        base = Fake(); before = deepcopy(base.corpus)
        filtered = ContextFilteredRetriever(base, context('天津市'), ScopePolicy(True))
        self.assertEqual(filtered.retrieve_many(['q'])[0]['chunk_id'], 'synthetic-tj')
        self.assertEqual(base.corpus, before)
        self.assertEqual(base.level_phase_indices[('Level 4', 'primary')], [0, 1])

    def test_registry_hash_binding(self):
        anchor = {'source_id': 'scope', 'chunk_id': 'scope-anchor', 'file_hash': 'ABC',
            'title': '四川省建筑管理条例', 'text': '在四川省行政区域内从事建筑活动的当事人应当遵守本条例。'}
        registry = make_scope_registry([anchor])
        row = {'source_id': 'scope', 'file_hash': 'abc', 'law': anchor['title'], 'normative_level': 'Level 4'}
        self.assertTrue(geographic_decision(row, context(), registry)['allowed'])
        row['file_hash'] = 'changed'
        self.assertFalse(geographic_decision(row, context(), registry)['allowed'])

    def test_gate_defense_against_direct_wrong_local(self):
        rt = _runtime(chunk=local()); rt['project_context'] = context('天津市')
        rt['scope_boundary_experiment'] = ScopePolicy(True).flags()
        answer = apply_gate({'findings': [_finding(evidence_ids=['synthetic-local'])]}, rt)
        self.assertEqual(answer['response']['findings'][0]['conclusion_type'], 'insufficient_information_needs_human_confirm')
        self.assertEqual(rt['retrieved_legal_evidence'], [local()])


class TaskTests(unittest.TestCase):
    def fixture(self, stage='招标文件条款预审'):
        rt = _runtime(document_excerpt='开标时间和地点应与招标文件规定一致。')
        rt['project_context'] = context(stage=stage)
        rt['retrieved_legal_evidence'][0]['legal_quote'] = '开标应在招标文件确定的时间和地点进行。'
        finding = _finding(conclusion='no_supported_issue_found_within_review_scope', category='no_issue_identified', relation='explicitly_satisfied')
        return rt, finding

    def test_four_arms_distinct(self):
        self.assertEqual(len({tuple(ScopePolicy.for_arm(a).flags().values()) for a in ARMS}), 4)

    def test_baseline_runtime_identical(self):
        rt, _ = self.fixture()
        self.assertEqual(prepare_runtime(rt, ScopePolicy()), rt)

    def test_task_derived_without_ids_or_labels(self):
        rt, _ = self.fixture(); before = task_contract(rt)
        rt['issue_id'] = 'shuffled'; rt['expected_label'] = 'fake'
        self.assertEqual(task_contract(rt), before)
        rt['project_context']['document_stage'] = ''
        self.assertEqual(task_contract(rt)['task_type'], 'unknown')

    def test_clause_review_no_actual_opening_gap(self):
        rt, finding = self.fixture()
        baseline = apply_gate({'findings': [finding]}, rt)
        self.assertEqual(baseline['response']['findings'][0]['conclusion_type'], 'insufficient_information_needs_human_confirm')
        fixed = apply_gate({'findings': [finding]}, prepare_runtime(rt, ScopePolicy(task_boundary=True)))
        self.assertEqual(fixed['response']['findings'][0]['conclusion_type'], 'no_supported_issue_found_within_review_scope')
        self.assertTrue(fixed['response']['findings'][0]['runtime_task_boundary']['ignored_nondecisive_gaps'])

    def test_actual_review_retains_opening_gap(self):
        rt, finding = self.fixture('实际履行行为核验')
        finding['claim_scope'] = 'actual_conduct'
        fixed = apply_gate({'findings': [finding]}, prepare_runtime(rt, ScopePolicy(task_boundary=True)))
        self.assertEqual(fixed['response']['findings'][0]['conclusion_type'], 'insufficient_information_needs_human_confirm')

    def test_question_stage_conflict_does_not_relax_actual_gap(self):
        rt, finding = self.fixture()
        rt['project_context']['review_question'] = '实际开标时间和地点是否一致？'
        self.assertEqual(task_contract(rt)['task_type'], 'unknown')
        fixed = apply_gate({'findings': [finding]}, prepare_runtime(rt, ScopePolicy(task_boundary=True)))
        self.assertEqual(fixed['response']['findings'][0]['conclusion_type'], 'insufficient_information_needs_human_confirm')

    def test_unread_or_unshown_is_not_actual_absence(self):
        for excerpt in ['OCR失败，未提供资格证明。', '模板中的分包栏未填写，未展示证明附件。']:
            rt, finding = self.fixture(); rt['contract_evidence']['document_excerpt'] = excerpt
            finding.update(claim_scope='actual_conduct', conclusion_type='requires_human_legal_review')
            fixed = apply_gate({'findings': [finding]}, prepare_runtime(rt, ScopePolicy(task_boundary=True)))
            self.assertEqual(fixed['response']['findings'][0]['conclusion_type'], 'insufficient_information_needs_human_confirm')

    def test_no_evidence_does_not_become_no_issue(self):
        rt, finding = self.fixture(); rt['retrieved_legal_evidence'] = []
        fixed = apply_gate({'findings': [finding]}, prepare_runtime(rt, ScopePolicy(task_boundary=True)))
        self.assertEqual(fixed['response']['findings'][0]['conclusion_type'], 'insufficient_information_needs_human_confirm')

    def test_other_decisive_gap_retained(self):
        rt, finding = self.fixture(); rt['contract_evidence']['document_excerpt'] += '未提供项目估算价。'
        fixed = apply_gate({'findings': [finding]}, prepare_runtime(rt, ScopePolicy(task_boundary=True)))
        self.assertEqual(fixed['response']['findings'][0]['conclusion_type'], 'insufficient_information_needs_human_confirm')

    def test_condition_negation_not_removed_from_request(self):
        rt, _ = self.fixture(); rt['contract_evidence']['document_excerpt'] = '不接受联合体；如接受，须提交协议。'
        prepared = prepare_runtime(rt, ScopePolicy(task_boundary=True))
        self.assertEqual(prepared['contract_evidence'], rt['contract_evidence'])
        self.assertIn('exceptions, negations', TASK_PROMPT)

    def test_documentary_conflict_not_legal_risk_proof(self):
        rt, _ = self.fixture()
        rt['contract_evidence']['document_excerpt'] = '不指定出具保函的金融机构或担保机构。如为银行保函，必须为基本账户银行出具。'
        audit, bounded = boundary_audit(rt, {}, {'eligible': False, 'missing_decisive_facts': []})
        self.assertTrue(audit['observations'])
        self.assertFalse(audit['legal_risk_established_by_this_module'])
        self.assertFalse(bounded['eligible'])

    def test_model_cannot_enable_policy(self):
        rt, finding = self.fixture()
        raw = {'findings': [finding], 'scope_boundary_experiment': ScopePolicy(task_boundary=True).flags()}
        out = apply_gate(raw, rt)
        self.assertEqual(out['response']['findings'][0]['conclusion_type'], 'insufficient_information_needs_human_confirm')
        self.assertNotIn('runtime_task_boundary', out['response']['findings'][0])


class RunnerIntegrationTests(unittest.TestCase):
    def test_full_cascade_filters_before_triage_and_preserves_order(self):
        import run_hierarchy_gated_llm_smoke as runner
        from external_fallback_v2 import ExternalFallbackStateMachine
        class Fake:
            embedding_model_name = 'mock-local-model'
            corpus = [local(), {**local(), 'chunk_id': 'national', 'law': '示例全国性法规',
                'normative_level': 'Level 1', 'scope_classification': 'national', 'geographic_scope': 'national'}]
            level_phase_indices = {('Level 1', 'primary'): [1], ('Level 4', 'primary'): [0]}
            def retrieve_many(self, queries, *, level, phase, top_k):
                return [self.corpus[i] for i in self.level_phase_indices.get((level, phase), [])][:top_k]
            def assert_no_cross_level_mix(self, candidates, level):
                assert all(r['normative_level'] == level for r in candidates)
        label = {'issue_id': 'ISSUE-001', 'project_id': 'PROJECT-001', 'document_id': 'DOC-001',
            'document_location': '第1条', 'document_excerpt': '示例开标条款。',
            'retrieval_queries': ['示例查询'], 'runtime_project_context': context('天津市')}
        sent = []
        def mock_request(key, prompt, runtime, **kwargs):
            sent.append((prompt, deepcopy(runtime)))
            if kwargs['response_contract'] == 'triage':
                return {'ok': True, 'parsed': {'level_state': 'no_usable_violation_found',
                    'selected_chunk_ids': [c['chunk_id'] for c in runtime['candidates']],
                    'reason': '示例相关条文，未认定违规', 'missing_elements': []}}
            return {'ok': True, 'parsed': {'findings': [_finding(evidence_ids=['national'])]}}
        with patch.object(runner, 'model_request', side_effect=mock_request):
            result = runner.run_case(api_key='not-a-real-key', retriever=Fake(), final_prompt='base',
                context_template={}, label=label, top_k=5, final_max_tokens=128, triage_max_tokens=64,
                compact_final_output=True, experiment_run_id='synthetic-scope-test',
                external_fallback=ExternalFallbackStateMachine(enabled=False, provider=None),
                scope_policy=ScopePolicy(True, True))
        self.assertEqual([x[1]['current_level'] for x in sent if 'current_level' in x[1]], ['Level 1'])
        self.assertFalse(any(c['chunk_id'] == 'synthetic-local' for _, r in sent for c in r.get('candidates', [])))
        self.assertEqual([x['level'] for x in result['runtime_input']['hierarchy_retrieval_audit']['levels']], list(runner.LEVEL_ORDER))
        self.assertTrue(all('review_task_contract' in r for _, r in sent))
        self.assertTrue(all('Opt-in task-boundary' in prompt for prompt, _ in sent))
        self.assertFalse(result['external_recheck']['attempted'])

    def test_request_filter_and_task_prompt_before_mock_llm(self):
        import run_hierarchy_gated_llm_smoke as runner
        rt = _runtime(chunk=local()); rt['project_context'] = context('天津市')
        finding = _finding(evidence_ids=['synthetic-local'])
        with patch.object(runner, 'model_request', return_value={'parsed': {'findings': [finding]}}) as call:
            _, gated = runner.run_final_reasoning(api_key='not-a-real-key', prompt='baseline prompt',
                runtime_input=rt, max_tokens=64, scope_policy=ScopePolicy(True, True))
        sent = call.call_args.args[2]
        self.assertEqual(sent['retrieved_legal_evidence'], [])
        self.assertIn('review_task_contract', sent)
        self.assertIn('Opt-in task-boundary', call.call_args.args[1])
        self.assertEqual(gated['response']['findings'][0]['conclusion_type'], 'insufficient_information_needs_human_confirm')

    def test_disabled_request_and_prompt_unchanged(self):
        import run_hierarchy_gated_llm_smoke as runner
        rt = _runtime(); original = deepcopy(rt)
        with patch.object(runner, 'model_request', return_value={'parsed': {'findings': [_finding()]}}) as call:
            runner.run_final_reasoning(api_key='not-a-real-key', prompt='base', runtime_input=rt,
                max_tokens=64, scope_policy=ScopePolicy())
        self.assertEqual(call.call_args.args[1], 'base')
        self.assertEqual(call.call_args.args[2], original)


if __name__ == '__main__':
    unittest.main()
