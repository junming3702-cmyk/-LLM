"""Synthetic mechanism checks, not expert labels or legal accuracy tests."""
from copy import deepcopy
import unittest
from test_nu_boundary_policy import fixture, gap, N, U
from review_task_contract_v2 import build_contract, validate_contract, gap_resolution
from llm_abstention_gate import apply_gate


def scoped_fixture():
    rt, f = fixture()
    rt['project_context'].update(document_stage='document_response', review_question='两处表达是否一致？')
    rt['contract_evidence'].update(document_excerpt='[段1]提供真实有效的证明文件。[段2]提供真实有效的证明文件。',
                                   document_location='段1;段2')
    f['decision_basis'].update(review_question='两处表达是否一致？', review_target='document_response')
    f['decision_basis']['completed_checks'][0]['document_locator']='段1'
    rt['review_task_contract_v2']=build_contract(rt)
    return rt, f


def run(rt, f):
    return apply_gate({'findings':[f]}, rt, task_contract_v2=True)


class ContractV2Tests(unittest.TestCase):
    def test_scope_input_only_and_bound(self):
        rt,f=scoped_fixture(); c=build_contract(rt)
        self.assertEqual(c['scope'],'supplied_text_consistency')
        self.assertTrue(validate_contract(rt,c)); self.assertFalse(c['human_scope_approval'])
        rt['contract_evidence']['document_excerpt']+='新内容'
        self.assertFalse(validate_contract(rt,c))

    def test_external_requirement_not_needed_for_two_supplied_expressions(self):
        rt,f=scoped_fixture();gap(f,'required_document_missing')
        f['decision_basis']['gaps'][0]['detail']='招标文件前附表完整原文未提供'
        original=deepcopy((rt,f)); old=apply_gate({'findings':[f]},rt,nu_boundary=True)
        new=run(rt,f)
        self.assertEqual(old['response']['findings'][0]['conclusion_type'],U)
        self.assertFalse(new['blocked']);self.assertEqual(new['response']['findings'][0]['conclusion_type'],N)
        self.assertEqual((rt,f),original)
        self.assertEqual(new['raw_response'],{'findings':[f]})
        self.assertEqual(new['response']['findings'][0]['decision_basis'],f['decision_basis'])

    def test_core_gaps_never_waived_by_false(self):
        for kind in ('key_legal_source_missing','decisive_applicability_missing','comparison_value_missing','unreadable_evidence'):
            with self.subTest(kind=kind):
                rt,f=scoped_fixture();gap(f,kind)
                self.assertEqual(run(rt,f)['response']['findings'][0]['conclusion_type'],U)

    def test_unknown_material_not_waived(self):
        rt,f=scoped_fixture();gap(f,'input_evidence_missing')
        self.assertEqual(run(rt,f)['response']['findings'][0]['conclusion_type'],U)

    def test_true_blocking_not_waived(self):
        rt,f=scoped_fixture();gap(f,'required_document_missing',True)
        f['decision_basis']['gaps'][0]['detail']='招标文件前附表完整原文未提供'
        self.assertEqual(run(rt,f)['response']['findings'][0]['conclusion_type'],U)

    def test_completeness_and_actual_tasks_never_narrowed(self):
        for stage,target in [('document_completeness','document_completeness'),('performance_verification','actual_conduct')]:
            rt,f=scoped_fixture();rt['project_context']['document_stage']=stage
            rt['review_task_contract_v2']=build_contract(rt);f['decision_basis']['review_target']=target
            gap(f,'required_document_missing');f['decision_basis']['gaps'][0]['detail']='招标文件前附表完整原文未提供'
            self.assertEqual(run(rt,f)['response']['findings'][0]['conclusion_type'],U)

    def test_ambiguous_question_not_narrowed_for_better_score(self):
        rt,f=scoped_fixture();rt['project_context']['review_question']='该承诺可支持何种判断？'
        rt['review_task_contract_v2']=build_contract(rt);f['decision_basis']['review_question']=rt['project_context']['review_question']
        gap(f,'input_evidence_missing');f['decision_basis']['gaps'][0]['detail']='招标文件前附表完整原文未提供'
        g=run(rt,f);self.assertEqual(g['response']['findings'][0]['conclusion_type'],U)
        self.assertTrue(g['response']['findings'][0]['review_handoff']['scope_needs_confirmation'])

    def test_exception_context_not_waived(self):
        rt,f=scoped_fixture();gap(f,'input_evidence_missing')
        f['decision_basis']['gaps'][0]['detail']='招标文件前附表完整原文未提供，包含适用例外'
        self.assertEqual(run(rt,f)['response']['findings'][0]['conclusion_type'],U)

    def test_missing_or_forged_contract_is_technical_block(self):
        rt,f=scoped_fixture();rt.pop('review_task_contract_v2')
        self.assertTrue(run(rt,f)['blocked'])
        rt,f=scoped_fixture();rt['review_task_contract_v2']['scope']='clause_design'
        self.assertTrue(run(rt,f)['blocked'])

    def test_bad_locator_is_not_valid_legal_abstention(self):
        rt,f=scoped_fixture();f['decision_basis']['completed_checks'][0]['document_locator']='不存在的页'
        g=run(rt,f);self.assertTrue(g['blocked'])
        self.assertEqual(g['response']['findings'][0]['review_handoff']['processing_status'],'evidence_binding_blocked')

    def test_redaction_brackets_do_not_split_declared_locator(self):
        rt,f=scoped_fixture()
        rt['contract_evidence']['document_excerpt']='[段1]供应商[姓名已隐去]提供真实有效的证明文件。[段2]提供真实有效的证明文件。'
        rt['review_task_contract_v2']=build_contract(rt)
        g=run(rt,f)
        self.assertFalse(g['blocked'])
        self.assertEqual(g['response']['findings'][0]['conclusion_type'],N)

    def test_redaction_brackets_do_not_create_two_sources(self):
        rt,f=scoped_fixture()
        rt['contract_evidence'].update(document_location='段1',document_excerpt='[段1]供应商[姓名已隐去]提供真实有效的证明文件。')
        self.assertNotEqual(build_contract(rt)['scope'],'supplied_text_consistency')

    def test_cross_locator_quote_not_silently_merged(self):
        rt,f=scoped_fixture()
        rt['contract_evidence']['document_excerpt']='[段1]提供真实有效的[段2]证明文件。'
        rt['review_task_contract_v2']=build_contract(rt)
        self.assertTrue(run(rt,f)['blocked'])

    def test_no_law_or_supplement_only_not_N(self):
        for supplement in (False,True):
            rt,f=scoped_fixture()
            if supplement:rt['retrieved_legal_evidence'][0].update(independent_legal_evidence=False,legal_evidence_eligibility='supplement_only')
            else:rt['retrieved_legal_evidence']=[]
            self.assertNotEqual(run(rt,f)['response']['findings'][0]['conclusion_type'],N)

    def test_supplied_supplement_not_a_technical_failure(self):
        rt,f=scoped_fixture()
        rt['retrieved_legal_evidence'][0].update(independent_legal_evidence=False,legal_evidence_eligibility='supplement_only')
        g=run(rt,f)
        self.assertEqual(g['response']['findings'][0]['review_handoff']['processing_status'],'valid')
        self.assertEqual(g['response']['findings'][0]['conclusion_type'],U)

    def test_clause_future_act_vs_decisive_exception(self):
        rt,f=scoped_fixture();rt['project_context'].update(document_stage='招标文件条款预审',review_question='该履行条款如何评价？')
        c=build_contract(rt)
        g={'kind':'input_evidence_missing','detail':'实际履行记录未提供','blocks_current_question':False}
        self.assertEqual(gap_resolution(c,g)['resolution'],'follow_up_only')
        g['detail']+='，包含适用例外'
        self.assertEqual(gap_resolution(c,g)['resolution'],'preserve')

    def test_candidate_prompt_drift_is_fail_closed(self):
        from task_gate_v2_prompt import candidate_prompt,build_prompt
        p=candidate_prompt()
        self.assertIn('schema/定位校验失败须另记处理状态',p)
        self.assertNotIn('或虽有候选材料却没有形成具体风险关系',p)
        with self.assertRaises(ValueError):build_prompt('Unrecognized prompt version')

    def test_online_opt_in_binds_contract_before_mocked_generation(self):
        from unittest.mock import patch
        from pathlib import Path
        import run_hierarchy_gated_llm_smoke as runner
        rt,f=scoped_fixture();rt.pop('review_task_contract_v2')
        base=(Path(__file__).resolve().parents[1]/'prompts/system_prompt_final.md').read_text(encoding='utf-8')
        def mock_request(key,prompt,runtime,**kwargs):
            self.assertTrue(validate_contract(runtime,runtime['review_task_contract_v2']))
            self.assertIn('Task-gate v2 candidate',prompt)
            return {'ok':True,'parsed':{'findings':[f]}}
        with patch.object(runner,'model_request',side_effect=mock_request):
            _,g=runner.run_final_reasoning(api_key='synthetic-only',prompt=base,runtime_input=rt,max_tokens=100,task_contract_v2=True)
        self.assertIn('review_handoff',g['response']['findings'][0])

    def test_U_not_automatically_promoted(self):
        rt,f=scoped_fixture();f['conclusion_type']=U
        f['decision_basis'].update(answerability='decisive_gap');gap(f,'input_evidence_missing',True)
        self.assertEqual(run(rt,f)['response']['findings'][0]['conclusion_type'],U)

    def test_explanation_survives_U_with_unverified_label(self):
        rt,f=scoped_fixture();gap(f,'input_evidence_missing',True)
        f['fact_law_comparison']={'difference_summary':'识别到主体不匹配，尚不能建立法律判断。'}
        g=run(rt,f);h=g['response']['findings'][0]['review_handoff']
        self.assertEqual(h['model_comparison_for_review'],f['fact_law_comparison']['difference_summary'])
        self.assertEqual(h['model_comparison_status'],'unverified_model_explanation_not_independent_legal_evidence')
        self.assertEqual(h['workflow_status'],'requires_human_second_review')

    def test_no_version_change_when_opt_out(self):
        rt,f=scoped_fixture()
        self.assertEqual(apply_gate({'findings':[f]},rt,nu_boundary=True),apply_gate({'findings':[f]},rt,nu_boundary=True,task_contract_v2=False))


if __name__=='__main__':unittest.main()
