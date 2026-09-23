"""Finite synthetic guards; no claim of legal accuracy or semantic completeness."""
from copy import deepcopy
import unittest

from test_scope_dependency_v41 import fixture, add_gap, finding
from test_nu_boundary_policy import N, U
from llm_abstention_gate import apply_gate
from scope_dependency_v41 import build_contract
from scope_dependency_v41_schema import SCHEMA, VERSION, render_schema
from scope_routing_v412 import PERFORMANCE_ALIASES


def run(rt, f, s, a=True, b=True):
    return apply_gate({"findings": [f]}, rt, scope_dependency_v41=s,
                      material_aliases_v412=a, processing_presentation_v412=b)


class RoutingGuards(unittest.TestCase):
    def test_aliases_need_all_scope_conditions(self):
        for word in PERFORMANCE_ALIASES + ("后续履行", "实际履行", "实际到岗", "履约"):
            with self.subTest(word=word):
                rt, f, s = fixture(); add_gap(f, "actual_performance", detail=f"承诺在{word}是否持续成立未核验。")
                result = run(rt, f, s)
                self.assertEqual(result["valid_legal_verdicts"], [N])
                r = finding(result)["nu_boundary_audit"]["gap_resolutions"][0]
                self.assertEqual(r["resolution"], "out_of_scope_item")
                self.assertTrue(r["material_recognition"]["matches"])

    def test_current_promise_omissions_never_excluded(self):
        for text in ("承诺文字未涵盖合同履行阶段的任职限制。", "承诺文字未说明合同履行期间是否仍不任其他项目。",
                     "未明确合同履行期间的承诺期限。", "合同履行阶段的关键日期未提供。"):
            with self.subTest(text=text):
                rt, f, s = fixture(); add_gap(f, "actual_performance", detail=text)
                self.assertTrue(run(rt, f, s)["scope_review_required"])
                self.assertFalse(run(rt, f, s)["valid_legal_verdicts"])

    def test_mixed_material_preserved(self):
        for text in ("合同履行阶段是否持续成立及补遗未核验。", "真实性与合同履行期间表现均未核验。",
                     "合同履行阶段的项目金额未提供。"):
            rt, f, s = fixture(); add_gap(f, "actual_performance", detail=text)
            original = deepcopy(f); result = run(rt, f, s)
            self.assertTrue(result["scope_review_required"])
            self.assertEqual(f, original)
            self.assertEqual(len(result["raw_response"]["findings"][0]["decision_basis"]["gaps"]), 1)

    def test_reason_does_not_supply_detail(self):
        rt, f, s = fixture(); add_gap(f, "actual_performance", detail="资料未核验。", reason="只是未来合同履行阶段。")
        self.assertTrue(run(rt, f, s)["scope_review_required"])

    def test_actual_conduct_task_keeps_decisive_U(self):
        rt, f, s = fixture("actual_submission_check")
        q = "项目经理是否实际到岗履行？"
        s.update(question_verbatim=q, review_mode="actual_conduct_check")
        rt["project_context"].update(review_question=q, document_stage="actual_conduct")
        rt["review_task_contract_v41"] = build_contract(rt, s)
        f["decision_basis"].update(review_question=q, review_target="actual_conduct", task_scope_sha256=rt["review_task_contract_v41"]["input_scope_sha256"])
        add_gap(f, "actual_performance", "decisive_for_claim", detail="合同履行期间实际到岗情况未核验。")
        self.assertEqual(run(rt, f, s)["valid_legal_verdicts"], [U])

    def test_unapproved_exclusion_held(self):
        rt, f, s = fixture(); s["excluded_dependencies"].remove("actual_performance")
        rt["review_task_contract_v41"] = build_contract(rt, s)
        f["decision_basis"]["task_scope_sha256"] = rt["review_task_contract_v41"]["input_scope_sha256"]
        add_gap(f, "actual_performance", detail="合同履行阶段未核验。")
        self.assertTrue(run(rt, f, s)["scope_review_required"])

    def test_conflicting_flags_held(self):
        for kwargs in ({"blocks_current_question": True}, {"affected_claim_ids": ["C1"]}, {"dependency_trigger": "generic_unverified_possibility"}):
            rt, f, s = fixture(); add_gap(f, "actual_performance", detail="合同履行阶段未核验。", **kwargs)
            self.assertTrue(run(rt, f, s)["scope_review_required"])

    def test_core_dependencies_keep_U(self):
        for dep in ("applicable_rule", "current_clause_context", "regulatory_applicability", "comparison_operand", "readability"):
            rt, f, s = fixture(); add_gap(f, dep, "decisive_for_claim")
            self.assertEqual(run(rt, f, s)["valid_legal_verdicts"], [U])

    def test_affirmative_risk_is_not_promoted_to_N(self):
        rt, f, s = fixture(); add_gap(f, "actual_performance", detail="合同履行阶段未核验。")
        f["conclusion_type"] = "requires_human_legal_review"
        self.assertNotIn(N, run(rt, f, s)["valid_legal_verdicts"])

    def test_binding_failure_stays_technical(self):
        for target in ("quote", "hash", "field"):
            rt, f, s = fixture(); add_gap(f, "actual_performance", detail="合同履行阶段未核验。")
            if target == "quote": f["decision_basis"]["completed_checks"][0]["document_quote"] = "不存在的原文"
            if target == "hash": f["decision_basis"]["task_scope_sha256"] = "forged"
            if target == "field": f["decision_basis"].pop("review_target")
            result = run(rt, f, s)
            self.assertTrue(result["technical_blocked"])
            self.assertFalse(result["valid_legal_verdicts"])

    def test_no_json_cannot_create_verdict(self):
        rt, _, s = fixture()
        r = apply_gate("not JSON", rt, scope_dependency_v41=s, material_aliases_v412=True, processing_presentation_v412=True)
        self.assertFalse(r["valid_legal_verdicts"])

    def test_requires_explicit_v41(self):
        rt, f, _ = fixture()
        with self.assertRaises(ValueError): apply_gate({"findings": [f]}, rt, material_aliases_v412=True)

    def test_schema_and_source_are_not_modified(self):
        schema = render_schema(); rt, f, s = fixture(); before = deepcopy((rt, f, s))
        add_gap(f, "actual_performance", detail="合同履行阶段未核验。")
        original = deepcopy(f); run(rt, f, s)
        self.assertEqual(rt, before[0]); self.assertEqual(s, before[2]); self.assertEqual(f, original)
        self.assertEqual(render_schema(), schema)
        self.assertEqual(VERSION, "scope-dependency-v4.1.1-candidate")


