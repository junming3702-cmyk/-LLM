"""New gate semantics are opt-in for caller-locked QX/bundle tasks."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
from llm_abstention_gate import apply_gate  # noqa: E402
from test_post_llm_gate_v2 import _finding, _runtime  # noqa: E402


def runtime():
    value = _runtime()
    value["gate_protocol_version"] = "task-aware-v1"
    value["review_task_contract_v2"] = {
        "question_verbatim": "当前条款是否满足已锁定的提交要求？",
        "declared_task_type": "clause_design",
        "required_for_legal_conclusion": ["independent_applicable_rule", "grounded_comparison", "question_decisive_facts"],
    }
    return value


class TaskAwareGateTests(unittest.TestCase):
    def test_invalid_coverage_is_processing_not_legal_u(self):
        value = runtime()
        raw = _finding(coverage={"subject": "not_a_state"})
        result = apply_gate({"findings": [raw]}, value)
        self.assertTrue(result["blocked"])
        self.assertEqual("schema_failure", result["failure_class"])
        self.assertEqual([], result["response"]["findings"])
        self.assertIsNone(result["response"]["review_table"][0]["conclusion"]["conclusion_type"])

    def test_unrecognized_conclusion_is_processing_not_legal_u(self):
        result = apply_gate({"findings": [_finding(conclusion="unknown-code")]}, runtime())
        self.assertTrue(result["blocked"])
        self.assertEqual("schema_failure", result["failure_class"])

    def test_parser_failure_does_not_assert_material_absence(self):
        value = runtime()
        value["contract_evidence"]["extraction_status"] = "incomplete"
        result = apply_gate({"findings": [_finding()]}, value)
        self.assertTrue(result["blocked"])
        self.assertEqual("source_processing_failure", result["failure_class"])
        self.assertFalse(result["legal_conclusion_available"])

    def test_unsupported_risk_is_hold_not_automatic_u_or_n(self):
        value = runtime()
        raw = _finding(relation="requirement_not_shown")
        result = apply_gate({"findings": [raw]}, value)
        self.assertTrue(result["blocked"])
        self.assertEqual("claim_support_failure", result["failure_class"])
        self.assertEqual(raw["conclusion_type"], result["raw_response"]["findings"][0]["conclusion_type"])

    def test_u_without_attested_decisive_gap_is_hold(self):
        value = runtime()
        raw = _finding(conclusion="insufficient_information", category="missing_or_insufficient_evidence",
                       relation="unresolved")
        result = apply_gate({"findings": [raw]}, value)
        self.assertTrue(result["blocked"])
        self.assertEqual("unverified_decisive_gap", result["failure_class"])

    def test_untransmitted_excerpt_cannot_be_called_legal_u(self):
        value = runtime()
        raw = _finding(conclusion="insufficient_information", category="missing_or_insufficient_evidence",
                       relation="unresolved")
        raw["legal_u_basis"] = {
            "claim_id": value["issue_id"],
            "question_verbatim": value["review_task_contract_v2"]["question_verbatim"],
            "dependency_key": "question_decisive_facts", "missing_material": "同包附件",
            "material_status": "not_in_current_input", "reason": "尚未传给推理端",
            "counterfactual_impact": "回填后可核验内容", "next_check": "读取原包",
        }
        result = apply_gate({"findings": [raw]}, value)
        self.assertTrue(result["blocked"])
        self.assertIn("source_processing_gap_not_legal_u", result["actions"][-1])

    def test_attested_question_bound_gap_can_retain_bounded_u(self):
        value = runtime()
        raw = _finding(conclusion="insufficient_information", category="missing_or_insufficient_evidence",
                       relation="unresolved")
        basis = {"claim_id": value["issue_id"],
                 "question_verbatim": value["review_task_contract_v2"]["question_verbatim"],
                 "dependency_key": "question_decisive_facts", "missing_material": "当前条款决定性数值",
                 "material_status": "decisive_fact_unknown", "reason": "本题明确要求数值比较",
                 "counterfactual_impact": "补值后才能比较法定阈值", "next_check": "定位数值"}
        raw["legal_u_basis"] = basis
        value["task_gap_audit"] = [{"validated": True, "issue_id": value["issue_id"],
                                    "record_origin": "deterministic_input_audit",
                                    "dependency_key": basis["dependency_key"],
                                    "material_status": basis["material_status"],
                                    "missing_material": basis["missing_material"],
                                    "review_question": basis["question_verbatim"],
                                    "audit_locator": "input-inventory-log:line-7"}]
        result = apply_gate({"findings": [raw]}, value)
        self.assertFalse(result["blocked"])
        self.assertEqual("insufficient_information_needs_human_confirm",
                         result["response"]["findings"][0]["conclusion_type"])
        value["task_gap_audit"][0]["record_origin"] = "model_self_report"
        rejected = apply_gate({"findings": [raw]}, value)
        self.assertTrue(rejected["blocked"])
        self.assertIn("decisive_gap_not_attested_by_runtime", rejected["actions"][-1])


if __name__ == "__main__":
    unittest.main()
