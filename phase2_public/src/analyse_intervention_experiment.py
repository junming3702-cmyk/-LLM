"""Evaluator CLI: reference labels never cross into the execution process."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from experiment_integrity import write_new_json
from experiment_metrics import intervention_observation, pair_metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--enrollment", required=True, type=Path)
    parser.add_argument("--run-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    enrollment = [json.loads(line) for line in args.enrollment.read_text(encoding="utf-8").splitlines() if line.strip()]
    manifest = json.loads(args.run_manifest.read_text(encoding="utf-8"))
    raw, gated = [], []
    for row in manifest["results"]:
        path = Path(row["path"])
        # Missing results are retained in pair_metrics' enrollment denominator.
        if not path.exists():
            continue
        result = json.loads(path.read_text(encoding="utf-8"))
        identifier = result["identity"]["observation_id"]
        if row["observation_id"] != identifier:
            raise ValueError("manifest/result identity mismatch")
        raw.append(intervention_observation(identifier, result, before_gate=True))
        gated.append(intervention_observation(identifier, result))
    report = {"scope": "fixed-evidence mechanism experiment; not independent project validation",
              "raw": pair_metrics(enrollment, raw), "gated": pair_metrics(enrollment, gated),
              "labels_used_only_by_evaluator": True,
              "statistical_significance": "not_tested", "expert_results": "not_loaded"}
    write_new_json(args.output, report)
    print(json.dumps({"output": str(args.output), "pairs": report["gated"]["pairs"]}, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
