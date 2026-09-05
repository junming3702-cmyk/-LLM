"""Pure trigger tests for the one-shot external recheck policy."""

from __future__ import annotations

import unittest

from run_hierarchy_gated_llm_smoke import (
    eligible_for_one_shot_external_recheck,
    gated_conclusion_types,
)


class OneShotExternalRecheckPolicyTests(unittest.TestCase):
    def test_valid_preliminary_insufficient_result_is_eligible(self):
        gate = {
            "status": "corrected",
            "blocked": False,
            "response": {
                "findings": [
                    {
                        "conclusion_type": (
                            "insufficient_information_needs_human_confirm"
                        )
                    }
                ]
            },
        }
        self.assertTrue(eligible_for_one_shot_external_recheck(gate))

    def test_supported_risk_does_not_trigger_external_recheck(self):
        gate = {
            "status": "passed",
            "blocked": False,
            "response": {
                "findings": [
                    {"conclusion_type": "requires_human_legal_review"}
                ]
            },
        }
        self.assertFalse(eligible_for_one_shot_external_recheck(gate))

    def test_blocked_schema_result_does_not_trigger_legal_recheck(self):
        gate = {
            "status": "blocked",
            "blocked": True,
            "response": {
                "findings": [
                    {
                        "conclusion_type": (
                            "insufficient_information_needs_human_confirm"
                        )
                    }
                ]
            },
        }
        self.assertFalse(eligible_for_one_shot_external_recheck(gate))

    def test_conclusion_reader_ignores_non_object_findings(self):
        gate = {
            "response": {
                "findings": [
                    None,
                    "invalid",
                    {"conclusion_type": "no_supported_issue_found_within_review_scope"},
                ]
            }
        }
        self.assertEqual(
            gated_conclusion_types(gate),
            ["no_supported_issue_found_within_review_scope"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
