"""Fictional source and law fixtures only; never import private project data."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import unittest

from lineage import trace_result
from preflight import audit_preflight, capture_selected_from_retrieval
from guarded_runtime import verify_request
from task_scope import audit_task


def h(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


CHUNK = {"chunk_id": "SYN-C1", "source_id": "SYN-LAW", "article": "synthetic-article-1",
         "normative_level": "Level 2", "corpus_partition": "primary", "file_hash": h("synthetic-file"),
         "text": "FICTIONAL RULE ONLY: two checks required."}
SOURCE = {"source_id": "SYN-LAW", "file_hash": CHUNK["file_hash"], "local_file": "unverified/fictional.txt"}
EXTRACT = {"source_id": "SYN-LAW", "file_hash": CHUNK["file_hash"], "article": CHUNK["article"],
           "text": CHUNK["text"], "source_locator": "SYN:page-1"}
PACKET = {"chunk_id": "SYN-C1", "legal_quote": CHUNK["text"], "file_hash": CHUNK["file_hash"],
          "citation_ready": True, "independent_legal_evidence": True,
          "applicability_status": "applicable", "temporal_status": "valid"}


def fixture(*, found=True, selected=True, sent=True, cited=True):
    candidate = {"chunk_id": CHUNK["chunk_id"], "legal_quote": CHUNK["text"], "file_hash": CHUNK["file_hash"]}
    phase = {"phase": "primary", "retrieval_status": "completed_with_candidates" if found else "completed_no_hit",
             "candidates": [candidate] if found else [],
             "decision": {"selected_chunk_ids": [CHUNK["chunk_id"]] if selected and found else []}}
    payload = {"contract_evidence": {"document_id": "SYN-DOC", "document_excerpt": "fictional contract"},
               "retrieved_legal_evidence": [deepcopy(PACKET)] if sent else []}
    evidence = [{"chunk_id": CHUNK["chunk_id"]}] if cited else []
    return {"issue_id": "SYN-1", "runtime_input": deepcopy(payload),
            "cascade_execution_audit": [{"level": "Level 2", "phases": [phase]}],
            "final_llm_response": {"request_body": {"messages": [{"role": "user", "content": json.dumps(payload)}]},
                                   "parsed": {"findings": [{"legal_evidence": evidence}]}},
            "post_llm_gate": {"status": "passed", "response": {"findings": [{"legal_evidence": evidence}]}}}


def trace(result):
    return trace_result(result, [deepcopy(CHUNK)], {"sources": [deepcopy(SOURCE)]},
                        [deepcopy(EXTRACT)], [CHUNK["chunk_id"]])["traces"][0]


class LineageTests(unittest.TestCase):
    def test_seven_stages_and_identity(self):
        row = trace(fixture())
        self.assertEqual("catalog_only", row["source_library"]["status"])
        self.assertEqual("verified", row["parse"]["status"])
        self.assertEqual("present", row["index"]["status"])
        self.assertEqual("retrieved", row["retrieval"]["status"])
        self.assertEqual("present", row["final_input"]["status"])
        self.assertEqual("admitted_from_upstream_metadata", row["applicability_admission"]["status"])
        self.assertTrue(row["output_citation"]["gated_output"])

    def test_source_absent_from_catalog_distinct_from_article_missing(self):
        r = fixture()
        absent = trace_result(r, [CHUNK], {"sources": []}, [],
                              [{"source_id": "OTHER", "article": "1"}])["traces"][0]
        self.assertEqual("source_not_in_local_library_snapshot", absent["first_break"])
        missing_article = trace_result(r, [CHUNK], {"sources": [SOURCE]}, [],
                                       [{"source_id": "SYN-LAW", "article": "2"}])["traces"][0]
        self.assertEqual("source_present_but_article_not_indexed", missing_article["first_break"])
        unknown = trace_result(r, [CHUNK], None, None, ["unknown-id"])["traces"][0]
        self.assertEqual("unknown_without_source_id", unknown["source_library"]["status"])

    def test_indexed_but_not_retrieved(self):
        self.assertEqual("indexed_not_retrieved", trace(fixture(found=False, selected=False, sent=False, cited=False))["first_break"])

    def test_skipped_search_not_called_retrieval_failure(self):
        r = fixture(found=False, selected=False, sent=False, cited=False)
        r["cascade_execution_audit"] = [{"level": "Level 2", "status": "skipped_after_higher_level_stop"}]
        self.assertEqual("indexed_but_search_not_completed", trace(r)["first_break"])

    def test_retrieved_but_triage_did_not_select(self):
        self.assertEqual("retrieved_not_selected_for_final_packet", trace(fixture(selected=False, sent=False, cited=False))["first_break"])

    def test_unselected_candidate_delivered_is_distinct(self):
        self.assertEqual("unselected_candidate_in_final_request", trace(fixture(selected=False))["first_break"])

    def test_selected_but_lost_in_frozen_request(self):
        self.assertEqual("selected_but_missing_from_final_request", trace(fixture(sent=False, cited=False))["first_break"])

    def test_runtime_copy_not_substituted_for_actual_request(self):
        r = fixture(sent=False, cited=False)
        r["runtime_input"]["retrieved_legal_evidence"] = [deepcopy(PACKET)]
        row = trace(r)
        self.assertEqual("selected_but_missing_from_final_request", row["first_break"])

    def test_inapplicable_and_unknown_separate(self):
        r = fixture()
        payload = json.loads(r["final_llm_response"]["request_body"]["messages"][0]["content"])
        payload["retrieved_legal_evidence"][0]["applicability_status"] = "inapplicable"
        r["final_llm_response"]["request_body"]["messages"][0]["content"] = json.dumps(payload)
        self.assertEqual("in_final_request_but_inapplicable", trace(r)["first_break"])
        payload["retrieved_legal_evidence"][0]["applicability_status"] = "unknown"
        r["final_llm_response"]["request_body"]["messages"][0]["content"] = json.dumps(payload)
        self.assertEqual("in_final_request_but_not_admitted", trace(r)["first_break"])

    def test_packet_identity_conflict(self):
        r = fixture()
        payload = json.loads(r["final_llm_response"]["request_body"]["messages"][0]["content"])
        payload["retrieved_legal_evidence"][0]["legal_quote"] = "altered"
        r["final_llm_response"]["request_body"]["messages"][0]["content"] = json.dumps(payload)
        self.assertEqual("source_or_packet_identity_conflict", trace(r)["first_break"])

    def test_parse_unverified_is_not_called_retrieval_miss(self):
        row = trace_result(fixture(), [CHUNK], {"sources": [SOURCE]}, [], ["SYN-C1"])["traces"][0]
        self.assertEqual("parse_to_index_not_verified", row["first_break"])
        self.assertEqual("retrieved", row["retrieval"]["status"])

    def test_discovery_only_delivered_does_not_become_independent_basis(self):
        r = fixture()
        discovery = deepcopy(r["cascade_execution_audit"][0]["phases"][0]["candidates"][0])
        r["cascade_execution_audit"] = [{"level": "Level 2", "retrieval_status": "completed_with_candidates",
                                          "discovery_only_candidates": [discovery]}]
        self.assertEqual("discovery_only_delivered_not_independent_basis", trace(r)["first_break"])

    def test_comparison_gap_is_declared_not_proven(self):
        r = fixture()
        r["post_llm_gate"]["response"] = {
            "completed_checks": [{"legal_chunk_ids": ["SYN-C1"], "claim_ids": ["C1"]}],
            "gaps": [{"gap_id": "G1", "task_relation": "decisive_for_claim", "affected_claim_ids": ["C1"]}]}
        row = trace(r)
        self.assertEqual("model_declared_decisive_gap", row["comparison_completion"]["status"])
        self.assertFalse(row["comparison_completion"]["independently_verified"])
        self.assertEqual("admitted_evidence_but_decisive_comparison_gap_declared", row["first_break"])

    def test_locked_claim_links_gap_even_without_legal_check(self):
        r = fixture(cited=False)
        r["post_llm_gate"]["response"] = {"completed_checks": [],
            "gaps": [{"gap_id": "G1", "task_relation": "decisive_for_claim", "affected_claim_ids": ["C1"]}]}
        row = trace_result(r, [CHUNK], {"sources": [SOURCE]}, [EXTRACT],
                           [{"chunk_id": "SYN-C1", "claim_id": "C1"}])["traces"][0]
        self.assertEqual("admitted_evidence_but_decisive_comparison_gap_declared", row["first_break"])


class TaskAndPreflightTests(unittest.TestCase):
    def task(self, question, excluded=None, required=None):
        return {"question": question, "excluded_dependencies": excluded or [],
                "required_claims": [{"claim_id": "C1", "required_dependencies": required or ["applicable_rule"]}]}

    def test_negated_authenticity_and_other_positive_question(self):
        task = self.task("审查承诺是否满足招标要求，不核验实际业绩真实性。", ["authenticity"])
        audit = audit_task(task)
        self.assertEqual("task_contract_consistent", audit["status"])
        self.assertTrue(any(s["dependency"] == "authenticity" and s["polarity"] == "excluded" for s in audit["signals"]))

    def test_unlocked_exclusion_needs_review(self):
        self.assertEqual("needs_scope_review", audit_task(self.task("不核验实际业绩真实性。"))["status"])

    def test_required_dependency_cannot_be_erased(self):
        audit = audit_task(self.task("不核验实际业绩真实性。", ["authenticity"], ["authenticity"]))
        self.assertIn("required_dependency_excluded:C1:authenticity", audit["issues"])

    def test_positive_and_ambiguous_cues_not_silent_exclusions(self):
        self.assertEqual("needs_scope_review", audit_task(self.task("核验实际业绩真实性。", ["authenticity"]))["status"])
        self.assertEqual("needs_scope_review", audit_task(self.task("不是不核验实际业绩真实性。", ["authenticity"]))["status"])

    def test_selected_evidence_must_reach_actual_request(self):
        task = self.task("仅比对文本。")
        body = json.dumps({"task": task, "laws": []}, ensure_ascii=False)
        self.assertEqual("blocked_before_inference", audit_preflight(task, body, [{"chunk_id": "SYN-C1", "text": "x"}])["status"])
        body = json.dumps({"task": task, "laws": [{"chunk_id": "SYN-C1", "text": "x"}]}, ensure_ascii=False)
        self.assertEqual("ready_for_inference", audit_preflight(task, body, [{"chunk_id": "SYN-C1", "text": "x"}])["status"])

    def test_unselected_or_changed_evidence_blocked(self):
        task = self.task("仅比对文本。")
        body = json.dumps({"task": task, "laws": [{"chunk_id": "SYN-C1", "text": "wrong"},
                                                   {"chunk_id": "EXTRA", "text": "x"}]}, ensure_ascii=False)
        errors = audit_preflight(task, body, [{"chunk_id": "SYN-C1", "text": "right"}])["errors"]
        self.assertTrue(any("selected_chunk_text_changed" in x for x in errors))
        self.assertTrue(any("unselected_law_in_final_request" in x for x in errors))

    def test_retrieval_capture_then_packet_guard(self):
        task = self.task("仅比对文本。")
        audit_levels = fixture()["cascade_execution_audit"]
        captured = capture_selected_from_retrieval(audit_levels, task)
        self.assertEqual("SYN-C1", captured["selected_chunks"][0]["chunk_id"])
        context = {"task": task, "laws": [{"chunk_id": "SYN-C1", "text": CHUNK["text"],
                                           "source_sha256": CHUNK["file_hash"]}]}
        record = {"context": context, "body": {"messages": [{"role": "user", "content": json.dumps(context, ensure_ascii=False)}]}}
        self.assertEqual("internal_binding_only", verify_request(record)["status"])
        self.assertEqual("ready_for_inference", verify_request(record, captured)["status"])
        context["laws"][0]["text"] = "changed"
        record["body"]["messages"][0]["content"] = json.dumps(context, ensure_ascii=False)
        self.assertEqual("blocked_before_inference", verify_request(record, captured)["status"])

    def test_selected_id_must_exist_in_completed_retrieval(self):
        levels = fixture()["cascade_execution_audit"]
        levels[0]["phases"][0]["decision"]["selected_chunk_ids"] = ["NOT-CANDIDATE"]
        with self.assertRaisesRegex(ValueError, "selected_chunk_not_in_retrieval_candidates"):
            capture_selected_from_retrieval(levels, self.task("仅比对文本。"))

    def test_selection_manifest_task_and_source_hash_binding(self):
        task = self.task("仅比对文本。")
        captured = capture_selected_from_retrieval(fixture()["cascade_execution_audit"], task)
        context = {"task": task, "laws": [{"chunk_id": "SYN-C1", "text": CHUNK["text"],
                                           "source_sha256": CHUNK["file_hash"]}]}
        record = {"context": context, "body": {"messages": [{"role": "user", "content": json.dumps(context, ensure_ascii=False)}]}}
        tampered = deepcopy(captured)
        tampered["task_sha256"] = h("other task")
        self.assertEqual("blocked_before_inference", verify_request(record, tampered)["status"])
        context["laws"][0]["source_sha256"] = h("different source")
        record["body"]["messages"][0]["content"] = json.dumps(context, ensure_ascii=False)
        self.assertIn("selected_chunk_source_hash_changed:SYN-C1", verify_request(record, captured)["errors"])


if __name__ == "__main__":
    unittest.main()
