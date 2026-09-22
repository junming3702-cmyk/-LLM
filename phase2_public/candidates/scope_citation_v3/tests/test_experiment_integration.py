"""Offline integration with the existing retriever conversion, parser and gate."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
from hierarchy_cascade_retriever import RankedCandidate
from llm_abstention_gate import _canonicalize_evidence, apply_gate
from run_hierarchy_gated_llm_smoke import model_request, evidence_applicability
from test_post_llm_gate_v2 import _runtime, _finding
from experiment_integrity import RunJournal
import tempfile


class IntegrationTests(unittest.TestCase):
    def test_source_metadata_survives_candidate_and_gate(self):
        row = {"chunk_id": "x", "title": "Test law", "article": "1", "text": "fixture",
               "source_locator": "1", "normative_level": "Level 2", "corpus_partition": "primary",
               "source_id": "source-x", "file_hash": "hash-x", "geographic_scope": "unknown",
               "version": None, "effective_date": None, "project_type_scope": None,
               "applicability_status": "source_applicability_not_explicitly_stated"}
        candidate = RankedCandidate(row, .5, .4, .6).as_dict(1)
        self.assertEqual(candidate["file_hash"], "hash-x")
        self.assertIsNone(candidate["effective_date"])
        candidate.update(evidence_applicability(candidate, {}))
        finding = {"legal_evidence": [{"chunk_id": "x", "effective_date": "2099-01-01", "file_hash": "invented"}]}
        _canonicalize_evidence(finding, {"retrieved_legal_evidence": [candidate]}, [])
        actual = finding["legal_evidence"][0]
        self.assertEqual(actual["file_hash"], "hash-x")
        self.assertIsNone(actual["effective_date"])

    def test_unknown_metadata_not_created_by_candidate(self):
        candidate = RankedCandidate({"chunk_id": "x", "text": "test"}, .1, .1, .1).as_dict(1)
        self.assertNotIn("effective_date", candidate)
        self.assertNotIn("version", candidate)

    def test_runtime_and_raw_output_unchanged_by_gate(self):
        runtime = _runtime()
        raw = {"findings": [_finding()]}
        before_runtime, before_raw = deepcopy(runtime), deepcopy(raw)
        result = apply_gate(raw, runtime)
        self.assertEqual(runtime, before_runtime)
        self.assertEqual(raw, before_raw)
        self.assertEqual(result["raw_response"], before_raw)

    def test_actual_llm_payload_both_channels_and_usage_preserved(self):
        class Response:
            status_code, ok = 200, True
            def json(self):
                return {"model": "deepseek-v4-flash", "usage": {"total_tokens": 7},
                        "choices": [{"finish_reason": "stop", "message": {
                            "content": "unselected content", "reasoning_content": json.dumps({"findings": [{}]})}}]}
        with tempfile.TemporaryDirectory() as temp, patch("run_hierarchy_gated_llm_smoke.requests.post", return_value=Response()) as post:
            journal = RunJournal(temp, {"method": "integration"})
            with journal.case("i1"):
                output = model_request("TEST-CREDENTIAL", "test prompt", {"issue_id": "i1"}, 2048)
            self.assertEqual(post.call_count, 1)
            self.assertEqual(output["raw_provider_payload"]["choices"][0]["message"]["content"], "unselected content")
            self.assertEqual(output["usage"]["total_tokens"], 7)
            self.assertEqual(output["request_body"]["max_tokens"], 2048)
            self.assertEqual(output["request_body"]["model"], "deepseek-v4-flash")
            self.assertNotIn("TEST-CREDENTIAL", json.dumps(output))

    def test_empty_choices_does_not_crash_parser(self):
        class Response:
            status_code, ok = 200, True
            def json(self): return {"choices": []}
        with patch("run_hierarchy_gated_llm_smoke.requests.post", return_value=Response()):
            out = model_request("", "test", {}, 2048)
        self.assertIsNone(out["parsed"])

    def test_labels_rejected_before_provider_call(self):
        with patch("run_hierarchy_gated_llm_smoke.requests.post") as post:
            with self.assertRaises(ValueError):
                model_request("", "test", {"reference_answer": "N"}, 2048)
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
