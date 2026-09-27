"""Synthetic guards for offline V1 scope alignment; not real-project accuracy."""

import unittest

from scope_alignment_v1 import classify, scoped_approval


def issue(task, quote, *, document_key="TENDER", pair=None):
    return {"issue_id": "SYN-01", "task": task,
            "primary_source": {"document_key": document_key, "block_id": "B1",
                               "page_number": 1, "quote": quote}, "pairing": pair}


class ScopeAlignmentTests(unittest.TestCase):
    def test_tender_clarification_rule_is_candidate_only(self):
        row = classify(issue("tender_clause_legality",
                             "招标文件的澄清不足15日且影响投标文件编制的，延长投标截止时间。"))
        self.assertEqual(row["scope"], "legal_compliance")
        self.assertTrue(row["not_a_legal_or_responsiveness_finding"])

    def test_technical_bid_not_routed_by_should(self):
        row = classify(issue("bid_standalone_legality", "施工过程中应加强质量管理。",
                             document_key="TECH"))
        self.assertEqual(row["scope"], "auxiliary_nonlegal_not_reviewed")

    def test_insurance_terms_not_bidder_violation(self):
        row = classify(issue("bid_standalone_legality",
                             "第六条 保险金额不超过投标保证金的限制额度。", document_key="BID"))
        self.assertEqual(row["scope"], "auxiliary_nonlegal_not_reviewed")

    def test_recited_collusion_definition_not_bidder_fact(self):
        row = classify(issue("bid_standalone_legality",
                             "不同投标人的投标文件异常一致或者投标报价呈规律性差异。",
                             document_key="BID"))
        self.assertEqual(row["scope"], "auxiliary_nonlegal_not_reviewed")

    def test_current_bid_fact_is_only_a_candidate(self):
        row = classify(issue("bid_standalone_legality",
                             "我方已使用受让的资质证书参与本项目投标。", document_key="BID"))
        self.assertEqual(row["scope"], "legal_compliance")
        self.assertTrue(row["not_a_legal_or_responsiveness_finding"])

    def test_located_duration_pair_can_be_compared(self):
        pair = {"status": "provisional_match_needs_verification",
                "candidate_matches": [{"score": 0.68, "source": {"quote": "计划工期270日历天。"}}]}
        row = classify(issue("bid_responsiveness", "计划工期：270日历天。", pair=pair))
        self.assertEqual(row["scope"], "material_bid_response")

    def test_tender_template_does_not_become_requirement(self):
        pair = {"status": "provisional_match_needs_verification",
                "candidate_matches": [{"score": 0.8, "source": {"quote": "金额为：____元"}}]}
        row = classify(issue("bid_responsiveness", "人民币（大写）：____元", pair=pair))
        self.assertEqual(row["scope"], "auxiliary_nonlegal_not_reviewed")

    def test_unmatched_is_not_nonresponse(self):
        row = classify(issue("bid_responsiveness", "投标人应提交资格证明。",
                             pair={"status": "not_found_in_reviewed_text", "candidate_matches": []}))
        self.assertEqual(row["scope"], "scope_uncertain")

    def test_bid_form_copy_does_not_prove_attachment(self):
        pair = {"status": "provisional_match_needs_verification",
                "candidate_matches": [{"score": 0.8, "source": {"quote": "备注：本表后应附营业执照。"}}]}
        row = classify(issue("bid_responsiveness", "投标人应附营业执照。", pair=pair))
        self.assertEqual(row["scope"], "scope_uncertain")

    def test_scoped_approval_does_not_inherit_privacy_signoff(self):
        base = {"project_id": "P", "candidate_labels_sha256": "L",
                "source_manifest_sha256": "M", "approved": [
                    {"issue_id": "A", "label_sha256": "H"}],
                "privacy_review_complete": True}
        report = {"project_id": "P", "candidate_labels_sha256": "L",
                  "selected_runnable_ids": ["A"]}
        derived = scoped_approval(base, report)
        self.assertEqual(derived["approved"], base["approved"])
        self.assertFalse(derived["privacy_review_complete"])


if __name__ == "__main__":
    unittest.main()
