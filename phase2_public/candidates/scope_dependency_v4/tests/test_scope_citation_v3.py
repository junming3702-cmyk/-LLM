"""Synthetic mechanism regression, never legal/author-reference labels."""
from copy import deepcopy
import unittest
from test_review_task_contract_v2 import scoped_fixture, run
from test_nu_boundary_policy import fixture, gap, N, U
from review_task_contract_v2 import build_contract, audit_basis_v2, source_spans
from question_scope_signals import factual_question_audit
from exact_citation_fragments import check_document_binding
from llm_abstention_gate import apply_gate


def clause(question):
    rt,f=fixture()
    rt['project_context'].update(document_stage='clause_pre_review:条款设置审查',review_question=question)
    f['decision_basis'].update(review_question=question,review_target='textual_pre_review')
    rt['review_task_contract_v2']=build_contract(rt)
    return rt,f


def fragments_fixture():
    rt,f=scoped_fixture()
    rt['contract_evidence'].update(document_excerpt='[段1]项目经理不得同时在其他项目任职。[段2]我方承诺项目经理不在其他项目任职。',document_location='段1;段2')
    parts=[{'document_quote':'项目经理不得同时在其他项目任职','document_locator':'段1'},
           {'document_quote':'我方承诺项目经理不在其他项目任职','document_locator':'段2'}]
    check=f['decision_basis']['completed_checks'][0]
    check.update(document_fragments=parts,document_quote='\n'.join(p['document_quote'] for p in parts),document_locator='段1;段2',
                 check='两个已供片段的文字比对',comparison='分别列明当前文字；不据承诺证明真实任职。')
    rt['review_task_contract_v2']=build_contract(rt)
    return rt,f


class ScopeSignalsTests(unittest.TestCase):
    def test_explicit_exclusions_do_not_create_factual_task(self):
        cases=['仅审查资质要求条款，不核验实际业绩真实性。','预审当前条款；也不核验实际业绩真实性。',
               '审查条款设置，无需核验业绩真实性。','只审查约定，不再核实材料真实性。',
               '条款预审，无须核验真实性。','审查条款，不核验是否已提交。',
               '审查条款；不确认是否齐全。','条款审查，不判断是否实际履行。',
               '只审查条款，不审查实际履行。','只审查条款，不核验是否已送达。']
        for q in cases:
            with self.subTest(q=q):
                rt,f=clause(q);a=audit_basis_v2(rt,f,rt['retrieved_legal_evidence'])
                self.assertEqual(build_contract(rt)['scope'],'clause_design')
                self.assertNotIn('explicit_factual_question_narrowed',a['blocking_reasons'])
                self.assertEqual(run(rt,f)['response']['findings'][0]['conclusion_type'],N)

    def test_positive_or_ambiguous_tasks_remain_blocking(self):
        cases=['核验实际业绩真实性。','核实业绩真实性。','证明是否已提交？','材料是否齐全？',
               '材料是否完整提交？','核验是否实际履行？','不得不核验真实性。','并非不核验真实性。',
               '不但核验真实性，而且核验完整性。','无需不核验真实性。',
               '只检查条款，不核验真实性；但本次必须核验是否已提交。',
               '预审“无需核验真实性”条款。','不清楚是否不核验真实性。',
               '如果具备其他材料则不核验真实性。','除非额外要求否则不核验真实性。',
               '是否无需核验真实性？']
        for q in cases:
            with self.subTest(q=q):
                rt,f=clause(q);a=audit_basis_v2(rt,f,rt['retrieved_legal_evidence'])
                self.assertTrue(factual_question_audit(q)['has_active_factual_cue'])
                self.assertIn('explicit_factual_question_narrowed',a['blocking_reasons'])
                self.assertNotEqual(run(rt,f)['response']['findings'][0]['conclusion_type'],N)

    def test_scope_does_not_come_from_model_explanation(self):
        rt,f=clause('证书是否真实？')
        f['reasoning_conclusion']='不核验真实性，仅比较文字'
        self.assertTrue(build_contract(rt)['factual_question_audit']['has_active_factual_cue'])

    def test_input_quote_cannot_override_question(self):
        rt,f=clause('是否已提交？');rt['contract_evidence']['document_excerpt']='不核验真实性'
        self.assertTrue(build_contract(rt)['factual_question_audit']['has_active_factual_cue'])

    def test_explicit_factual_stage_not_downgraded_by_question_exclusion(self):
        for stage in ['performance_verification','document_completeness']:
            rt,f=clause('只审查条款，不核验真实性。');rt['project_context']['document_stage']=stage
            self.assertEqual(build_contract(rt)['scope'],'actual_or_completeness')

    def test_stale_contract_still_blocks(self):
        rt,f=clause('只审查条款，不核验真实性。');rt['project_context']['review_question']='现在核验真实性。'
        self.assertTrue(run(rt,f)['blocked'])

    def test_core_gaps_not_relabelled_as_followup(self):
        for kind in ['key_legal_source_missing','comparison_value_missing','unreadable_evidence','decisive_applicability_missing']:
            rt,f=clause('只审查条款，不核验真实性。');gap(f,kind,False)
            self.assertEqual(run(rt,f)['response']['findings'][0]['conclusion_type'],U)


