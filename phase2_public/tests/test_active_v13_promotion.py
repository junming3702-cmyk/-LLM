"""Guards for the active Phase-2 prompt, source policy and task routes."""

from __future__ import annotations

import inspect
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bundle_legal_review_v1 import prompt_addendum as bundle_prompt  # noqa: E402
from law_source_version_v1 import OLD_SOURCE_ID, active_versioned_corpus  # noqa: E402
from run_hierarchy_gated_llm_smoke import run_case, run_final_reasoning  # noqa: E402


class ActiveSourcePolicyTests(unittest.TestCase):
    def setUp(self):
        self.rows = [{"source_id": OLD_SOURCE_ID, "chunk_id": "0708ceb43ccf18c323b2"},
                     {"source_id": OLD_SOURCE_ID, "chunk_id": "b43221a19bc5c4996abc"},
                     {"source_id": OLD_SOURCE_ID, "chunk_id": "2f1c6fbdaa4e8489b42b"},
                     {"source_id": "level2", "chunk_id": "article16"}]

    def test_unknown_date_quarantines_instead_of_serving_stale_law(self):
        active, audit = active_versioned_corpus(self.rows, as_of_date=None)
        self.assertEqual(["article16"], [row["chunk_id"] for row in active])
        self.assertEqual("stale_source_quarantined_no_verified_replacement", audit["status"])

    def test_2022_admits_only_targeted_checked_articles(self):
        active, audit = active_versioned_corpus(self.rows, as_of_date="2022-06-21")
        self.assertEqual("targeted_2022_excerpts_admitted", audit["status"])
        self.assertEqual(3, len(audit["corrected_chunk_ids"]))
        self.assertFalse(any(row.get("source_id") == OLD_SOURCE_ID for row in active))

    def test_other_date_quarantines_without_2022_replacement(self):
        active, audit = active_versioned_corpus(self.rows, as_of_date="2026-09-28")
        self.assertEqual(1, len(active))
        self.assertEqual([], audit["corrected_chunk_ids"])


class ActivePromptAndRouteTests(unittest.TestCase):
    def test_active_prompts_and_answer_free_expansion_are_default(self):
        base = (ROOT / "prompts" / "system_prompt_final.md").read_text(encoding="utf-8")
        self.assertIn("**状态**：`ACTIVE`", base)
        self.assertNotIn("CANDIDATE / NOT ACTIVE", base)
        self.assertIn("条件—法律效果", base)
        self.assertIn("T → E", bundle_prompt())
        self.assertIn("legal_effect_relation", bundle_prompt())
        self.assertTrue(inspect.signature(run_case).parameters["duration_query_expansion"].default)

    def test_bounded_two_source_text_task_never_calls_legal_llm(self):
        runtime = {
            "issue_id": "SYN-TEXT-01",
            "review_task_contract_v2": {
                "declared_task_type": "document_response",
                "question_verbatim": "技术标建设规模文字是否回应招标范围概况？",
            },
            "contract_evidence": {"document_excerpt":
                "[TENDER-p1-b1]\n建设规模：宿舍楼100平方米。\n"
                "[TECH-p2-b2]\n建设规模：教学楼100平方米。"},
        }
        with patch("run_hierarchy_gated_llm_smoke.model_request") as llm:
            response, result = run_final_reasoning(
                api_key="unused", prompt="legal", runtime_input=runtime, max_tokens=1024)
        llm.assert_not_called()
        self.assertEqual("none", response["model_requested"])
        self.assertEqual("observed_difference_requires_review", result["response"]["task_completion"])
        self.assertFalse(result["legal_conclusion_available"])
        self.assertEqual("different", result["response"]["observations"][0]["status"])
        self.assertEqual("matched", result["response"]["observations"][1]["status"])

    def test_v2_legal_task_receives_independent_gap_audit_and_prompt(self):
        runtime = {
            "run_id": "synthetic", "project_id": "synthetic", "issue_id": "SYN-LEGAL-01",
            "review_task_contract_v2": {
                "declared_task_type": "clause_design",
                "question_verbatim": "当前条款规定何种条件和法律效果？",
                "required_for_legal_conclusion": ["independent_applicable_rule"],
            },
            "contract_evidence": {"document_id": "synthetic", "document_location": "p1",
                                  "document_excerpt": "条件发生时，应通知投标人。"},
            "retrieved_legal_evidence": [], "hierarchy_retrieval_audit": {},
        }
        with patch("run_hierarchy_gated_llm_smoke.model_request",
                   return_value={"ok": False, "selected_text": "", "parsed": None}) as llm:
            _, gate = run_final_reasoning(api_key="unused", prompt="base",
                                          runtime_input=runtime, max_tokens=1024)
        self.assertEqual("task-aware-v1", runtime["gate_protocol_version"])
        self.assertEqual("task-gap-audit-v1", runtime["task_gap_audit_version"])
        self.assertFalse(runtime["task_gap_audit"][0]["validated"])
        self.assertIn("## Task-aware legal-U and independent gap ledger", llm.call_args.args[1])
        self.assertEqual("transport_failure", gate["failure_class"])

    def test_mixed_contract_versions_are_protocol_hold_not_legal_u(self):
        runtime = {
            "issue_id": "SYN-MIXED-01", "review_task_contract_v1": {"task_kind": "clause_design"},
            "review_task_contract_v2": {"declared_task_type": "clause_design"},
            "contract_evidence": {"document_excerpt": "条件发生时，应通知投标人。"},
        }
        with patch("run_hierarchy_gated_llm_smoke.model_request") as llm:
            response, gate = run_final_reasoning(
                api_key="unused", prompt="legal", runtime_input=runtime, max_tokens=1024)
        llm.assert_not_called()
        self.assertEqual("none", response["model_requested"])
        self.assertEqual("task_protocol_failure", gate["failure_class"])
        self.assertNotEqual("insufficient_information_needs_human_confirm",
                            gate.get("conclusion_type"))


if __name__ == "__main__":
    unittest.main()
