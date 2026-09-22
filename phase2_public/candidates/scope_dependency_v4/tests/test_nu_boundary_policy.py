"""Synthetic scope/provenance guards; not a legal accuracy benchmark."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from nu_boundary_policy import audit_basis, HARD_GAPS, FOLLOWUP_GAPS
from llm_abstention_gate import apply_gate
from test_post_llm_gate_v2 import _runtime, _finding
from test_scope_boundary_policy import context

N = 'no_supported_issue_found_within_review_scope'
U = 'insufficient_information_needs_human_confirm'

def fixture():
    rt = _runtime(document_excerpt='申请人承诺提供真实有效的证明文件。')
    rt['project_context'] = context()
    f = _finding(conclusion=N, category='no_issue_identified', relation='no_supported_conflict_within_scope')
    f.update(risk_severity='none', severity_basis='no_supported_risk',
             reasoning_conclusion='当前声明要求提供真实有效的证明，与引用规则的文字要求一致。')
    f['decision_basis'] = {'review_question': '预审当前条款', 'review_target': 'textual_pre_review',
        'answerability': 'sufficient', 'completed_checks': [{
            'check': '声明文字与证明要求比对', 'document_quote': '提供真实有效的证明文件',
            'document_locator': '第3.2条', 'legal_chunk_ids': ['law-1'],
            'comparison': '文字明确要求真实有效证明，与示例规则一致；不核验后续提交。'}],
        'gaps': [], 'bounded_conclusion': '当前声明文字未发现支持性冲突，不证明实际提交。'}
    return rt, f

def gap(f, kind, blocks=False):
    f['decision_basis']['gaps'] = [{'kind': kind, 'detail': '指定资料或事实待核验',
        'blocks_current_question': blocks, 'reason': '仅当前文字预审，不推定实际执行。'}]

def run(rt, f, **kwargs):
    return apply_gate({'findings': [f]}, rt, nu_boundary=True, **kwargs)

class AnswerabilityTests(unittest.TestCase):
    def test_existing_document_response_target_accepted(self):
        rt,f=fixture(); rt['project_context']['document_stage']='document_response'
        f['decision_basis']['review_target']='document_response';gap(f,'input_evidence_missing',True)
        f['decision_basis']['answerability']='decisive_gap'
        g=run(rt,f);self.assertFalse(g['blocked'])
        self.assertEqual(g['response']['findings'][0]['conclusion_type'],U)

    def test_document_response_followup_can_stay_bounded_N(self):
        rt,f=fixture();rt['project_context']['document_stage']='document_response'
        f['decision_basis']['review_target']='document_response';gap(f,'future_performance_unverified')
        g=run(rt,f);self.assertFalse(g['blocked'])
        self.assertEqual(g['response']['findings'][0]['conclusion_type'],N)

    def test_prompt_mirror_matches_executable(self):
        from nu_boundary_policy import PROMPT
        path=Path(__file__).resolve().parents[1]/'prompts/nu_boundary_candidate_v1.md'
        self.assertEqual(path.read_text(encoding='utf-8').strip(),PROMPT.strip())

    def test_grounded_bounded_N(self):
        rt, f = fixture(); g = run(rt, f)
        self.assertFalse(g['blocked'])
        self.assertEqual(g['response']['findings'][0]['conclusion_type'], N)

    def test_each_followup_does_not_require_U(self):
        for kind in FOLLOWUP_GAPS:
            with self.subTest(kind=kind):
                rt,f=fixture(); gap(f,kind)
                g=run(rt,f)
                self.assertEqual(g['response']['findings'][0]['conclusion_type'],N)
                self.assertEqual(len(g['response']['findings'][0]['nu_boundary_audit']['follow_up_only']),1)

    def test_each_decisive_gap_cannot_be_hidden_as_followup(self):
        for kind in HARD_GAPS:
            for label in (N, 'requires_human_legal_review'):
                with self.subTest(kind=kind,label=label):
                    rt,f=fixture(); gap(f,kind); f['conclusion_type']=label
                    self.assertEqual(run(rt,f)['response']['findings'][0]['conclusion_type'],U)

    def test_followup_marked_decisive_stays_U(self):
        rt,f=fixture(); gap(f,'authenticity_unverified',True)
        self.assertEqual(run(rt,f)['response']['findings'][0]['conclusion_type'],U)

    def test_actual_question_cannot_be_narrowed(self):
        rt,f=fixture(); rt['project_context']['document_stage']='performance_verification'
        self.assertTrue(audit_basis(rt,f,rt['retrieved_legal_evidence'])['force_insufficient'])

    def test_explicit_factual_question_cannot_be_narrowed(self):
        rt,f=fixture(); rt['project_context']['review_question']='证明文件是否已提交？'
        f['decision_basis']['review_question']=rt['project_context']['review_question']
        self.assertEqual(run(rt,f)['response']['findings'][0]['conclusion_type'],U)

    def test_completeness_question_cannot_be_narrowed(self):
        rt,f=fixture(); rt['project_context']['document_stage']='document_completeness'
        self.assertTrue(audit_basis(rt,f,rt['retrieved_legal_evidence'])['force_insufficient'])

    def test_actual_target_authenticity_missing(self):
        rt,f=fixture(); rt['project_context']['document_stage']='performance_verification'
        f['decision_basis']['review_target']='actual_conduct'; gap(f,'authenticity_unverified')
        self.assertEqual(run(rt,f)['response']['findings'][0]['conclusion_type'],U)

    def test_U_not_automatically_promoted(self):
        rt,f=fixture(); f['conclusion_type']=U; gap(f,'input_evidence_missing',True)
        f['decision_basis']['answerability']='decisive_gap'; f['decision_basis']['completed_checks']=[]
        self.assertEqual(run(rt,f)['response']['findings'][0]['conclusion_type'],U)

    def test_no_law_not_N(self):
        rt,f=fixture(); rt['retrieved_legal_evidence']=[]
        self.assertEqual(run(rt,f)['response']['findings'][0]['conclusion_type'],U)

    def test_supplement_only_not_N(self):
        rt,f=fixture(); rt['retrieved_legal_evidence'][0].update(
            independent_legal_evidence=False,legal_evidence_eligibility='supplement_only',source_role='supplement')
        self.assertEqual(run(rt,f)['response']['findings'][0]['conclusion_type'],U)

    def test_no_completed_check_not_N(self):
        rt,f=fixture(); f['decision_basis']['completed_checks']=[]
        self.assertEqual(run(rt,f)['response']['findings'][0]['conclusion_type'],U)

    def test_fabricated_bindings_not_N(self):
        for field,value in [('document_quote','输入中并不存在的合同内容'),('document_locator','第999页'),('legal_chunk_ids',['invented'])]:
            with self.subTest(field=field):
                rt,f=fixture(); f['decision_basis']['completed_checks'][0][field]=value
                self.assertEqual(run(rt,f)['response']['findings'][0]['conclusion_type'],U)

    def test_quote_wrong_supplied_page_not_N(self):
        rt,f=fixture(); rt['contract_evidence']['document_excerpt']='[第1页]其他内容文字。[第2页]提供真实有效的证明文件。'
        rt['contract_evidence']['document_location']='第1页;第2页'
        f['decision_basis']['completed_checks'][0]['document_locator']='第1页'
        self.assertEqual(run(rt,f)['response']['findings'][0]['conclusion_type'],U)

    def test_schema_error_is_blocked_not_valid_abstention(self):
        for field in ['review_question','review_target','answerability','gaps','bounded_conclusion']:
            with self.subTest(field=field):
                rt,f=fixture(); f['decision_basis'].pop(field)
                self.assertTrue(run(rt,f)['blocked'])
        rt,f=fixture(); f.pop('decision_basis'); self.assertTrue(run(rt,f)['blocked'])

    def test_question_mismatch_is_blocked(self):
        rt,f=fixture(); f['decision_basis']['review_question']='另一个问题'
        self.assertTrue(run(rt,f)['blocked'])

    def test_decisive_gap_needs_description(self):
        rt,f=fixture(); f['decision_basis']['answerability']='decisive_gap'
        self.assertTrue(run(rt,f)['blocked'])

    def test_missing_consequence_not_automatic_U(self):
        rt,f=fixture(); f['legal_element_coverage']['legal_consequence']='missing'
        self.assertEqual(run(rt,f)['response']['findings'][0]['conclusion_type'],N)

    def test_risk_relation_not_overridden_by_N_basis(self):
        rt,f=fixture(); f.update(conclusion_type='requires_human_legal_review',
            risk_category='potential_non_compliance',compliance_relation='potential_non_compliance')
        self.assertNotEqual(run(rt,f)['response']['findings'][0]['conclusion_type'],N)

    def test_no_input_mutation(self):
        rt,f=fixture(); before=deepcopy((rt,f)); run(rt,f)
        self.assertEqual((rt,f),before)

    def test_default_flag_preserves_original_behavior(self):
        rt,f=fixture(); raw={'findings':[f]}
        self.assertEqual(apply_gate(raw,rt), apply_gate(raw,rt,nu_boundary=False))

if __name__ == '__main__': unittest.main()
