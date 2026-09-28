"""Offline, synthetic guards for the bundle-only legal-effect protocol."""

from __future__ import annotations

from copy import deepcopy
import unittest

from bundle_legal_review_v1 import (
    CLAIM_ID, VERSION, assess_protocol, build_task_contract, prompt_addendum,
    selected_chunk_ids,
)


EXCERPT = (
    "招标人应书面通知所有取得招标文件者；修改影响投标编制且距原截止不足15日的，"
    "应顺延投标截止时间。"
)
LAW_1 = "law-23"
LAW_2 = "reg-21"


def task(requires_operand=False):
    label = {"issue_id": "SYN-TENDER-1", "review_task_kind": "tender_clause_legality",
             "document_id": "DOC-1", "document_location": "p2-b3",
             "document_excerpt": EXCERPT, "bundle_evidence": {"documents_received": ["DOC-1"]},
             "requires_comparison_operand": requires_operand}
    contract = build_task_contract(label)
    runtime = {
        "review_task_contract_v1": contract,
        "contract_evidence": {"document_excerpt": EXCERPT},
        "hierarchy_retrieval_audit": {"levels": [
            {"level": "Level 1", "level_state": "relevant_but_inconclusive",
             "phases": [{"decision": {"selected_chunk_ids": [LAW_1]}}]},
            {"level": "Level 2", "level_state": "no_usable_violation_found",
             "phases": [{"decision": {"selected_chunk_ids": [LAW_2]}}]},
        ]},
    }
    return contract, runtime


def finding(contract):
    elements = ("actor", "trigger_and_scope", "required_conduct",
                "timing_or_threshold", "exception_or_cure", "obligation_stage")
    analysis = {
        "protocol_version": VERSION, "task_contract_sha256": contract["contract_sha256"],
        "claim_id": CLAIM_ID, "applied_legal_chunk_ids": [LAW_1, LAW_2],
        "normative_elements": {key: "supported or not expressly regulated" for key in elements},
        "element_comparisons": [
            {"element": key, "relation": "aligned", "legal_chunk_id": LAW_1,
             "document_quote": "", "explanation": "the clause preserves the reviewed duty"}
            for key in elements
        ],
        "governing_rule": "law-23: the governing law requires timely written notice to recipients.",
        "normative_relation": "implements_or_clarifies",
        "implementation_effect": "reg-21: the implementing rule provides extension where a late change affects preparation.",
        "document_rule": "The clause requires notice and extension when the stated conditions hold.",
        "legal_effect_relation": "aligned_with_reviewed_rule",
        "effect_comparison": "The governing protection remains; extension preserves preparation time.",
        "contrary_document_quote": "", "gaps": [],
    }
    return {"conclusion_type": "no_supported_issue_found_within_review_scope",
            "legal_element_coverage": {
                "subject": "supported", "conduct_or_condition": "supported",
                "jurisdiction_and_scope": "supported", "legal_consequence": "supported",
            },
            "legal_evidence": [
                {"chunk_id": LAW_1, "independent_legal_evidence": True},
                {"chunk_id": LAW_2, "independent_legal_evidence": True},
            ],
            "professional_review": analysis}


def gated(row):
    return {"status": "passed", "blocked": False, "actions": [],
            "raw_response": {"findings": [deepcopy(row)]},
            "response": {"findings": [row]}}


def admitted(row):
    return row.get("independent_legal_evidence") is True


