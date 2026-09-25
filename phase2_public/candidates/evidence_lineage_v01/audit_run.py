"""Offline one-run lineage CLI. New output only; frozen inputs are read-only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lineage import sha256, trace_result


def jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--extracted-dir", type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--run-manifest", type=Path, help="Frozen manifest with binding.corpus_sha256")
    parser.add_argument("--target-id", action="append", default=[])
    parser.add_argument("--diagnostic-targets-from-frozen-reference", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = json.loads(args.result.read_text(encoding="utf-8"))
    corpus = jsonl(args.corpus)
    catalog = json.loads(args.catalog.read_text(encoding="utf-8")) if args.catalog else None
    extracted = None
    if args.extracted_dir:
        extracted = []
        for path in sorted(args.extracted_dir.glob("*.jsonl")):
            if path.name != "extraction_manifest.jsonl":
                extracted.extend(jsonl(path))
    targets = list(args.target_id)
    if args.diagnostic_targets_from_frozen_reference:
        targets.extend(result.get("offline_gold_comparison", {}).get("gold_legal_basis_chunk_ids", []))
    if not targets:
        raise ValueError("at_least_one_diagnostic_target_required")
    trace = trace_result(result, corpus, catalog, extracted, targets, source_root=args.source_root)
    trace["source_corpus_sha256"] = sha256(args.corpus)
    expected_corpus = None
    if args.run_manifest:
        manifest = json.loads(args.run_manifest.read_text(encoding="utf-8"))
        binding = manifest.get("binding", manifest)
        for _ in range(4):
            expected_corpus = binding.get("corpus_sha256")
            if expected_corpus or not isinstance(binding.get("parent_binding"), dict):
                break
            binding = binding["parent_binding"]
    trace["historical_index_binding"] = (
        "verified_same_corpus_bytes" if expected_corpus == trace["source_corpus_sha256"] else
        "identity_conflict" if expected_corpus else "unverified_no_frozen_manifest")
    trace["run_manifest_sha256"] = sha256(args.run_manifest) if args.run_manifest else None
    trace["frozen_result_sha256"] = sha256(args.result)
    trace["diagnostic_code_sha256"] = {
        name: sha256(Path(__file__).parent / name)
        for name in ("audit_run.py", "lineage.py", "task_scope.py", "preflight.py", "guarded_runtime.py")}
    trace["catalog_sha256"] = sha256(args.catalog) if args.catalog else None
    trace["extracted_files_sha256"] = (
        {p.name: sha256(p) for p in sorted(args.extracted_dir.glob("*.jsonl"))}
        if args.extracted_dir else None)
    trace["diagnostic_target_source"] = (
        "frozen_reference_posthoc_not_in_model_request"
        if args.diagnostic_targets_from_frozen_reference else "caller_supplied_posthoc")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(trace, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"output": str(args.output), "run_id": trace["run_id"],
                      "targets": trace["target_count"],
                      "breaks": [t["first_break"] for t in trace["traces"]],
                      "api_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
