"""Offline U30-style guard: visible body and unreadable chart stay separate."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from task_subconclusion_v1 import apply_task_gate, build_contract  # noqa: E402


def fixture():
    contract = build_contract("SYN-U30", "document_visibility", [
        {"claim_id": "body", "claim_type": "narrative_visibility"},
        {"claim_id": "chart", "claim_type": "chart_visibility"},
    ], [
        {"source_id": "TECH-BODY", "document_id": "TECH", "locator": "p186-b6",
         "source_kind": "text", "text": "施工总进度计划说明：先完成基础工程，再开展主体工程。"},
        {"source_id": "TECH-INDEX", "document_id": "TECH", "locator": "p2-b1",
         "source_kind": "text", "text": "目录：施工总进度计划和进度计划保证措施。"},
    ])
    raw = {"issue_id": "SYN-U30", "contract_sha256": contract["contract_sha256"],
           "subconclusions": [
               {"claim_id": "body", "status": "observed", "source_refs": [
                   {"source_id": "TECH-BODY", "locator": "p186-b6", "quote": "施工总进度计划说明"}],
                "explanation": "Provided body contains progress-plan narrative."},
               {"claim_id": "chart", "status": "pending_verification", "source_refs": [],
                "explanation": "Chart page has not been parsed; index alone does not verify chart."},
           ]}
    return contract, raw


class TaskSubconclusionTests(unittest.TestCase):
    def test_body_visible_chart_pending_is_partial_not_n_or_legal_u(self):
        contract, raw = fixture()
        result = apply_task_gate(raw, contract)
        self.assertFalse(result["blocked"])
        self.assertEqual("partially_observed_requires_review", result["response"]["task_completion"])
        self.assertEqual(["chart"], result["response"]["pending_claim_ids"])
        self.assertIsNone(result["response"]["legal_conclusion_type"])

    def test_index_cannot_falsely_clear_chart(self):
        contract, raw = fixture()
        raw["subconclusions"][1] = {"claim_id": "chart", "status": "observed",
                                    "source_refs": [{"source_id": "TECH-INDEX", "locator": "p2-b1",
                                                     "quote": "施工总进度计划"}],
                                    "explanation": "Index names a chart."}
        result = apply_task_gate(raw, contract)
        self.assertTrue(result["blocked"])
        self.assertIn("subconclusions[1].chart_not_verified_by_chart_source", result["errors"])

    def test_missing_chart_cannot_be_silently_dropped(self):
        contract, raw = fixture()
        raw["subconclusions"].pop()
        result = apply_task_gate(raw, contract)
        self.assertTrue(result["blocked"])
        self.assertIn("required_subconclusions_incomplete", result["errors"])

    def test_fabricated_body_quote_is_blocked(self):
        contract, raw = fixture()
        raw["subconclusions"][0]["source_refs"][0]["quote"] = "已完整符合进度图表要求"
        result = apply_task_gate(raw, contract)
        self.assertTrue(result["blocked"])
        self.assertIn("subconclusions[0].source_quote_not_in_input", result["errors"])

    def test_transport_and_legal_verdict_injection_are_blocked(self):
        contract, raw = fixture()
        self.assertTrue(apply_task_gate(raw, contract, finish_reason="length")["blocked"])
        copied = deepcopy(raw)
        copied["conclusion_type"] = "no_supported_issue_found_within_review_scope"
        self.assertTrue(apply_task_gate(copied, contract)["blocked"])


if __name__ == "__main__":
    unittest.main()
