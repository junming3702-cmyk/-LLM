from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from generate_dataset import build_cases  # noqa: E402
from experiment import (  # noqa: E402
    metric_block,
    metrics_document,
    run_pipeline,
    validate_cases,
)


class PilotExperimentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cases = build_cases()
        validate_cases(self.cases)
        self.traces = run_pipeline(self.cases)
        self.metrics = metrics_document(self.traces)

    def test_dataset_has_four_balanced_case_types(self) -> None:
        self.assertEqual(len(self.cases), 24)
        counts = {}
        for case in self.cases:
            counts[case["case_type"]] = counts.get(case["case_type"], 0) + 1
            self.assertIn("source_version", case["candidates"][0])
            self.assertIn("locator", case["candidates"][0])
            self.assertIn("gold", case)
            self.assertIn("support_evidence", case)
            self.assertIn("conflict_evidence", case)
        self.assertEqual(set(counts.values()), {6})

    def test_m1_is_unconstrained_and_m2_gates(self) -> None:
        m1 = self.metrics["overall"]["M1"]
        m2 = self.metrics["overall"]["M2"]
        self.assertEqual(m1["accepted_count"], 24)
        self.assertNotIn("mapping_accuracy", m1)
        self.assertEqual(m1["decision_accuracy"], 0.25)
        self.assertEqual(m1["gold_accept_recall"], 1.0)
        self.assertEqual(m1["unsupported_attribution"], 0.75)
        self.assertEqual(m1["appropriate_abstention"], 0.0)
        self.assertEqual(m2["accepted_count"], 6)
        self.assertEqual(m2["abstained_count"], 18)
        self.assertEqual(m2["decision_accuracy"], 1.0)
        self.assertEqual(m2["gold_accept_recall"], 1.0)
        self.assertEqual(m2["accepted_accuracy"], 1.0)
        self.assertEqual(m2["coverage"], 0.25)
        self.assertEqual(m2["unsupported_attribution"], 0.0)
        self.assertEqual(m2["provenance_resolvability"], 1.0)
        self.assertEqual(m2["appropriate_abstention"], 1.0)

    def test_gate_reasons_match_failure_modes(self) -> None:
        by_type = {trace["case_type"]: trace for trace in self.traces}
        explicit = by_type["explicit_mapping"]["methods"]["M2"]
        ambiguous = by_type["ambiguous_alternatives"]["methods"]["M2"]
        conflict = by_type["cross_document_version_conflict"]["methods"]["M2"]
        insufficient = by_type["insufficient_evidence"]["methods"]["M2"]
        self.assertEqual(explicit["status"], "accept")
        self.assertEqual(ambiguous["status"], "abstain")
        self.assertIn("ambiguous_score_margin", ambiguous["gate_reasons"])
        self.assertEqual(conflict["status"], "abstain")
        self.assertIn("conflict_evidence_present", conflict["gate_reasons"])
        self.assertEqual(insufficient["status"], "abstain")
        self.assertIn("missing_support_evidence", insufficient["gate_reasons"])
        self.assertIn("unresolvable_provenance", insufficient["gate_reasons"])

    def test_traces_are_auditable_and_json_serialisable(self) -> None:
        self.assertEqual(len(self.traces), 24)
        for trace in self.traces:
            self.assertIn("design_revision", trace)
            self.assertIn("candidate_boq", trace)
            self.assertIn("support_evidence", trace)
            self.assertIn("conflict_evidence", trace)
            self.assertIn("gold", trace)
            self.assertEqual(set(trace["methods"]), {"M1", "M2"})
        json.dumps(self.traces, ensure_ascii=False, sort_keys=True)

    def test_repeated_pipeline_is_byte_stable_after_canonical_serialisation(self) -> None:
        first = json.dumps(run_pipeline(self.cases), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        second = json.dumps(run_pipeline(self.cases), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertEqual(first, second)

    def test_stratified_counts_are_six(self) -> None:
        for case_type, method_metrics in self.metrics["by_case_type"].items():
            for method in ("M1", "M2"):
                self.assertEqual(method_metrics[method]["case_count"], 6, case_type)

    def test_entrypoint_creates_required_directories_from_clean_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="clean-root-", dir=str(ROOT)) as temporary:
            clean_root = Path(temporary)
            input_path = clean_root / "inputs" / "cases.jsonl"
            input_path.parent.mkdir(parents=True)
            input_path.write_bytes((ROOT / "inputs" / "cases.jsonl").read_bytes())
            completed = subprocess.run(
                [sys.executable, str(ROOT / "src" / "experiment.py"), "--root", str(clean_root)],
                cwd=clean_root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            for directory in ("outputs", "reports", "logs", "tmp"):
                self.assertTrue((clean_root / directory).is_dir(), directory)
            self.assertTrue((clean_root / "manifest.json").is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
