"""Offline guards for source-version, U01 retrieval queries, and U28 routing."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from law_source_version_v1 import OLD_SOURCE_ID, versioned_2022_corpus  # noqa: E402
from retrieval_task_query_v1 import expand_document_acquisition_queries  # noqa: E402
from task_text_comparison_v1 import build_contract, compare, route_task  # noqa: E402


class SourceVersionTests(unittest.TestCase):
    def setUp(self):
        self.old_ids = ["0708ceb43ccf18c323b2", "b43221a19bc5c4996abc",
                        "2f1c6fbdaa4e8489b42b"]
        self.rows = ([{"chunk_id": key, "source_id": OLD_SOURCE_ID, "article": "OLD"}
                      for key in self.old_ids]
                     + [{"chunk_id": "old-other", "source_id": OLD_SOURCE_ID}]
                     + [{"chunk_id": "level-two", "source_id": "other", "article": "第十六条"}])

    def test_retires_stale_source_and_inserts_only_checked_2022_articles(self):
        updated, audit = versioned_2022_corpus(self.rows, as_of_date="2022-06-21")
        self.assertEqual(4, len(updated))
        self.assertEqual({"第六条", "第二十六条", "第四十七条"},
                         {row["article"] for row in updated if row.get("normative_level") == "Level 3"})
        self.assertEqual("第十六条", updated[0]["article"])
        self.assertEqual(4, len(audit["retired_chunk_ids"]))
        self.assertTrue(all(row["requires_human_review"] for row in updated[1:]))
        self.assertEqual("OLD", self.rows[0]["article"])

    def test_unverified_date_is_not_silently_accepted(self):
        with self.assertRaisesRegex(ValueError, "not_verified_for_date"):
            versioned_2022_corpus(self.rows, as_of_date="2026-09-28")


class RetrievalQueryTests(unittest.TestCase):
    def test_duration_synonyms_contain_no_answer_or_article_number(self):
        question = "招标文件获取期限是否满足法定最短期限？"
        queries, audit = expand_document_acquisition_queries(question, [question])
        self.assertEqual(3, len(queries))
        self.assertTrue(audit["matched"])
        self.assertNotIn("第十六条", " ".join(queries))
        self.assertNotIn("5日", " ".join(queries))

    def test_locked_question_may_omit_document_type_if_query_supplies_it(self):
        question = "2022年5月31日至6月8日的文件获取期限设置，是否满足可适用的法定最短期限？"
        queries, audit = expand_document_acquisition_queries(question, [question, "招标文件获取期限"])
        self.assertTrue(audit["matched"])
        self.assertIn("招标文件 发售期 最短期限", queries)
        self.assertNotIn("第十六条", " ".join(queries))

    def test_unrelated_question_is_unchanged(self):
        queries, audit = expand_document_acquisition_queries("履约担保上限？", ["履约担保上限"])
        self.assertEqual(["履约担保上限"], queries)
        self.assertFalse(audit["matched"])

    def test_mismatched_retrieval_hint_cannot_change_the_locked_question(self):
        question = "投标截止期限是否满足法定要求？"
        queries, audit = expand_document_acquisition_queries(question, ["招标文件获取期限"])
        self.assertFalse(audit["matched"])
        self.assertEqual(["招标文件获取期限"], queries)


class TextRouteTests(unittest.TestCase):
    def setUp(self):
        self.question = "技术标建设规模文字是否回应招标范围概况？不审图算量。"
        self.tender = {"source_id": "TENDER-p1", "locator": "p1-b1", "text":
                       "建设规模：建筑面积100.00平方米，宿舍楼60.00平方米，浴室40.00平方米。"}
        self.bid = {"source_id": "TECH-p2", "locator": "p2-b3", "text":
                    "建设规模: 建筑面积 100.00 平方米, 宿舍楼 60.00 平方米, 浴室 40.00 平方米。"}
        self.checks = [{"field": name, "mode": "decimal", "tender_quote": value,
                        "bid_quote": value.replace("平方米", " 平方米"),
                        "tender_start": self.tender["text"].find(value),
                        "bid_start": self.bid["text"].find(value.replace("平方米", " 平方米"))}
                       for name, value in (("total", "100.00平方米"), ("dorm", "60.00平方米"),
                                           ("bath", "40.00平方米"))]

    def test_qx28_style_question_routes_outside_legal_u(self):
        evidence = "[TENDER-p1] " + self.tender["text"] + "\n[TECH-p2] " + self.bid["text"]
        route = route_task({"declared_task_type": "document_response",
                            "scope": "scope_needs_confirmation", "question_verbatim": self.question}, evidence)
        self.assertEqual("text_response_comparison", route["route"])
        contract = build_contract("SYN-U28", self.question, self.tender, self.bid, self.checks)
        result = compare(contract)
        self.assertFalse(result["blocked"])
        self.assertFalse(result["legal_conclusion_available"])
        self.assertEqual("observed_within_supplied_scope", result["response"]["task_completion"])
        self.assertIsNone(result["response"]["legal_conclusion_type"])

    def test_difference_is_review_item_not_legal_risk_or_u(self):
        changed = dict(self.bid, text=self.bid["text"].replace("40.00", "41.00"))
        checks = [dict(item) for item in self.checks]
        checks[-1]["bid_quote"] = "41.00 平方米"
        checks[-1]["bid_start"] = changed["text"].find("41.00 平方米")
        result = compare(build_contract("SYN-2", self.question, self.tender, changed, checks))
        self.assertEqual("observed_difference_requires_review", result["response"]["task_completion"])
        self.assertIsNone(result["response"]["legal_conclusion_type"])

    def test_missing_quote_and_tampering_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "quote_not_in_locked_source"):
            build_contract("SYN-3", self.question, self.tender, self.bid,
                           [dict(self.checks[0], bid_quote="不存在的图表")])
        contract = build_contract("SYN-4", self.question, self.tender, self.bid, self.checks)
        contract["checks"][0]["bid_quote"] = "999"
        self.assertEqual("task_contract_binding_failure", compare(contract)["failure_class"])

    def test_legal_and_actual_conduct_questions_not_auto_routed(self):
        evidence = "[TENDER-p1] " + self.tender["text"] + "\n[TECH-p2] " + self.bid["text"]
        for question in ("技术标文字是否在法律上构成实质性响应？",
                         "技术标实际上传是否满足要求？"):
            self.assertEqual("legal_or_other_task", route_task(
                {"declared_task_type": "document_response", "question_verbatim": question},
                evidence)["route"])

    def test_runner_never_calls_legal_llm_for_locked_text_contract(self):
        from run_hierarchy_gated_llm_smoke import run_final_reasoning
        contract = build_contract("SYN-U28", self.question, self.tender, self.bid, self.checks)
        with patch("run_hierarchy_gated_llm_smoke.model_request") as llm:
            response, gate = run_final_reasoning(api_key="unused", prompt="legal",
                runtime_input={"issue_id": "SYN-U28", "task_text_comparison_contract_v1": contract},
                max_tokens=1024)
        llm.assert_not_called()
        self.assertEqual("none", response["model_requested"])
        self.assertEqual("observed_within_supplied_scope", gate["response"]["task_completion"])

    def test_opted_in_text_task_cannot_be_passed_to_legal_gate(self):
        from llm_abstention_gate import apply_gate
        evidence = "[TENDER-p1] " + self.tender["text"] + "\n[TECH-p2] " + self.bid["text"]
        runtime = {"issue_id": "SYN-U28", "run_id": "test", "project_id": "synthetic",
                   "task_route_protocol_version": "text-pair-v1",
                   "review_task_contract_v2": {"declared_task_type": "document_response",
                                               "question_verbatim": self.question},
                   "contract_evidence": {"document_excerpt": evidence}}
        result = apply_gate({"findings": []}, runtime)
        self.assertTrue(result["blocked"])
        self.assertEqual("task_route_mismatch", result["failure_class"])


if __name__ == "__main__":
    unittest.main()