class FragmentBindingTests(unittest.TestCase):
    def test_explicit_fragments_are_individually_bound(self):
        rt,f=fragments_fixture();before=deepcopy((rt,f));g=run(rt,f)
        self.assertFalse(g['blocked']);self.assertEqual(g['response']['findings'][0]['conclusion_type'],N)
        self.assertEqual((rt,f),before);self.assertEqual(g['raw_response'],{'findings':[f]})
        audit=g['response']['findings'][0]['review_handoff']['citation_binding_audits'][0]
        self.assertTrue(audit['bound']);self.assertFalse(audit['legal_entailment_verified'])
        self.assertFalse(audit['contiguous_quote_claimed'])
        self.assertEqual(len(audit['fragments']),2)

    def test_semicolon_locator_alone_still_fails(self):
        rt,f=fragments_fixture();f['decision_basis']['completed_checks'][0].pop('document_fragments')
        self.assertTrue(run(rt,f)['blocked'])

    def test_each_fragment_requires_exact_quote_and_supplied_locator(self):
        mutations=[('document_quote','项目经理可同时在其他项目任职'),
                   ('document_quote','项目经理不得同时……任职'),('document_locator','不存在的页'),
                   ('document_locator','段2'),('document_locator','段1;段2')]
        for key,value in mutations:
            with self.subTest(key=key,value=value):
                rt,f=fragments_fixture();c=f['decision_basis']['completed_checks'][0]
                c['document_fragments'][0][key]=value
                c['document_quote']='\n'.join(p['document_quote'] for p in c['document_fragments'])
                c['document_locator']=';'.join(p['document_locator'] for p in c['document_fragments'])
                self.assertTrue(run(rt,f)['blocked'])

    def test_summary_cannot_add_new_prose_or_reorder_sources(self):
        for key,value in [('document_quote','我方完全符合所有要求'),('document_locator','段2;段1')]:
            rt,f=fragments_fixture();f['decision_basis']['completed_checks'][0][key]=value
            self.assertTrue(run(rt,f)['blocked'])

    def test_no_silent_date_or_number_normalization(self):
        spans={'页A':['截止日期为2022年6月21日09时30分。']}
        for q in ['截止日期为2022年06月21日09时30分','截止日期为2022年6月22日09时30分','截止日期为2022年6月21日 09时30分']:
            c={'document_quote':q,'document_locator':'页A'}
            self.assertFalse(check_document_binding(c,spans,spans['页A'][0])['bound'])

    def test_duplicate_ambiguous_or_malformed_fragments_fail(self):
        for mode in ['duplicate','ambiguous','wrong-shape','empty','too-many','extra-key','invalid-type']:
            with self.subTest(mode=mode):
                rt,f=fragments_fixture();c=f['decision_basis']['completed_checks'][0]
                if mode=='duplicate':c['document_fragments']=[c['document_fragments'][0]]*2
                if mode=='ambiguous':rt['contract_evidence']['document_excerpt']+=rt['contract_evidence']['document_excerpt']
                if mode=='wrong-shape':c['document_fragments']=[{},{}]
                if mode=='empty':c['document_fragments']=[]
                if mode=='too-many':c['document_fragments']*=5
                if mode=='extra-key':c['document_fragments'][0]['pretend_verified']=True
                if mode=='invalid-type':c['document_fragments'][0]['document_quote']=123
                rt['review_task_contract_v2']=build_contract(rt)
                self.assertTrue(run(rt,f)['blocked'])

    def test_fragments_cannot_upgrade_supplement_or_fabricated_law(self):
        for mode in ['none','supplement','unknown_id']:
            rt,f=fragments_fixture()
            if mode=='none':rt['retrieved_legal_evidence']=[]
            if mode=='supplement':rt['retrieved_legal_evidence'][0].update(independent_legal_evidence=False,legal_evidence_eligibility='supplement_only')
            if mode=='unknown_id':f['decision_basis']['completed_checks'][0]['legal_chunk_ids']=['made-up']
            self.assertNotEqual(run(rt,f)['response']['findings'][0]['conclusion_type'],N)

    def test_fragment_mode_cannot_override_decisive_gaps(self):
        rt,f=fragments_fixture();gap(f,'key_legal_source_missing',True)
        self.assertEqual(run(rt,f)['response']['findings'][0]['conclusion_type'],U)

    def test_opt_out_retains_legacy_semicolon_rejection(self):
        rt,f=fragments_fixture()
        old=apply_gate({'findings':[f]},rt,nu_boundary=True,task_contract_v2=False)
        self.assertEqual(old['response']['findings'][0]['conclusion_type'],U)

    def test_prompt_addendum_is_candidate_only(self):
        from scope_citation_v3_prompt import build_prompt,ADDENDUM
        from pathlib import Path
        p=Path(__file__).resolve().parents[1]/'prompts/system_prompt_final.md'
        text=p.read_text(encoding='utf-8')
        self.assertNotIn(ADDENDUM,text)
        self.assertIn('document_fragments',build_prompt(text))

    def test_mocked_online_entry_receives_fragment_protocol(self):
        from unittest.mock import patch
        from pathlib import Path
        import run_hierarchy_gated_llm_smoke as runner
        rt,f=fragments_fixture();rt.pop('review_task_contract_v2')
        base=(Path(__file__).resolve().parents[1]/'prompts/system_prompt_final.md').read_text(encoding='utf-8')
        def request(key,prompt,runtime,**kwargs):
            self.assertIn('Scope/citation v3 candidate',prompt)
            self.assertIn('document_fragments',prompt)
            self.assertEqual(runtime['review_task_contract_v2'],build_contract(runtime))
            return {'ok':True,'parsed':{'findings':[f]}}
        with patch.object(runner,'model_request',side_effect=request):
            _,g=runner.run_final_reasoning(api_key='synthetic-only',prompt=base,runtime_input=rt,max_tokens=100,task_contract_v2=True)
        self.assertFalse(g['blocked'])

if __name__=='__main__':unittest.main()