class BundleLegalReviewTests(unittest.TestCase):
    def setUp(self):
        self.contract, self.runtime = task()
        self.row = finding(self.contract)

    def evaluate(self, row=None, runtime=None):
        return assess_protocol(gated(row or self.row), runtime or self.runtime, admitted)

    def test_task_is_locked_before_inference_and_prompt_uses_old_taxonomy(self):
        self.assertEqual("clause_design", self.contract["review_mode"])
        self.assertEqual([CLAIM_ID], [x["claim_id"] for x in self.contract["required_claims"]])
        self.assertNotIn("comparison_operand", self.contract["required_claims"][0]["required_dependencies"])
        self.assertIn("applicable_rule", prompt_addendum())
        self.assertIn("outside_locked_scope", prompt_addendum())

    def test_implementing_detail_supports_bounded_no_issue(self):
        result = self.evaluate()
        self.assertFalse(result["blocked"])
        self.assertEqual("valid", result["professional_review_v1"]["status"])
        self.assertFalse(result["professional_review_v1"]["legal_semantics_verified"])

    def test_real_cascade_decision_shape_is_read(self):
        levels = self.runtime["hierarchy_retrieval_audit"]["levels"]
        self.assertEqual({LAW_1}, selected_chunk_ids(levels[0]))
        self.assertEqual({LAW_2}, selected_chunk_ids(levels[1]))
        self.assertEqual({LAW_2}, selected_chunk_ids(
            {"phases": [{"selected_chunk_ids": [LAW_2]}]}
        ))

    def test_implementing_article_cannot_be_silently_omitted_from_no_issue(self):
        row = deepcopy(self.row)
        row["professional_review"]["applied_legal_chunk_ids"] = [LAW_1]
        row["legal_evidence"] = [row["legal_evidence"][0]]
        result = self.evaluate(row)
        self.assertTrue(result["blocked"])
        self.assertIn("cross_level_implementing_article_omitted", result["professional_review_v1"]["errors"])

    def test_governing_article_cannot_be_silently_omitted_from_no_issue(self):
        row = deepcopy(self.row)
        row["professional_review"]["applied_legal_chunk_ids"] = [LAW_2]
        row["legal_evidence"] = [row["legal_evidence"][1]]
        result = self.evaluate(row)
        self.assertTrue(result["blocked"])
        self.assertIn("cross_level_governing_article_omitted", result["professional_review_v1"]["errors"])

    def test_actual_performance_followup_does_not_make_u(self):
        row = deepcopy(self.row)
        row["professional_review"]["gaps"] = [{
            "gap_id": "G1", "kind": "future_performance_unverified",
            "dependency_key": "actual_performance", "task_relation": "outside_locked_scope",
            "affected_claim_ids": [], "detail": "实际履行记录未提供",
            "reason": "this task reviews wording only",
            "counterfactual_impact": "does not change the clause comparison",
            "dependency_trigger": "explicit_scope_exclusion", "next_step": "check actual records separately",
        }]
        result = self.evaluate(row)
        self.assertFalse(result["blocked"])
        self.assertEqual(["G1"], result["professional_review_v1"]["gap_groups"]["out_of_scope_item"])

    def test_risk_without_a_contrary_element_is_held(self):
        row = deepcopy(self.row)
        row["conclusion_type"] = "requires_human_legal_review"
        row["professional_review"].update(
            legal_effect_relation="concrete_contrary_effect",
            contrary_document_quote="应顺延投标截止时间",
        )
        result = self.evaluate(row)
        self.assertTrue(result["blocked"])
        self.assertIn("risk_without_contrary_legal_element", result["professional_review_v1"]["errors"])

    def test_concrete_opposite_clause_can_remain_a_risk_candidate(self):
        opposite_excerpt = "招标人修改招标文件后，即使距截止不足15日且影响投标编制，也不予顺延投标截止时间。"
        label = {"issue_id": "SYN-TENDER-2", "review_task_kind": "tender_clause_legality",
                 "document_id": "DOC-2", "document_location": "p3-b1",
                 "document_excerpt": opposite_excerpt,
                 "bundle_evidence": {"documents_received": ["DOC-2"]}}
        contract = build_task_contract(label)
        runtime = deepcopy(self.runtime)
        runtime["review_task_contract_v1"] = contract
        runtime["contract_evidence"]["document_excerpt"] = opposite_excerpt
        row = finding(contract)
        row["conclusion_type"] = "requires_human_legal_review"
        row["fact_law_comparison"] = {
            "supporting_chunk_id": LAW_2,
            "difference_summary": "法规要求在所述条件下顺延；条款明示不顺延。",
        }
        row["professional_review"].update(
            legal_effect_relation="concrete_contrary_effect",
            contrary_document_quote="不予顺延投标截止时间",
        )
        row["professional_review"]["element_comparisons"][3].update(
            relation="concrete_contrary", legal_chunk_id=LAW_2,
            document_quote="不予顺延投标截止时间",
        )
        result = self.evaluate(row, runtime)
        self.assertFalse(result["blocked"])
        self.assertFalse(result["professional_review_v1"]["legal_semantics_verified"])

    def test_missing_raw_coverage_is_a_processing_hold_not_legal_u(self):
        row = deepcopy(self.row)
        row.pop("legal_element_coverage")
        result = self.evaluate(row)
        self.assertTrue(result["blocked"])
        self.assertIn("raw_legal_element_coverage_incomplete_not_legal_u", result["professional_review_v1"]["errors"])

    def test_no_issue_cannot_hide_unresolved_core_coverage(self):
        row = deepcopy(self.row)
        row["legal_element_coverage"]["conduct_or_condition"] = "missing"
        result = self.evaluate(row)
        self.assertTrue(result["blocked"])
        self.assertIn("no_issue_with_unresolved_core_coverage", result["professional_review_v1"]["errors"])

    def test_no_issue_needs_at_least_one_material_element_compared(self):
        row = deepcopy(self.row)
        for item in row["professional_review"]["element_comparisons"]:
            item["relation"] = "not_stated_nonexclusive"
        result = self.evaluate(row)
        self.assertTrue(result["blocked"])
        self.assertIn("no_issue_without_material_element_comparison", result["professional_review_v1"]["errors"])

    def test_u_requires_typed_decisive_gap_and_unresolved_element(self):
        self.contract, self.runtime = task(requires_operand=True)
        self.row = finding(self.contract)
        row = deepcopy(self.row)
        row["conclusion_type"] = "insufficient_information_needs_human_confirm"
        row["professional_review"]["legal_effect_relation"] = "decisive_gap"
        row["professional_review"]["element_comparisons"][3]["relation"] = "unresolved_decisive"
        row["professional_review"]["gaps"] = [{
            "gap_id": "G1", "kind": "comparison_value_missing",
            "dependency_key": "comparison_operand", "task_relation": "decisive_for_claim",
            "affected_claim_ids": [CLAIM_ID], "detail": "决定性截止日期未提供",
            "reason": "the task requires an actual date comparison",
            "counterfactual_impact": "cannot compare the deadline with the legal threshold",
            "dependency_trigger": "locked_requirement", "next_step": "obtain the date record",
        }]
        result = self.evaluate(row)
        self.assertFalse(result["blocked"])
        self.assertEqual(["comparison_operand"], result["professional_review_v1"]["u_cause_codes"])

    def test_unlocked_comparison_operand_cannot_make_legal_u(self):
        row = deepcopy(self.row)
        row["conclusion_type"] = "insufficient_information_needs_human_confirm"
        row["professional_review"]["legal_effect_relation"] = "decisive_gap"
        row["professional_review"]["element_comparisons"][3]["relation"] = "unresolved_decisive"
        row["professional_review"]["gaps"] = [{
            "gap_id": "G1", "kind": "comparison_value_missing",
            "dependency_key": "comparison_operand", "task_relation": "decisive_for_claim",
            "affected_claim_ids": [CLAIM_ID], "detail": "未来修改的日期未提供",
            "reason": "a future change might occur", "counterfactual_impact": "could alter a future review",
            "dependency_trigger": "locked_requirement", "next_step": "ask for a future record",
        }]
        result = self.evaluate(row)
        self.assertTrue(result["blocked"])
        self.assertIn("gap_not_bound_to_required_dependency", result["professional_review_v1"]["errors"])

    def test_modified_task_contract_is_processing_hold(self):
        self.runtime["review_task_contract_v1"]["required_claims"][0]["required_dependencies"].append("comparison_operand")
        result = self.evaluate()
        self.assertTrue(result["blocked"])
        self.assertIn("task_contract_digest_mismatch", result["professional_review_v1"]["errors"])

    def test_generic_u_without_decisive_gap_is_a_protocol_hold(self):
        row = deepcopy(self.row)
        row["conclusion_type"] = "insufficient_information_needs_human_confirm"
        row["professional_review"]["legal_effect_relation"] = "decisive_gap"
        result = self.evaluate(row)
        self.assertTrue(result["blocked"])
        self.assertIn("u_without_typed_decisive_gap", result["professional_review_v1"]["errors"])

    def test_wrong_geographic_law_cannot_be_applied(self):
        row = deepcopy(self.row)
        row["professional_review"]["applied_legal_chunk_ids"] = [LAW_1, "local-other-province"]
        row["legal_evidence"].append({"chunk_id": "local-other-province", "independent_legal_evidence": False})
        result = self.evaluate(row)
        self.assertTrue(result["blocked"])
        self.assertIn("applied_law_not_admitted_or_applicable", result["professional_review_v1"]["errors"])

    def test_transport_or_schema_hold_does_not_become_legal_u(self):
        raw = gated(self.row)
        raw["status"] = "blocked"
        raw["blocked"] = True
        result = assess_protocol(raw, self.runtime, admitted)
        self.assertEqual("upstream_processing_hold", result["professional_review_v1"]["status"])
        self.assertEqual([], result["professional_review_v1"]["u_cause_codes"])

    def test_unresolved_task_relation_is_not_legal_u(self):
        row = deepcopy(self.row)
        row["conclusion_type"] = "insufficient_information_needs_human_confirm"
        row["professional_review"]["legal_effect_relation"] = "decisive_gap"
        row["professional_review"]["gaps"] = [{
            "gap_id": "G1", "kind": "material_type_undetermined",
            "dependency_key": "other_undetermined", "task_relation": "undetermined",
            "affected_claim_ids": [CLAIM_ID], "detail": "unclear material type",
            "reason": "task relationship not established",
            "counterfactual_impact": "cannot know whether current claim changes",
            "dependency_trigger": "undetermined", "next_step": "clarify review scope",
        }]
        result = self.evaluate(row)
        self.assertTrue(result["blocked"])
        self.assertIn("scope_relation_pending_not_legal_u", result["professional_review_v1"]["errors"])


if __name__ == "__main__":
    unittest.main()
