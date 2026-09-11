"""Offline mechanism tests only. Fixtures are not legal ground truth."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from experiment_integrity import (
    RunJournal, digest, request_fingerprint, result_status, validate_runtime,
    write_new_json,
)
from experiment_metrics import retrieval_metrics, pair_metrics, intervention_observation
from clarification_adapter import Budget, bind_requests, return_materials, review_once
from run_intervention_experiment import preflight


class Response:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self.ok = 200 <= status < 400
        self.payload = payload if payload is not None else {"choices": [{"message": {"content": "not json"}}]}
        self.text = "not json"

    def json(self):
        return self.payload


class AuditTests(unittest.TestCase):
    def test_fingerprint_binds_all_runtime_dimensions(self):
        body = {"text": "a", "project_context": {"city": "x"}, "evidence": ["law1"],
                "prompt": "p", "model": "deepseek-v4-flash", "max_tokens": 2048}
        binding = {"method": "b", "history": [], "corpus": "c", "code": "d"}
        key = request_fingerprint("url", body, binding)
        for name in body:
            altered = deepcopy(body)
            altered[name] = "changed"
            with self.subTest(field=name):
                self.assertNotEqual(key, request_fingerprint("url", altered, binding))
        for name in binding:
            altered = deepcopy(binding)
            altered[name] = "changed"
            self.assertNotEqual(key, request_fingerprint("url", body, altered))

    def test_label_and_secret_isolation(self):
        for key in ["expected_relation", "reference_answer", "hidden_materials", "expert_label", "api_key"]:
            with self.subTest(field=key), self.assertRaises(ValueError):
                validate_runtime({"nested": [{key: "private"}]})
        validate_runtime({"runtime_constraints": {"gold_labels_available_to_runtime": False}, "max_tokens": 2048})

    def test_resume_uses_exact_request_and_preserves_both_channels(self):
        with tempfile.TemporaryDirectory() as temp:
            calls = []
            def post(*args, **kwargs):
                calls.append(kwargs)
                return Response(payload={"choices": [{"message": {"content": "c", "reasoning_content": "r"}}], "usage": {"total_tokens": 9}})
            first = RunJournal(temp, {"model": "m"})
            with first.case("one"):
                out = first.request("url", {"messages": []}, "TEST-CREDENTIAL", post)
            resumed = RunJournal(temp, {"model": "m"}, resume=True)
            with resumed.case("one"):
                cached = resumed.request("url", {"messages": []}, "TEST-CREDENTIAL", post)
            self.assertEqual(len(calls), 1)
            self.assertTrue(cached["cache_hit"])
            self.assertEqual(cached["incurred_elapsed_seconds"], 0)
            self.assertEqual(out["payload"]["choices"][0]["message"]["reasoning_content"], "r")
            self.assertNotIn("TEST-CREDENTIAL", (Path(temp) / "events.jsonl").read_text())
            with resumed.case("one"):
                resumed.request("url", {"messages": ["changed evidence"]}, "TEST-CREDENTIAL", post)
            self.assertEqual(len(calls), 2)

    def test_400_invalid_json_and_length_do_not_retry(self):
        for response in [Response(400), Response(), Response(payload={"choices": [{"finish_reason": "length"}]})]:
            with tempfile.TemporaryDirectory() as temp:
                calls = []
                def post(*args, **kwargs):
                    calls.append(1)
                    return response
                journal = RunJournal(temp, {}, max_attempts=2)
                with journal.case("one"):
                    out = journal.request("url", {}, "", post, sleeper=lambda _: None)
                self.assertEqual(len(calls), 1)
                self.assertEqual(out["retry_count"], 0)

    def test_predeclared_transport_retry_records_every_attempt(self):
        with tempfile.TemporaryDirectory() as temp:
            responses = iter([Response(503), Response()])
            journal = RunJournal(temp, {}, max_attempts=2)
            with journal.case("one"):
                out = journal.request("url", {}, "", lambda *a, **k: next(responses), sleeper=lambda _: None)
            self.assertEqual([a["http_status"] for a in out["attempts"]], [503, 200])
            self.assertEqual(out["retry_count"], 1)

    def test_cached_failure_not_retried_until_satisfactory(self):
        with tempfile.TemporaryDirectory() as temp:
            first = RunJournal(temp, {})
            with first.case("one"):
                first.request("url", {}, "", lambda *a, **k: Response(400))
            second = RunJournal(temp, {}, resume=True)
            with second.case("one"):
                out = second.request("url", {}, "", lambda *a, **k: self.fail("must not retry"))
            self.assertEqual(out["http_status"], 400)

    def test_interrupt_and_corrupt_cache_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            journal = RunJournal(temp, {})
            binding = {"case_id": "one", "request_ordinal": 1}
            key = request_fingerprint("url", {}, binding)
            write_new_json(Path(temp) / "request_cache" / f"{key}.started.json", {})
            with journal.case("one"), self.assertRaises(RuntimeError):
                journal.request("url", {}, "", lambda *a, **k: self.fail("no request"))
        with tempfile.TemporaryDirectory() as temp:
            journal = RunJournal(temp, {})
            with journal.case("one"):
                journal.request("url", {}, "", lambda *a, **k: Response())
            path = next(p for p in (Path(temp) / "request_cache").glob("*.json") if not p.name.endswith("started.json"))
            row = json.loads(path.read_text())
            row["observation"]["ok"] = False
            path.write_text(json.dumps(row))
            journal = RunJournal(temp, {}, resume=True)
            with journal.case("one"), self.assertRaises(ValueError):
                journal.request("url", {}, "", lambda *a, **k: self.fail("no request"))

    def test_existing_outputs_and_changed_binding_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            RunJournal(temp, {"corpus": "one"})
            with self.assertRaises(ValueError):
                RunJournal(temp, {"corpus": "two"}, resume=True)
            path = Path(temp) / "old.json"
            write_new_json(path, {"old": True})
            with self.assertRaises(FileExistsError):
                write_new_json(path, {})


def completed(conclusion="requires_human_legal_review"):
    finding = {"conclusion_type": conclusion}
    return {"final_llm_response": {"ok": True, "parsed": {"findings": [finding]}, "finish_reason": "stop"},
            "post_llm_gate": {"blocked": False, "status": "passed", "response": {"findings": [finding]}}}


class MetricTests(unittest.TestCase):
    def test_hit_is_not_complete_recall(self):
        metric = retrieval_metrics(["a", "x", "y"], ["a", "b"], k=2)
        self.assertEqual(metric["hit_at_k"], 1)
        self.assertEqual(metric["reference_evidence_recall_at_k"], .5)
        self.assertIsNone(metric["complete_necessary_evidence_recall_at_k"])
        self.assertFalse(retrieval_metrics([], [], k=5)["scorable"])
        self.assertEqual(retrieval_metrics(["x", "b"], ["b"])["reciprocal_rank"], .5)

    def test_duplicate_ranks_rejected(self):
        with self.assertRaises(ValueError):
            retrieval_metrics(["a", "a"], ["a"])

    def test_human_review_is_not_abstention(self):
        result = result_status(completed())
        self.assertEqual(result["verdicts"], ["R"])
        self.assertEqual(result["workflow_status"], "requires_human_second_review")
        self.assertTrue(result["ready_for_human_delivery"])
        self.assertEqual(result_status(completed("not_supported_by_current_corpus"))["verdicts"], ["U"])

    def test_failures_never_become_successful_abstentions(self):
        for change, expected in [("gate", "gate_blocked"), ("http", "execution_failed"),
                                 ("length", "invalid_output"), ("triage", "execution_failed")]:
            result = completed("insufficient_information")
            if change == "gate": result["post_llm_gate"]["blocked"] = True
            if change == "http": result["final_llm_response"]["ok"] = False
            if change == "length": result["final_llm_response"]["finish_reason"] = "length"
            if change == "triage": result["runtime_input"] = {"hierarchy_retrieval_audit": {"cascade_failure_level": "Level 1"}}
            status = result_status(result)
            self.assertEqual(status["execution_status"], expected)
            self.assertFalse(status["ready_for_human_delivery"])
            self.assertEqual(status["verdicts"], [])

    def test_raw_and_gate_are_separate(self):
        result = completed("requires_human_legal_review")
        result["post_llm_gate"]["response"]["findings"] = [{"conclusion_type": "insufficient_information"}]
        self.assertEqual(intervention_observation("o", result, before_gate=True)["verdict"], "R")
        self.assertEqual(intervention_observation("o", result)["verdict"], "U")

    def test_missing_results_stay_in_pair_denominator(self):
        pair = {"pair_id": "p", "mother_case_id": "m", "verification_status": "human_verified",
                "original_observation_id": "o", "variant_observation_id": "v", "expected_relation": "same",
                "original_allowed_verdicts": ["N"], "variant_allowed_verdicts": ["N"]}
        metrics = pair_metrics([pair], [{"observation_id": "o", "execution_status": "completed", "verdict": "N"}])
        self.assertEqual(metrics["pair_correctness"], {"numerator": 0, "denominator": 1, "rate": 0})
        self.assertEqual(metrics["missing_or_noncompleted_pairs"], 1)

    def test_consistently_wrong_not_pair_success(self):
        pair = {"pair_id": "p", "mother_case_id": "m", "verification_status": "human_verified",
                "original_observation_id": "o", "variant_observation_id": "v", "expected_relation": "same",
                "original_allowed_verdicts": ["N"], "variant_allowed_verdicts": ["N"]}
        results = [{"observation_id": x, "execution_status": "completed", "verdict": "R"} for x in ["o", "v"]]
        metrics = pair_metrics([pair], results)
        self.assertEqual(metrics["relations"]["same"]["rate"], 1)
        self.assertEqual(metrics["pair_correctness"]["rate"], 0)


class ClarificationTests(unittest.TestCase):
    def setUp(self):
        self.request = {"request_id": "r1", "issue_id": "i1", "finding_id": "f1",
                        "missing_element": "jurisdiction_and_scope", "material_id": "d1",
                        "kind": "project_fact", "reason": "Locate project", "expected_review_action": "Recheck applicability"}
        self.findings = {"findings": [{"finding_id": "f1", "issue_id": "i1",
                                      "legal_element_coverage": {"jurisdiction_and_scope": "missing"}}]}
        self.registry = {"d1": {"allowed_issue_ids": ["i1"], "allowed_missing_elements": ["jurisdiction_and_scope"],
                                "text": "Synthetic location X", "text_hash": digest("Synthetic location X"),
                                "source_locator": "synthetic fixture paragraph 1", "release_status": "owner_verified_for_experiment"}}

    def test_reuses_existing_gap_and_rejects_unbound_proposal(self):
        out = bind_requests(self.findings, [self.request])
        self.assertEqual(len(out["requests"]), 1)
        wrong = {**self.request, "missing_element": "invented"}
        self.assertEqual(len(bind_requests(self.findings, [wrong])["invalid_requests"]), 1)

    def test_law_gap_is_not_supplementable(self):
        out = bind_requests(self.findings, [{**self.request, "kind": "new_law"}])
        self.assertEqual(len(out["requests"]), 0)

    def test_unavailable_or_tampered_material_not_fabricated(self):
        self.assertEqual(return_materials([self.request], {})["materials"], [])
        self.registry["d1"]["text"] = "changed"
        out = return_materials([self.request], self.registry)
        self.assertEqual(out["events"][0]["reason"], "material_hash_mismatch")

    def test_common_budget_and_no_truncation(self):
        out = return_materials([self.request], self.registry, budget=Budget(max_returned_characters=1))
        self.assertEqual(out["materials"], [])
        self.assertEqual(out["events"][0]["reason"], "material_budget_exceeded_no_truncation")

    def test_wrong_issue_and_duplicate_material_rejected(self):
        out = return_materials([{**self.request, "issue_id": "wrong"}], self.registry)
        self.assertEqual(out["materials"], [])
        out = return_materials([self.request, self.request], self.registry)
        self.assertEqual(len(out["materials"]), 1)

    def test_one_review_keeps_original_and_fixed_corpus(self):
        runtime = {"issue_id": "i1", "retrieved_legal_evidence": [{"chunk_id": "l1"}], "project_context": {}}
        original = deepcopy(runtime)
        calls = []
        def reviewer(packet):
            calls.append(packet)
            self.assertNotIn("allowed_issue_ids", packet["supplemental_project_materials"][0])
            return {"result": "still_unknown"}
        returned = return_materials([self.request], self.registry)
        out = review_once(runtime, {"supported_finding": "preserved"}, returned, reviewer)
        self.assertEqual(len(calls), 1)
        self.assertEqual(runtime, original)
        self.assertEqual(out["initial_result"]["supported_finding"], "preserved")
        with self.assertRaises(ValueError):
            review_once(runtime, {}, returned, reviewer, prior_rounds=1)

    def test_no_material_no_repeat(self):
        out = review_once({}, {}, {"materials": []}, lambda _: self.fail("must not call"))
        self.assertFalse(out["rereview_called"])


class PreflightTests(unittest.TestCase):
    def test_disabled_external_policy_rejects_external_material(self):
        rows = [{"mother_case_id": "m", "method_id": "b", "repeat_id": 0,
                 "runtime_input": {"retrieved_legal_evidence": [{"external_source": True}]}}]
        with self.assertRaises(ValueError):
            preflight(rows, {"external_policy": "disabled"}, "h")

    def test_unreviewed_variants_block_online(self):
        rows = [{"mother_case_id": "m", "method_id": "b", "repeat_id": 0,
                 "runtime_input": {"retrieved_legal_evidence": []}}]
        self.assertFalse(preflight(rows, {"external_policy": "disabled"}, "h")["ready_for_online"])

    def test_fixed_evidence_must_not_change_between_variants(self):
        rows = [{"mother_case_id": "m", "method_id": "b", "repeat_id": 0,
                 "runtime_input": {"retrieved_legal_evidence": [x]}} for x in ["a", "b"]]
        with self.assertRaises(ValueError):
            preflight(rows, {}, "h")


if __name__ == "__main__":
    unittest.main(verbosity=2)
