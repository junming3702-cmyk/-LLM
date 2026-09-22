"""Paired synthetic mechanism guards, NOT legal/expert accuracy evidence."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import unittest

from test_nu_boundary_policy import fixture as old_fixture, N, U
from llm_abstention_gate import apply_gate
from scope_dependency_v4 import build_contract, audit_basis_v4, validate_spec


def fixture(mode="text_response_comparison"):
    rt, f = old_fixture()
    question = "承诺是否回应所给招标文字？仅核对承诺，不核验真实任职。"
    stage, target = "document_response", "document_response"
    exclusions = ["submission_package_completeness", "authenticity", "actual_performance"]
    if mode == "actual_submission_check":
        question, stage, target = "证明文件是否已提交？", "document_completeness", "document_completeness"
        exclusions = []
    if mode == "clause_design":
        question, stage, target = "当前证明要求条款设置是否合规？仅审查条款，不核验实际履行。", "clause_pre_review", "textual_pre_review"
    rt["project_context"].update(review_question=question, document_stage=stage)
    spec = {"question_verbatim": question, "review_mode": mode,
            "scope_basis": "Synthetic pre-inference test configuration; no human approval inferred",
            "excluded_dependencies": exclusions,
            "required_claims": [{"claim_id": "C1", "description": "当前文字与适用要求的比对",
                                 "required_dependencies": ["applicable_rule", "current_clause_context", "regulatory_applicability", "comparison_operand", "readability"] +
                                  (["submission_package_completeness", "authenticity", "actual_performance"] if mode == "actual_submission_check" else [])}]}
    rt["review_task_contract_v4"] = build_contract(rt, spec)
    b = f["decision_basis"]
    b.update(review_question=question, review_target=target,
             task_scope_sha256=rt["review_task_contract_v4"]["input_scope_sha256"])
    b["completed_checks"][0].update(check_id="Ck1", check_kind="legal_comparison", claim_ids=["C1"])
    return rt, f, spec


def add_gap(f, dep="submission_package_completeness", kind="input_evidence_missing", blocks=False, detail="未确认最终递交包完整性", affected=None):
    f["decision_basis"]["gaps"].append({"dependency_key": dep, "kind": kind, "detail": detail,
         "blocks_current_question": blocks, "affected_claim_ids": [] if affected is None else affected,
         "reason": "仅核对现有文字，不以范围外核验代替当前文字比对。"})


def run(rt, f, spec):
    return apply_gate({"findings": [f]}, rt, scope_dependency_v4=spec)


def finding(result):
    return result["response"]["findings"][0]


class ScopeDependencyTests(unittest.TestCase):
    def test_explicit_text_scope_can_keep_bounded_N(self):
        rt, f, s = fixture(); add_gap(f)
        g = run(rt, f, s)
        self.assertFalse(g["blocked"])
        self.assertEqual(finding(g)["conclusion_type"], N)
        self.assertEqual(len(finding(g)["review_handoff"]["out_of_scope_items"]), 1)

    def test_paired_actual_submission_scope_preserves_U(self):
        rt, f, s = fixture("actual_submission_check"); add_gap(f, affected=["C1"])
        g = run(rt, f, s)
        self.assertFalse(g["blocked"])
        self.assertEqual(finding(g)["conclusion_type"], U)

    def test_unapproved_exclusion_not_inferred(self):
        rt, f, s = fixture(); s["excluded_dependencies"] = []
        rt["review_task_contract_v4"] = build_contract(rt, s)
        f["decision_basis"]["task_scope_sha256"] = rt["review_task_contract_v4"]["input_scope_sha256"]
        add_gap(f)
        self.assertEqual(finding(run(rt, f, s))["conclusion_type"], U)

    def test_missing_and_stale_input_binding_block(self):
        for edit in ("missing", "source", "question", "spec"):
            with self.subTest(edit=edit):
                rt, f, s = fixture()
                if edit == "missing": rt.pop("review_task_contract_v4")
                if edit == "source": rt["contract_evidence"]["document_excerpt"] += "已更正"
                if edit == "question": rt["project_context"]["review_question"] += "检查实际提交。"
                if edit == "spec": s["excluded_dependencies"] = []
                self.assertTrue(run(rt, f, s)["blocked"])

    def test_response_cannot_forge_scope(self):
        rt, f, s = fixture(); f["decision_basis"]["task_scope_sha256"] = "forged"
        self.assertTrue(run(rt, f, s)["blocked"])

    def test_false_alone_does_not_waive_core_gaps(self):
        for dep, kind in (("applicable_rule", "key_legal_source_missing"),
                          ("regulatory_applicability", "decisive_applicability_missing"),
                          ("comparison_operand", "comparison_value_missing"),
                          ("readability", "unreadable_evidence"),
                          ("current_clause_context", "input_evidence_missing")):
            with self.subTest(dep=dep):
                rt, f, s = fixture(); add_gap(f, dep, kind, detail="当前子结论所需资料未提供", affected=["C1"])
                g = run(rt, f, s)
                self.assertFalse(g["blocked"])
                self.assertEqual(finding(g)["conclusion_type"], U)

    def test_core_dependency_cannot_be_excluded_in_spec(self):
        rt, f, s = fixture(); s["excluded_dependencies"].append("applicable_rule")
        self.assertTrue(validate_spec(rt, s))
        self.assertTrue(run(rt, f, s)["blocked"])

    def test_mixed_amendment_context_not_waived(self):
        for detail in ("递交包完整性未确认，且补遗可能改变条款", "最终提交包缺条款优先顺序", "完整承诺书中关键数值无法辨认"):
            rt, f, s = fixture(); add_gap(f, detail=detail)
            self.assertEqual(finding(run(rt, f, s))["conclusion_type"], U)

    def test_positive_gap_flag_not_overridden(self):
        rt, f, s = fixture(); add_gap(f, blocks=True, affected=["C1"])
        self.assertEqual(finding(run(rt, f, s))["conclusion_type"], U)

    def test_unknown_gap_not_waived(self):
        rt, f, s = fixture(); add_gap(f, "other_undetermined", "other_outside_question", detail="其他未说明资料")
        self.assertEqual(finding(run(rt, f, s))["conclusion_type"], U)

    def test_wrong_dependency_kind_is_technical_failure(self):
        rt, f, s = fixture(); add_gap(f, kind="key_legal_source_missing")
        self.assertTrue(run(rt, f, s)["blocked"])

    def test_excluded_item_cannot_affect_required_claim(self):
        rt, f, s = fixture(); add_gap(f, affected=["C1"])
        g = run(rt, f, s)
        self.assertTrue(g["blocked"])
        self.assertEqual(finding(g)["conclusion_type"], U)

    def test_ambiguous_exclusion_wording_preserved(self):
        rt, f, s = fixture(); add_gap(f, detail="还需其他有关文件")
        self.assertEqual(finding(run(rt, f, s))["conclusion_type"], U)

    def test_authenticity_and_performance_scope_pairs(self):
        for dep, kind, detail in (("authenticity", "authenticity_unverified", "真实任职未核验"),
                                  ("actual_performance", "future_performance_unverified", "后续履行未核验")):
            rt, f, s = fixture(); add_gap(f, dep, kind, detail=detail)
            self.assertEqual(finding(run(rt, f, s))["conclusion_type"], N)
            rt, f, s = fixture("actual_submission_check"); add_gap(f, dep, kind, detail=detail, affected=["C1"])
            self.assertEqual(finding(run(rt, f, s))["conclusion_type"], U)

    def test_text_observation_does_not_need_law(self):
        rt, f, s = fixture()
        c = deepcopy(f["decision_basis"]["completed_checks"][0])
        c.update(check_id="O1", check_kind="text_observation", claim_ids=[], legal_chunk_ids=[])
        f["decision_basis"]["completed_checks"].insert(0, c)
        g = run(rt, f, s)
        self.assertFalse(g["blocked"])
        self.assertEqual(finding(g)["conclusion_type"], N)
        self.assertTrue(finding(g)["review_handoff"]["text_observations"][0]["source_bound"])

    def test_only_observations_cannot_support_N_or_R(self):
        for label in (N, "requires_human_legal_review"):
            rt, f, s = fixture(); f["conclusion_type"] = label
            f["decision_basis"]["completed_checks"][0].update(check_kind="text_observation", legal_chunk_ids=[], claim_ids=[])
            self.assertEqual(finding(run(rt, f, s))["conclusion_type"], U)

    def test_observation_cannot_claim_legal_coverage(self):
        rt, f, s = fixture(); f["decision_basis"]["completed_checks"][0]["check_kind"] = "text_observation"
        self.assertTrue(run(rt, f, s)["blocked"])

    def test_observation_quote_still_must_be_exact(self):
        rt, f, s = fixture(); c = deepcopy(f["decision_basis"]["completed_checks"][0])
        c.update(check_id="O1", check_kind="text_observation", claim_ids=[], legal_chunk_ids=[], document_quote="不存在的原文")
        f["decision_basis"]["completed_checks"].append(c)
        self.assertTrue(run(rt, f, s)["blocked"])

    def test_each_required_claim_needs_own_bound_check(self):
        rt, f, s = fixture(); s["required_claims"].append({"claim_id": "C2", "description": "另一项专项合规核验", "required_dependencies": ["comparison_operand"]})
        rt["review_task_contract_v4"] = build_contract(rt, s)
        f["decision_basis"]["task_scope_sha256"] = rt["review_task_contract_v4"]["input_scope_sha256"]
        a = finding(run(rt, f, s))["nu_boundary_audit"]
        self.assertIn("C2", a["required_claims_not_grounded"])
        self.assertTrue(a["force_insufficient"])

    def test_no_law_supplement_or_unknown_law_cannot_release(self):
        for mode in ("no_law", "supplement", "invented"):
            rt, f, s = fixture(); add_gap(f)
            if mode == "no_law": rt["retrieved_legal_evidence"] = []
            if mode == "supplement": rt["retrieved_legal_evidence"][0].update(independent_legal_evidence=False, legal_evidence_eligibility="supplement_only", source_role="supplement")
            if mode == "invented": f["decision_basis"]["completed_checks"][0]["legal_chunk_ids"] = ["fake"]
            self.assertNotEqual(finding(run(rt, f, s))["conclusion_type"], N)

    def test_model_U_not_automatically_promoted(self):
        rt, f, s = fixture(); add_gap(f)
        f["conclusion_type"] = U
        f["decision_basis"]["answerability"] = "decisive_gap"
        self.assertEqual(finding(run(rt, f, s))["conclusion_type"], U)

    def test_actual_task_cannot_be_disguised_as_text(self):
        rt, f, s = fixture(); rt["project_context"]["review_question"] = "证明文件是否已提交？"
        s["question_verbatim"] = rt["project_context"]["review_question"]
        self.assertTrue(validate_spec(rt, s))
        with self.assertRaises(ValueError): build_contract(rt, s)

    def test_required_dependency_not_excludable(self):
        rt, f, s = fixture(); s["required_claims"][0]["required_dependencies"].append("submission_package_completeness")
        with self.assertRaises(ValueError): build_contract(rt, s)

    def test_boundaries_preserve_raw_and_input(self):
        rt, f, s = fixture(); add_gap(f)
        before = deepcopy((rt, f, s)); g = run(rt, f, s)
        self.assertEqual(before, (rt, f, s))
        self.assertEqual(g["raw_response"], {"findings": [f]})
        self.assertEqual(finding(g)["review_handoff"]["workflow_status"], "requires_human_second_review")
        self.assertFalse(finding(g)["nu_boundary_audit"]["legal_correctness_verified"])

    def test_protocol_missing_does_not_silently_upgrade_legacy(self):
        rt, f, s = fixture(); f["decision_basis"].pop("task_scope_sha256")
        f["decision_basis"]["completed_checks"][0].pop("check_kind")
        self.assertTrue(run(rt, f, s)["blocked"])

    def test_v4_opt_out_retains_v3_hard_gap_policy(self):
        from review_task_contract_v2 import build_contract as old_contract
        rt, f, s = fixture(); add_gap(f)
        rt["review_task_contract_v2"] = old_contract(rt)
        g = apply_gate({"findings": [f]}, rt, task_contract_v2=True)
        self.assertEqual(finding(g)["conclusion_type"], U)

    def test_missing_claim_or_invalid_target_is_blocked(self):
        for mode in ("claim", "target", "check_id"):
            rt, f, s = fixture()
            if mode == "claim": f["decision_basis"]["completed_checks"][0]["claim_ids"] = ["not_declared"]
            if mode == "target": f["decision_basis"]["review_target"] = "actual_conduct"
            if mode == "check_id": f["decision_basis"]["completed_checks"][0].pop("check_id")
            self.assertTrue(run(rt, f, s)["blocked"])

    def test_clause_design_mode_with_outside_submission(self):
        rt, f, s = fixture("clause_design"); add_gap(f)
        self.assertEqual(finding(run(rt, f, s))["conclusion_type"], N)

    def test_descriptive_stage_suffix_supported(self):
        rt, f, s = fixture(); rt["project_context"]["document_stage"] += ": 文本响应比对"
        self.assertFalse(validate_spec(rt, s))

    def test_new_core_dependency_cannot_silently_expand_locked_claim(self):
        rt, f, s = fixture(); s["required_claims"][0]["required_dependencies"].remove("comparison_operand")
        rt["review_task_contract_v4"] = build_contract(rt, s)
        f["decision_basis"]["task_scope_sha256"] = rt["review_task_contract_v4"]["input_scope_sha256"]
        add_gap(f, "comparison_operand", "comparison_value_missing", affected=["C1"])
        g = run(rt, f, s)
        self.assertTrue(g["blocked"])
        self.assertIn("gap_dependency_not_declared_for_affected_claim", finding(g)["nu_boundary_audit"]["schema_errors"])

    def test_case_identifier_does_not_change_policy(self):
        rt, f, s = fixture(); add_gap(f)
        a = run(rt, f, s)
        rt["issue_id"] = "ANOTHER-SYNTHETIC-ID"
        f["issue_id"] = rt["issue_id"]
        b = run(rt, f, s)
        self.assertEqual(finding(a)["nu_boundary_audit"], finding(b)["nu_boundary_audit"])

    def test_geographic_filter_cannot_be_bypassed_by_scope_exclusion(self):
        from test_scope_boundary_policy import local
        rt, f, s = fixture(); add_gap(f)
        rt["project_context"]["project_location"].update(province="天津市", city="天津市")
        law = local(); law["chunk_id"] = "law-1"
        rt["retrieved_legal_evidence"] = [law]
        rt["scope_boundary_experiment"] = {"version": "scope-boundary-v1", "geographic_filter": True, "task_boundary": False}
        rt["review_task_contract_v4"] = build_contract(rt, s)
        f["decision_basis"]["task_scope_sha256"] = rt["review_task_contract_v4"]["input_scope_sha256"]
        self.assertNotEqual(finding(run(rt, f, s))["conclusion_type"], N)

    def test_reversed_negation_and_wrong_page_are_not_repaired(self):
        for field, value in (("document_quote", "申请人不提供真实有效的证明文件"), ("document_locator", "第999页")):
            rt, f, s = fixture(); f["decision_basis"]["completed_checks"][0][field] = value
            self.assertTrue(run(rt, f, s)["blocked"])

    def test_unknown_claim_does_not_become_ordinary_U(self):
        rt, f, s = fixture(); add_gap(f, affected=["new-task"])
        g = run(rt, f, s)
        self.assertTrue(g["blocked"])
        self.assertEqual(finding(g)["review_handoff"]["processing_status"], "schema_blocked")

    def test_mocked_entry_constructs_scope_before_inference(self):
        import run_hierarchy_gated_llm_smoke as runner
        from scope_dependency_v4_prompt import build_prompt
        rt, f, s = fixture(); rt.pop("review_task_contract_v4")
        base = (Path(__file__).resolve().parents[1] / "prompts/system_prompt_final.md").read_text(encoding="utf-8")
        def request(key, prompt, runtime, **kwargs):
            self.assertEqual(prompt, build_prompt(base))
            self.assertEqual(runtime["review_task_contract_v4"], build_contract(runtime, s))
            self.assertEqual(kwargs["reasoning_effort"], "low")
            self.assertNotIn("reference_answer", runtime)
            return {"parsed": {"findings": [f]}}
        with patch.object(runner, "model_request", side_effect=request) as mock:
            _, g = runner.run_final_reasoning(api_key="synthetic-only", prompt=base, runtime_input=rt, max_tokens=100, scope_dependency_v4=s)
        self.assertEqual(mock.call_count, 1)
        self.assertFalse(g["blocked"])


if __name__ == "__main__":
    unittest.main()
