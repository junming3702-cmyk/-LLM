"""Offline guards for same-issue higher-law and implementing-rule interpretation."""

from __future__ import annotations

import unittest

from run_hierarchy_gated_llm_smoke import require_cross_level_reconciliation


def runtime(level1_state="relevant_but_inconclusive", level2_state="no_usable_violation_found"):
    return {"hierarchy_retrieval_audit": {"levels": [
        {"level": "Level 1", "level_state": level1_state,
         "phases": [{"selected_chunk_ids": ["law-article"]}]},
        {"level": "Level 2", "level_state": level2_state,
         "phases": [{"selected_chunk_ids": ["implementing-article"]}]},
    ]}}


def gate(conclusion="requires_human_legal_review", citations=None, conflict_note=""):
    return {"status": "passed", "blocked": False, "actions": [],
            "raw_response": {"original": True},
            "response": {"findings": [{
                "conclusion_type": conclusion,
                "legal_evidence": citations or [{"chunk_id": "law-article", "normative_level": "Level 1"}],
                "conflict_note": conflict_note,
            }]}}


class CrossLevelReconciliationTests(unittest.TestCase):
    def test_inconclusive_law_cannot_be_solo_basis_against_satisfying_regulation(self):
        result = require_cross_level_reconciliation(gate(), runtime())
        self.assertTrue(result["blocked"])
        self.assertEqual(result["cross_level_reconciliation"]["status"], "held_for_human_review")
        self.assertEqual(result["raw_response"], {"original": True})

    def test_no_issue_is_not_converted_into_risk(self):
        result = require_cross_level_reconciliation(
            gate(conclusion="no_supported_issue_found_within_review_scope"), runtime())
        self.assertFalse(result["blocked"])

    def test_true_level1_violation_is_not_suppressed(self):
        result = require_cross_level_reconciliation(
            gate(), runtime(level1_state="violation_or_inconsistency_detected"))
        self.assertFalse(result["blocked"])

    def test_level3_risk_is_not_treated_as_level1_only(self):
        result = require_cross_level_reconciliation(
            gate(citations=[{"chunk_id": "department-article", "normative_level": "Level 3"}]), runtime())
        self.assertFalse(result["blocked"])

    def test_level3_citation_does_not_hide_unreconciled_level1_claim(self):
        result = require_cross_level_reconciliation(
            gate(citations=[{"chunk_id": "law-article", "normative_level": "Level 1"},
                            {"chunk_id": "department-article", "normative_level": "Level 3"}]), runtime())
        self.assertTrue(result["blocked"])

    def test_both_levels_and_explanation_allow_human_review(self):
        result = require_cross_level_reconciliation(
            gate(citations=[{"chunk_id": "law-article", "normative_level": "Level 1"},
                            {"chunk_id": "implementing-article", "normative_level": "Level 2"}],
                 conflict_note="The implementing rule addresses notice, but the observed contrary clause differs."),
            runtime())
        self.assertFalse(result["blocked"])

    def test_empty_reconciliation_note_remains_blocked(self):
        result = require_cross_level_reconciliation(
            gate(citations=[{"chunk_id": "law-article", "normative_level": "Level 1"},
                            {"chunk_id": "implementing-article", "normative_level": "Level 2"}]), runtime())
        self.assertTrue(result["blocked"])


if __name__ == "__main__":
    unittest.main()
