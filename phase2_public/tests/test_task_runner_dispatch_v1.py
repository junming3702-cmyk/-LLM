"""Offline proof that response failures and task routing do not become U."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
from run_hierarchy_gated_llm_smoke import run_final_reasoning  # noqa: E402
from test_task_subconclusion_v1 import fixture  # noqa: E402


class RunnerDispatchTests(unittest.TestCase):
    def test_locked_observation_task_bypasses_legal_gate(self):
        contract, raw = fixture()
        runtime = {"issue_id": "SYN-U30", "task_subconclusion_contract_v1": contract}
        with patch("run_hierarchy_gated_llm_smoke.model_request", return_value={
            "ok": True, "finish_reason": "stop", "parsed": raw,
        }) as request:
            _, gate = run_final_reasoning(api_key="dummy", prompt="LEGAL PROMPT MUST NOT APPLY",
                                          runtime_input=runtime, max_tokens=1024)
        self.assertEqual("partially_observed_requires_review", gate["response"]["task_completion"])
        self.assertNotIn("LEGAL PROMPT", request.call_args.args[1])

    def test_truncated_legal_response_is_processing_hold(self):
        runtime = {"issue_id": "SYN-LEGAL", "contract_evidence": {"document_excerpt": "example"}}
        with patch("run_hierarchy_gated_llm_smoke.model_request", return_value={
            "ok": True, "finish_reason": "length", "parsed": {"findings": []},
            "selected_text": "{...",
        }):
            _, gate = run_final_reasoning(api_key="dummy", prompt="legal",
                                          runtime_input=runtime, max_tokens=1024)
        self.assertTrue(gate["blocked"])
        self.assertEqual("truncated_output", gate["failure_class"])
        self.assertFalse(gate["legal_conclusion_available"])
        self.assertIsNone(gate["response"]["review_table"][0]["conclusion"]["conclusion_type"])


if __name__ == "__main__":
    unittest.main()