class PresentationGuards(unittest.TestCase):
    def test_presentation_only_does_not_change_decision_or_gap_route(self):
        rt, f, s = fixture(); add_gap(f, "actual_performance", detail="合同履行阶段未核验。")
        old, new = run(rt, f, s, False, False), run(rt, f, s, False, True)
        self.assertEqual(old["valid_legal_verdicts"], new["valid_legal_verdicts"])
        self.assertEqual(finding(old)["nu_boundary_audit"], finding(new)["nu_boundary_audit"])
        self.assertEqual(old["raw_response"], new["raw_response"])
        rec = finding(new)["assistant_recommendation"]
        self.assertNotIn("决定性缺口", rec["substantive_conclusion"])
        self.assertNotIn("请补充并核验", rec["recommended_handling"])
        self.assertIsNone(finding(new)["review_handoff"]["decision_status"])

    def test_real_gap_and_scope_hold_kept_separate(self):
        rt, f, s = fixture(); add_gap(f, "current_clause_context", "decisive_for_claim")
        add_gap(f, "actual_performance", detail="未知资料未核验。")
        new = run(rt, f, s); rec = finding(new)["assistant_recommendation"]
        self.assertIn("另有已列阻断缺口", rec["substantive_conclusion"])
        self.assertIn("当前条款上下文", rec["recommended_handling"])
        self.assertIn("关系待确认事项", rec["recommended_handling"])
        self.assertFalse(new["valid_legal_verdicts"])

    def test_views_and_summary_do_not_count_scope_U(self):
        from export_review_excel import flatten_record
        rt, f, s = fixture(); add_gap(f, "other_undetermined", "undetermined")
        new = run(rt, f, s)
        summary = new["response"]["project_summary"]
        self.assertEqual(summary["valid_legal_verdict_count"], 0)
        self.assertEqual(len(summary["processing_holds"]), 1)
        table = new["response"]["review_table"][0]
        self.assertEqual(table["risk_category"], "scope_relationship_unresolved")
        self.assertNotIn("决定性缺口", new["response"]["table_markdown"])
        for include in (False, True):
            row = list(flatten_record({"gate_result": new, "runtime_input": rt}, include_handoff=include))[0]
            self.assertIn("scope_review_required", row[3])
            self.assertEqual(row[4], "scope_relationship_unresolved")
            self.assertNotIn("决定性缺口", row[7])

    def test_valid_U_presentation_remains_unchanged(self):
        rt, f, s = fixture(); add_gap(f, "comparison_operand", "decisive_for_claim")
        old, new = run(rt, f, s, False, False), run(rt, f, s, False, True)
        self.assertEqual(finding(old), finding(new))
        self.assertEqual(new["valid_legal_verdicts"], [U])

    def test_finite_factorial(self):
        rt, f, s = fixture(); add_gap(f, "actual_performance", detail="合同履行阶段未核验。")
        results = [run(rt, f, s, a, b) for a, b in ((False, False), (True, False), (False, True), (True, True))]
        self.assertEqual([r["valid_legal_verdicts"] for r in results], [[], [N], [], [N]])
        self.assertTrue(all(r["raw_response"] == results[0]["raw_response"] for r in results))


if __name__ == "__main__": unittest.main()
