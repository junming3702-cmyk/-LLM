"""Synthetic dispatcher checks: no law corpus, real files or external calls."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from docx import Document

from auto_pre_review import (classify, execute_approved, plan, result_bound_to_label,
                             summarize, validate_approval, privacy_risk_codes, propose_pilot,
                             SENSITIVE_NUMBER)
from bundle_review import run
from pair_reasoner import apply_pair_gate


def docx(path: Path, lines: list[str]) -> None:
    document = Document()
    for line in lines:
        document.add_paragraph(line)
    document.save(path)


def runtime(label: dict) -> dict:
    return {"review_task_kind": label["review_task_kind"], "bundle_evidence": label["bundle_evidence"],
            "contract_evidence": {"document_excerpt": label["document_excerpt"]},
            "review_scope": {"documents_received": label["bundle_evidence"]["documents_received"]}}


class AutomaticPreReviewTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        docx(self.root / "tender.docx", ["投标人须提供建筑施工资质证书。", "投标保证金应不超过估算价的2%。"])
        docx(self.root / "bid.docx", ["我方提供建筑施工资质证书。", "投标保证金按估算价的2%提供。"])
        manifest = {"project_id": "SYN-AUTO-001", "project_type": "construction_project",
                    "documents": [{"document_key": "T", "role": "tender", "path": "tender.docx",
                                   "declared_issued": True, "source_status": "synthetic"},
                                  {"document_key": "B", "role": "final_bid", "path": "bid.docx",
                                   "declared_final_submitted": True, "source_status": "synthetic"}]}
        manifest_path = self.root / "bundle.json"
        self.manifest_path = manifest_path
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        self.bundle_dir = self.root / "bundle"
        run(manifest_path, self.bundle_dir)

    def test_plan_is_not_a_verdict_and_approval_is_exact(self) -> None:
        planned = plan(self.bundle_dir)
        self.assertGreater(planned["route_counts"]["strict_legal_cascade"], 0)
        self.assertGreater(planned["route_counts"]["pair_reasoner"], 0)
        self.assertEqual(sum(planned["route_counts"].values()), planned["candidate_count"])
        legal = next(x for x in planned["items"] if x["machine_route"] == "strict_legal_cascade")
        approval = {"project_id": planned["project_id"],
                    "candidate_labels_sha256": planned["candidate_labels_sha256"],
                    "approved": [{"issue_id": legal["issue_id"], "label_sha256": legal["label_sha256"]}]}
        self.assertEqual(validate_approval(planned, approval, 1), [legal["issue_id"]])
        with self.assertRaisesRegex(ValueError, "positive_max_issues_required"):
            validate_approval(planned, approval, 0)
        approval["approved"][0]["label_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "exact_label_mismatch"):
            validate_approval(planned, approval, 1)

    def test_pilot_proposal_is_bounded_screened_and_requires_privacy_review(self) -> None:
        planned = plan(self.bundle_dir, self.manifest_path)
        targets = {"tender_clause_legality": 1, "bid_standalone_legality": 1,
                   "bid_responsiveness": 1}
        approval, audit = propose_pilot(self.bundle_dir, planned, targets)
        self.assertEqual(len(validate_approval(planned, approval, 3)), 3)
        self.assertFalse(approval["privacy_review_complete"])
        self.assertEqual(set(audit["selected_ids_by_task"]), set(targets))
        curated_ids = [row["issue_id"] for row in approval["approved"]]
        curated, curated_audit = propose_pilot(self.bundle_dir, planned, targets,
                                               selected_ids=curated_ids)
        self.assertEqual([row["issue_id"] for row in curated["approved"]], curated_ids)
        self.assertEqual(curated_audit["selection_method"], "curated_ids_then_privacy_screen")
        with self.assertRaisesRegex(ValueError, "curated_pilot_ids_must_be_unique"):
            propose_pilot(self.bundle_dir, planned, targets, selected_ids=curated_ids[:1] * 3)
        with self.assertRaisesRegex(ValueError, "exact_excerpt_privacy_review_required"):
            execute_approved(self.bundle_dir, self.root / "pilot_not_reviewed", approval, 3,
                             lambda _: {}, lambda _: {}, source_manifest=self.manifest_path)

    def test_machine_conclusions_and_human_signoff_are_separate(self) -> None:
        planned = plan(self.bundle_dir, self.manifest_path)
        legal = next(x for x in planned["items"] if x["machine_route"] == "strict_legal_cascade")
        pair = next(x for x in planned["items"] if x["machine_route"] == "pair_reasoner")
        approval = {"project_id": planned["project_id"],
                    "privacy_review_complete": True,
                    "candidate_labels_sha256": planned["candidate_labels_sha256"],
                    "source_manifest_sha256": planned["source_manifest_sha256"],
                    "approved": [{"issue_id": x["issue_id"], "label_sha256": x["label_sha256"]}
                                 for x in (legal, pair)]}

        def legal_executor(label: dict) -> dict:
            finding = {"issue_id": label["issue_id"], "conclusion_type": "requires_human_legal_review",
                       "document_excerpt": label["document_excerpt"], "legal_evidence": [],
                       "assistant_recommendation": "核对资质依据。"}
            return {"issue_id": label["issue_id"], "runtime_input": runtime(label),
                    "final_llm_response": {"findings": [finding]},
                    "post_llm_gate": {"status": "review_required", "blocked": False,
                                      "response": {"findings": [finding]}}}

        def pair_executor(label: dict) -> dict:
            primary = label["bundle_evidence"]["primary"]
            bid = label["bundle_evidence"]["paired_bid_source"]
            raw = {"findings": [{"issue_id": label["issue_id"], "tender_quote": primary["quote"],
                                 "bid_quote": bid["quote"], "difference": "所选文本表述一致。",
                                 "status": "textually_consistent", "recommended_human_action": "核对真实性。"}]}
            return {"issue_id": label["issue_id"], "runtime_input": runtime(label),
                    "final_llm_response": raw, "post_llm_gate": apply_pair_gate(raw, label)}

        output = self.root / "automatic"
        audit = execute_approved(self.bundle_dir, output, approval, 2, legal_executor, pair_executor,
                                 {"test_only": True}, self.manifest_path)
        self.assertEqual(len(audit["completed"]), 2)
        self.assertEqual(audit["failed"], [])
        self.assertTrue((output / "machine_preliminary_summary.json").exists())
        self.assertTrue((output / "review_assembled.private.json").exists())
        summary = summarize(self.bundle_dir, output / "legal", output / "pair")
        self.assertEqual(summary["machine_status_counts"]["preliminary_risk_for_human_confirmation"], 1)
        self.assertEqual(summary["machine_status_counts"]["no_supported_issue_within_reviewed_scope"], 1)
        self.assertGreater(summary["machine_status_counts"].get("eligible_but_not_run", 0), 0)
        self.assertTrue(all(x["human_signoff_status"] == "not_signed_off" for x in summary["items"]))
        self.assertEqual(sum(bool(x["preliminary_findings"]) for x in summary["items"]), 2)
        self.assertTrue(all(not x["preliminary_findings"] for x in summary["items"]
                            if x["machine_processing_status"] == "eligible_but_not_run"))
        self.assertFalse(summary["whole_bundle_preliminary_review_complete"])
        with self.assertRaisesRegex(FileExistsError, "overwrite"):
            execute_approved(self.bundle_dir, output, approval, 2, legal_executor, pair_executor,
                             source_manifest=self.manifest_path)

    def test_unpaired_and_blocked_never_become_clean(self) -> None:
        unpaired = {"issue_id": "U", "task": "bid_responsiveness", "core_status": "not_eligible_unpaired",
                    "risk_response_gated_unmodified": None,
                    "presentation_response": {"findings": [{"conclusion_type": "not_yet_assessed"}]}}
        self.assertEqual(classify(unpaired)["machine_processing_status"],
                         "pairing_unresolved_not_a_nonresponse_finding")
        blocked = {**unpaired, "core_status": "blocked",
                   "risk_response_gated_unmodified": {"blocked": True, "response": {"findings": []}}}
        self.assertEqual(classify(blocked)["machine_processing_status"], "machine_output_blocked")

    def test_result_binding_and_raw_quarantine(self) -> None:
        planned = plan(self.bundle_dir, self.manifest_path)
        legal = next(x for x in planned["items"] if x["machine_route"] == "strict_legal_cascade")
        approval = {"project_id": planned["project_id"],
                    "privacy_review_complete": True,
                    "candidate_labels_sha256": planned["candidate_labels_sha256"],
                    "source_manifest_sha256": planned["source_manifest_sha256"],
                    "approved": [{"issue_id": legal["issue_id"], "label_sha256": legal["label_sha256"]}]}
        def bad(label: dict) -> dict:
            return {"issue_id": "wrong", "runtime_input": runtime(label),
                    "post_llm_gate": {"status": "accepted", "response": {"findings": []}}}
        output = self.root / "bad"
        audit = execute_approved(self.bundle_dir, output, approval, 1, bad, bad,
                                 source_manifest=self.manifest_path)
        self.assertEqual(audit["completed"], [])
        self.assertEqual(audit["failed"][0]["failure_code"], "result_not_bound_to_approved_label")
        self.assertTrue((output / "legal" / f"{legal['issue_id']}.quarantine.json").exists())
        self.assertFalse((output / "legal" / f"{legal['issue_id']}.json").exists())

    def test_unknown_gate_state_is_not_counted_as_an_assessment(self) -> None:
        planned = plan(self.bundle_dir, self.manifest_path)
        legal = next(x for x in planned["items"] if x["machine_route"] == "strict_legal_cascade")
        approval = {"project_id": planned["project_id"],
                    "privacy_review_complete": True,
                    "candidate_labels_sha256": planned["candidate_labels_sha256"],
                    "source_manifest_sha256": planned["source_manifest_sha256"],
                    "approved": [{"issue_id": legal["issue_id"], "label_sha256": legal["label_sha256"]}]}

        def invalid_gate(label: dict) -> dict:
            return {"issue_id": label["issue_id"], "runtime_input": runtime(label),
                    "post_llm_gate": {"status": "unknown", "blocked": False,
                                      "response": {"findings": [{"issue_id": label["issue_id"],
                                                                 "conclusion_type": "potential_risk"}]}}}

        output = self.root / "unknown_gate"
        audit = execute_approved(self.bundle_dir, output, approval, 1, invalid_gate, invalid_gate,
                                 source_manifest=self.manifest_path)
        self.assertEqual(audit["completed"], [])
        self.assertEqual(audit["failed"][0]["failure_code"], "invalid_gate_status_or_block_flag")
        summary = json.loads((output / "machine_preliminary_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["machine_status_counts"].get("preliminary_risk_for_human_confirmation", 0), 0)

    def test_original_manifest_and_excerpt_are_bound_before_online(self) -> None:
        planned = plan(self.bundle_dir, self.manifest_path)
        self.assertIsNotNone(planned["source_manifest_sha256"])
        item = next(x for x in planned["items"] if x["machine_route"] == "strict_legal_cascade")
        incomplete_approval = {"project_id": planned["project_id"],
                               "candidate_labels_sha256": planned["candidate_labels_sha256"],
                               "approved": [{"issue_id": item["issue_id"], "label_sha256": item["label_sha256"]}]}
        with self.assertRaisesRegex(ValueError, "approval_bundle_fingerprint_mismatch"):
            validate_approval(planned, incomplete_approval, 1)
        label_path = self.bundle_dir / "candidate_labels.jsonl"
        labels = [json.loads(line) for line in label_path.read_text(encoding="utf-8").splitlines()]
        labels[0]["document_excerpt"] = "不属于原文件的替代文本"
        label_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in labels), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "candidate_label_source_mismatch"):
            plan(self.bundle_dir, self.manifest_path)

    def test_candidate_quote_must_still_match_parsed_locator(self) -> None:
        path = self.bundle_dir / "candidates.json"
        candidates = json.loads(path.read_text(encoding="utf-8"))
        candidates[0]["primary_source"]["quote"] = "替换后的来源文本"
        path.write_text(json.dumps(candidates, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "candidate_source_not_in_locator_map"):
            plan(self.bundle_dir, self.manifest_path)

    def test_secondary_sensitive_number_screen_prevents_dispatch(self) -> None:
        self.assertIsNotNone(SENSITIVE_NUMBER.search("联系人13812345678"))
        self.assertIsNone(SENSITIVE_NUMBER.search("投标保证金按估算价的2%提供"))
        self.assertIn("email_address", privacy_risk_codes({"document_excerpt": "contact@example.com"}))
        self.assertIn("named_organization", privacy_risk_codes({"document_excerpt": "某某建设有限公司"}))
        with self.assertRaisesRegex(ValueError, "requires_original_source_manifest"):
            execute_approved(self.bundle_dir, self.root / "privacy", {}, 1,
                             lambda _: {}, lambda _: {})

    def test_even_approved_sensitive_source_is_not_sent(self) -> None:
        docx(self.root / "sensitive_tender.docx", ["投标人须提供联系人手机13812345678。"])
        docx(self.root / "sensitive_bid.docx", ["我方提供联系人手机13812345678。"])
        manifest = {"project_id": "SYN-SENSITIVE", "project_type": "construction_project",
                    "documents": [{"document_key": "T", "role": "tender", "path": "sensitive_tender.docx",
                                   "declared_issued": True},
                                  {"document_key": "B", "role": "final_bid", "path": "sensitive_bid.docx",
                                   "declared_final_submitted": True}]}
        manifest_path = self.root / "sensitive_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        bundle = self.root / "sensitive_bundle"
        run(manifest_path, bundle)
        planned = plan(bundle, manifest_path)
        item = next(x for x in planned["items"] if x["machine_route"] == "strict_legal_cascade")
        approval = {"project_id": planned["project_id"],
                    "privacy_review_complete": True,
                    "candidate_labels_sha256": planned["candidate_labels_sha256"],
                    "source_manifest_sha256": planned["source_manifest_sha256"],
                    "approved": [{"issue_id": item["issue_id"], "label_sha256": item["label_sha256"]}]}
        dispatched = []
        def must_not_call(label: dict) -> dict:
            dispatched.append(label["issue_id"])
            raise AssertionError("model call should not occur")
        audit = execute_approved(bundle, self.root / "sensitive_batch", approval, 1,
                                 must_not_call, must_not_call, source_manifest=manifest_path)
        self.assertEqual(dispatched, [])
        self.assertEqual(audit["failed"][0]["failure_code"], "sensitive_content_detected_before_transmission")
        self.assertIn("numeric_identifier", audit["failed"][0]["privacy_risk_codes"])


if __name__ == "__main__":
    unittest.main()
